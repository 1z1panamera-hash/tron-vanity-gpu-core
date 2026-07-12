#include "tron_pattern.hpp"

#include <array>
#include <cstdint>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using vanity_v2::ParsedPattern;
using vanity_v2::kBase58Alphabet;
using vanity_v2::kPayload25Size;
using vanity_v2::kTronAddressLength;

void require(bool condition, const std::string& message) {
  if (!condition) throw std::runtime_error(message);
}

std::string encode_base58_25(std::array<std::uint8_t, kPayload25Size> payload) {
  std::string reversed;
  while (true) {
    std::uint32_t remainder = 0;
    bool nonzero = false;
    for (std::uint8_t& byte : payload) {
      const std::uint32_t value = (remainder << 8) | byte;
      byte = static_cast<std::uint8_t>(value / 58U);
      remainder = value % 58U;
      nonzero = nonzero || byte != 0;
    }
    reversed.push_back(kBase58Alphabet[remainder]);
    if (!nonzero) break;
  }
  return std::string(reversed.rbegin(), reversed.rend());
}

std::array<std::uint8_t, kPayload25Size> random_tron_payload(std::mt19937_64* random) {
  std::array<std::uint8_t, kPayload25Size> payload{};
  payload[0] = 0x41;
  for (std::size_t index = 1; index < payload.size(); ++index) {
    payload[index] = static_cast<std::uint8_t>((*random)() & 0xffU);
  }
  return payload;
}

std::vector<ParsedPattern> all_split_patterns(const std::string& address) {
  std::vector<ParsedPattern> patterns;
  std::uint32_t target_id = 0;
  for (std::size_t total = 6; total <= 8; ++total) {
    for (std::size_t prefix_length = 0; prefix_length <= total; ++prefix_length) {
      const std::size_t suffix_length = total - prefix_length;
      const std::string prefix = address.substr(1, prefix_length);
      const std::string suffix = address.substr(address.size() - suffix_length, suffix_length);
      patterns.push_back(vanity_v2::parse_pattern("T" + prefix + "*" + suffix, target_id++));
    }
  }
  return patterns;
}

void test_all_24_splits_match() {
  std::mt19937_64 random(0x5090U);
  for (int sample = 0; sample < 200; ++sample) {
    const auto payload = random_tron_payload(&random);
    const std::string address = encode_base58_25(payload);
    require(address.size() == kTronAddressLength, "TRON payload did not encode to 34 characters");
    require(address.front() == 'T', "TRON payload did not encode with T prefix");
    const auto patterns = all_split_patterns(address);
    require(patterns.size() == 24, "expected exactly 24 length splits");
    for (const ParsedPattern& pattern : patterns) {
      require(vanity_v2::direct_pattern_match(pattern, address), "direct match rejected source address");
      require(
          vanity_v2::descriptor_matches_address(pattern.descriptor, address),
          "descriptor rejected source address for " + pattern.canonical);
    }
  }
}

void test_descriptor_equivalence_on_random_addresses() {
  std::mt19937_64 random(0x6000U);
  const auto source_payload = random_tron_payload(&random);
  const std::string source_address = encode_base58_25(source_payload);
  const auto patterns = all_split_patterns(source_address);
  for (int sample = 0; sample < 5000; ++sample) {
    const auto payload = random_tron_payload(&random);
    const std::string address = encode_base58_25(payload);
    for (const ParsedPattern& pattern : patterns) {
      const bool direct = vanity_v2::direct_pattern_match(pattern, address);
      const bool compiled = vanity_v2::descriptor_matches_address(pattern.descriptor, address);
      require(direct == compiled, "descriptor mismatch for " + pattern.canonical);

      std::array<std::uint8_t, kPayload25Size> decoded{};
      require(vanity_v2::decode_base58_25(address, &decoded), "cannot decode test address");
      const auto device = vanity_v2::make_device_descriptor(pattern.descriptor);
      const auto be32 = [&decoded](std::size_t offset) {
        return (static_cast<std::uint32_t>(decoded[offset]) << 24) |
            (static_cast<std::uint32_t>(decoded[offset + 1]) << 16) |
            (static_cast<std::uint32_t>(decoded[offset + 2]) << 8) |
            static_cast<std::uint32_t>(decoded[offset + 3]);
      };
      const bool device_match = vanity_v2::device_descriptor_matches(
          device, be32(1), be32(5), be32(9), be32(13), be32(17), be32(21));
      require(direct == device_match, "device descriptor mismatch for " + pattern.canonical);
    }
  }
}

void test_hit_metadata() {
  for (std::uint16_t target = 0; target < vanity_v2::kDeviceMaxActiveTargets; ++target) {
    for (std::uint8_t endomorphism = 0; endomorphism < 3; ++endomorphism) {
      for (bool mode : {false, true}) {
        const std::uint16_t packed =
            vanity_v2::pack_hit_metadata(target, endomorphism, mode);
        require(vanity_v2::unpack_hit_target(packed) == target, "target metadata mismatch");
        require(
            vanity_v2::unpack_hit_endomorphism(packed) == endomorphism,
            "endomorphism metadata mismatch");
        require(vanity_v2::unpack_hit_mode(packed) == mode, "mode metadata mismatch");
      }
    }
  }
}

void test_invalid_patterns() {
  const std::vector<std::string> invalid = {
      "ABCDEF*",
      "TABCDEF",
      "T**ABCDEF",
      "T*ABCDE",
      "T*ABCDEFGHI",
      "T0*ABCDE",
      "TO*ABCDE",
      "TI*ABCDE",
      "Tl*ABCDE",
      "Ta*ABCDE",
  };
  for (const std::string& pattern : invalid) {
    bool rejected = false;
    try {
      (void)vanity_v2::parse_pattern(pattern, 1);
    } catch (const std::invalid_argument&) {
      rejected = true;
    }
    require(rejected, "invalid pattern accepted: " + pattern);
  }
  bool target_rejected = false;
  try {
    (void)vanity_v2::parse_pattern("T*123456", vanity_v2::kMaxPackedTargetId + 1);
  } catch (const std::invalid_argument&) {
    target_rejected = true;
  }
  require(target_rejected, "oversized target id accepted");
}

void test_suffix_powers() {
  require(vanity_v2::base58_power(5) == 656356768ULL, "58^5 mismatch");
  require(vanity_v2::base58_power(6) == 38068692544ULL, "58^6 mismatch");
  require(vanity_v2::base58_power(7) == 2207984167552ULL, "58^7 mismatch");
  require(vanity_v2::base58_power(8) == 128063081718016ULL, "58^8 mismatch");
}

void test_linear_residue() {
  std::mt19937_64 random(0x58U);
  for (int sample = 0; sample < 10000; ++sample) {
    const auto payload = random_tron_payload(&random);
    const std::uint64_t expected =
        vanity_v2::payload_suffix_residue(payload, vanity_v2::kBase58Power8);
    const std::uint64_t actual = vanity_v2::payload25_residue58p8_linear(payload.data());
    require(actual == expected, "linear 58^8 residue mismatch");
  }
}

}  // namespace

int main() {
  try {
    test_all_24_splits_match();
    test_descriptor_equivalence_on_random_addresses();
    test_invalid_patterns();
    test_suffix_powers();
    test_linear_residue();
    test_hit_metadata();
  } catch (const std::exception& error) {
    std::cerr << "test failure: " << error.what() << '\n';
    return 1;
  }
  std::cout << "all tron pattern tests passed\n";
  return 0;
}
