#include <algorithm>
#include <iostream>
#include <set>
#include <string>
#include <vector>

struct ScheduleConfig {
    unsigned long long start_counter;
    unsigned long long max_attempts;
    unsigned long long shard_count;
    unsigned long long batch_limit;
    unsigned long long launch_threads_cap;
    unsigned long long total_threads_fallback;
};

std::vector<unsigned long long> simulate_worker(
    const ScheduleConfig& config,
    unsigned long long shard_id) {
    std::vector<unsigned long long> candidates;
    unsigned long long launched = 0;
    while (launched < config.max_attempts) {
        unsigned long long remaining = config.max_attempts - launched;
        unsigned long long batch_attempts =
            remaining < config.batch_limit ? remaining : config.batch_limit;
        unsigned long long launch_threads = batch_attempts;
        if (launch_threads > config.launch_threads_cap) {
            launch_threads = config.launch_threads_cap;
        }
        if (launch_threads == 0) {
            launch_threads = config.total_threads_fallback;
        }

        const unsigned long long batch_start_counter =
            config.start_counter + launched * config.shard_count;
        for (unsigned long long global_idx = 0; global_idx < launch_threads; ++global_idx) {
            for (unsigned long long attempt_idx = global_idx;
                 attempt_idx < batch_attempts;
                 attempt_idx += launch_threads) {
                candidates.push_back(
                    batch_start_counter +
                    attempt_idx * config.shard_count +
                    shard_id +
                    1ULL);
            }
        }

        launched += batch_attempts;
    }
    return candidates;
}

std::vector<unsigned long long> expected_worker(
    const ScheduleConfig& config,
    unsigned long long shard_id) {
    std::vector<unsigned long long> out;
    for (unsigned long long attempt = 0; attempt < config.max_attempts; ++attempt) {
        out.push_back(config.start_counter + attempt * config.shard_count + shard_id + 1ULL);
    }
    return out;
}

int main() {
    const std::vector<ScheduleConfig> configs = {
        {0ULL, 17ULL, 1ULL, 8ULL, 4ULL, 1ULL},
        {100ULL, 257ULL, 3ULL, 64ULL, 16ULL, 1ULL},
        {999ULL, 2051ULL, 7ULL, 1024ULL, 64ULL, 1ULL},
    };

    std::vector<std::string> failures;
    unsigned long long checked_candidates = 0;

    for (size_t config_index = 0; config_index < configs.size(); ++config_index) {
        const auto& config = configs[config_index];
        std::set<unsigned long long> all_candidates;

        for (unsigned long long shard_id = 0; shard_id < config.shard_count; ++shard_id) {
            auto actual = simulate_worker(config, shard_id);
            auto expected = expected_worker(config, shard_id);
            std::sort(actual.begin(), actual.end());
            std::sort(expected.begin(), expected.end());
            if (actual != expected) {
                failures.push_back(
                    "config " + std::to_string(config_index) +
                    " shard " + std::to_string(shard_id) +
                    ": worker sequence mismatch");
            }
            for (const auto candidate : actual) {
                if (!all_candidates.insert(candidate).second) {
                    failures.push_back(
                        "config " + std::to_string(config_index) +
                        ": duplicate candidate " + std::to_string(candidate));
                }
            }
            checked_candidates += actual.size();
        }

        const unsigned long long expected_total = config.max_attempts * config.shard_count;
        if (all_candidates.size() != expected_total) {
            failures.push_back(
                "config " + std::to_string(config_index) +
                ": expected " + std::to_string(expected_total) +
                " unique candidates, got " + std::to_string(all_candidates.size()));
        }
    }

    std::cout << "{\n";
    std::cout << "  \"mode\": \"verify_shard_schedule\",\n";
    std::cout << "  \"configs\": " << configs.size() << ",\n";
    std::cout << "  \"checked_candidates\": " << checked_candidates << ",\n";
    std::cout << "  \"passed\": " << (failures.empty() ? "true" : "false") << ",\n";
    std::cout << "  \"failures\": [";
    for (size_t i = 0; i < failures.size(); ++i) {
        if (i) std::cout << ", ";
        std::cout << "\"" << failures[i] << "\"";
    }
    std::cout << "],\n";
    std::cout << "  \"notes\": [\n";
    std::cout << "    \"CPU schedule validation only; no CUDA kernel or benchmark is run.\",\n";
    std::cout << "    \"This validates shard, batch, and thread-stride candidate coverage.\",\n";
    std::cout << "    \"No key material is generated or printed.\"\n";
    std::cout << "  ]\n";
    std::cout << "}\n";

    return failures.empty() ? 0 : 1;
}
