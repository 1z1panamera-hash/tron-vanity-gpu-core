#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

#include "GPU/GPUEngine.h"
#include "GPU/GPUGroup.h"

namespace {

using Clock = std::chrono::steady_clock;

double seconds(Clock::time_point start, Clock::time_point end) {
  return std::chrono::duration<double>(end - start).count();
}

std::string nonmatching_prefix8(const std::string& address) {
  static const std::string alphabet =
      "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
  std::string pattern = address.substr(0, 9);
  const std::size_t position = alphabet.find(pattern.back());
  pattern.back() = alphabet[(position + 1) % alphabet.size()];
  return pattern + "*";
}

}  // namespace

int main() {
  Secp256K1 secp;
  secp.Init();
  GPUEngine gpu(160, 128, 0, 2048, true);
  gpu.SetSearchType(TRON_ADDR);
  gpu.SetSearchMode(SEARCH_UNCOMPRESSED);

  const int thread_count = gpu.GetNbThread();
  std::vector<Point> points(thread_count);
  std::vector<std::string> target_pool;
  target_pool.reserve(16);
  for (int thread = 0; thread < thread_count; ++thread) {
    Int scalar;
    scalar.SetInt32(100000 + thread);
    scalar.Add(static_cast<uint64_t>(GRP_SIZE / 2));
    points[thread] = secp.ComputePublicKey(&scalar);
    if (thread < 16) {
      Point point = points[thread];
      const std::string address = secp.GetTronAddress(point);
      target_pool.push_back(nonmatching_prefix8(address));
    }
  }

  constexpr int iterations = 12;
  if (!gpu.SetTronGroupsPerLaunch(STEP_SIZE / GRP_SIZE)) return 1;
  for (const int target_count : {1, 4, 8, 16}) {
    std::vector<std::string> targets(
        target_pool.begin(), target_pool.begin() + target_count);
    if (!gpu.SetTronPatternsV2(targets)) return 1;
    const auto start = Clock::now();
    if (!gpu.SetKeys(points.data())) return 1;
    std::size_t hits = 0;
    for (int iteration = 0; iteration < iterations; ++iteration) {
      std::vector<ITEM> found;
      if (!gpu.Launch(found, true, iteration + 1 < iterations)) return 1;
      hits += found.size();
    }
    const double elapsed = seconds(start, Clock::now());
    const double attempts = static_cast<double>(iterations) * thread_count * STEP_SIZE * 3.0;
    std::cout << std::fixed << std::setprecision(6)
              << "throughput targets=" << target_count
              << " billion_per_second=" << attempts / elapsed / 1.0e9
              << " elapsed_seconds=" << elapsed
              << " hits=" << hits << '\n';
  }

  std::vector<std::string> targets(target_pool.begin(), target_pool.end());
  if (!gpu.SetTronPatternsV2(targets) || !gpu.SetTronGroupsPerLaunch(1) ||
      !gpu.SetKeys(points.data())) {
    return 1;
  }
  std::vector<double> latency_ms;
  constexpr int latency_iterations = 80;
  latency_ms.reserve(latency_iterations);
  for (int iteration = 0; iteration < latency_iterations; ++iteration) {
    std::vector<ITEM> found;
    const auto start = Clock::now();
    if (!gpu.Launch(found, true, iteration + 1 < latency_iterations)) return 1;
    latency_ms.push_back(seconds(start, Clock::now()) * 1000.0);
  }
  std::sort(latency_ms.begin(), latency_ms.end());
  const double p50 = latency_ms[latency_ms.size() / 2];
  const double p99 = latency_ms[(latency_ms.size() * 99) / 100];
  std::cout << std::fixed << std::setprecision(3)
            << "preemption groups=1 targets=16"
            << " p50_ms=" << p50
            << " p99_ms=" << p99
            << " max_ms=" << latency_ms.back() << '\n';
  return p99 <= 20.0 ? 0 : 1;
}
