#ifndef VANITY_API_V2_TRON_PATTERN_HPP
#define VANITY_API_V2_TRON_PATTERN_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>

#include "tron_pattern_device.hpp"

namespace vanity_v2 {

constexpr char kBase58Alphabet[] =
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
constexpr std::size_t kTronAddressLength = 34;
constexpr std::size_t kPayload25Size = 25;
constexpr std::size_t kMaxCustomLength = 8;
constexpr std::size_t kMaxActiveTargets = 16;

enum PatternFlags : std::uint8_t {
  kHasPrefix = 1U << 0,
  kHasSuffix = 1U << 1,
};

// The layout intentionally uses fixed-width fields so a matching CUDA struct
// can be copied to constant memory without pointers or dynamic allocation.
struct TronPatternDescriptor {
  std::array<std::uint64_t, 4> prefix_low{};
  std::array<std::uint64_t, 4> prefix_high{};
  std::array<std::uint64_t, 3> payload_low{};
  std::array<std::uint64_t, 3> payload_high{};
  std::uint64_t suffix_value{0};
  std::uint64_t suffix_modulus{1};
  std::uint32_t target_id{0};
  std::uint8_t prefix_length{0};
  std::uint8_t suffix_length{0};
  std::uint8_t total_custom_length{0};
  std::uint8_t flags{0};
};

struct ParsedPattern {
  std::string canonical;
  std::string prefix;
  std::string suffix;
  TronPatternDescriptor descriptor;
};

bool is_base58_char(char value);
std::uint64_t base58_power(std::size_t exponent);

ParsedPattern parse_pattern(const std::string& pattern, std::uint32_t target_id);

TronPatternDeviceDescriptor make_device_descriptor(
    const TronPatternDescriptor& descriptor);

bool decode_base58_25(
    const std::string& address,
    std::array<std::uint8_t, kPayload25Size>* payload);

std::array<std::uint64_t, 4> pack_payload25(
    const std::array<std::uint8_t, kPayload25Size>& payload);

std::array<std::uint64_t, 3> pack_payload21(
    const std::array<std::uint8_t, kPayload25Size>& payload);

std::uint64_t payload_suffix_residue(
    const std::array<std::uint8_t, kPayload25Size>& payload,
    std::uint64_t modulus);

bool descriptor_matches_payload(
    const TronPatternDescriptor& descriptor,
    const std::array<std::uint8_t, kPayload25Size>& payload);

bool descriptor_matches_address(
    const TronPatternDescriptor& descriptor,
    const std::string& address);

bool direct_pattern_match(const ParsedPattern& pattern, const std::string& address);

}  // namespace vanity_v2

#endif
