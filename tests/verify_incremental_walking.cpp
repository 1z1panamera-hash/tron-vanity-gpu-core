#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "../src/secp256k1_device.cuh"
#include "../src/tron_core_device.cuh"

struct WalkConfig {
    unsigned long long start_counter;
    unsigned long long shard_id;
    unsigned long long shard_count;
    unsigned long long total_threads;
    unsigned long long threads_to_check;
    unsigned long long iterations_per_thread;
};

secp256k1_device::UInt256 scalar_from_u64(unsigned long long value) {
    secp256k1_device::UInt256 out;
    secp256k1_device::zero(out);
    out.limb[0] = static_cast<uint32_t>(value & 0xffffffffULL);
    out.limb[1] = static_cast<uint32_t>((value >> 32) & 0xffffffffULL);
    return out;
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

bool same_point(const secp256k1_device::Point& a, const secp256k1_device::Point& b) {
    if (a.infinity != b.infinity) return false;
    if (a.infinity) return true;
    return secp256k1_device::cmp(a.x, b.x) == 0 &&
           secp256k1_device::cmp(a.y, b.y) == 0;
}

int main() {
    const std::vector<WalkConfig> configs = {
        {0ULL, 0ULL, 1ULL, 4ULL, 2ULL, 3ULL},
        {1000ULL, 2ULL, 5ULL, 7ULL, 2ULL, 3ULL},
    };

    std::vector<std::string> failures;
    unsigned long long checked = 0;

    for (size_t config_index = 0; config_index < configs.size(); ++config_index) {
        const WalkConfig& config = configs[config_index];
        const unsigned long long step_scalar_value = config.total_threads * config.shard_count;
        secp256k1_device::Point step_point;
        if (!secp256k1_device::scalar_multiply(step_point, scalar_from_u64(step_scalar_value))) {
            failures.push_back("config " + std::to_string(config_index) + ": step scalar multiply failed");
            continue;
        }

        for (unsigned long long thread_idx = 0; thread_idx < config.threads_to_check; ++thread_idx) {
            const unsigned long long first_candidate =
                config.start_counter +
                thread_idx * config.shard_count +
                config.shard_id +
                1ULL;

            secp256k1_device::Point walked_point;
            if (!secp256k1_device::scalar_multiply(walked_point, scalar_from_u64(first_candidate))) {
                failures.push_back("config " + std::to_string(config_index) + ": first scalar multiply failed");
                continue;
            }

            for (unsigned long long iteration = 0; iteration < config.iterations_per_thread; ++iteration) {
                const unsigned long long direct_candidate =
                    first_candidate + iteration * step_scalar_value;
                secp256k1_device::Point direct_point;
                if (!secp256k1_device::scalar_multiply(direct_point, scalar_from_u64(direct_candidate))) {
                    failures.push_back("candidate " + std::to_string(direct_candidate) + ": direct scalar multiply failed");
                    break;
                }
                if (!same_point(walked_point, direct_point)) {
                    failures.push_back("candidate " + std::to_string(direct_candidate) + ": walked point mismatch");
                    break;
                }
                const std::string walked_address = point_to_address(walked_point);
                const std::string direct_address = point_to_address(direct_point);
                if (walked_address != direct_address) {
                    failures.push_back("candidate " + std::to_string(direct_candidate) + ": address mismatch");
                    break;
                }
                ++checked;

                if (iteration + 1 < config.iterations_per_thread) {
                    secp256k1_device::Point next_point;
                    if (!secp256k1_device::point_add(next_point, walked_point, step_point)) {
                        failures.push_back("candidate " + std::to_string(direct_candidate) + ": point_add failed");
                        break;
                    }
                    walked_point = next_point;
                }
            }
        }
    }

    std::cout << "{\n";
    std::cout << "  \"mode\": \"verify_incremental_walking\",\n";
    std::cout << "  \"configs\": " << configs.size() << ",\n";
    std::cout << "  \"checked_candidates\": " << checked << ",\n";
    std::cout << "  \"passed\": " << (failures.empty() ? "true" : "false") << ",\n";
    std::cout << "  \"failures\": [";
    for (size_t i = 0; i < failures.size(); ++i) {
        if (i) std::cout << ", ";
        std::cout << "\"" << failures[i] << "\"";
    }
    std::cout << "],\n";
    std::cout << "  \"notes\": [\n";
    std::cout << "    \"Host-side incremental walking validation only; no CUDA kernel or benchmark is run.\",\n";
    std::cout << "    \"Each walked public key is compared with direct scalar multiplication for the same candidate.\",\n";
    std::cout << "    \"No random private keys are generated and no key material is printed.\"\n";
    std::cout << "  ]\n";
    std::cout << "}\n";

    return failures.empty() ? 0 : 1;
}
