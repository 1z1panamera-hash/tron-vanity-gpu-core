#include <iostream>
#include <string>
#include <vector>

#include "../src/secp256k1_device.cuh"
#include "../src/tron_core_device.cuh"

secp256k1_device::UInt256 scalar_from_u64(unsigned long long value) {
    secp256k1_device::UInt256 out;
    secp256k1_device::zero(out);
    out.limb[0] = static_cast<uint32_t>(value & 0xffffffffULL);
    out.limb[1] = static_cast<uint32_t>((value >> 32) & 0xffffffffULL);
    return out;
}

bool same_point(const secp256k1_device::Point& a, const secp256k1_device::Point& b) {
    if (a.infinity != b.infinity) return false;
    if (a.infinity) return true;
    return secp256k1_device::cmp(a.x, b.x) == 0 &&
           secp256k1_device::cmp(a.y, b.y) == 0;
}

std::string point_to_address(const secp256k1_device::Point& point) {
    if (point.infinity) {
        throw std::runtime_error("point is infinity");
    }
    uint8_t public_key64[64];
    secp256k1_device::uint256_to_be32(point.x, public_key64);
    secp256k1_device::uint256_to_be32(point.y, public_key64 + 32);

    uint8_t payload25[25];
    uint8_t keccak_out[32];
    if (!tron_device::payload25_from_public_key64(public_key64, payload25, keccak_out)) {
        throw std::runtime_error("payload25_from_public_key64 failed");
    }
    char address[tron_device::BASE58_MAX_LEN];
    int address_len = tron_device::base58_encode_payload25(payload25, address);
    if (address_len <= 0) {
        throw std::runtime_error("base58_encode_payload25 failed");
    }
    return std::string(address, address_len);
}

bool batch_add_same_stride(
    secp256k1_device::Point* outputs,
    const secp256k1_device::Point* inputs,
    const secp256k1_device::Point& stride_point,
    int count) {
    if (count < 0 || stride_point.infinity) return false;
    if (count == 0) return true;

    std::vector<secp256k1_device::UInt256> denominators(count);
    std::vector<secp256k1_device::UInt256> inverses(count);
    std::vector<secp256k1_device::UInt256> scratch(count);
    const secp256k1_device::UInt256 p = secp256k1_device::field_p();

    for (int i = 0; i < count; ++i) {
        if (inputs[i].infinity) return false;
        if (secp256k1_device::cmp(inputs[i].x, stride_point.x) == 0) return false;
        secp256k1_device::sub_mod(denominators[i], stride_point.x, inputs[i].x, p);
        if (secp256k1_device::is_zero(denominators[i])) return false;
    }
    if (!secp256k1_device::batch_inv_mod_p(inverses.data(), scratch.data(), denominators.data(), count)) {
        return false;
    }

    for (int i = 0; i < count; ++i) {
        secp256k1_device::UInt256 numerator;
        secp256k1_device::UInt256 lambda;
        secp256k1_device::UInt256 lambda2;
        secp256k1_device::UInt256 xr_tmp;
        secp256k1_device::UInt256 xr;
        secp256k1_device::UInt256 ax_minus_xr;
        secp256k1_device::UInt256 yr_tmp;
        secp256k1_device::UInt256 yr;

        secp256k1_device::sub_mod(numerator, stride_point.y, inputs[i].y, p);
        secp256k1_device::mul_mod(lambda, numerator, inverses[i], p);
        secp256k1_device::mul_mod(lambda2, lambda, lambda, p);
        secp256k1_device::sub_mod(xr_tmp, lambda2, inputs[i].x, p);
        secp256k1_device::sub_mod(xr, xr_tmp, stride_point.x, p);
        secp256k1_device::sub_mod(ax_minus_xr, inputs[i].x, xr, p);
        secp256k1_device::mul_mod(yr_tmp, lambda, ax_minus_xr, p);
        secp256k1_device::sub_mod(yr, yr_tmp, inputs[i].y, p);

        outputs[i].infinity = false;
        outputs[i].x = xr;
        outputs[i].y = yr;
    }
    return true;
}

int main() {
    static constexpr int kCount = 8;
    const unsigned long long start_scalar = 1000ULL;
    const unsigned long long stride_scalar = 17ULL;

    std::vector<std::string> failures;
    secp256k1_device::Point stride_point;
    if (!secp256k1_device::scalar_multiply(stride_point, scalar_from_u64(stride_scalar))) {
        failures.push_back("stride scalar multiply failed");
    }

    secp256k1_device::Point inputs[kCount];
    secp256k1_device::Point batch_outputs[kCount];
    secp256k1_device::Point direct_outputs[kCount];

    for (int i = 0; i < kCount; ++i) {
        const unsigned long long scalar = start_scalar + static_cast<unsigned long long>(i) * stride_scalar;
        if (!secp256k1_device::scalar_multiply(inputs[i], scalar_from_u64(scalar))) {
            failures.push_back("input scalar multiply failed at index " + std::to_string(i));
        }
    }

    if (failures.empty() && !batch_add_same_stride(batch_outputs, inputs, stride_point, kCount)) {
        failures.push_back("batch_add_same_stride failed");
    }

    for (int i = 0; i < kCount && failures.empty(); ++i) {
        if (!secp256k1_device::point_add(direct_outputs[i], inputs[i], stride_point)) {
            failures.push_back("direct point_add failed at index " + std::to_string(i));
            break;
        }
        if (!same_point(batch_outputs[i], direct_outputs[i])) {
            failures.push_back("batch point add mismatch at index " + std::to_string(i));
            break;
        }
        const std::string batch_address = point_to_address(batch_outputs[i]);
        const std::string direct_address = point_to_address(direct_outputs[i]);
        if (batch_address != direct_address) {
            failures.push_back("batch address mismatch at index " + std::to_string(i));
            break;
        }
    }

    std::cout << "{\n";
    std::cout << "  \"mode\": \"verify_batch_point_add\",\n";
    std::cout << "  \"checked_points\": " << kCount << ",\n";
    std::cout << "  \"passed\": " << (failures.empty() ? "true" : "false") << ",\n";
    std::cout << "  \"failures\": [";
    for (size_t i = 0; i < failures.size(); ++i) {
        if (i) std::cout << ", ";
        std::cout << "\"" << failures[i] << "\"";
    }
    std::cout << "],\n";
    std::cout << "  \"notes\": [\n";
    std::cout << "    \"Host-side validation only; no CUDA kernel or benchmark is run.\",\n";
    std::cout << "    \"This proves same-stride affine point adds can share one batch inversion.\",\n";
    std::cout << "    \"No random private keys are generated and no key material is printed.\"\n";
    std::cout << "  ]\n";
    std::cout << "}\n";

    return failures.empty() ? 0 : 1;
}
