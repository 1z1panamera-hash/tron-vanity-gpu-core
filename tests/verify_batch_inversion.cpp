#include <iostream>
#include <string>
#include <vector>

#include "../src/secp256k1_device.cuh"

int main() {
    static constexpr int kCount = 8;
    const uint32_t sample_values[kCount] = {2U, 3U, 5U, 7U, 11U, 13U, 17U, 19U};

    secp256k1_device::UInt256 values[kCount];
    secp256k1_device::UInt256 inverses[kCount];
    secp256k1_device::UInt256 scratch[kCount];
    std::vector<std::string> failures;

    for (int i = 0; i < kCount; ++i) {
        values[i] = secp256k1_device::make_u32(sample_values[i]);
    }

    if (!secp256k1_device::batch_inv_mod_p(inverses, scratch, values, kCount)) {
        failures.push_back("batch_inv_mod_p returned false");
    }

    const secp256k1_device::UInt256 one = secp256k1_device::make_u32(1);
    const secp256k1_device::UInt256 p = secp256k1_device::field_p();
    for (int i = 0; i < kCount; ++i) {
        secp256k1_device::UInt256 individual_inverse;
        secp256k1_device::UInt256 product;
        secp256k1_device::inv_mod_p(individual_inverse, values[i]);
        if (secp256k1_device::cmp(individual_inverse, inverses[i]) != 0) {
            failures.push_back("inverse mismatch at index " + std::to_string(i));
        }
        secp256k1_device::mul_mod(product, values[i], inverses[i], p);
        if (secp256k1_device::cmp(product, one) != 0) {
            failures.push_back("value * inverse != 1 at index " + std::to_string(i));
        }
    }

    secp256k1_device::UInt256 zero_values[1];
    secp256k1_device::UInt256 zero_inverse[1];
    secp256k1_device::UInt256 zero_scratch[1];
    secp256k1_device::zero(zero_values[0]);
    if (secp256k1_device::batch_inv_mod_p(zero_inverse, zero_scratch, zero_values, 1)) {
        failures.push_back("zero input should fail");
    }

    std::cout << "{\n";
    std::cout << "  \"mode\": \"verify_batch_inversion\",\n";
    std::cout << "  \"checked_values\": " << kCount << ",\n";
    std::cout << "  \"passed\": " << (failures.empty() ? "true" : "false") << ",\n";
    std::cout << "  \"failures\": [";
    for (size_t i = 0; i < failures.size(); ++i) {
        if (i) std::cout << ", ";
        std::cout << "\"" << failures[i] << "\"";
    }
    std::cout << "],\n";
    std::cout << "  \"notes\": [\n";
    std::cout << "    \"Host-side validation only; no CUDA kernel or benchmark is run.\",\n";
    std::cout << "    \"Batch inversion is a prerequisite for reducing per-candidate affine point-add inversions.\",\n";
    std::cout << "    \"No key material is generated or printed.\"\n";
    std::cout << "  ]\n";
    std::cout << "}\n";

    return failures.empty() ? 0 : 1;
}
