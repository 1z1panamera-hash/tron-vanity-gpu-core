#pragma once

#include <array>
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

namespace tron_core {

static constexpr char BASE58_ALPHABET[] =
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

inline int base58_index(char c) {
    for (int i = 0; i < 58; ++i) {
        if (BASE58_ALPHABET[i] == c) {
            return i;
        }
    }
    return -1;
}

inline uint8_t hex_value(char c) {
    if (c >= '0' && c <= '9') return static_cast<uint8_t>(c - '0');
    if (c >= 'a' && c <= 'f') return static_cast<uint8_t>(c - 'a' + 10);
    if (c >= 'A' && c <= 'F') return static_cast<uint8_t>(c - 'A' + 10);
    throw std::runtime_error("invalid hex character");
}

inline std::vector<uint8_t> hex_to_bytes(const std::string& hex) {
    if (hex.size() % 2 != 0) {
        throw std::runtime_error("hex string length must be even");
    }
    std::vector<uint8_t> out(hex.size() / 2);
    for (size_t i = 0; i < out.size(); ++i) {
        out[i] = static_cast<uint8_t>((hex_value(hex[i * 2]) << 4) | hex_value(hex[i * 2 + 1]));
    }
    return out;
}

inline std::string bytes_to_hex(const uint8_t* data, size_t len) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string out;
    out.resize(len * 2);
    for (size_t i = 0; i < len; ++i) {
        out[i * 2] = digits[data[i] >> 4];
        out[i * 2 + 1] = digits[data[i] & 0x0f];
    }
    return out;
}

inline uint64_t rotl64(uint64_t value, int shift) {
    shift &= 63;
    return (value << shift) | (value >> ((64 - shift) & 63));
}

inline uint32_t rotr32(uint32_t value, int shift) {
    return (value >> shift) | (value << (32 - shift));
}

inline void keccak_f1600(std::array<uint64_t, 25>& state) {
    static constexpr int rho[5][5] = {
        {0, 36, 3, 41, 18},
        {1, 44, 10, 45, 2},
        {62, 6, 43, 15, 61},
        {28, 55, 25, 21, 56},
        {27, 20, 39, 8, 14},
    };
    static constexpr uint64_t rc[24] = {
        0x0000000000000001ULL, 0x0000000000008082ULL,
        0x800000000000808aULL, 0x8000000080008000ULL,
        0x000000000000808bULL, 0x0000000080000001ULL,
        0x8000000080008081ULL, 0x8000000000008009ULL,
        0x000000000000008aULL, 0x0000000000000088ULL,
        0x0000000080008009ULL, 0x000000008000000aULL,
        0x000000008000808bULL, 0x800000000000008bULL,
        0x8000000000008089ULL, 0x8000000000008003ULL,
        0x8000000000008002ULL, 0x8000000000000080ULL,
        0x000000000000800aULL, 0x800000008000000aULL,
        0x8000000080008081ULL, 0x8000000000008080ULL,
        0x0000000080000001ULL, 0x8000000080008008ULL,
    };

    for (int round = 0; round < 24; ++round) {
        uint64_t c[5];
        uint64_t d[5];
        for (int x = 0; x < 5; ++x) {
            c[x] = state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20];
        }
        for (int x = 0; x < 5; ++x) {
            d[x] = c[(x + 4) % 5] ^ rotl64(c[(x + 1) % 5], 1);
        }
        for (int x = 0; x < 5; ++x) {
            for (int y = 0; y < 5; ++y) {
                state[x + 5 * y] ^= d[x];
            }
        }

        std::array<uint64_t, 25> b{};
        for (int x = 0; x < 5; ++x) {
            for (int y = 0; y < 5; ++y) {
                b[y + 5 * ((2 * x + 3 * y) % 5)] = rotl64(state[x + 5 * y], rho[x][y]);
            }
        }

        for (int x = 0; x < 5; ++x) {
            for (int y = 0; y < 5; ++y) {
                state[x + 5 * y] =
                    b[x + 5 * y] ^ ((~b[((x + 1) % 5) + 5 * y]) & b[((x + 2) % 5) + 5 * y]);
            }
        }
        state[0] ^= rc[round];
    }
}

inline std::array<uint8_t, 32> keccak256(const uint8_t* data, size_t len) {
    constexpr size_t rate = 136;
    std::array<uint64_t, 25> state{};
    std::vector<uint8_t> padded(data, data + len);
    padded.push_back(0x01);
    while ((padded.size() % rate) != rate - 1) {
        padded.push_back(0x00);
    }
    padded.push_back(0x80);

    for (size_t offset = 0; offset < padded.size(); offset += rate) {
        for (size_t lane = 0; lane < rate / 8; ++lane) {
            uint64_t value = 0;
            for (size_t b = 0; b < 8; ++b) {
                value |= static_cast<uint64_t>(padded[offset + lane * 8 + b]) << (8 * b);
            }
            state[lane] ^= value;
        }
        keccak_f1600(state);
    }

    std::array<uint8_t, 32> out{};
    size_t pos = 0;
    for (size_t lane = 0; lane < rate / 8 && pos < out.size(); ++lane) {
        for (size_t b = 0; b < 8 && pos < out.size(); ++b) {
            out[pos++] = static_cast<uint8_t>((state[lane] >> (8 * b)) & 0xff);
        }
    }
    return out;
}

inline std::array<uint8_t, 32> sha256(const uint8_t* data, size_t len) {
    static constexpr uint32_t k[64] = {
        0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U,
        0x3956c25bU, 0x59f111f1U, 0x923f82a4U, 0xab1c5ed5U,
        0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
        0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U,
        0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU,
        0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
        0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U,
        0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U,
        0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
        0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U,
        0xa2bfe8a1U, 0xa81a664bU, 0xc24b8b70U, 0xc76c51a3U,
        0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
        0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U,
        0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
        0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
        0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U,
    };

    uint32_t h[8] = {
        0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
        0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U,
    };

    std::vector<uint8_t> msg(data, data + len);
    uint64_t bit_len = static_cast<uint64_t>(len) * 8U;
    msg.push_back(0x80);
    while ((msg.size() % 64) != 56) {
        msg.push_back(0x00);
    }
    for (int i = 7; i >= 0; --i) {
        msg.push_back(static_cast<uint8_t>((bit_len >> (i * 8)) & 0xff));
    }

    for (size_t offset = 0; offset < msg.size(); offset += 64) {
        uint32_t w[64];
        for (int i = 0; i < 16; ++i) {
            w[i] = (static_cast<uint32_t>(msg[offset + i * 4]) << 24) |
                   (static_cast<uint32_t>(msg[offset + i * 4 + 1]) << 16) |
                   (static_cast<uint32_t>(msg[offset + i * 4 + 2]) << 8) |
                   static_cast<uint32_t>(msg[offset + i * 4 + 3]);
        }
        for (int i = 16; i < 64; ++i) {
            uint32_t s0 = rotr32(w[i - 15], 7) ^ rotr32(w[i - 15], 18) ^ (w[i - 15] >> 3);
            uint32_t s1 = rotr32(w[i - 2], 17) ^ rotr32(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }

        uint32_t a = h[0], b = h[1], c = h[2], d = h[3];
        uint32_t e = h[4], f = h[5], g = h[6], hh = h[7];

        for (int i = 0; i < 64; ++i) {
            uint32_t s1 = rotr32(e, 6) ^ rotr32(e, 11) ^ rotr32(e, 25);
            uint32_t ch = (e & f) ^ ((~e) & g);
            uint32_t temp1 = hh + s1 + ch + k[i] + w[i];
            uint32_t s0 = rotr32(a, 2) ^ rotr32(a, 13) ^ rotr32(a, 22);
            uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
            uint32_t temp2 = s0 + maj;
            hh = g;
            g = f;
            f = e;
            e = d + temp1;
            d = c;
            c = b;
            b = a;
            a = temp1 + temp2;
        }

        h[0] += a; h[1] += b; h[2] += c; h[3] += d;
        h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
    }

    std::array<uint8_t, 32> out{};
    for (int i = 0; i < 8; ++i) {
        out[i * 4] = static_cast<uint8_t>((h[i] >> 24) & 0xff);
        out[i * 4 + 1] = static_cast<uint8_t>((h[i] >> 16) & 0xff);
        out[i * 4 + 2] = static_cast<uint8_t>((h[i] >> 8) & 0xff);
        out[i * 4 + 3] = static_cast<uint8_t>(h[i] & 0xff);
    }
    return out;
}

inline std::array<uint8_t, 25> tron_hex_to_payload25(const std::string& tron_hex) {
    auto payload21_vec = hex_to_bytes(tron_hex);
    if (payload21_vec.size() != 21 || payload21_vec[0] != 0x41) {
        throw std::runtime_error("TRON hex address must be 21 bytes and start with 0x41");
    }
    std::array<uint8_t, 25> payload25{};
    std::memcpy(payload25.data(), payload21_vec.data(), 21);
    auto first = sha256(payload21_vec.data(), payload21_vec.size());
    auto second = sha256(first.data(), first.size());
    std::memcpy(payload25.data() + 21, second.data(), 4);
    return payload25;
}

inline std::string base58_encode(const uint8_t* data, size_t len) {
    std::vector<uint8_t> digits(data, data + len);
    size_t leading_zeroes = 0;
    while (leading_zeroes < digits.size() && digits[leading_zeroes] == 0) {
        ++leading_zeroes;
    }

    std::string out;
    size_t start = leading_zeroes;
    while (start < digits.size()) {
        int remainder = 0;
        for (size_t i = start; i < digits.size(); ++i) {
            int value = remainder * 256 + digits[i];
            digits[i] = static_cast<uint8_t>(value / 58);
            remainder = value % 58;
        }
        out.push_back(BASE58_ALPHABET[remainder]);
        while (start < digits.size() && digits[start] == 0) {
            ++start;
        }
    }

    for (size_t i = 0; i < leading_zeroes; ++i) {
        out.push_back('1');
    }
    if (out.empty()) {
        return "1";
    }
    std::reverse(out.begin(), out.end());
    return out;
}

inline std::array<uint8_t, 25> base58_decode_payload25(const std::string& value) {
    std::vector<uint8_t> out(25, 0);
    for (char c : value) {
        int digit = base58_index(c);
        if (digit < 0) {
            throw std::runtime_error("invalid Base58 character");
        }
        int carry = digit;
        for (int i = 24; i >= 0; --i) {
            int v = out[i] * 58 + carry;
            out[i] = static_cast<uint8_t>(v & 0xff);
            carry = v >> 8;
        }
        if (carry != 0) {
            throw std::runtime_error("Base58 value does not fit payload25");
        }
    }
    std::array<uint8_t, 25> payload{};
    std::memcpy(payload.data(), out.data(), 25);
    return payload;
}

inline uint64_t suffix_value_from_base58_suffix(const std::string& suffix) {
    uint64_t value = 0;
    for (char c : suffix) {
        int digit = base58_index(c);
        if (digit < 0) {
            throw std::runtime_error("invalid Base58 suffix character");
        }
        value = value * 58ULL + static_cast<uint64_t>(digit);
    }
    return value;
}

inline uint64_t payload25_mod_suffix_base(const std::array<uint8_t, 25>& payload25, int suffix_len) {
    uint64_t base = 1;
    for (int i = 0; i < suffix_len; ++i) {
        base *= 58ULL;
    }
    uint64_t value = 0;
    for (uint8_t byte : payload25) {
        value = ((value * 256ULL) + byte) % base;
    }
    return value;
}

struct Big256 {
    std::array<uint32_t, 8> limb{};

    static Big256 from_u64(uint64_t value) {
        Big256 out;
        out.limb[0] = static_cast<uint32_t>(value & 0xffffffffULL);
        out.limb[1] = static_cast<uint32_t>(value >> 32);
        return out;
    }

    static Big256 from_payload25(const std::array<uint8_t, 25>& payload25) {
        Big256 out;
        for (uint8_t byte : payload25) {
            out.mul_small(256);
            out.add_small(byte);
        }
        return out;
    }

    void add_small(uint32_t value) {
        uint64_t carry = value;
        for (size_t i = 0; i < limb.size() && carry; ++i) {
            uint64_t sum = static_cast<uint64_t>(limb[i]) + carry;
            limb[i] = static_cast<uint32_t>(sum & 0xffffffffULL);
            carry = sum >> 32;
        }
        if (carry) {
            throw std::runtime_error("Big256 overflow");
        }
    }

    void mul_small(uint32_t value) {
        uint64_t carry = 0;
        for (size_t i = 0; i < limb.size(); ++i) {
            uint64_t product = static_cast<uint64_t>(limb[i]) * value + carry;
            limb[i] = static_cast<uint32_t>(product & 0xffffffffULL);
            carry = product >> 32;
        }
        if (carry) {
            throw std::runtime_error("Big256 overflow");
        }
    }

    int cmp(const Big256& other) const {
        for (int i = 7; i >= 0; --i) {
            if (limb[i] < other.limb[i]) return -1;
            if (limb[i] > other.limb[i]) return 1;
        }
        return 0;
    }
};

inline Big256 base58_to_big256(const std::string& value) {
    Big256 out;
    for (char c : value) {
        int digit = base58_index(c);
        if (digit < 0) {
            throw std::runtime_error("invalid Base58 character");
        }
        out.mul_small(58);
        out.add_small(static_cast<uint32_t>(digit));
    }
    return out;
}

inline Big256 pow58_big256(int exponent) {
    Big256 out = Big256::from_u64(1);
    for (int i = 0; i < exponent; ++i) {
        out.mul_small(58);
    }
    return out;
}

inline bool base58_prefix_range_filter(
    const std::array<uint8_t, 25>& payload25,
    const std::string& prefix,
    int total_len) {
    if (prefix.empty()) {
        return true;
    }
    if (static_cast<int>(prefix.size()) > total_len) {
        return false;
    }
    Big256 lower_scaled = base58_to_big256(prefix);
    Big256 upper_scaled = base58_to_big256(prefix);
    upper_scaled.add_small(1);
    for (int i = 0; i < total_len - static_cast<int>(prefix.size()); ++i) {
        lower_scaled.mul_small(58);
        upper_scaled.mul_small(58);
    }

    Big256 value = Big256::from_payload25(payload25);
    return value.cmp(lower_scaled) >= 0 && value.cmp(upper_scaled) < 0;
}

inline bool address_matches_full(
    const std::string& address,
    const std::string& target_address,
    int prefix_len,
    int suffix_len) {
    if (prefix_len < 0 || suffix_len < 0) {
        throw std::runtime_error("prefix_len and suffix_len must be non-negative");
    }
    if (static_cast<int>(target_address.size()) < prefix_len + suffix_len) {
        return false;
    }
    if (address.substr(0, prefix_len) != target_address.substr(0, prefix_len)) {
        return false;
    }
    if (suffix_len == 0) {
        return true;
    }
    return address.substr(address.size() - suffix_len) ==
           target_address.substr(target_address.size() - suffix_len);
}

inline bool address_matches_filter(
    const std::array<uint8_t, 25>& payload25,
    const std::string& target_address,
    int prefix_len,
    int suffix_len) {
    const std::string prefix = target_address.substr(0, prefix_len);
    const std::string suffix = suffix_len ? target_address.substr(target_address.size() - suffix_len) : "";

    if (!base58_prefix_range_filter(payload25, prefix, static_cast<int>(target_address.size()))) {
        return false;
    }
    if (suffix_len) {
        uint64_t expected = suffix_value_from_base58_suffix(suffix);
        if (payload25_mod_suffix_base(payload25, suffix_len) != expected) {
            return false;
        }
    }
    std::string confirmed = base58_encode(payload25.data(), payload25.size());
    return address_matches_full(confirmed, target_address, prefix_len, suffix_len);
}

}  // namespace tron_core
