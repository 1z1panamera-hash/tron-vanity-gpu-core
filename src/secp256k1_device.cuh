#pragma once

#include <stdint.h>

#ifndef SECP_HD
#ifdef __CUDACC__
#define SECP_HD __host__ __device__ inline
#else
#define SECP_HD inline
#endif
#endif

namespace secp256k1_device {

struct UInt256 {
    uint32_t limb[8];
};

struct UInt512 {
    uint32_t limb[16];
};

struct Point {
    bool infinity;
    UInt256 x;
    UInt256 y;
};

SECP_HD void zero(UInt256& out) {
    for (int i = 0; i < 8; ++i) out.limb[i] = 0;
}

SECP_HD void zero(UInt512& out) {
    for (int i = 0; i < 16; ++i) out.limb[i] = 0;
}

SECP_HD UInt256 make_u32(uint32_t value) {
    UInt256 out;
    zero(out);
    out.limb[0] = value;
    return out;
}

SECP_HD UInt256 field_p() {
    return UInt256{{0xfffffc2fU, 0xfffffffeU, 0xffffffffU, 0xffffffffU,
                    0xffffffffU, 0xffffffffU, 0xffffffffU, 0xffffffffU}};
}

SECP_HD UInt256 order_n() {
    return UInt256{{0xd0364141U, 0xbfd25e8cU, 0xaf48a03bU, 0xbaaedce6U,
                    0xfffffffeU, 0xffffffffU, 0xffffffffU, 0xffffffffU}};
}

SECP_HD UInt256 p_minus_2() {
    return UInt256{{0xfffffc2dU, 0xfffffffeU, 0xffffffffU, 0xffffffffU,
                    0xffffffffU, 0xffffffffU, 0xffffffffU, 0xffffffffU}};
}

SECP_HD UInt256 gx() {
    return UInt256{{0x16f81798U, 0x59f2815bU, 0x2dce28d9U, 0x029bfcdbU,
                    0xce870b07U, 0x55a06295U, 0xf9dcbbacU, 0x79be667eU}};
}

SECP_HD UInt256 gy() {
    return UInt256{{0xfb10d4b8U, 0x9c47d08fU, 0xa6855419U, 0xfd17b448U,
                    0x0e1108a8U, 0x5da4fbfcU, 0x26a3c465U, 0x483ada77U}};
}

SECP_HD bool is_zero(const UInt256& value) {
    uint32_t acc = 0;
    for (int i = 0; i < 8; ++i) acc |= value.limb[i];
    return acc == 0;
}

SECP_HD int cmp(const UInt256& a, const UInt256& b) {
    for (int i = 7; i >= 0; --i) {
        if (a.limb[i] < b.limb[i]) return -1;
        if (a.limb[i] > b.limb[i]) return 1;
    }
    return 0;
}

SECP_HD bool bit(const UInt256& value, int index) {
    if (index < 0 || index >= 256) return false;
    return ((value.limb[index / 32] >> (index % 32)) & 1U) != 0;
}

SECP_HD int bit_length(const UInt256& value) {
    for (int i = 7; i >= 0; --i) {
        if (value.limb[i] == 0) continue;
        for (int b = 31; b >= 0; --b) {
            if ((value.limb[i] >> b) & 1U) return i * 32 + b + 1;
        }
    }
    return 0;
}

SECP_HD void sub_raw(UInt256& out, const UInt256& a, const UInt256& b, uint32_t* final_borrow) {
    uint64_t borrow = 0;
    for (int i = 0; i < 8; ++i) {
        uint64_t av = a.limb[i];
        uint64_t bv = static_cast<uint64_t>(b.limb[i]) + borrow;
        if (av >= bv) {
            out.limb[i] = static_cast<uint32_t>(av - bv);
            borrow = 0;
        } else {
            out.limb[i] = static_cast<uint32_t>((1ULL << 32) + av - bv);
            borrow = 1;
        }
    }
    if (final_borrow) *final_borrow = static_cast<uint32_t>(borrow);
}

SECP_HD uint32_t add_raw(UInt256& out, const UInt256& a, const UInt256& b) {
    uint64_t carry = 0;
    for (int i = 0; i < 8; ++i) {
        uint64_t sum = static_cast<uint64_t>(a.limb[i]) + b.limb[i] + carry;
        out.limb[i] = static_cast<uint32_t>(sum & 0xffffffffULL);
        carry = sum >> 32;
    }
    return static_cast<uint32_t>(carry);
}

SECP_HD void reduce_once_with_carry(UInt256& value, uint32_t carry, const UInt256& modulus) {
    if (carry || cmp(value, modulus) >= 0) {
        UInt256 reduced;
        uint32_t borrow = 0;
        sub_raw(reduced, value, modulus, &borrow);
        value = reduced;
    }
}

SECP_HD void add_mod(UInt256& out, const UInt256& a, const UInt256& b, const UInt256& modulus) {
    uint32_t carry = add_raw(out, a, b);
    reduce_once_with_carry(out, carry, modulus);
}

SECP_HD void sub_mod(UInt256& out, const UInt256& a, const UInt256& b, const UInt256& modulus) {
    uint32_t borrow = 0;
    sub_raw(out, a, b, &borrow);
    if (borrow) {
        UInt256 tmp;
        add_raw(tmp, out, modulus);
        out = tmp;
    }
}

SECP_HD void mul_512(UInt512& out, const UInt256& a, const UInt256& b) {
    zero(out);
    for (int i = 0; i < 8; ++i) {
        uint64_t carry = 0;
        for (int j = 0; j < 8; ++j) {
            uint64_t current = out.limb[i + j];
            uint64_t product = static_cast<uint64_t>(a.limb[i]) * b.limb[j] + current + carry;
            out.limb[i + j] = static_cast<uint32_t>(product & 0xffffffffULL);
            carry = product >> 32;
        }
        int k = i + 8;
        while (carry && k < 16) {
            uint64_t sum = static_cast<uint64_t>(out.limb[k]) + carry;
            out.limb[k] = static_cast<uint32_t>(sum & 0xffffffffULL);
            carry = sum >> 32;
            ++k;
        }
    }
}

SECP_HD bool bit512(const UInt512& value, int index) {
    if (index < 0 || index >= 512) return false;
    return ((value.limb[index / 32] >> (index % 32)) & 1U) != 0;
}

SECP_HD void shift_add_reduce(UInt256& rem, bool add_bit, const UInt256& modulus) {
    uint32_t carry = 0;
    for (int i = 0; i < 8; ++i) {
        uint32_t next_carry = rem.limb[i] >> 31;
        rem.limb[i] = (rem.limb[i] << 1) | carry;
        carry = next_carry;
    }
    if (add_bit) {
        uint64_t sum = static_cast<uint64_t>(rem.limb[0]) + 1ULL;
        rem.limb[0] = static_cast<uint32_t>(sum & 0xffffffffULL);
        uint64_t c = sum >> 32;
        for (int i = 1; i < 8 && c; ++i) {
            uint64_t s = static_cast<uint64_t>(rem.limb[i]) + c;
            rem.limb[i] = static_cast<uint32_t>(s & 0xffffffffULL);
            c = s >> 32;
        }
        if (c) carry = 1;
    }
    reduce_once_with_carry(rem, carry, modulus);
}

SECP_HD void mod_reduce_512(UInt256& out, const UInt512& value, const UInt256& modulus) {
    zero(out);
    for (int i = 511; i >= 0; --i) {
        shift_add_reduce(out, bit512(value, i), modulus);
    }
}

SECP_HD void mul_mod(UInt256& out, const UInt256& a, const UInt256& b, const UInt256& modulus) {
    UInt512 product;
    mul_512(product, a, b);
    mod_reduce_512(out, product, modulus);
}

SECP_HD void pow_mod(UInt256& out, UInt256 base, const UInt256& exponent, const UInt256& modulus) {
    UInt256 result = make_u32(1);
    UInt256 base_mod = base;
    reduce_once_with_carry(base_mod, 0, modulus);
    for (int i = 0; i < 256; ++i) {
        if (bit(exponent, i)) {
            UInt256 tmp;
            mul_mod(tmp, result, base_mod, modulus);
            result = tmp;
        }
        UInt256 squared;
        mul_mod(squared, base_mod, base_mod, modulus);
        base_mod = squared;
    }
    out = result;
}

SECP_HD void inv_mod_p(UInt256& out, const UInt256& value) {
    pow_mod(out, value, p_minus_2(), field_p());
}

SECP_HD Point generator() {
    Point out;
    out.infinity = false;
    out.x = gx();
    out.y = gy();
    return out;
}

SECP_HD bool point_add(Point& out, const Point& a, const Point& b) {
    const UInt256 p = field_p();
    if (a.infinity) {
        out = b;
        return true;
    }
    if (b.infinity) {
        out = a;
        return true;
    }

    if (cmp(a.x, b.x) == 0) {
        UInt256 ysum;
        add_mod(ysum, a.y, b.y, p);
        if (is_zero(ysum)) {
            out.infinity = true;
            zero(out.x);
            zero(out.y);
            return true;
        }
    }

    UInt256 lambda;
    if (cmp(a.x, b.x) == 0 && cmp(a.y, b.y) == 0) {
        UInt256 x2;
        UInt256 numerator;
        UInt256 denominator;
        UInt256 inv_denominator;
        mul_mod(x2, a.x, a.x, p);
        mul_mod(numerator, make_u32(3), x2, p);
        mul_mod(denominator, make_u32(2), a.y, p);
        if (is_zero(denominator)) return false;
        inv_mod_p(inv_denominator, denominator);
        mul_mod(lambda, numerator, inv_denominator, p);
    } else {
        UInt256 numerator;
        UInt256 denominator;
        UInt256 inv_denominator;
        sub_mod(numerator, b.y, a.y, p);
        sub_mod(denominator, b.x, a.x, p);
        if (is_zero(denominator)) return false;
        inv_mod_p(inv_denominator, denominator);
        mul_mod(lambda, numerator, inv_denominator, p);
    }

    UInt256 lambda2;
    UInt256 xr_tmp;
    UInt256 xr;
    UInt256 ax_minus_xr;
    UInt256 yr_tmp;
    UInt256 yr;
    mul_mod(lambda2, lambda, lambda, p);
    sub_mod(xr_tmp, lambda2, a.x, p);
    sub_mod(xr, xr_tmp, b.x, p);
    sub_mod(ax_minus_xr, a.x, xr, p);
    mul_mod(yr_tmp, lambda, ax_minus_xr, p);
    sub_mod(yr, yr_tmp, a.y, p);

    out.infinity = false;
    out.x = xr;
    out.y = yr;
    return true;
}

SECP_HD bool scalar_multiply(Point& out, const UInt256& scalar) {
    if (is_zero(scalar) || cmp(scalar, order_n()) >= 0) return false;
    Point result;
    result.infinity = true;
    zero(result.x);
    zero(result.y);
    Point addend = generator();
    for (int i = 0; i < 256; ++i) {
        if (bit(scalar, i)) {
            Point next;
            if (!point_add(next, result, addend)) return false;
            result = next;
        }
        Point doubled;
        if (!point_add(doubled, addend, addend)) return false;
        addend = doubled;
    }
    out = result;
    return !out.infinity;
}

SECP_HD void uint256_to_be32(const UInt256& value, uint8_t out32[32]) {
    for (int byte_index = 0; byte_index < 32; ++byte_index) {
        int limb_index = byte_index / 4;
        int shift = (byte_index % 4) * 8;
        out32[31 - byte_index] = static_cast<uint8_t>((value.limb[limb_index] >> shift) & 0xff);
    }
}

SECP_HD bool private_key_to_public_key64(const UInt256& scalar, uint8_t public_key64[64]) {
    Point public_point;
    if (!scalar_multiply(public_point, scalar)) return false;
    uint256_to_be32(public_point.x, public_key64);
    uint256_to_be32(public_point.y, public_key64 + 32);
    return true;
}

}  // namespace secp256k1_device
