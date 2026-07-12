#include <iostream>
#include <string>
#include <vector>

#include "GPU/GPUEngine.h"
#include "GPU/GPUGroup.h"

namespace {

bool matches(const std::string& pattern, const std::string& address) {
  const std::size_t wildcard = pattern.find('*');
  const std::string prefix = pattern.substr(1, wildcard - 1);
  const std::string suffix = pattern.substr(wildcard + 1);
  return address.size() == 34 &&
      address.compare(0, 1 + prefix.size(), "T" + prefix) == 0 &&
      address.compare(address.size() - suffix.size(), suffix.size(), suffix) == 0;
}

}  // namespace

int main() {
  Secp256K1 secp;
  secp.Init();

  GPUEngine gpu(1, 32, 0, 2048, true);
  if (gpu.GetNbThread() != 32) {
    std::cerr << "unexpected GPU thread count\n";
    return 1;
  }
  gpu.SetSearchType(TRON_ADDR);
  gpu.SetSearchMode(SEARCH_UNCOMPRESSED);
  if (!gpu.SetTronGroupsPerLaunch(1)) return 1;

  Int scalar;
  scalar.SetInt32(1);
  scalar.Add(static_cast<uint64_t>(GRP_SIZE / 2));
  Point known_point = secp.ComputePublicKey(&scalar);
  const std::string expected_address = secp.GetTronAddress(known_point);
  std::vector<Point> points(gpu.GetNbThread(), known_point);

  int passed = 0;
  for (std::size_t total = 6; total <= 8; ++total) {
    for (std::size_t prefix_length = 0; prefix_length <= total; ++prefix_length) {
      const std::size_t suffix_length = total - prefix_length;
      const std::string prefix = expected_address.substr(1, prefix_length);
      const std::string suffix = suffix_length == 0
          ? std::string()
          : expected_address.substr(expected_address.size() - suffix_length);
      const std::string pattern = "T" + prefix + "*" + suffix;
      std::vector<std::string> targets(1, pattern);
      if (!gpu.SetTronPatternsV2(targets) || !gpu.SetKeys(points.data())) {
        std::cerr << "setup failed pattern=" << pattern << '\n';
        return 1;
      }
      std::vector<ITEM> found;
      if (!gpu.Launch(found, true, false)) {
        std::cerr << "launch failed pattern=" << pattern << '\n';
        return 1;
      }
      bool verified = false;
      for (const ITEM& item : found) {
        const std::string address = secp.GetAddress(TRON_ADDR, item.mode, item.hash);
        if (item.targetId == 0 && address == expected_address && matches(pattern, address)) {
          verified = true;
          break;
        }
      }
      if (!verified) {
        std::cerr << "verification failed pattern=" << pattern
                  << " found=" << found.size() << '\n';
        return 1;
      }
      ++passed;
      std::cout << "PASS total=" << total
                << " prefix=" << prefix_length
                << " suffix=" << suffix_length
                << " pattern=" << pattern << '\n';
    }
  }

  for (const int target_count : {1, 4, 8, 16}) {
    std::vector<std::string> targets;
    std::vector<std::string> expected;
    for (int thread = 0; thread < gpu.GetNbThread(); ++thread) {
      Int thread_scalar;
      thread_scalar.SetInt32(10000 + thread);
      thread_scalar.Add(static_cast<uint64_t>(GRP_SIZE / 2));
      Point thread_point = secp.ComputePublicKey(&thread_scalar);
      points[thread] = thread_point;
      if (thread < target_count) {
        const std::string address = secp.GetTronAddress(thread_point);
        targets.push_back(address.substr(0, 9) + "*");
        expected.push_back(address);
      }
    }
    if (!gpu.SetTronPatternsV2(targets) || !gpu.SetKeys(points.data())) {
      std::cerr << "multi-target setup failed count=" << target_count << '\n';
      return 1;
    }
    std::vector<ITEM> found;
    if (!gpu.Launch(found, true, false)) {
      std::cerr << "multi-target launch failed count=" << target_count << '\n';
      return 1;
    }
    std::vector<bool> verified(target_count, false);
    for (const ITEM& item : found) {
      if (item.targetId >= verified.size()) continue;
      const std::string address = secp.GetAddress(TRON_ADDR, item.mode, item.hash);
      if (address == expected[item.targetId] &&
          matches(targets[item.targetId], address)) {
        verified[item.targetId] = true;
      }
    }
    for (bool value : verified) {
      if (!value) {
        std::cerr << "multi-target verification failed count=" << target_count
                  << " found=" << found.size() << '\n';
        return 1;
      }
    }
    std::cout << "PASS multi_target_count=" << target_count
              << " found=" << found.size() << '\n';
  }
  std::cout << "gpu_pattern_matrix passed=" << passed
            << " expected_address=" << expected_address << '\n';
  return passed == 24 ? 0 : 1;
}
