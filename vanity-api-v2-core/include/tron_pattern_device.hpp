#ifndef VANITY_API_V2_TRON_PATTERN_DEVICE_HPP
#define VANITY_API_V2_TRON_PATTERN_DEVICE_HPP

#include <cstdint>
#include <type_traits>

#if defined(__CUDACC__)
#define VANITY_V2_HD __host__ __device__ __forceinline__
#else
#define VANITY_V2_HD inline
#endif

namespace vanity_v2 {

constexpr std::uint32_t kDeviceMaxActiveTargets = 16;
constexpr std::uint32_t kMaxPackedTargetId = 8191;
constexpr std::uint64_t kBase58Power8 = 128063081718016ULL;
constexpr std::uint64_t kResidue58Power8Coefficients[25] = {
    32994552086272ULL, 112684327885312ULL, 51465307277824ULL,
    59230113085952ULL, 67264386966016ULL, 15270143900416ULL,
    18568766279168ULL, 121132166179840ULL, 10478100783360ULL,
    127603765386240ULL, 114554634363648ULL, 127009821519616ULL,
    121055517638912ULL, 15980511917568ULL, 37080658433792ULL,
    4647064038656ULL, 25530719654912ULL, 86142112402944ULL,
    25348813274624ULL, 1099511627776ULL, 4294967296ULL,
    16777216ULL, 65536ULL, 256ULL, 1ULL};

// Pointer-free layout copied directly into CUDA constant memory.
struct TronPatternDeviceDescriptor {
  std::uint64_t prefix_low[4];
  std::uint64_t prefix_high[4];
  std::uint64_t payload_low[3];
  std::uint64_t payload_high[3];
  std::uint64_t suffix_value;
  std::uint64_t suffix_modulus;
  std::uint32_t target_id;
  std::uint8_t prefix_length;
  std::uint8_t suffix_length;
  std::uint8_t total_custom_length;
  std::uint8_t flags;
};

static_assert(std::is_standard_layout<TronPatternDeviceDescriptor>::value, "descriptor ABI");
static_assert(std::is_trivially_copyable<TronPatternDeviceDescriptor>::value, "descriptor copy");
static_assert(sizeof(TronPatternDeviceDescriptor) == 136, "descriptor size");

VANITY_V2_HD std::uint64_t payload25_residue58p8_linear(
    const std::uint8_t payload[25]) {
  std::uint64_t sum = 0;
  for (int index = 0; index < 25; ++index) {
    sum += static_cast<std::uint64_t>(payload[index]) *
        kResidue58Power8Coefficients[index];
  }
  return sum % kBase58Power8;
}

VANITY_V2_HD int compare_words4(
    const std::uint64_t lhs[4],
    const std::uint64_t rhs[4]) {
  for (int index = 0; index < 4; ++index) {
    if (lhs[index] < rhs[index]) return -1;
    if (lhs[index] > rhs[index]) return 1;
  }
  return 0;
}

VANITY_V2_HD std::uint64_t append_be32_mod(
    std::uint64_t residue,
    std::uint32_t value,
    std::uint64_t modulus) {
  for (int shift = 24; shift >= 0; shift -= 8) {
    residue = (residue * 256ULL + ((value >> shift) & 0xffU)) % modulus;
  }
  return residue;
}

VANITY_V2_HD std::uint64_t digest_checksum_residue(
    std::uint32_t d0,
    std::uint32_t d1,
    std::uint32_t d2,
    std::uint32_t d3,
    std::uint32_t d4,
    std::uint32_t checksum,
    std::uint64_t modulus) {
  std::uint64_t residue = 0x41ULL % modulus;
  residue = append_be32_mod(residue, d0, modulus);
  residue = append_be32_mod(residue, d1, modulus);
  residue = append_be32_mod(residue, d2, modulus);
  residue = append_be32_mod(residue, d3, modulus);
  residue = append_be32_mod(residue, d4, modulus);
  return append_be32_mod(residue, checksum, modulus);
}

VANITY_V2_HD bool device_descriptor_matches(
    const TronPatternDeviceDescriptor& descriptor,
    std::uint32_t d0,
    std::uint32_t d1,
    std::uint32_t d2,
    std::uint32_t d3,
    std::uint32_t d4,
    std::uint32_t checksum) {
  if ((descriptor.flags & 1U) != 0U) {
    const std::uint64_t words[4] = {
        0x41ULL,
        (static_cast<std::uint64_t>(d0) << 32) | d1,
        (static_cast<std::uint64_t>(d2) << 32) | d3,
        (static_cast<std::uint64_t>(d4) << 32) | checksum,
    };
    if (compare_words4(words, descriptor.prefix_low) < 0 ||
        compare_words4(words, descriptor.prefix_high) > 0) {
      return false;
    }
  }
  return (descriptor.flags & 2U) == 0U ||
      digest_checksum_residue(d0, d1, d2, d3, d4, checksum,
                              descriptor.suffix_modulus) ==
          descriptor.suffix_value;
}

VANITY_V2_HD std::uint16_t pack_hit_metadata(
    std::uint16_t target_id,
    std::uint8_t endomorphism,
    bool mode) {
  return static_cast<std::uint16_t>(
      (mode ? 0x8000U : 0U) |
      ((static_cast<std::uint16_t>(target_id) & 0x1fffU) << 2) |
      (endomorphism & 0x03U));
}

VANITY_V2_HD std::uint16_t unpack_hit_target(std::uint16_t metadata) {
  return static_cast<std::uint16_t>((metadata >> 2) & 0x1fffU);
}

VANITY_V2_HD std::uint8_t unpack_hit_endomorphism(std::uint16_t metadata) {
  return static_cast<std::uint8_t>(metadata & 0x03U);
}

VANITY_V2_HD bool unpack_hit_mode(std::uint16_t metadata) {
  return (metadata & 0x8000U) != 0U;
}

}  // namespace vanity_v2

#undef VANITY_V2_HD

#endif
