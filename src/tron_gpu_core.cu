// TRON GPU core implementation contract.
//
// This file is intentionally a compile target skeleton, not a completed CUDA
// vanity generator. It must not be used to report speed until every TODO in the
// correctness chain is implemented and Phase 0 vectors pass.

#include <cstdint>
#include <cstdio>
#include <cstring>

#include "secp256k1_device.cuh"
#include "tron_core_device.cuh"

#ifdef __CUDACC__
#include <chrono>
#include <cstdlib>
#include <cuda_runtime.h>
#include <fstream>
#include <iostream>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#endif

static constexpr int DEFAULT_PREFIX_LEN = 2;
static constexpr int DEFAULT_SUFFIX_LEN = 5;
static constexpr int PAYLOAD25_LEN = 25;
static constexpr int MAX_VECTOR_CASES = 16;
static constexpr int BENCHMARK_KERNEL_SCALAR_MULTIPLY = 0;
static constexpr int BENCHMARK_KERNEL_INCREMENTAL_WALK = 1;
static constexpr int BENCHMARK_BLOCK_THREADS = 128;

struct ValidationInput {
    uint8_t scalar32[32];
    uint8_t expected_public_key64[64];
    uint8_t expected_payload25[25];
    char expected_address[64];
    int expected_address_len;
};

struct ValidationResult {
    int passed;
    uint32_t failure_flags;
    char computed_address[64];
    int computed_address_len;
};

struct BenchmarkConfig {
    char target_address[64];
    int target_len;
    int prefix_len;
    int suffix_len;
    int prefix_range_enabled;
    uint8_t prefix_lower[PAYLOAD25_LEN];
    uint8_t prefix_upper[PAYLOAD25_LEN];
    int suffix_filter_enabled;
    unsigned long long suffix_value;
    int incremental_step_point_ready;
    secp256k1_device::Point incremental_step_point;
    int duration_seconds;
    int kernel_mode;
    unsigned long long max_attempts;
    unsigned long long start_counter;
    unsigned long long shard_id;
    unsigned long long shard_count;
};

struct BenchmarkResult {
    unsigned long long attempts;
    double elapsed_seconds;
    double addresses_per_second;
    int matched;
    char matched_address[64];
};

enum ValidationFailure : uint32_t {
    VALIDATION_PUBLIC_KEY_MISMATCH = 1U << 0,
    VALIDATION_PAYLOAD25_MISMATCH = 1U << 1,
    VALIDATION_ADDRESS_MISMATCH = 1U << 2,
    VALIDATION_FILTER_MISMATCH = 1U << 3,
    VALIDATION_SECP_FAILURE = 1U << 4,
    VALIDATION_PAYLOAD_FAILURE = 1U << 5,
};

// Required chain for each candidate:
// 1. private scalar -> secp256k1 public key
// 2. Keccak-256(public_key_without_04)
// 3. TRON payload21 = 0x41 + last20(keccak)
// 4. checksum4 = double_sha256(payload21)[0:4]
// 5. payload25 = payload21 + checksum4
// 6. Base58 suffix modulo filter
// 7. Base58 prefix range filter
// 8. full Base58Check confirmation

__device__ bool secp256k1_scalar_to_public_key(
    const uint8_t scalar32[32],
    uint8_t public_key_uncompressed65[65]) {
    secp256k1_device::UInt256 scalar;
    secp256k1_device::zero(scalar);
    for (int i = 0; i < 32; ++i) {
        int byte_from_right = 31 - i;
        int limb_index = i / 4;
        int shift = (i % 4) * 8;
        scalar.limb[limb_index] |= static_cast<uint32_t>(scalar32[byte_from_right]) << shift;
    }
    public_key_uncompressed65[0] = 0x04;
    return secp256k1_device::private_key_to_public_key64(scalar, public_key_uncompressed65 + 1);
}

__device__ void keccak256_public_key_without_04(
    const uint8_t public_key_uncompressed65[65],
    uint8_t digest32[32]) {
    tron_device::keccak256_single_block(public_key_uncompressed65 + 1, 64, digest32);
}

__device__ void double_sha256_checksum4(
    const uint8_t payload21[21],
    uint8_t checksum4[4]) {
    uint8_t first_sha[32];
    uint8_t second_sha[32];
    tron_device::sha256_single_block(payload21, 21, first_sha);
    tron_device::sha256_single_block(first_sha, 32, second_sha);
    for (int i = 0; i < 4; ++i) {
        checksum4[i] = second_sha[i];
    }
}

__device__ bool base58_suffix_mod_filter(
    const uint8_t payload25[PAYLOAD25_LEN],
    int suffix_len,
    unsigned long long suffix_value) {
    return tron_device::payload25_mod_suffix_base(payload25, suffix_len) == suffix_value;
}

__device__ bool base58_prefix_range_filter(
    const uint8_t payload25[PAYLOAD25_LEN],
    const uint8_t prefix_lower[PAYLOAD25_LEN],
    const uint8_t prefix_upper[PAYLOAD25_LEN]) {
    int lower_cmp = 0;
    int upper_cmp = 0;
    for (int i = 0; i < PAYLOAD25_LEN; ++i) {
        if (lower_cmp == 0) {
            if (payload25[i] < prefix_lower[i]) lower_cmp = -1;
            if (payload25[i] > prefix_lower[i]) lower_cmp = 1;
        }
        if (upper_cmp == 0) {
            if (payload25[i] < prefix_upper[i]) upper_cmp = -1;
            if (payload25[i] > prefix_upper[i]) upper_cmp = 1;
        }
    }
    return lower_cmp >= 0 && upper_cmp < 0;
}

__device__ bool full_base58check_confirm(
    const uint8_t payload25[PAYLOAD25_LEN],
    const char* target_address,
    int prefix_len,
    int suffix_len) {
    int target_len = 0;
    while (target_len < tron_device::BASE58_MAX_LEN && target_address[target_len] != '\0') {
        ++target_len;
    }
    char address[tron_device::BASE58_MAX_LEN];
    int address_len = tron_device::base58_encode_payload25(payload25, address);
    if (address_len <= 0) {
        return false;
    }
    return tron_device::str_prefix_suffix_match(
        address,
        address_len,
        target_address,
        target_len,
        prefix_len,
        suffix_len);
}

__device__ void scalar32_from_candidate(unsigned long long candidate, uint8_t scalar32[32]) {
    for (int i = 0; i < 32; ++i) {
        scalar32[i] = 0;
    }
    for (int i = 0; i < 8; ++i) {
        scalar32[31 - i] = static_cast<uint8_t>((candidate >> (8 * i)) & 0xffULL);
    }
}

__device__ void copy_cstr64(char dst[64], const char* src, int len);

SECP_HD secp256k1_device::UInt256 uint256_from_u64(unsigned long long value) {
    secp256k1_device::UInt256 out;
    secp256k1_device::zero(out);
    out.limb[0] = static_cast<uint32_t>(value & 0xffffffffULL);
    out.limb[1] = static_cast<uint32_t>((value >> 32) & 0xffffffffULL);
    return out;
}

__device__ bool point_to_public_key64(
    const secp256k1_device::Point& point,
    uint8_t public_key64[64]) {
    if (point.infinity) {
        return false;
    }
    secp256k1_device::uint256_to_be32(point.x, public_key64);
    secp256k1_device::uint256_to_be32(point.y, public_key64 + 32);
    return true;
}

__device__ bool payload_matches_target(
    const uint8_t payload25[25],
    const BenchmarkConfig& config,
    char matched_address[64]) {
    if (config.prefix_range_enabled &&
        !base58_prefix_range_filter(payload25, config.prefix_lower, config.prefix_upper)) {
        return false;
    }
    if (config.suffix_filter_enabled &&
        !base58_suffix_mod_filter(payload25, config.suffix_len, config.suffix_value)) {
        return false;
    }

    char address[tron_device::BASE58_MAX_LEN];
    int address_len = tron_device::base58_encode_payload25(payload25, address);
    if (address_len <= 0) {
        return false;
    }
    if (!tron_device::str_prefix_suffix_match(
            address,
            address_len,
            config.target_address,
            config.target_len,
            config.prefix_len,
            config.suffix_len)) {
        return false;
    }
    copy_cstr64(matched_address, address, address_len);
    return true;
}

__device__ bool point_matches_target(
    const secp256k1_device::Point& point,
    const BenchmarkConfig& config,
    char matched_address[64]) {
    uint8_t public_key64[64];
    uint8_t payload25[25];
    uint8_t keccak_out[32];
    if (!point_to_public_key64(point, public_key64)) {
        return false;
    }
    if (!tron_device::payload25_from_public_key64(public_key64, payload25, keccak_out)) {
        return false;
    }
    return payload_matches_target(payload25, config, matched_address);
}

__device__ void copy_cstr64(char dst[64], const char* src, int len) {
    int capped = len < 63 ? len : 63;
    for (int i = 0; i < capped; ++i) {
        dst[i] = src[i];
    }
    dst[capped] = '\0';
}

__global__ void benchmark_kernel(BenchmarkConfig config, BenchmarkResult* result) {
    const unsigned long long global_idx =
        static_cast<unsigned long long>(blockIdx.x) * static_cast<unsigned long long>(blockDim.x) +
        static_cast<unsigned long long>(threadIdx.x);
    if (global_idx >= config.max_attempts || config.shard_count == 0) {
        return;
    }

    const unsigned long long candidate =
        config.start_counter +
        global_idx * config.shard_count +
        config.shard_id +
        1ULL;

    uint8_t scalar32[32];
    uint8_t public_key65[65];
    uint8_t payload25[25];
    uint8_t keccak_out[32];
    scalar32_from_candidate(candidate, scalar32);

    if (!secp256k1_scalar_to_public_key(scalar32, public_key65)) {
        return;
    }
    if (!tron_device::payload25_from_public_key64(public_key65 + 1, payload25, keccak_out)) {
        return;
    }

    atomicAdd(&result->attempts, 1ULL);
    if (result->matched != 0) {
        return;
    }

    char matched_address[64];
    if (payload_matches_target(payload25, config, matched_address)) {
        if (atomicCAS(&result->matched, 0, 1) == 0) {
            int matched_len = 0;
            while (matched_len < 63 && matched_address[matched_len] != '\0') {
                ++matched_len;
            }
            copy_cstr64(result->matched_address, matched_address, matched_len);
        }
    }
}

__global__ void benchmark_incremental_kernel(BenchmarkConfig config, BenchmarkResult* result) {
    __shared__ secp256k1_device::Point shared_points[BENCHMARK_BLOCK_THREADS];
    __shared__ secp256k1_device::Point shared_next_points[BENCHMARK_BLOCK_THREADS];
    __shared__ secp256k1_device::UInt256 shared_denominators[BENCHMARK_BLOCK_THREADS];
    __shared__ secp256k1_device::UInt256 shared_inverses[BENCHMARK_BLOCK_THREADS];
    __shared__ secp256k1_device::UInt256 shared_scratch[BENCHMARK_BLOCK_THREADS];
    __shared__ int shared_normal_indices[BENCHMARK_BLOCK_THREADS];
    __shared__ int shared_stop;
    __shared__ int shared_active_count;
    __shared__ int shared_batch_ok;

    const unsigned long long global_idx =
        static_cast<unsigned long long>(blockIdx.x) * static_cast<unsigned long long>(blockDim.x) +
        static_cast<unsigned long long>(threadIdx.x);
    const unsigned long long total_threads =
        static_cast<unsigned long long>(gridDim.x) * static_cast<unsigned long long>(blockDim.x);
    if (total_threads == 0 || config.shard_count == 0 || blockDim.x > BENCHMARK_BLOCK_THREADS) {
        return;
    }

    const unsigned long long first_candidate =
        config.start_counter +
        global_idx * config.shard_count +
        config.shard_id +
        1ULL;
    bool thread_has_candidate = global_idx < config.max_attempts;
    secp256k1_device::Point current_point;
    secp256k1_device::Point step_point;
    secp256k1_device::UInt256 first_scalar = uint256_from_u64(first_candidate);
    if (!secp256k1_device::scalar_multiply(current_point, first_scalar)) {
        current_point = secp256k1_device::generator();
        thread_has_candidate = false;
    }
    if (config.incremental_step_point_ready) {
        step_point = config.incremental_step_point;
    } else {
        const unsigned long long step_scalar_value = total_threads * config.shard_count;
        secp256k1_device::UInt256 step_scalar = uint256_from_u64(step_scalar_value);
        if (!secp256k1_device::scalar_multiply(step_point, step_scalar)) {
            return;
        }
    }

    char candidate_address[64];
    unsigned long long local_attempts = 0ULL;
    for (unsigned long long attempt_idx = global_idx;; attempt_idx += total_threads) {
        if (threadIdx.x == 0) {
            shared_stop = result->matched != 0 ? 1 : 0;
            shared_active_count = 0;
            shared_batch_ok = 1;
        }
        __syncthreads();
        if (shared_stop) {
            break;
        }

        const bool active_attempt = thread_has_candidate && attempt_idx < config.max_attempts;
        if (active_attempt) {
            atomicAdd(&shared_active_count, 1);
        }
        __syncthreads();
        if (shared_active_count == 0) {
            break;
        }

        if (active_attempt && point_matches_target(current_point, config, candidate_address)) {
            ++local_attempts;
            if (atomicCAS(&result->matched, 0, 1) == 0) {
                int matched_len = 0;
                while (matched_len < 63 && candidate_address[matched_len] != '\0') {
                    ++matched_len;
                }
                copy_cstr64(result->matched_address, candidate_address, matched_len);
            }
            shared_stop = 1;
        }
        __syncthreads();
        if (shared_stop) {
            break;
        }

        if (active_attempt) {
            ++local_attempts;
        }

        shared_points[threadIdx.x] = current_point;
        __syncthreads();
        if (threadIdx.x == 0) {
            shared_batch_ok = secp256k1_device::point_add_same_stride_batch(
                shared_next_points,
                shared_denominators,
                shared_inverses,
                shared_scratch,
                shared_normal_indices,
                shared_points,
                step_point,
                blockDim.x) ? 1 : 0;
        }
        __syncthreads();
        if (!shared_batch_ok) {
            break;
        }
        current_point = shared_next_points[threadIdx.x];
    }

    if (local_attempts > 0ULL) {
        atomicAdd(&result->attempts, local_attempts);
    }
}

__global__ void validate_vectors_kernel(
    const ValidationInput* inputs,
    ValidationResult* results,
    int count) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= count) {
        return;
    }

    const ValidationInput& input = inputs[idx];
    ValidationResult result;
    result.passed = 0;
    result.failure_flags = 0;
    result.computed_address_len = 0;
    for (int i = 0; i < 64; ++i) {
        result.computed_address[i] = '\0';
    }

    uint8_t public_key65[65];
    if (!secp256k1_scalar_to_public_key(input.scalar32, public_key65)) {
        result.failure_flags |= VALIDATION_SECP_FAILURE;
        results[idx] = result;
        return;
    }

    for (int i = 0; i < 64; ++i) {
        if (public_key65[i + 1] != input.expected_public_key64[i]) {
            result.failure_flags |= VALIDATION_PUBLIC_KEY_MISMATCH;
            break;
        }
    }

    uint8_t payload25[25];
    uint8_t keccak_out[32];
    if (!tron_device::payload25_from_public_key64(public_key65 + 1, payload25, keccak_out)) {
        result.failure_flags |= VALIDATION_PAYLOAD_FAILURE;
        results[idx] = result;
        return;
    }

    for (int i = 0; i < 25; ++i) {
        if (payload25[i] != input.expected_payload25[i]) {
            result.failure_flags |= VALIDATION_PAYLOAD25_MISMATCH;
            break;
        }
    }

    char address[tron_device::BASE58_MAX_LEN];
    int address_len = tron_device::base58_encode_payload25(payload25, address);
    result.computed_address_len = address_len;
    if (address_len > 0) {
        for (int i = 0; i < address_len && i < 63; ++i) {
            result.computed_address[i] = address[i];
        }
        result.computed_address[address_len < 63 ? address_len : 63] = '\0';
    }

    if (address_len != input.expected_address_len) {
        result.failure_flags |= VALIDATION_ADDRESS_MISMATCH;
    } else {
        for (int i = 0; i < address_len; ++i) {
            if (address[i] != input.expected_address[i]) {
                result.failure_flags |= VALIDATION_ADDRESS_MISMATCH;
                break;
            }
        }
    }

    if (!tron_device::address_matches_filter(
            payload25,
            input.expected_address,
            input.expected_address_len,
            DEFAULT_PREFIX_LEN,
            DEFAULT_SUFFIX_LEN)) {
        result.failure_flags |= VALIDATION_FILTER_MISMATCH;
    }

    result.passed = result.failure_flags == 0 ? 1 : 0;
    results[idx] = result;
}

#ifdef __CUDACC__
static std::string read_file(const std::string& path) {
    std::ifstream in(path);
    if (!in) {
        throw std::runtime_error("failed to open " + path);
    }
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

static std::string extract_string(const std::string& object, const std::string& key) {
    std::regex re("\"" + key + "\"\\s*:\\s*\"([^\"]*)\"");
    std::smatch match;
    if (!std::regex_search(object, match, re)) {
        throw std::runtime_error("missing key: " + key);
    }
    return match[1].str();
}

static uint8_t hex_value(char c) {
    if (c >= '0' && c <= '9') return static_cast<uint8_t>(c - '0');
    if (c >= 'a' && c <= 'f') return static_cast<uint8_t>(c - 'a' + 10);
    if (c >= 'A' && c <= 'F') return static_cast<uint8_t>(c - 'A' + 10);
    throw std::runtime_error("invalid hex");
}

static std::vector<uint8_t> hex_to_bytes(const std::string& hex) {
    if (hex.size() % 2 != 0) {
        throw std::runtime_error("invalid hex length");
    }
    std::vector<uint8_t> out(hex.size() / 2);
    for (size_t i = 0; i < out.size(); ++i) {
        out[i] = static_cast<uint8_t>((hex_value(hex[i * 2]) << 4) | hex_value(hex[i * 2 + 1]));
    }
    return out;
}

static std::vector<ValidationInput> parse_validation_inputs(const std::string& path) {
    const std::string json = read_file(path);
    std::vector<ValidationInput> out;
    std::regex object_re("\\{[^{}]*\"label\"[^{}]*\\}");
    auto begin = std::sregex_iterator(json.begin(), json.end(), object_re);
    auto end = std::sregex_iterator();
    for (auto it = begin; it != end; ++it) {
        if (out.size() >= MAX_VECTOR_CASES) {
            throw std::runtime_error("too many validation vectors");
        }
        const std::string object = it->str();
        const auto scalar = hex_to_bytes(extract_string(object, "private_key_hex"));
        const std::string public_key_hex = extract_string(object, "public_key_uncompressed_hex");
        const auto public_key = hex_to_bytes(public_key_hex.substr(2));
        const auto payload25 = hex_to_bytes(extract_string(object, "payload25_hex"));
        const std::string address = extract_string(object, "tron_base58_address");

        if (scalar.size() != 32 || public_key.size() != 64 || payload25.size() != 25) {
            throw std::runtime_error("invalid validation vector field size");
        }
        if (address.size() >= 64) {
            throw std::runtime_error("address too long");
        }

        ValidationInput input{};
        std::memcpy(input.scalar32, scalar.data(), scalar.size());
        std::memcpy(input.expected_public_key64, public_key.data(), public_key.size());
        std::memcpy(input.expected_payload25, payload25.data(), payload25.size());
        std::memcpy(input.expected_address, address.c_str(), address.size());
        input.expected_address[address.size()] = '\0';
        input.expected_address_len = static_cast<int>(address.size());
        out.push_back(input);
    }
    if (out.empty()) {
        throw std::runtime_error("no validation vectors found");
    }
    return out;
}

static const char* cuda_status(cudaError_t status) {
    return cudaGetErrorString(status);
}

static std::string gpu_name() {
    int device = 0;
    cudaError_t status = cudaGetDevice(&device);
    if (status != cudaSuccess) {
        return "unknown";
    }
    cudaDeviceProp props{};
    status = cudaGetDeviceProperties(&props, device);
    if (status != cudaSuccess) {
        return "unknown";
    }
    return std::string(props.name);
}

static int run_validate_vectors_cuda(const char* vector_path) {
    std::vector<ValidationInput> inputs;
    try {
        inputs = parse_validation_inputs(vector_path);
    } catch (const std::exception& exc) {
        std::fprintf(stderr, "parse validation vectors failed: %s\n", exc.what());
        return 1;
    }

    ValidationInput* d_inputs = nullptr;
    ValidationResult* d_results = nullptr;
    const size_t input_bytes = inputs.size() * sizeof(ValidationInput);
    const size_t result_bytes = inputs.size() * sizeof(ValidationResult);
    std::vector<ValidationResult> results(inputs.size());

    cudaError_t status = cudaMalloc(&d_inputs, input_bytes);
    if (status != cudaSuccess) {
        std::fprintf(stderr, "cudaMalloc inputs failed: %s\n", cuda_status(status));
        return 1;
    }
    status = cudaMalloc(&d_results, result_bytes);
    if (status != cudaSuccess) {
        std::fprintf(stderr, "cudaMalloc results failed: %s\n", cuda_status(status));
        cudaFree(d_inputs);
        return 1;
    }
    status = cudaMemcpy(d_inputs, inputs.data(), input_bytes, cudaMemcpyHostToDevice);
    if (status != cudaSuccess) {
        std::fprintf(stderr, "cudaMemcpy inputs failed: %s\n", cuda_status(status));
        cudaFree(d_inputs);
        cudaFree(d_results);
        return 1;
    }

    const int threads = 32;
    const int blocks = static_cast<int>((inputs.size() + threads - 1) / threads);
    validate_vectors_kernel<<<blocks, threads>>>(d_inputs, d_results, static_cast<int>(inputs.size()));
    status = cudaDeviceSynchronize();
    if (status != cudaSuccess) {
        std::fprintf(stderr, "validate_vectors_kernel failed: %s\n", cuda_status(status));
        cudaFree(d_inputs);
        cudaFree(d_results);
        return 1;
    }

    status = cudaMemcpy(results.data(), d_results, result_bytes, cudaMemcpyDeviceToHost);
    cudaFree(d_inputs);
    cudaFree(d_results);
    if (status != cudaSuccess) {
        std::fprintf(stderr, "cudaMemcpy results failed: %s\n", cuda_status(status));
        return 1;
    }

    int passed = 0;
    std::printf("{\n");
    std::printf("  \"mode\": \"validate_vectors\",\n");
    std::printf("  \"vector_path\": \"%s\",\n", vector_path);
    std::printf("  \"total_vectors\": %zu,\n", results.size());
    std::printf("  \"results\": [");
    for (size_t i = 0; i < results.size(); ++i) {
        if (i) std::printf(", ");
        if (results[i].passed) ++passed;
        std::printf("{\"index\": %zu, \"passed\": %s, \"failure_flags\": %u}",
                    i,
                    results[i].passed ? "true" : "false",
                    results[i].failure_flags);
    }
    std::printf("],\n");
    std::printf("  \"passed\": %d,\n", passed);
    std::printf("  \"failed\": %zu,\n", results.size() - static_cast<size_t>(passed));
    std::printf("  \"notes\": [\n");
    std::printf("    \"CUDA vector validation only; no benchmark is run.\",\n");
    std::printf("    \"Only public TEST_ONLY vectors are used.\",\n");
    std::printf("    \"No plaintext key material or credential material is printed.\"\n");
    std::printf("  ]\n");
    std::printf("}\n");

    return passed == static_cast<int>(results.size()) ? 0 : 1;
}

static const char* arg_value(int argc, char** argv, const char* name, const char* fallback) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (std::strcmp(argv[i], name) == 0) {
            return argv[i + 1];
        }
    }
    return fallback;
}

static int parse_int_arg(int argc, char** argv, const char* name, int fallback) {
    const char* value = arg_value(argc, argv, name, nullptr);
    if (!value) return fallback;
    return std::atoi(value);
}

static unsigned long long parse_ull_arg(
    int argc,
    char** argv,
    const char* name,
    unsigned long long fallback) {
    const char* value = arg_value(argc, argv, name, nullptr);
    if (!value) return fallback;
    char* end = nullptr;
    unsigned long long parsed = std::strtoull(value, &end, 10);
    if (!end || *end != '\0') {
        throw std::runtime_error(std::string("invalid integer for ") + name);
    }
    return parsed;
}

static bool validate_target_address(const char* target_address, int* out_len) {
    if (!target_address || target_address[0] != 'T') {
        return false;
    }
    int len = 0;
    while (target_address[len] != '\0') {
        if (len >= 63 || tron_device::base58_index(target_address[len]) < 0) {
            return false;
        }
        ++len;
    }
    if (len < 26 || len > 40) {
        return false;
    }
    *out_len = len;
    return true;
}

static bool prepare_benchmark_filters(BenchmarkConfig& config, std::string& error) {
    config.prefix_range_enabled = config.prefix_len > 0 ? 1 : 0;
    config.suffix_filter_enabled = config.suffix_len > 0 ? 1 : 0;

    if (config.prefix_range_enabled &&
        !tron_device::base58_prefix_bounds(
            config.target_address,
            config.prefix_len,
            config.target_len,
            config.prefix_lower,
            config.prefix_upper)) {
        error = "failed to precompute Base58 prefix range";
        return false;
    }

    if (config.suffix_filter_enabled) {
        const char* suffix = config.target_address + config.target_len - config.suffix_len;
        const uint64_t suffix_value =
            tron_device::suffix_value_from_base58_suffix(suffix, config.suffix_len);
        if (suffix_value == UINT64_MAX) {
            error = "failed to precompute Base58 suffix value";
            return false;
        }
        config.suffix_value = suffix_value;
    }

    return true;
}

static int parse_kernel_mode(int argc, char** argv) {
    const char* mode = arg_value(argc, argv, "--kernel-mode", "incremental");
    if (std::strcmp(mode, "incremental") == 0) {
        return BENCHMARK_KERNEL_INCREMENTAL_WALK;
    }
    if (std::strcmp(mode, "scalar") == 0) {
        return BENCHMARK_KERNEL_SCALAR_MULTIPLY;
    }
    throw std::runtime_error("invalid --kernel-mode; expected incremental or scalar");
}

static const char* kernel_mode_name(int kernel_mode) {
    if (kernel_mode == BENCHMARK_KERNEL_INCREMENTAL_WALK) {
        return "incremental_public_key_walk";
    }
    if (kernel_mode == BENCHMARK_KERNEL_SCALAR_MULTIPLY) {
        return "scalar_multiply_per_candidate";
    }
    return "unknown";
}

static int run_benchmark_cuda(int argc, char** argv) {
    BenchmarkConfig config{};
    BenchmarkResult host_result{};
    const std::string detected_gpu_name = gpu_name();
    const char* target_address = arg_value(argc, argv, "--target-address", nullptr);
    if (!validate_target_address(target_address, &config.target_len)) {
        std::fprintf(stderr, "invalid --target-address; expected TRON Base58 address starting with T\n");
        return 1;
    }

    std::strncpy(config.target_address, target_address, sizeof(config.target_address) - 1);
    config.prefix_len = parse_int_arg(argc, argv, "--prefix-len", DEFAULT_PREFIX_LEN);
    config.suffix_len = parse_int_arg(argc, argv, "--suffix-len", DEFAULT_SUFFIX_LEN);
    config.duration_seconds = parse_int_arg(argc, argv, "--duration-seconds", 5);
    config.kernel_mode = parse_kernel_mode(argc, argv);
    config.max_attempts = parse_ull_arg(argc, argv, "--max-attempts", 1024ULL);
    config.start_counter = parse_ull_arg(argc, argv, "--start-counter", 0ULL);
    config.shard_id = parse_ull_arg(argc, argv, "--shard-id", 0ULL);
    config.shard_count = parse_ull_arg(argc, argv, "--shard-count", 1ULL);

    if (config.prefix_len < 0 || config.suffix_len < 0 ||
        config.prefix_len + config.suffix_len > config.target_len) {
        std::fprintf(stderr, "invalid prefix/suffix lengths\n");
        return 1;
    }
    if (config.duration_seconds < 1 || config.duration_seconds > 10) {
        std::fprintf(stderr, "duration_seconds must be between 1 and 10 for this gated worker\n");
        return 1;
    }
    if (config.max_attempts == 0) {
        std::fprintf(stderr, "max_attempts must be positive\n");
        return 1;
    }
    if (config.shard_count == 0 || config.shard_id >= config.shard_count) {
        std::fprintf(stderr, "invalid shard_id/shard_count\n");
        return 1;
    }
    std::string filter_error;
    if (!prepare_benchmark_filters(config, filter_error)) {
        std::fprintf(stderr, "%s\n", filter_error.c_str());
        return 1;
    }

    BenchmarkResult* d_result = nullptr;
    cudaError_t status = cudaMalloc(&d_result, sizeof(BenchmarkResult));
    if (status != cudaSuccess) {
        std::fprintf(stderr, "cudaMalloc benchmark result failed: %s\n", cuda_status(status));
        return 1;
    }
    status = cudaMemset(d_result, 0, sizeof(BenchmarkResult));
    if (status != cudaSuccess) {
        std::fprintf(stderr, "cudaMemset benchmark result failed: %s\n", cuda_status(status));
        cudaFree(d_result);
        return 1;
    }

    const int threads = BENCHMARK_BLOCK_THREADS;
    const unsigned long long scalar_batch_limit = 1024ULL;
    const unsigned long long incremental_batch_limit = 1048576ULL;
    const unsigned long long max_incremental_launch_threads = 65536ULL;
    unsigned long long launched = 0;
    const auto started = std::chrono::steady_clock::now();
    double elapsed = 0.0;

    while (launched < config.max_attempts) {
        elapsed = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - started).count();
        if (elapsed >= static_cast<double>(config.duration_seconds)) {
            break;
        }

        BenchmarkConfig batch_config = config;
        unsigned long long remaining = config.max_attempts - launched;
        unsigned long long batch_limit =
            config.kernel_mode == BENCHMARK_KERNEL_INCREMENTAL_WALK
                ? incremental_batch_limit
                : scalar_batch_limit;
        unsigned long long batch_attempts = remaining < batch_limit ? remaining : batch_limit;
        batch_config.max_attempts = batch_attempts;
        batch_config.start_counter = config.start_counter + launched * config.shard_count;
        unsigned long long launch_threads = batch_attempts;
        if (config.kernel_mode == BENCHMARK_KERNEL_INCREMENTAL_WALK &&
            launch_threads > max_incremental_launch_threads) {
            launch_threads = max_incremental_launch_threads;
        }
        int blocks = static_cast<int>((launch_threads + threads - 1) / threads);
        const unsigned long long actual_total_threads =
            static_cast<unsigned long long>(blocks) * static_cast<unsigned long long>(threads);

        batch_config.incremental_step_point_ready = 0;
        if (config.kernel_mode == BENCHMARK_KERNEL_INCREMENTAL_WALK) {
            if (batch_config.shard_count != 0 &&
                actual_total_threads > (~0ULL / batch_config.shard_count)) {
                std::fprintf(stderr, "incremental step scalar overflow\n");
                cudaFree(d_result);
                return 1;
            }
            const unsigned long long step_scalar_value = actual_total_threads * batch_config.shard_count;
            secp256k1_device::UInt256 step_scalar = uint256_from_u64(step_scalar_value);
            if (!secp256k1_device::scalar_multiply(batch_config.incremental_step_point, step_scalar)) {
                std::fprintf(stderr, "incremental step point precompute failed\n");
                cudaFree(d_result);
                return 1;
            }
            batch_config.incremental_step_point_ready = 1;
        }

        if (config.kernel_mode == BENCHMARK_KERNEL_INCREMENTAL_WALK) {
            benchmark_incremental_kernel<<<blocks, threads>>>(batch_config, d_result);
        } else {
            benchmark_kernel<<<blocks, threads>>>(batch_config, d_result);
        }
        status = cudaDeviceSynchronize();
        if (status != cudaSuccess) {
            std::fprintf(stderr, "benchmark kernel failed: %s\n", cuda_status(status));
            cudaFree(d_result);
            return 1;
        }

        launched += batch_attempts;
        status = cudaMemcpy(&host_result, d_result, sizeof(BenchmarkResult), cudaMemcpyDeviceToHost);
        if (status != cudaSuccess) {
            std::fprintf(stderr, "cudaMemcpy benchmark result failed: %s\n", cuda_status(status));
            cudaFree(d_result);
            return 1;
        }
        if (host_result.matched != 0) {
            break;
        }
    }

    elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    cudaFree(d_result);

    host_result.elapsed_seconds = elapsed;
    host_result.addresses_per_second =
        elapsed > 0.0 ? static_cast<double>(host_result.attempts) / elapsed : 0.0;

    std::printf("{\n");
    std::printf("  \"mode\": \"benchmark\",\n");
    std::printf("  \"target_prefix\": \"%.*s\",\n", config.prefix_len, config.target_address);
    std::printf("  \"target_suffix\": \"%s\",\n", config.target_address + config.target_len - config.suffix_len);
    std::printf("  \"duration_seconds\": %d,\n", config.duration_seconds);
    std::printf("  \"kernel_mode\": \"%s\",\n", kernel_mode_name(config.kernel_mode));
    std::printf("  \"attempts\": %llu,\n", host_result.attempts);
    std::printf("  \"elapsed_seconds\": %.6f,\n", host_result.elapsed_seconds);
    std::printf("  \"addresses_per_second\": %.6f,\n", host_result.addresses_per_second);
    std::printf("  \"keys_per_second\": %.6f,\n", host_result.addresses_per_second);
    std::printf("  \"gpu_name\": \"%s\",\n", detected_gpu_name.c_str());
    std::printf("  \"matched\": %s,\n", host_result.matched ? "true" : "false");
    std::printf("  \"matched_address\": \"%s\",\n", host_result.matched ? host_result.matched_address : "");
    std::printf("  \"max_attempts\": %llu,\n", config.max_attempts);
    std::printf("  \"start_counter\": %llu,\n", config.start_counter);
    std::printf("  \"shard_id\": %llu,\n", config.shard_id);
    std::printf("  \"shard_count\": %llu,\n", config.shard_count);
    std::printf("  \"notes\": [\n");
    std::printf("    \"Counts are complete TRON address attempts, not hash speed.\",\n");
    std::printf("    \"This smoke benchmark emits no private key, seed, mnemonic, token, or secret.\",\n");
    std::printf("    \"Incremental mode uses one base scalar multiply per thread, then block-level batch inversion for stride point additions.\",\n");
    std::printf("    \"This deterministic candidate generator is intended for benchmark/correctness staging only.\"\n");
    std::printf("  ]\n");
    std::printf("}\n");
    return 0;
}
#endif

static void print_usage(const char* argv0) {
    std::fprintf(stderr,
        "Usage:\n"
        "  %s --validate-vectors tests/phase0_test_vectors.json\n"
        "  %s --benchmark --kernel-mode incremental --target-address T... --prefix-len 2 --suffix-len 5 --duration-seconds 5 --max-attempts 1024 --start-counter 0 --shard-id 0 --shard-count 1\n",
        argv0,
        argv0);
}

int main(int argc, char** argv) {
    if (argc >= 2 && std::strcmp(argv[1], "--validate-vectors") == 0) {
#ifdef __CUDACC__
        const char* vector_path = argc >= 3 ? argv[2] : "tests/phase0_test_vectors.json";
        return run_validate_vectors_cuda(vector_path);
#else
        std::fprintf(stderr,
            "GPU core CUDA validation requires nvcc build; host-stub parse only confirms source syntax.\n");
        return 2;
#endif
    }

    if (argc >= 2 && std::strcmp(argv[1], "--benchmark") == 0) {
#ifdef __CUDACC__
        return run_benchmark_cuda(argc, argv);
#else
        std::fprintf(stderr,
            "GPU benchmark requires nvcc build and explicit RunPod-side benchmark gate.\n");
        return 2;
#endif
    }

    print_usage(argv[0]);
    return 2;
}
