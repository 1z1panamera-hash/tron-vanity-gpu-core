#pragma once

#include <stdint.h>
#include <string.h>

#ifndef __CUDACC__
#define TRON_HD inline
#else
#define TRON_HD __host__ __device__ inline
#endif

namespace tron_device {

static constexpr int PAYLOAD25_LEN = 25;
static constexpr int BASE58_MAX_LEN = 64;

TRON_HD char base58_char(int digit) {
    if (digit >= 0 && digit <= 8) return static_cast<char>('1' + digit);
    if (digit >= 9 && digit <= 16) return static_cast<char>('A' + (digit - 9));
    if (digit >= 17 && digit <= 21) return static_cast<char>('J' + (digit - 17));
    if (digit >= 22 && digit <= 32) return static_cast<char>('P' + (digit - 22));
    if (digit >= 33 && digit <= 43) return static_cast<char>('a' + (digit - 33));
    if (digit >= 44 && digit <= 57) return static_cast<char>('m' + (digit - 44));
    return '\0';
}

TRON_HD int base58_index(char c) {
    if (c >= '1' && c <= '9') return c - '1';
    if (c >= 'A' && c <= 'H') return 9 + c - 'A';
    if (c >= 'J' && c <= 'N') return 17 + c - 'J';
    if (c >= 'P' && c <= 'Z') return 22 + c - 'P';
    if (c >= 'a' && c <= 'k') return 33 + c - 'a';
    if (c >= 'm' && c <= 'z') return 44 + c - 'm';
    return -1;
}

TRON_HD uint64_t rotl64(uint64_t value, int shift) {
    shift &= 63;
    return (value << shift) | (value >> ((64 - shift) & 63));
}

TRON_HD uint32_t rotr32(uint32_t value, int shift) {
    return (value >> shift) | (value << (32 - shift));
}

TRON_HD void keccak_f1600(uint64_t state[25]) {
    const int rho[5][5] = {
        {0, 36, 3, 41, 18},
        {1, 44, 10, 45, 2},
        {62, 6, 43, 15, 61},
        {28, 55, 25, 21, 56},
        {27, 20, 39, 8, 14},
    };
    const uint64_t rc[24] = {
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

        uint64_t b[25];
        for (int i = 0; i < 25; ++i) {
            b[i] = 0;
        }
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

TRON_HD bool keccak256_single_block(const uint8_t* data, int len, uint8_t out32[32]) {
    if (len < 0 || len > 135) {
        return false;
    }
    uint64_t state[25];
    uint8_t block[136];
    for (int i = 0; i < 25; ++i) state[i] = 0;
    for (int i = 0; i < 136; ++i) block[i] = 0;
    for (int i = 0; i < len; ++i) block[i] = data[i];
    block[len] = 0x01;
    block[135] |= 0x80;

    for (int lane = 0; lane < 17; ++lane) {
        uint64_t value = 0;
        for (int b = 0; b < 8; ++b) {
            value |= static_cast<uint64_t>(block[lane * 8 + b]) << (8 * b);
        }
        state[lane] ^= value;
    }
    keccak_f1600(state);

    int pos = 0;
    for (int lane = 0; lane < 17 && pos < 32; ++lane) {
        for (int b = 0; b < 8 && pos < 32; ++b) {
            out32[pos++] = static_cast<uint8_t>((state[lane] >> (8 * b)) & 0xff);
        }
    }
    return true;
}

TRON_HD bool sha256_single_block(const uint8_t* data, int len, uint8_t out32[32]) {
    if (len < 0 || len > 55) {
        return false;
    }
    const uint32_t k[64] = {
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

    uint8_t block[64];
    for (int i = 0; i < 64; ++i) block[i] = 0;
    for (int i = 0; i < len; ++i) block[i] = data[i];
    block[len] = 0x80;
    uint64_t bit_len = static_cast<uint64_t>(len) * 8ULL;
    for (int i = 0; i < 8; ++i) {
        block[63 - i] = static_cast<uint8_t>((bit_len >> (8 * i)) & 0xff);
    }

    uint32_t h[8] = {
        0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
        0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U,
    };
    uint32_t w[64];
    for (int i = 0; i < 16; ++i) {
        w[i] = (static_cast<uint32_t>(block[i * 4]) << 24) |
               (static_cast<uint32_t>(block[i * 4 + 1]) << 16) |
               (static_cast<uint32_t>(block[i * 4 + 2]) << 8) |
               static_cast<uint32_t>(block[i * 4 + 3]);
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

    for (int i = 0; i < 8; ++i) {
        out32[i * 4] = static_cast<uint8_t>((h[i] >> 24) & 0xff);
        out32[i * 4 + 1] = static_cast<uint8_t>((h[i] >> 16) & 0xff);
        out32[i * 4 + 2] = static_cast<uint8_t>((h[i] >> 8) & 0xff);
        out32[i * 4 + 3] = static_cast<uint8_t>(h[i] & 0xff);
    }
    return true;
}

TRON_HD bool payload25_from_public_key64(const uint8_t public_key64[64], uint8_t payload25[25], uint8_t keccak_out32[32]) {
    if (!keccak256_single_block(public_key64, 64, keccak_out32)) {
        return false;
    }
    payload25[0] = 0x41;
    for (int i = 0; i < 20; ++i) {
        payload25[1 + i] = keccak_out32[12 + i];
    }
    uint8_t first_sha[32];
    uint8_t second_sha[32];
    if (!sha256_single_block(payload25, 21, first_sha)) {
        return false;
    }
    if (!sha256_single_block(first_sha, 32, second_sha)) {
        return false;
    }
    for (int i = 0; i < 4; ++i) {
        payload25[21 + i] = second_sha[i];
    }
    return true;
}

TRON_HD int base58_encode_payload25(const uint8_t payload25[25], char out[BASE58_MAX_LEN]) {
    uint8_t digits[25];
    for (int i = 0; i < 25; ++i) digits[i] = payload25[i];
    int leading_zeroes = 0;
    while (leading_zeroes < 25 && digits[leading_zeroes] == 0) {
        ++leading_zeroes;
    }
    char reverse[BASE58_MAX_LEN];
    int reverse_len = 0;
    int start = leading_zeroes;
    while (start < 25) {
        int remainder = 0;
        for (int i = start; i < 25; ++i) {
            int value = remainder * 256 + digits[i];
            digits[i] = static_cast<uint8_t>(value / 58);
            remainder = value % 58;
        }
        if (reverse_len >= BASE58_MAX_LEN - 1) return -1;
        reverse[reverse_len++] = base58_char(remainder);
        while (start < 25 && digits[start] == 0) {
            ++start;
        }
    }
    for (int i = 0; i < leading_zeroes; ++i) {
        if (reverse_len >= BASE58_MAX_LEN - 1) return -1;
        reverse[reverse_len++] = '1';
    }
    if (reverse_len == 0) {
        reverse[reverse_len++] = '1';
    }
    for (int i = 0; i < reverse_len; ++i) {
        out[i] = reverse[reverse_len - 1 - i];
    }
    out[reverse_len] = '\0';
    return reverse_len;
}

TRON_HD uint64_t suffix_value_from_base58_suffix(const char* suffix, int suffix_len) {
    uint64_t value = 0;
    for (int i = 0; i < suffix_len; ++i) {
        int digit = base58_index(suffix[i]);
        if (digit < 0) return UINT64_MAX;
        value = value * 58ULL + static_cast<uint64_t>(digit);
    }
    return value;
}

TRON_HD uint64_t payload25_mod_suffix_base(const uint8_t payload25[25], int suffix_len) {
    uint64_t base = 1;
    for (int i = 0; i < suffix_len; ++i) {
        base *= 58ULL;
    }
    uint64_t value = 0;
    for (int i = 0; i < 25; ++i) {
        value = ((value * 256ULL) + payload25[i]) % base;
    }
    return value;
}

struct Big256 {
    uint32_t limb[8];
};

TRON_HD void big256_zero(Big256& value) {
    for (int i = 0; i < 8; ++i) value.limb[i] = 0;
}

TRON_HD bool big256_add_small(Big256& value, uint32_t addend) {
    uint64_t carry = addend;
    for (int i = 0; i < 8 && carry; ++i) {
        uint64_t sum = static_cast<uint64_t>(value.limb[i]) + carry;
        value.limb[i] = static_cast<uint32_t>(sum & 0xffffffffULL);
        carry = sum >> 32;
    }
    return carry == 0;
}

TRON_HD bool big256_mul_small(Big256& value, uint32_t multiplier) {
    uint64_t carry = 0;
    for (int i = 0; i < 8; ++i) {
        uint64_t product = static_cast<uint64_t>(value.limb[i]) * multiplier + carry;
        value.limb[i] = static_cast<uint32_t>(product & 0xffffffffULL);
        carry = product >> 32;
    }
    return carry == 0;
}

TRON_HD int big256_cmp(const Big256& a, const Big256& b) {
    for (int i = 7; i >= 0; --i) {
        if (a.limb[i] < b.limb[i]) return -1;
        if (a.limb[i] > b.limb[i]) return 1;
    }
    return 0;
}

TRON_HD bool big256_from_base58(const char* value, int len, Big256& out) {
    big256_zero(out);
    for (int i = 0; i < len; ++i) {
        int digit = base58_index(value[i]);
        if (digit < 0) return false;
        if (!big256_mul_small(out, 58)) return false;
        if (!big256_add_small(out, static_cast<uint32_t>(digit))) return false;
    }
    return true;
}

TRON_HD bool big256_from_payload25(const uint8_t payload25[25], Big256& out) {
    big256_zero(out);
    for (int i = 0; i < 25; ++i) {
        if (!big256_mul_small(out, 256)) return false;
        if (!big256_add_small(out, payload25[i])) return false;
    }
    return true;
}

TRON_HD void big256_to_payload25(const Big256& value, uint8_t payload25[25]) {
    for (int i = 0; i < 25; ++i) {
        const int byte_from_right = 24 - i;
        const int limb_index = byte_from_right / 4;
        const int shift = (byte_from_right % 4) * 8;
        payload25[i] = static_cast<uint8_t>((value.limb[limb_index] >> shift) & 0xffU);
    }
}

TRON_HD bool base58_prefix_bounds(
    const char* prefix,
    int prefix_len,
    int total_len,
    uint8_t lower_payload25[25],
    uint8_t upper_payload25[25]) {
    if (prefix_len <= 0) {
        for (int i = 0; i < 25; ++i) {
            lower_payload25[i] = 0x00;
            upper_payload25[i] = 0xff;
        }
        return true;
    }
    if (prefix_len > total_len) return false;

    Big256 lower;
    Big256 upper;
    if (!big256_from_base58(prefix, prefix_len, lower)) return false;
    if (!big256_from_base58(prefix, prefix_len, upper)) return false;
    if (!big256_add_small(upper, 1)) return false;
    for (int i = 0; i < total_len - prefix_len; ++i) {
        if (!big256_mul_small(lower, 58)) return false;
        if (!big256_mul_small(upper, 58)) return false;
    }
    big256_to_payload25(lower, lower_payload25);
    big256_to_payload25(upper, upper_payload25);
    return true;
}

TRON_HD bool base58_prefix_range_filter(const uint8_t payload25[25], const char* prefix, int prefix_len, int total_len) {
    if (prefix_len <= 0) return true;
    if (prefix_len > total_len) return false;

    uint8_t lower_payload25[25];
    uint8_t upper_payload25[25];
    Big256 value;
    Big256 lower;
    Big256 upper;
    if (!base58_prefix_bounds(prefix, prefix_len, total_len, lower_payload25, upper_payload25)) return false;
    if (!big256_from_payload25(lower_payload25, lower)) return false;
    if (!big256_from_payload25(upper_payload25, upper)) return false;
    if (!big256_from_payload25(payload25, value)) return false;
    return big256_cmp(value, lower) >= 0 && big256_cmp(value, upper) < 0;
}

TRON_HD bool str_prefix_suffix_match(
    const char* address,
    int address_len,
    const char* target,
    int target_len,
    int prefix_len,
    int suffix_len) {
    if (address_len != target_len) return false;
    if (prefix_len < 0 || suffix_len < 0 || prefix_len + suffix_len > target_len) return false;
    for (int i = 0; i < prefix_len; ++i) {
        if (address[i] != target[i]) return false;
    }
    for (int i = 0; i < suffix_len; ++i) {
        if (address[address_len - suffix_len + i] != target[target_len - suffix_len + i]) return false;
    }
    return true;
}

TRON_HD bool address_matches_filter(
    const uint8_t payload25[25],
    const char* target_address,
    int target_len,
    int prefix_len,
    int suffix_len) {
    if (!base58_prefix_range_filter(payload25, target_address, prefix_len, target_len)) {
        return false;
    }
    if (suffix_len > 0) {
        const char* suffix = target_address + target_len - suffix_len;
        uint64_t expected = suffix_value_from_base58_suffix(suffix, suffix_len);
        if (expected == UINT64_MAX) return false;
        if (payload25_mod_suffix_base(payload25, suffix_len) != expected) {
            return false;
        }
    }
    char address[BASE58_MAX_LEN];
    int address_len = base58_encode_payload25(payload25, address);
    if (address_len <= 0) return false;
    return str_prefix_suffix_match(address, address_len, target_address, target_len, prefix_len, suffix_len);
}

}  // namespace tron_device
