#include "tron_pattern.hpp"

#include <algorithm>
#include <cstring>
#include <limits>
#include <stdexcept>

namespace vanity_v2 {
namespace {

int base58_value(char value) {
  const char* found = std::strchr(kBase58Alphabet, value);
  return found == nullptr ? -1 : static_cast<int>(found - kBase58Alphabet);
}

bool big25_mul_small(
    std::array<std::uint8_t, kPayload25Size>* value,
    std::uint32_t multiplier) {
  std::uint32_t carry = 0;
  for (std::size_t offset = value->size(); offset > 0; --offset) {
    const std::size_t index = offset - 1;
    const std::uint32_t product =
        static_cast<std::uint32_t>((*value)[index]) * multiplier + carry;
    (*value)[index] = static_cast<std::uint8_t>(product & 0xffU);
    carry = product >> 8;
  }
  return carry == 0;
}

bool big25_add_small(
    std::array<std::uint8_t, kPayload25Size>* value,
    std::uint32_t addend) {
  std::uint32_t carry = addend;
  for (std::size_t offset = value->size(); offset > 0 && carry != 0; --offset) {
    const std::size_t index = offset - 1;
    const std::uint32_t sum =
        static_cast<std::uint32_t>((*value)[index]) + (carry & 0xffU);
    (*value)[index] = static_cast<std::uint8_t>(sum & 0xffU);
    carry = (carry >> 8) + (sum >> 8);
  }
  return carry == 0;
}

bool big25_sub_one(std::array<std::uint8_t, kPayload25Size>* value) {
  for (std::size_t offset = value->size(); offset > 0; --offset) {
    const std::size_t index = offset - 1;
    if ((*value)[index] != 0) {
      --(*value)[index];
      return true;
    }
    (*value)[index] = 0xffU;
  }
  return false;
}

std::uint64_t pack_be(
    const std::array<std::uint8_t, kPayload25Size>& payload,
    std::size_t offset,
    std::size_t length) {
  std::uint64_t result = 0;
  for (std::size_t index = 0; index < length; ++index) {
    result = (result << 8) | payload[offset + index];
  }
  return result;
}

int compare_words(
    const std::array<std::uint64_t, 4>& lhs,
    const std::array<std::uint64_t, 4>& rhs) {
  for (std::size_t index = 0; index < lhs.size(); ++index) {
    if (lhs[index] < rhs[index]) return -1;
    if (lhs[index] > rhs[index]) return 1;
  }
  return 0;
}

void make_prefix_range(
    const std::string& full_prefix,
    std::array<std::uint8_t, kPayload25Size>* low,
    std::array<std::uint8_t, kPayload25Size>* high) {
  low->fill(0);
  for (char value : full_prefix) {
    const int digit = base58_value(value);
    if (digit < 0 || !big25_mul_small(low, 58U) ||
        !big25_add_small(low, static_cast<std::uint32_t>(digit))) {
      throw std::invalid_argument("prefix cannot be represented as a TRON address range");
    }
  }

  *high = *low;
  if (!big25_add_small(high, 1U)) {
    throw std::invalid_argument("prefix range upper bound overflow");
  }
  for (std::size_t index = full_prefix.size(); index < kTronAddressLength; ++index) {
    if (!big25_mul_small(low, 58U) || !big25_mul_small(high, 58U)) {
      throw std::invalid_argument("prefix range exceeds 25-byte address space");
    }
  }
  if (!big25_sub_one(high)) {
    throw std::invalid_argument("invalid empty prefix range");
  }
}

bool prefix_range_intersects_tron(
    const std::array<std::uint8_t, kPayload25Size>& low,
    const std::array<std::uint8_t, kPayload25Size>& high) {
  std::array<std::uint8_t, kPayload25Size> tron_low{};
  std::array<std::uint8_t, kPayload25Size> tron_high{};
  tron_low[0] = 0x41;
  tron_high.fill(0xffU);
  tron_high[0] = 0x41;
  return compare_words(pack_payload25(high), pack_payload25(tron_low)) >= 0 &&
      compare_words(pack_payload25(low), pack_payload25(tron_high)) <= 0;
}

}  // namespace

bool is_base58_char(char value) { return base58_value(value) >= 0; }

std::uint64_t base58_power(std::size_t exponent) {
  if (exponent > kMaxCustomLength) {
    throw std::invalid_argument("Base58 exponent exceeds V2 limit");
  }
  std::uint64_t value = 1;
  for (std::size_t index = 0; index < exponent; ++index) value *= 58U;
  return value;
}

ParsedPattern parse_pattern(const std::string& pattern, std::uint32_t target_id) {
  if (target_id > kMaxPackedTargetId) {
    throw std::invalid_argument("target id exceeds packed hit metadata");
  }
  if (pattern.empty() || pattern.front() != 'T') {
    throw std::invalid_argument("pattern must start with T");
  }
  const std::size_t wildcard = pattern.find('*');
  if (wildcard == std::string::npos || pattern.find('*', wildcard + 1) != std::string::npos) {
    throw std::invalid_argument("pattern must contain exactly one wildcard");
  }

  ParsedPattern parsed;
  parsed.canonical = pattern;
  parsed.prefix = pattern.substr(1, wildcard - 1);
  parsed.suffix = pattern.substr(wildcard + 1);
  const std::size_t total = parsed.prefix.size() + parsed.suffix.size();
  if (total < 6 || total > 8) {
    throw std::invalid_argument("custom prefix and suffix length must total 6, 7, or 8");
  }
  if (!std::all_of(parsed.prefix.begin(), parsed.prefix.end(), is_base58_char) ||
      !std::all_of(parsed.suffix.begin(), parsed.suffix.end(), is_base58_char)) {
    throw std::invalid_argument("pattern contains a non-Base58 character");
  }

  TronPatternDescriptor& descriptor = parsed.descriptor;
  descriptor.target_id = target_id;
  descriptor.prefix_length = static_cast<std::uint8_t>(parsed.prefix.size());
  descriptor.suffix_length = static_cast<std::uint8_t>(parsed.suffix.size());
  descriptor.total_custom_length = static_cast<std::uint8_t>(total);

  if (!parsed.prefix.empty()) {
    descriptor.flags |= kHasPrefix;
    std::array<std::uint8_t, kPayload25Size> low{};
    std::array<std::uint8_t, kPayload25Size> high{};
    make_prefix_range("T" + parsed.prefix, &low, &high);
    if (!prefix_range_intersects_tron(low, high)) {
      throw std::invalid_argument("prefix cannot occur in a TRON address");
    }
    descriptor.prefix_low = pack_payload25(low);
    descriptor.prefix_high = pack_payload25(high);
    descriptor.payload_low = pack_payload21(low);
    descriptor.payload_high = pack_payload21(high);
  }

  if (!parsed.suffix.empty()) {
    descriptor.flags |= kHasSuffix;
    descriptor.suffix_modulus = base58_power(parsed.suffix.size());
    descriptor.suffix_value = 0;
    for (char value : parsed.suffix) {
      descriptor.suffix_value =
          descriptor.suffix_value * 58U + static_cast<std::uint64_t>(base58_value(value));
    }
  }

  return parsed;
}

TronPatternDeviceDescriptor make_device_descriptor(
    const TronPatternDescriptor& descriptor) {
  TronPatternDeviceDescriptor device{};
  std::copy(descriptor.prefix_low.begin(), descriptor.prefix_low.end(), device.prefix_low);
  std::copy(descriptor.prefix_high.begin(), descriptor.prefix_high.end(), device.prefix_high);
  std::copy(descriptor.payload_low.begin(), descriptor.payload_low.end(), device.payload_low);
  std::copy(descriptor.payload_high.begin(), descriptor.payload_high.end(), device.payload_high);
  device.suffix_value = descriptor.suffix_value;
  device.suffix_modulus = descriptor.suffix_modulus;
  device.target_id = descriptor.target_id;
  device.prefix_length = descriptor.prefix_length;
  device.suffix_length = descriptor.suffix_length;
  device.total_custom_length = descriptor.total_custom_length;
  device.flags = descriptor.flags;
  return device;
}

bool decode_base58_25(
    const std::string& address,
    std::array<std::uint8_t, kPayload25Size>* payload) {
  if (payload == nullptr || address.size() != kTronAddressLength) return false;
  payload->fill(0);
  for (char value : address) {
    const int digit = base58_value(value);
    if (digit < 0 || !big25_mul_small(payload, 58U) ||
        !big25_add_small(payload, static_cast<std::uint32_t>(digit))) {
      return false;
    }
  }
  return true;
}

std::array<std::uint64_t, 4> pack_payload25(
    const std::array<std::uint8_t, kPayload25Size>& payload) {
  return {
      static_cast<std::uint64_t>(payload[0]),
      pack_be(payload, 1, 8),
      pack_be(payload, 9, 8),
      pack_be(payload, 17, 8),
  };
}

std::array<std::uint64_t, 3> pack_payload21(
    const std::array<std::uint8_t, kPayload25Size>& payload) {
  return {
      pack_be(payload, 0, 8),
      pack_be(payload, 8, 8),
      pack_be(payload, 16, 5) << 24,
  };
}

std::uint64_t payload_suffix_residue(
    const std::array<std::uint8_t, kPayload25Size>& payload,
    std::uint64_t modulus) {
  if (modulus == 0) throw std::invalid_argument("suffix modulus cannot be zero");
  std::uint64_t residue = 0;
  for (std::uint8_t value : payload) {
    residue = (residue * 256U + value) % modulus;
  }
  return residue;
}

bool descriptor_matches_payload(
    const TronPatternDescriptor& descriptor,
    const std::array<std::uint8_t, kPayload25Size>& payload) {
  if ((descriptor.flags & kHasPrefix) != 0) {
    const auto words = pack_payload25(payload);
    if (compare_words(words, descriptor.prefix_low) < 0 ||
        compare_words(words, descriptor.prefix_high) > 0) {
      return false;
    }
  }
  if ((descriptor.flags & kHasSuffix) != 0 &&
      payload_suffix_residue(payload, descriptor.suffix_modulus) !=
          descriptor.suffix_value) {
    return false;
  }
  return true;
}

bool descriptor_matches_address(
    const TronPatternDescriptor& descriptor,
    const std::string& address) {
  std::array<std::uint8_t, kPayload25Size> payload{};
  return decode_base58_25(address, &payload) && descriptor_matches_payload(descriptor, payload);
}

bool direct_pattern_match(const ParsedPattern& pattern, const std::string& address) {
  if (address.size() != kTronAddressLength || address.front() != 'T') return false;
  if (!pattern.prefix.empty() && address.compare(1, pattern.prefix.size(), pattern.prefix) != 0) {
    return false;
  }
  if (!pattern.suffix.empty() &&
      address.compare(address.size() - pattern.suffix.size(), pattern.suffix.size(), pattern.suffix) != 0) {
    return false;
  }
  return true;
}

}  // namespace vanity_v2
