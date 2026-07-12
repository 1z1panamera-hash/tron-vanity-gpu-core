#include "core_security.hpp"

#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstring>
#include <fcntl.h>
#include <poll.h>
#include <spawn.h>
#include <stdexcept>
#include <string_view>
#include <sys/resource.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#ifdef __linux__
#include <sys/prctl.h>
#include <sys/random.h>
#endif

extern char** environ;

namespace vanity_v2::security {
namespace {

constexpr std::size_t kMaximumCiphertext = 64U * 1024U;
constexpr auto kEncryptTimeout = std::chrono::seconds(5);

class FileDescriptor {
 public:
  explicit FileDescriptor(int value = -1) : value_(value) {}
  ~FileDescriptor() {
    if (value_ >= 0) close(value_);
  }
  FileDescriptor(const FileDescriptor&) = delete;
  FileDescriptor& operator=(const FileDescriptor&) = delete;
  FileDescriptor(FileDescriptor&& other) noexcept : value_(other.release()) {}
  FileDescriptor& operator=(FileDescriptor&& other) noexcept {
    if (this != &other) {
      if (value_ >= 0) close(value_);
      value_ = other.release();
    }
    return *this;
  }
  int get() const { return value_; }
  int release() {
    const int result = value_;
    value_ = -1;
    return result;
  }
  void reset(int value = -1) {
    if (value_ >= 0) close(value_);
    value_ = value;
  }

 private:
  int value_;
};

void set_cloexec(int descriptor) {
  const int flags = fcntl(descriptor, F_GETFD);
  if (flags < 0 || fcntl(descriptor, F_SETFD, flags | FD_CLOEXEC) < 0) {
    throw std::runtime_error("failed to secure an encryption pipe");
  }
}

std::array<FileDescriptor, 2> make_pipe() {
  int descriptors[2];
  if (pipe(descriptors) != 0) throw std::runtime_error("failed to create an encryption pipe");
  FileDescriptor read_end(descriptors[0]);
  FileDescriptor write_end(descriptors[1]);
  set_cloexec(read_end.get());
  set_cloexec(write_end.get());
  return {std::move(read_end), std::move(write_end)};
}

void write_all(int descriptor, const void* data, std::size_t length) {
  const auto* cursor = static_cast<const std::uint8_t*>(data);
  while (length != 0) {
    const ssize_t written = write(descriptor, cursor, length);
    if (written < 0 && errno == EINTR) continue;
    if (written <= 0) throw std::runtime_error("failed to write private key to age");
    cursor += written;
    length -= static_cast<std::size_t>(written);
  }
}

bool valid_recipient(const std::string& recipient) {
  static constexpr std::string_view alphabet = "023456789acdefghjklmnpqrstuvwxyz";
  if (recipient.size() != 62 || recipient.rfind("age1", 0) != 0) return false;
  for (char value : recipient.substr(4)) {
    if (alphabet.find(value) == std::string_view::npos) return false;
  }
  return true;
}

void validate_executable(const std::string& executable) {
  if (executable.empty() || executable.front() != '/') {
    throw std::invalid_argument("age executable must be an absolute path");
  }
  struct stat status {};
  if (stat(executable.c_str(), &status) != 0 || !S_ISREG(status.st_mode) ||
      access(executable.c_str(), X_OK) != 0) {
    throw std::invalid_argument("age executable is unavailable or not executable");
  }
}

class LockedHexPrivateKey {
 public:
  explicit LockedHexPrivateKey(const std::array<std::uint8_t, 32>& private_key)
      : bytes_{} {
    static constexpr char digits[] = "0123456789abcdef";
    for (std::size_t index = 0; index < private_key.size(); ++index) {
      bytes_[index * 2] = digits[private_key[index] >> 4];
      bytes_[index * 2 + 1] = digits[private_key[index] & 0x0fU];
    }
    if (mlock(bytes_.data(), bytes_.size()) != 0) {
      secure_zero(bytes_.data(), bytes_.size());
      throw std::runtime_error("failed to lock private-key memory");
    }
    locked_ = true;
  }

  ~LockedHexPrivateKey() {
    secure_zero(bytes_.data(), bytes_.size());
    if (locked_) munlock(bytes_.data(), bytes_.size());
  }

  LockedHexPrivateKey(const LockedHexPrivateKey&) = delete;
  LockedHexPrivateKey& operator=(const LockedHexPrivateKey&) = delete;
  const char* data() const { return bytes_.data(); }
  std::size_t size() const { return bytes_.size(); }

 private:
  std::array<char, 64> bytes_{};
  bool locked_{false};
};

void terminate_child(pid_t child) noexcept {
  if (child <= 0) return;
  kill(child, SIGKILL);
  int status = 0;
  while (waitpid(child, &status, 0) < 0 && errno == EINTR) {
  }
}

}  // namespace

void secure_zero(void* pointer, std::size_t length) noexcept {
  volatile auto* bytes = static_cast<volatile std::uint8_t*>(pointer);
  while (length-- != 0) *bytes++ = 0;
}

void disable_process_dumps() {
  struct rlimit limit {};
  limit.rlim_cur = 0;
  limit.rlim_max = 0;
  if (setrlimit(RLIMIT_CORE, &limit) != 0) {
    throw std::runtime_error("failed to disable core dumps");
  }
#ifdef __linux__
  if (prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0) {
    throw std::runtime_error("failed to mark worker as non-dumpable");
  }
#endif
}

void secure_random(void* output, std::size_t length) {
  auto* cursor = static_cast<std::uint8_t*>(output);
#ifdef __linux__
  while (length != 0) {
    const ssize_t received = getrandom(cursor, length, 0);
    if (received < 0 && errno == EINTR) continue;
    if (received < 0) break;
    cursor += received;
    length -= static_cast<std::size_t>(received);
  }
  if (length == 0) return;
#endif
  FileDescriptor random(open("/dev/urandom", O_RDONLY | O_CLOEXEC));
  if (random.get() < 0) throw std::runtime_error("secure random source is unavailable");
  while (length != 0) {
    const ssize_t received = read(random.get(), cursor, length);
    if (received < 0 && errno == EINTR) continue;
    if (received <= 0) throw std::runtime_error("secure random source failed");
    cursor += received;
    length -= static_cast<std::size_t>(received);
  }
}

std::string random_uuid_v4() {
  std::array<std::uint8_t, 16> bytes{};
  secure_random(bytes.data(), bytes.size());
  bytes[6] = static_cast<std::uint8_t>((bytes[6] & 0x0fU) | 0x40U);
  bytes[8] = static_cast<std::uint8_t>((bytes[8] & 0x3fU) | 0x80U);
  static constexpr char digits[] = "0123456789abcdef";
  char output[37]{};
  std::size_t position = 0;
  for (std::size_t index = 0; index < bytes.size(); ++index) {
    if (index == 4 || index == 6 || index == 8 || index == 10) output[position++] = '-';
    output[position++] = digits[bytes[index] >> 4];
    output[position++] = digits[bytes[index] & 0x0fU];
  }
  std::string result(output, 36);
  secure_zero(output, sizeof(output));
  secure_zero(bytes.data(), bytes.size());
  return result;
}

AgeEncryptor::AgeEncryptor(std::string executable, std::string recipient)
    : executable_(std::move(executable)), recipient_(std::move(recipient)) {
  validate_executable(executable_);
  if (!valid_recipient(recipient_)) throw std::invalid_argument("invalid Age X25519 recipient");
}

std::string AgeEncryptor::encrypt_private_key(
    const std::array<std::uint8_t, 32>& private_key) const {
  LockedHexPrivateKey plaintext(private_key);

  auto input = make_pipe();
  auto output = make_pipe();
  FileDescriptor null_error(open("/dev/null", O_WRONLY | O_CLOEXEC));
  if (null_error.get() < 0) {
    throw std::runtime_error("failed to open the age error sink");
  }

  posix_spawn_file_actions_t actions;
  if (posix_spawn_file_actions_init(&actions) != 0) {
    throw std::runtime_error("failed to initialize age process actions");
  }
  posix_spawn_file_actions_adddup2(&actions, input[0].get(), STDIN_FILENO);
  posix_spawn_file_actions_adddup2(&actions, output[1].get(), STDOUT_FILENO);
  posix_spawn_file_actions_adddup2(&actions, null_error.get(), STDERR_FILENO);
  posix_spawn_file_actions_addclose(&actions, input[1].get());
  posix_spawn_file_actions_addclose(&actions, output[0].get());

  char* arguments[] = {
      const_cast<char*>(executable_.c_str()),
      const_cast<char*>("-a"),
      const_cast<char*>("-r"),
      const_cast<char*>(recipient_.c_str()),
      nullptr,
  };
  char path_environment[] = "PATH=/usr/bin:/bin";
  char language_environment[] = "LANG=C";
  char* environment[] = {path_environment, language_environment, nullptr};
  pid_t child = -1;
  const int spawn_status =
      posix_spawn(&child, executable_.c_str(), &actions, nullptr, arguments, environment);
  posix_spawn_file_actions_destroy(&actions);
  if (spawn_status != 0) {
    throw std::runtime_error("failed to start age encryption");
  }

  input[0].reset();
  output[1].reset();
  try {
    write_all(input[1].get(), plaintext.data(), plaintext.size());
  } catch (...) {
    terminate_child(child);
    throw;
  }
  input[1].reset();

  std::string ciphertext;
  ciphertext.reserve(2048);
  const auto deadline = std::chrono::steady_clock::now() + kEncryptTimeout;
  bool reached_eof = false;
  while (!reached_eof) {
    const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(
        deadline - std::chrono::steady_clock::now());
    if (remaining.count() <= 0) {
      terminate_child(child);
      throw std::runtime_error("age encryption timed out");
    }
    struct pollfd descriptor {output[0].get(), POLLIN | POLLHUP, 0};
    const int ready = poll(&descriptor, 1, static_cast<int>(remaining.count()));
    if (ready < 0 && errno == EINTR) continue;
    if (ready <= 0) {
      terminate_child(child);
      throw std::runtime_error("age encryption timed out");
    }
    char buffer[4096];
    const ssize_t received = read(output[0].get(), buffer, sizeof(buffer));
    if (received < 0 && errno == EINTR) continue;
    if (received < 0) {
      secure_zero(buffer, sizeof(buffer));
      terminate_child(child);
      throw std::runtime_error("failed to read age ciphertext");
    }
    if (received == 0) {
      reached_eof = true;
    } else {
      if (ciphertext.size() + static_cast<std::size_t>(received) > kMaximumCiphertext) {
        secure_zero(buffer, sizeof(buffer));
        terminate_child(child);
        throw std::runtime_error("age ciphertext exceeds the size limit");
      }
      ciphertext.append(buffer, static_cast<std::size_t>(received));
    }
    secure_zero(buffer, sizeof(buffer));
  }

  int child_status = 0;
  while (waitpid(child, &child_status, 0) < 0) {
    if (errno != EINTR) {
      throw std::runtime_error("failed to collect age encryption status");
    }
  }
  const bool plaintext_leaked =
      ciphertext.find(plaintext.data(), 0, plaintext.size()) != std::string::npos;

  if (!WIFEXITED(child_status) || WEXITSTATUS(child_status) != 0) {
    throw std::runtime_error("age encryption failed");
  }
  if (ciphertext.rfind("-----BEGIN AGE ENCRYPTED FILE-----", 0) != 0 ||
      ciphertext.find("-----END AGE ENCRYPTED FILE-----") == std::string::npos) {
    throw std::runtime_error("age returned a non-armored result");
  }
  if (plaintext_leaked) {
    throw std::runtime_error("age output unexpectedly contains plaintext private key data");
  }
  return ciphertext;
}

}  // namespace vanity_v2::security
