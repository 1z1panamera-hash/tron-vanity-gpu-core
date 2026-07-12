#include "core_security.hpp"

#include <array>
#include <cassert>
#include <cstdint>
#include <fstream>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

namespace {

template <typename Function>
void expect_error(Function function) {
  bool threw = false;
  try {
    function();
  } catch (const std::exception&) {
    threw = true;
  }
  assert(threw);
}

std::string make_fake_age(const std::string& body) {
  std::string path = "/tmp/vanity18035-fake-age-" + vanity_v2::security::random_uuid_v4();
  std::ofstream script(path);
  script << "#!/bin/sh\n"
         << "test \"$1\" = '-a' || exit 21\n"
         << "test \"$2\" = '-r' || exit 22\n"
         << "test \"${#3}\" = '62' || exit 23\n"
         << "IFS= read -r secret\n"
         << "test \"${#secret}\" = '64' || exit 24\n"
         << body;
  script.close();
  chmod(path.c_str(), 0700);
  return path;
}

}  // namespace

int main() {
  const std::string first_uuid = vanity_v2::security::random_uuid_v4();
  const std::string second_uuid = vanity_v2::security::random_uuid_v4();
  assert(first_uuid.size() == 36);
  assert(first_uuid != second_uuid);
  assert(first_uuid[14] == '4');

  const std::string recipient = "age1" + std::string(58, 'q');
  assert(recipient.size() == 62);
  std::array<std::uint8_t, 32> private_key{};
  for (std::size_t index = 0; index < private_key.size(); ++index) {
    private_key[index] = static_cast<std::uint8_t>(index + 1);
  }

  const std::string valid_script = make_fake_age(
      "printf '%s\\n' '-----BEGIN AGE ENCRYPTED FILE-----' 'test' "
      "'-----END AGE ENCRYPTED FILE-----'\n");
  vanity_v2::security::AgeEncryptor encryptor(valid_script, recipient);
  const std::string ciphertext = encryptor.encrypt_private_key(private_key);
  assert(ciphertext.rfind("-----BEGIN AGE ENCRYPTED FILE-----", 0) == 0);
  unlink(valid_script.c_str());

  const std::string invalid_script = make_fake_age("printf 'plaintext-output\\n'\n");
  vanity_v2::security::AgeEncryptor invalid_encryptor(invalid_script, recipient);
  expect_error([&] { invalid_encryptor.encrypt_private_key(private_key); });
  unlink(invalid_script.c_str());

  expect_error([&] { vanity_v2::security::AgeEncryptor("relative-age", recipient); });
  expect_error([&] { vanity_v2::security::AgeEncryptor("/bin/cat", "bad-recipient"); });

  vanity_v2::security::secure_zero(private_key.data(), private_key.size());
  for (std::uint8_t value : private_key) assert(value == 0);
  return 0;
}
