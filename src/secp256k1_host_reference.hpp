#pragma once

#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace secp256k1_host {

class UInt {
public:
    std::vector<uint32_t> limb;

    UInt() = default;
    explicit UInt(uint64_t value) {
        if (value == 0) return;
        limb.push_back(static_cast<uint32_t>(value & 0xffffffffULL));
        uint32_t hi = static_cast<uint32_t>(value >> 32);
        if (hi) limb.push_back(hi);
    }

    static UInt from_hex(const std::string& hex) {
        UInt out;
        for (char c : hex) {
            uint32_t v;
            if (c >= '0' && c <= '9') v = static_cast<uint32_t>(c - '0');
            else if (c >= 'a' && c <= 'f') v = static_cast<uint32_t>(c - 'a' + 10);
            else if (c >= 'A' && c <= 'F') v = static_cast<uint32_t>(c - 'A' + 10);
            else if (c == 'x' || c == 'X') continue;
            else throw std::runtime_error("invalid hex");
            out = mul_small(out, 16);
            out.add_small(v);
        }
        out.trim();
        return out;
    }

    bool is_zero() const {
        return limb.empty();
    }

    void trim() {
        while (!limb.empty() && limb.back() == 0) {
            limb.pop_back();
        }
    }

    int bit_length() const {
        if (limb.empty()) return 0;
        uint32_t top = limb.back();
        int bits = 32;
        while (bits > 0 && ((top >> (bits - 1)) & 1U) == 0) {
            --bits;
        }
        return static_cast<int>((limb.size() - 1) * 32 + bits);
    }

    bool bit(int index) const {
        if (index < 0) return false;
        size_t limb_index = static_cast<size_t>(index / 32);
        if (limb_index >= limb.size()) return false;
        return ((limb[limb_index] >> (index % 32)) & 1U) != 0;
    }

    void add_small(uint32_t value) {
        uint64_t carry = value;
        size_t i = 0;
        while (carry) {
            if (i == limb.size()) limb.push_back(0);
            uint64_t sum = static_cast<uint64_t>(limb[i]) + carry;
            limb[i] = static_cast<uint32_t>(sum & 0xffffffffULL);
            carry = sum >> 32;
            ++i;
        }
    }

    void shl1() {
        uint64_t carry = 0;
        for (uint32_t& x : limb) {
            uint64_t v = (static_cast<uint64_t>(x) << 1) | carry;
            x = static_cast<uint32_t>(v & 0xffffffffULL);
            carry = v >> 32;
        }
        if (carry) limb.push_back(static_cast<uint32_t>(carry));
    }

    std::string to_hex_padded(size_t bytes) const {
        static constexpr char digits[] = "0123456789abcdef";
        std::string out(bytes * 2, '0');
        for (size_t byte_index = 0; byte_index < bytes; ++byte_index) {
            size_t limb_index = byte_index / 4;
            size_t shift = (byte_index % 4) * 8;
            uint8_t value = 0;
            if (limb_index < limb.size()) {
                value = static_cast<uint8_t>((limb[limb_index] >> shift) & 0xff);
            }
            size_t out_index = (bytes - 1 - byte_index) * 2;
            out[out_index] = digits[value >> 4];
            out[out_index + 1] = digits[value & 0x0f];
        }
        return out;
    }

    static int cmp(const UInt& a, const UInt& b) {
        if (a.limb.size() < b.limb.size()) return -1;
        if (a.limb.size() > b.limb.size()) return 1;
        for (size_t i = a.limb.size(); i-- > 0;) {
            if (a.limb[i] < b.limb[i]) return -1;
            if (a.limb[i] > b.limb[i]) return 1;
        }
        return 0;
    }

    static UInt add(const UInt& a, const UInt& b) {
        UInt out;
        size_t n = std::max(a.limb.size(), b.limb.size());
        out.limb.resize(n);
        uint64_t carry = 0;
        for (size_t i = 0; i < n; ++i) {
            uint64_t av = i < a.limb.size() ? a.limb[i] : 0;
            uint64_t bv = i < b.limb.size() ? b.limb[i] : 0;
            uint64_t sum = av + bv + carry;
            out.limb[i] = static_cast<uint32_t>(sum & 0xffffffffULL);
            carry = sum >> 32;
        }
        if (carry) out.limb.push_back(static_cast<uint32_t>(carry));
        return out;
    }

    static UInt sub(const UInt& a, const UInt& b) {
        if (cmp(a, b) < 0) {
            throw std::runtime_error("UInt underflow");
        }
        UInt out;
        out.limb.resize(a.limb.size());
        uint64_t borrow = 0;
        for (size_t i = 0; i < a.limb.size(); ++i) {
            uint64_t av = a.limb[i];
            uint64_t bv = i < b.limb.size() ? b.limb[i] : 0;
            uint64_t need = bv + borrow;
            if (av >= need) {
                out.limb[i] = static_cast<uint32_t>(av - need);
                borrow = 0;
            } else {
                out.limb[i] = static_cast<uint32_t>((1ULL << 32) + av - need);
                borrow = 1;
            }
        }
        out.trim();
        return out;
    }

    static UInt mul_small(const UInt& a, uint32_t m) {
        UInt out;
        if (m == 0 || a.is_zero()) return out;
        out.limb.resize(a.limb.size());
        uint64_t carry = 0;
        for (size_t i = 0; i < a.limb.size(); ++i) {
            uint64_t product = static_cast<uint64_t>(a.limb[i]) * m + carry;
            out.limb[i] = static_cast<uint32_t>(product & 0xffffffffULL);
            carry = product >> 32;
        }
        if (carry) out.limb.push_back(static_cast<uint32_t>(carry));
        return out;
    }

    static UInt mul(const UInt& a, const UInt& b) {
        UInt out;
        if (a.is_zero() || b.is_zero()) return out;
        out.limb.assign(a.limb.size() + b.limb.size(), 0);
        for (size_t i = 0; i < a.limb.size(); ++i) {
            uint64_t carry = 0;
            for (size_t j = 0; j < b.limb.size(); ++j) {
                uint64_t current = out.limb[i + j];
                uint64_t product = static_cast<uint64_t>(a.limb[i]) * b.limb[j] + current + carry;
                out.limb[i + j] = static_cast<uint32_t>(product & 0xffffffffULL);
                carry = product >> 32;
            }
            size_t k = i + b.limb.size();
            while (carry) {
                if (k == out.limb.size()) out.limb.push_back(0);
                uint64_t sum = static_cast<uint64_t>(out.limb[k]) + carry;
                out.limb[k] = static_cast<uint32_t>(sum & 0xffffffffULL);
                carry = sum >> 32;
                ++k;
            }
        }
        out.trim();
        return out;
    }
};

inline UInt mod(const UInt& a, const UInt& m) {
    if (m.is_zero()) throw std::runtime_error("mod by zero");
    UInt rem;
    for (int i = a.bit_length() - 1; i >= 0; --i) {
        rem.shl1();
        if (a.bit(i)) rem.add_small(1);
        if (UInt::cmp(rem, m) >= 0) {
            rem = UInt::sub(rem, m);
        }
    }
    return rem;
}

inline UInt mod_add(const UInt& a, const UInt& b, const UInt& m) {
    return mod(UInt::add(a, b), m);
}

inline UInt mod_sub(const UInt& a, const UInt& b, const UInt& m) {
    if (UInt::cmp(a, b) >= 0) {
        return UInt::sub(a, b);
    }
    return UInt::sub(UInt::add(a, m), b);
}

inline UInt mod_mul(const UInt& a, const UInt& b, const UInt& m) {
    return mod(UInt::mul(a, b), m);
}

inline UInt mod_pow(UInt base, UInt exponent, const UInt& m) {
    UInt result(1);
    base = mod(base, m);
    for (int i = 0; i < exponent.bit_length(); ++i) {
        if (exponent.bit(i)) {
            result = mod_mul(result, base, m);
        }
        base = mod_mul(base, base, m);
    }
    return result;
}

inline UInt P() {
    return UInt::from_hex("fffffffffffffffffffffffffffffffffffffffffffffffffffffffefffffc2f");
}

inline UInt N() {
    return UInt::from_hex("fffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141");
}

inline UInt GX() {
    return UInt::from_hex("79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798");
}

inline UInt GY() {
    return UInt::from_hex("483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8");
}

inline UInt mod_inv(const UInt& a) {
    UInt exponent = UInt::sub(P(), UInt(2));
    return mod_pow(a, exponent, P());
}

struct Point {
    bool infinity{true};
    UInt x;
    UInt y;
};

inline Point generator() {
    Point g;
    g.infinity = false;
    g.x = GX();
    g.y = GY();
    return g;
}

inline Point point_add(const Point& a, const Point& b) {
    if (a.infinity) return b;
    if (b.infinity) return a;
    const UInt p = P();

    if (UInt::cmp(a.x, b.x) == 0) {
        UInt ysum = mod_add(a.y, b.y, p);
        if (ysum.is_zero()) {
            return Point{};
        }
    }

    UInt lambda;
    if (UInt::cmp(a.x, b.x) == 0 && UInt::cmp(a.y, b.y) == 0) {
        UInt three(3);
        UInt two(2);
        UInt numerator = mod_mul(three, mod_mul(a.x, a.x, p), p);
        UInt denominator = mod_mul(two, a.y, p);
        lambda = mod_mul(numerator, mod_inv(denominator), p);
    } else {
        UInt numerator = mod_sub(b.y, a.y, p);
        UInt denominator = mod_sub(b.x, a.x, p);
        lambda = mod_mul(numerator, mod_inv(denominator), p);
    }

    UInt lambda2 = mod_mul(lambda, lambda, p);
    UInt xr = mod_sub(mod_sub(lambda2, a.x, p), b.x, p);
    UInt yr = mod_sub(mod_mul(lambda, mod_sub(a.x, xr, p), p), a.y, p);

    Point out;
    out.infinity = false;
    out.x = xr;
    out.y = yr;
    return out;
}

inline Point scalar_multiply(const UInt& scalar) {
    if (scalar.is_zero() || UInt::cmp(scalar, N()) >= 0) {
        throw std::runtime_error("invalid secp256k1 scalar");
    }
    Point result;
    Point addend = generator();
    for (int i = 0; i < scalar.bit_length(); ++i) {
        if (scalar.bit(i)) {
            result = point_add(result, addend);
        }
        addend = point_add(addend, addend);
    }
    return result;
}

inline std::string private_key_hex_to_public_key_uncompressed(const std::string& private_key_hex) {
    UInt scalar = UInt::from_hex(private_key_hex);
    Point pub = scalar_multiply(scalar);
    if (pub.infinity) {
        throw std::runtime_error("invalid public key point");
    }
    return "04" + pub.x.to_hex_padded(32) + pub.y.to_hex_padded(32);
}

}  // namespace secp256k1_host
