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

    std::vector<secp256k1_device::UInt256> denominators(kCount);
    std::vector<secp256k1_device::UInt256> inverses(kCount);
    std::vector<secp256k1_device::UInt256> scratch(kCount);
    std::vector<int> normal_indices(kCount);
    if (failures.empty() &&
        !secp256k1_device::point_add_same_stride_batch(
            batch_outputs,
            denominators.data(),
            inverses.data(),
            scratch.data(),
            normal_indices.data(),
            inputs,
            stride_point,
            kCount)) {
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
