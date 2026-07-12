#ifndef VANITY_API_V2_CORE_SECURITY_HPP
#define VANITY_API_V2_CORE_SECURITY_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>

namespace vanity_v2::security {

void secure_zero(void* pointer, std::size_t length) noexcept;
void disable_process_dumps();
void secure_random(void* output, std::size_t length);
std::string random_uuid_v4();

class AgeEncryptor {
 public:
  AgeEncryptor(std::string executable, std::string recipient);

  std::string encrypt_private_key(const std::array<std::uint8_t, 32>& private_key) const;

 private:
  std::string executable_;
  std::string recipient_;
};

}  // namespace vanity_v2::security

#endif
