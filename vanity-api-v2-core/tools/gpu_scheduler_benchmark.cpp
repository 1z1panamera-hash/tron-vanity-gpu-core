#include <algorithm>
#include <chrono>
#include <cstdint>
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

std::string changed_base58(std::string value, std::size_t position) {
  static const std::string alphabet =
      "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
  const std::size_t index = alphabet.find(value[position]);
  value[position] = alphabet[(index + 1) % alphabet.size()];
  return value;
}

std::vector<Point> make_points(
    Secp256K1& secp, int thread_count, std::uint64_t first_scalar) {
  std::vector<Point> points(thread_count);
  for (int thread = 0; thread < thread_count; ++thread) {
    Int scalar;
    scalar.SetInt32(first_scalar + static_cast<std::uint64_t>(thread));
    scalar.Add(static_cast<std::uint64_t>(GRP_SIZE / 2));
    points[thread] = secp.ComputePublicKey(&scalar);
  }
  return points;
}

std::vector<std::string> make_background_targets(
    Secp256K1& secp, const std::vector<Point>& points) {
  std::vector<std::string> targets;
  targets.reserve(16);
  for (int i = 0; i < 16; ++i) {
    Point point = points[i];
    std::string address = secp.GetTronAddress(point);
    address = changed_base58(address, 8);
    targets.push_back(address.substr(0, 9) + "*");
  }
  return targets;
}

std::string make_p0_target(Secp256K1& secp, Point point) {
  std::string address = secp.GetTronAddress(point);
  address = changed_base58(address, address.size() - 1);
  return "T*" + address.substr(address.size() - 5);
}

double percentile(const std::vector<double>& sorted, std::size_t numerator) {
  const std::size_t index = std::min(
      sorted.size() - 1, (sorted.size() * numerator) / 100);
  return sorted[index];
}

}  // namespace

int main() {
  Secp256K1 secp;
  secp.Init();
  GPUEngine gpu(160, 128, 0, 2048, true);
  gpu.SetSearchType(TRON_ADDR);
  gpu.SetSearchMode(SEARCH_UNCOMPRESSED);
  if (!gpu.SetTronGroupsPerLaunch(1)) return 1;

  const int thread_count = gpu.GetNbThread();
  std::vector<Point> background_points = make_points(secp, thread_count, 100000);
  std::vector<Point> p0_points = make_points(secp, thread_count, 100000000);
  const std::vector<std::string> background_targets =
      make_background_targets(secp, background_points);
  const std::string p0_target = make_p0_target(secp, p0_points.front());

  constexpr int throughput_groups = 80;
  if (!gpu.SetTronPatternsV2(background_targets) ||
      !gpu.SetKeys(background_points.data())) {
    return 1;
  }
  const auto continuous_start = Clock::now();
  for (int group = 0; group < throughput_groups; ++group) {
    std::vector<ITEM> found;
    if (!gpu.Launch(found, true, group + 1 < throughput_groups)) return 1;
  }
  const double continuous_seconds = seconds(continuous_start, Clock::now());

  if (!gpu.SetTronPatternsV2(background_targets) ||
      !gpu.SetKeys(background_points.data())) {
    return 1;
  }
  std::vector<std::uint64_t> scheduled_state;
  const auto scheduled_start = Clock::now();
  for (int group = 0; group < throughput_groups; ++group) {
    std::vector<ITEM> found;
    if (!gpu.Launch(found, true, false)) return 1;
    if (!gpu.ExportKeyState(scheduled_state)) return 1;
    if (group + 1 < throughput_groups) {
      if (!gpu.SetTronPatternsV2(background_targets) ||
          !gpu.ImportKeyState(scheduled_state)) {
        return 1;
      }
    }
  }
  const double scheduled_seconds = seconds(scheduled_start, Clock::now());

  const double attempts = static_cast<double>(throughput_groups) *
      thread_count * GRP_SIZE * 3.0;
  const double continuous_bps = attempts / continuous_seconds / 1.0e9;
  const double scheduled_bps = attempts / scheduled_seconds / 1.0e9;
  const double overhead_percent =
      (continuous_bps - scheduled_bps) / continuous_bps * 100.0;

  std::vector<std::uint64_t> background_state;
  std::vector<std::uint64_t> p0_state;
  std::vector<ITEM> found;
  if (!gpu.SetTronPatternsV2(background_targets) ||
      !gpu.SetKeys(background_points.data()) ||
      !gpu.Launch(found, true, false) ||
      !gpu.ExportKeyState(background_state)) {
    return 1;
  }
  if (!gpu.SetTronPattern(p0_target.c_str()) ||
      !gpu.SetKeys(p0_points.data()) ||
      !gpu.Launch(found, true, false) ||
      !gpu.ExportKeyState(p0_state)) {
    return 1;
  }

  constexpr int takeover_iterations = 60;
  std::vector<double> takeover_ms;
  takeover_ms.reserve(takeover_iterations);
  for (int iteration = 0; iteration < takeover_iterations; ++iteration) {
    if (!gpu.SetTronPatternsV2(background_targets) ||
        !gpu.ImportKeyState(background_state)) {
      return 1;
    }
    const auto request_arrival = Clock::now();
    if (!gpu.Launch(found, true, false) ||
        !gpu.ExportKeyState(background_state) ||
        !gpu.SetTronPattern(p0_target.c_str()) ||
        !gpu.ImportKeyState(p0_state)) {
      return 1;
    }
    takeover_ms.push_back(seconds(request_arrival, Clock::now()) * 1000.0);
    if (!gpu.Launch(found, true, false) || !gpu.ExportKeyState(p0_state)) return 1;
  }
  std::sort(takeover_ms.begin(), takeover_ms.end());

  std::cout << std::fixed << std::setprecision(6)
            << "scheduler_throughput continuous_billion_per_second=" << continuous_bps
            << " scheduled_billion_per_second=" << scheduled_bps
            << " overhead_percent=" << overhead_percent << '\n';
  std::cout << std::fixed << std::setprecision(3)
            << "p0_takeover iterations=" << takeover_iterations
            << " p50_ms=" << percentile(takeover_ms, 50)
            << " p99_ms=" << percentile(takeover_ms, 99)
            << " max_ms=" << takeover_ms.back() << '\n';

  const bool overhead_ok = overhead_percent <= 3.0;
  const bool takeover_ok = percentile(takeover_ms, 99) <= 20.0;
  std::cout << "acceptance scheduler_overhead_le_3pct="
            << (overhead_ok ? "true" : "false")
            << " p0_takeover_p99_le_20ms="
            << (takeover_ok ? "true" : "false") << '\n';
  return overhead_ok && takeover_ok ? 0 : 1;
}
