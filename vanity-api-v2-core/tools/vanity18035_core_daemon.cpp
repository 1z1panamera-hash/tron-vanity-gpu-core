#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <deque>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <vector>

#ifdef __linux__
#include <sys/prctl.h>
#endif

#include "GPU/GPUEngine.h"
#include "SECP256k1.h"
#include "core_security.hpp"
#include "tron_pattern.hpp"
#include "worker_protocol.hpp"
#include "worker_outbox.hpp"

namespace {

using vanity_v2::security::AgeEncryptor;
using vanity_v2::worker::Hit;
using vanity_v2::worker::HitAck;
using vanity_v2::worker::MessageType;
using vanity_v2::worker::Progress;
using vanity_v2::worker::Snapshot;
using vanity_v2::worker::Task;

constexpr std::size_t kMaximumInputBuffer = 256U * 1024U;
constexpr std::chrono::seconds kHitResendInterval(1);
std::atomic<bool> stop_requested{false};

void handle_signal(int) { stop_requested.store(true); }

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
    if (this != &other) reset(other.release());
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

struct Options {
  std::string socket_path;
  std::string age_executable{"/usr/bin/age"};
  std::string age_recipient_file;
  std::string worker_database;
  int gpu_id{0};
  int grid_x{160};
  int grid_y{128};
};

int parse_positive(const char* text, const char* name) {
  char* end = nullptr;
  errno = 0;
  const long value = std::strtol(text, &end, 10);
  if (errno != 0 || end == text || *end != '\0' || value < 0 || value > 65535) {
    throw std::invalid_argument(std::string("invalid ") + name);
  }
  return static_cast<int>(value);
}

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string argument(argv[index]);
    auto value = [&](const char* name) -> const char* {
      if (index + 1 >= argc) throw std::invalid_argument(std::string("missing ") + name);
      return argv[++index];
    };
    if (argument == "--socket") {
      options.socket_path = value("socket path");
    } else if (argument == "--age-bin") {
      options.age_executable = value("age executable");
    } else if (argument == "--age-recipient-file") {
      options.age_recipient_file = value("Age recipient file");
    } else if (argument == "--worker-db") {
      options.worker_database = value("worker database");
    } else if (argument == "--gpu") {
      options.gpu_id = parse_positive(value("GPU id"), "GPU id");
    } else if (argument == "--grid-x") {
      options.grid_x = parse_positive(value("grid x"), "grid x");
    } else if (argument == "--grid-y") {
      options.grid_y = parse_positive(value("grid y"), "grid y");
    } else {
      throw std::invalid_argument("unknown command-line option");
    }
  }
  if (options.socket_path.empty() || options.socket_path.front() != '/') {
    throw std::invalid_argument("--socket must be an absolute path");
  }
  if (options.age_recipient_file.empty() || options.age_recipient_file.front() != '/') {
    throw std::invalid_argument("--age-recipient-file must be an absolute path");
  }
  if (options.worker_database.empty() || options.worker_database.front() != '/') {
    throw std::invalid_argument("--worker-db must be an absolute path");
  }
  if (options.grid_x <= 0 || options.grid_y <= 0) {
    throw std::invalid_argument("GPU grid dimensions must be positive");
  }
  return options;
}

std::string parent_directory(const std::string& path) {
  const std::size_t slash = path.rfind('/');
  return slash == 0 ? "/" : path.substr(0, slash);
}

void require_private_directory(const std::string& path) {
  struct stat status {};
  if (stat(path.c_str(), &status) != 0 || !S_ISDIR(status.st_mode) ||
      status.st_uid != geteuid() || (status.st_mode & 0077) != 0) {
    throw std::runtime_error("core socket directory must be owned by the worker and mode 0700");
  }
}

std::string read_recipient_file(const std::string& path) {
  struct stat status {};
  if (stat(path.c_str(), &status) != 0 || !S_ISREG(status.st_mode) ||
      status.st_uid != geteuid() || (status.st_mode & 0077) != 0) {
    throw std::runtime_error("Age recipient file must be owned by the worker and mode 0600");
  }
  std::ifstream input(path);
  std::string recipient;
  std::getline(input, recipient);
  std::string extra;
  if (!input || recipient.empty() || recipient.size() > 128 || std::getline(input, extra)) {
    throw std::runtime_error("Age recipient file must contain exactly one recipient line");
  }
  return recipient;
}

void set_nonblocking(int descriptor) {
  const int flags = fcntl(descriptor, F_GETFL);
  if (flags < 0 || fcntl(descriptor, F_SETFL, flags | O_NONBLOCK) < 0) {
    throw std::runtime_error("failed to set a socket nonblocking");
  }
  const int descriptor_flags = fcntl(descriptor, F_GETFD);
  if (descriptor_flags < 0 ||
      fcntl(descriptor, F_SETFD, descriptor_flags | FD_CLOEXEC) < 0) {
    throw std::runtime_error("failed to set close-on-exec on a socket");
  }
}

std::vector<std::uint8_t> frame_payload(const std::vector<std::uint8_t>& payload) {
  if (payload.empty() || payload.size() > vanity_v2::worker::kMaxFrameSize) {
    throw std::invalid_argument("invalid core protocol payload size");
  }
  const std::uint32_t size = static_cast<std::uint32_t>(payload.size());
  std::vector<std::uint8_t> frame;
  frame.reserve(payload.size() + 4);
  frame.push_back(static_cast<std::uint8_t>(size >> 24));
  frame.push_back(static_cast<std::uint8_t>(size >> 16));
  frame.push_back(static_cast<std::uint8_t>(size >> 8));
  frame.push_back(static_cast<std::uint8_t>(size));
  frame.insert(frame.end(), payload.begin(), payload.end());
  return frame;
}

struct PersistentHit {
  std::vector<std::uint8_t> frame;
  std::chrono::steady_clock::time_point last_sent{};
  bool queued{false};
};

struct OutgoingFrame {
  std::string result_id;
  std::vector<std::uint8_t> frame;
  std::size_t offset{0};
  bool persistent{false};
};

class CoreSocketServer {
 public:
  explicit CoreSocketServer(std::string socket_path) : socket_path_(std::move(socket_path)) {
    require_private_directory(parent_directory(socket_path_));
    struct stat old_status {};
    if (lstat(socket_path_.c_str(), &old_status) == 0) {
      if (!S_ISSOCK(old_status.st_mode) || old_status.st_uid != geteuid()) {
        throw std::runtime_error("refusing to replace an unsafe core socket path");
      }
      if (unlink(socket_path_.c_str()) != 0) throw std::runtime_error("failed to replace old socket");
    } else if (errno != ENOENT) {
      throw std::runtime_error("failed to inspect core socket path");
    }

    const mode_t previous_umask = umask(0077);
    FileDescriptor listener(socket(AF_UNIX, SOCK_STREAM, 0));
    if (listener.get() < 0) {
      umask(previous_umask);
      throw std::runtime_error("failed to create the core socket");
    }
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    if (socket_path_.size() >= sizeof(address.sun_path)) {
      umask(previous_umask);
      throw std::invalid_argument("core socket path is too long");
    }
    std::memcpy(address.sun_path, socket_path_.c_str(), socket_path_.size() + 1);
    if (bind(listener.get(), reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0 ||
        chmod(socket_path_.c_str(), 0600) != 0 || listen(listener.get(), 1) != 0) {
      umask(previous_umask);
      unlink(socket_path_.c_str());
      throw std::runtime_error("failed to bind the core socket");
    }
    umask(previous_umask);
    set_nonblocking(listener.get());
    listener_ = std::move(listener);
  }

  ~CoreSocketServer() { unlink(socket_path_.c_str()); }

  bool connected() const { return client_.get() >= 0; }

  void queue_hit(const Hit& hit) {
    const auto frame = frame_payload(vanity_v2::worker::encode_hit(hit));
    PersistentHit persistent;
    persistent.frame = frame;
    persistent_hits_.insert_or_assign(hit.result_id, std::move(persistent));
    queue_persistent(hit.result_id);
  }

  void queue_progress(const Progress& progress) {
    if (!connected()) return;
    outgoing_.push_back(
        OutgoingFrame{"", frame_payload(vanity_v2::worker::encode_progress(progress)), 0, false});
  }

  std::optional<Snapshot> take_snapshot() {
    std::optional<Snapshot> result = std::move(pending_snapshot_);
    pending_snapshot_.reset();
    return result;
  }

  void poll_once(int timeout_ms) {
    schedule_resends();
    std::array<struct pollfd, 2> descriptors{};
    descriptors[0] = {listener_.get(), POLLIN, 0};
    nfds_t count = 1;
    if (connected()) {
      descriptors[1] = {
          client_.get(),
          static_cast<short>(POLLIN | (!outgoing_.empty() ? POLLOUT : 0)),
          0};
      count = 2;
    }
    const int ready = poll(descriptors.data(), count, timeout_ms);
    if (ready < 0 && errno == EINTR) return;
    if (ready < 0) throw std::runtime_error("core socket polling failed");
    if ((descriptors[0].revents & POLLIN) != 0) accept_client();
    if (!connected() || count < 2) return;
    if ((descriptors[1].revents & (POLLERR | POLLHUP | POLLNVAL)) != 0) {
      disconnect_client();
      return;
    }
    if ((descriptors[1].revents & POLLIN) != 0 && !read_client()) return;
    if (connected() && (descriptors[1].revents & POLLOUT) != 0) write_client();
  }

 private:
  void accept_client() {
    while (true) {
      const int accepted = accept(listener_.get(), nullptr, nullptr);
      if (accepted < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return;
      if (accepted < 0 && errno == EINTR) continue;
      if (accepted < 0) throw std::runtime_error("failed to accept core socket client");
      FileDescriptor candidate(accepted);
      set_nonblocking(candidate.get());
#ifdef __linux__
      struct ucred credentials {};
      socklen_t length = sizeof(credentials);
      if (getsockopt(candidate.get(), SOL_SOCKET, SO_PEERCRED, &credentials, &length) != 0 ||
          credentials.uid != geteuid()) {
        continue;
      }
#endif
      if (connected()) continue;
      client_ = std::move(candidate);
      input_.clear();
      outgoing_.clear();
      for (auto& [result_id, hit] : persistent_hits_) {
        hit.queued = false;
        queue_persistent(result_id);
      }
      return;
    }
  }

  void disconnect_client() {
    client_.reset();
    input_.clear();
    outgoing_.clear();
    pending_snapshot_.reset();
    for (auto& [_, hit] : persistent_hits_) hit.queued = false;
  }

  bool read_client() {
    std::array<std::uint8_t, 8192> buffer{};
    while (true) {
      const ssize_t received = recv(client_.get(), buffer.data(), buffer.size(), 0);
      if (received < 0 && errno == EINTR) continue;
      if (received < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) break;
      if (received <= 0) {
        disconnect_client();
        return false;
      }
      if (input_.size() + static_cast<std::size_t>(received) > kMaximumInputBuffer) {
        disconnect_client();
        return false;
      }
      input_.insert(input_.end(), buffer.begin(), buffer.begin() + received);
    }
    try {
      parse_input();
    } catch (const std::exception&) {
      disconnect_client();
      return false;
    }
    return true;
  }

  void parse_input() {
    std::size_t consumed = 0;
    while (input_.size() - consumed >= 4) {
      const std::uint32_t length =
          (static_cast<std::uint32_t>(input_[consumed]) << 24) |
          (static_cast<std::uint32_t>(input_[consumed + 1]) << 16) |
          (static_cast<std::uint32_t>(input_[consumed + 2]) << 8) |
          input_[consumed + 3];
      if (length == 0 || length > vanity_v2::worker::kMaxFrameSize) {
        throw std::invalid_argument("invalid incoming frame length");
      }
      if (input_.size() - consumed < static_cast<std::size_t>(length) + 4) break;
      std::vector<std::uint8_t> payload(
          input_.begin() + static_cast<std::ptrdiff_t>(consumed + 4),
          input_.begin() + static_cast<std::ptrdiff_t>(consumed + 4 + length));
      const MessageType type = vanity_v2::worker::message_type(payload);
      if (type == MessageType::kSnapshot) {
        Snapshot snapshot = vanity_v2::worker::decode_snapshot(payload);
        if (snapshot.revision >= last_snapshot_revision_ &&
            (!pending_snapshot_ || snapshot.revision >= pending_snapshot_->revision)) {
          last_snapshot_revision_ = snapshot.revision;
          pending_snapshot_ = std::move(snapshot);
        }
      } else if (type == MessageType::kHitAck) {
        acknowledge(vanity_v2::worker::decode_hit_ack(payload));
      } else {
        throw std::invalid_argument("client sent a forbidden core message type");
      }
      consumed += static_cast<std::size_t>(length) + 4;
    }
    if (consumed != 0) input_.erase(input_.begin(), input_.begin() + consumed);
  }

  void acknowledge(const HitAck& ack) {
    persistent_hits_.erase(ack.result_id);
    outgoing_.erase(
        std::remove_if(
            outgoing_.begin(), outgoing_.end(),
            [&](const OutgoingFrame& frame) {
              return frame.persistent && frame.result_id == ack.result_id;
            }),
        outgoing_.end());
  }

  void queue_persistent(const std::string& result_id) {
    auto found = persistent_hits_.find(result_id);
    if (found == persistent_hits_.end() || found->second.queued || !connected()) return;
    found->second.queued = true;
    outgoing_.push_back(OutgoingFrame{result_id, found->second.frame, 0, true});
  }

  void schedule_resends() {
    if (!connected()) return;
    const auto now = std::chrono::steady_clock::now();
    for (auto& [result_id, hit] : persistent_hits_) {
      if (!hit.queued && (hit.last_sent.time_since_epoch().count() == 0 ||
                          now - hit.last_sent >= kHitResendInterval)) {
        queue_persistent(result_id);
      }
    }
  }

  void write_client() {
    while (connected() && !outgoing_.empty()) {
      OutgoingFrame& frame = outgoing_.front();
#ifdef MSG_NOSIGNAL
      constexpr int flags = MSG_NOSIGNAL;
#else
      constexpr int flags = 0;
#endif
      const ssize_t written = send(
          client_.get(), frame.frame.data() + frame.offset, frame.frame.size() - frame.offset, flags);
      if (written < 0 && errno == EINTR) continue;
      if (written < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return;
      if (written <= 0) {
        disconnect_client();
        return;
      }
      frame.offset += static_cast<std::size_t>(written);
      if (frame.offset == frame.frame.size()) {
        if (frame.persistent) {
          auto found = persistent_hits_.find(frame.result_id);
          if (found != persistent_hits_.end()) {
            found->second.queued = false;
            found->second.last_sent = std::chrono::steady_clock::now();
          }
        }
        outgoing_.pop_front();
      }
    }
  }

  std::string socket_path_;
  FileDescriptor listener_;
  FileDescriptor client_;
  std::vector<std::uint8_t> input_;
  std::optional<Snapshot> pending_snapshot_;
  std::uint64_t last_snapshot_revision_{0};
  std::map<std::string, PersistentHit> persistent_hits_;
  std::deque<OutgoingFrame> outgoing_;
};

enum class StreamClass { kNone, kP0, kP1, kP2 };

StreamClass class_from_text(const std::string& value) {
  if (value == "P0") return StreamClass::kP0;
  if (value == "P1") return StreamClass::kP1;
  if (value == "P2") return StreamClass::kP2;
  throw std::invalid_argument("invalid task class");
}

class SearchStream {
 public:
  SearchStream() = default;
  ~SearchStream() { clear(); }
  SearchStream(const SearchStream&) = delete;
  SearchStream& operator=(const SearchStream&) = delete;

  bool initialized() const { return keys_ != nullptr; }
  std::uint64_t groups() const { return groups_; }
  const std::string& shard() const { return shard_; }
  Int& key(std::size_t index) { return keys_[index]; }
  std::vector<std::uint64_t>& gpu_state() { return gpu_state_; }

  std::vector<Point> initialize(Secp256K1& secp, int thread_count, int group_size) {
    if (initialized()) throw std::logic_error("search stream is already initialized");
    key_count_ = static_cast<std::size_t>(thread_count);
    keys_ = new Int[key_count_];
    if (mlock(keys_, key_count_ * sizeof(Int)) != 0) {
      delete[] keys_;
      keys_ = nullptr;
      key_count_ = 0;
      throw std::runtime_error("failed to lock search scalar memory");
    }

    Int master;
    std::array<std::uint8_t, 32> random_bytes{};
    do {
      vanity_v2::security::secure_random(random_bytes.data(), random_bytes.size());
      master.Set32Bytes(random_bytes.data());
    } while (master.IsZero() || master.IsGreaterOrEqual(&secp.order));
    vanity_v2::security::secure_zero(random_bytes.data(), random_bytes.size());

    std::vector<Point> points;
    points.reserve(key_count_);
    for (std::size_t index = 0; index < key_count_; ++index) {
      keys_[index].Set(&master);
      Int offset(static_cast<std::uint64_t>(index));
      offset.ShiftL(80);
      keys_[index].Add(&offset);
      if (keys_[index].IsGreaterOrEqual(&secp.order)) keys_[index].Sub(&secp.order);
      Int midpoint(&keys_[index]);
      midpoint.Add(static_cast<std::uint64_t>(group_size / 2));
      if (midpoint.IsGreaterOrEqual(&secp.order)) midpoint.Sub(&secp.order);
      const Point computed = secp.ComputePublicKey(&midpoint);
      points.emplace_back(computed);
      vanity_v2::security::secure_zero(&midpoint, sizeof(midpoint));
    }
    vanity_v2::security::secure_zero(&master, sizeof(master));
    groups_ = 0;
    shard_ = vanity_v2::security::random_uuid_v4();
    return points;
  }

  void advance(Secp256K1& secp, int group_size) {
    for (std::size_t index = 0; index < key_count_; ++index) {
      keys_[index].Add(static_cast<std::uint64_t>(group_size));
      if (keys_[index].IsGreaterOrEqual(&secp.order)) keys_[index].Sub(&secp.order);
    }
    ++groups_;
  }

 private:
  void clear() noexcept {
    if (keys_ != nullptr) {
      vanity_v2::security::secure_zero(keys_, key_count_ * sizeof(Int));
      munlock(keys_, key_count_ * sizeof(Int));
      delete[] keys_;
      keys_ = nullptr;
    }
    if (!gpu_state_.empty()) {
      std::fill(gpu_state_.begin(), gpu_state_.end(), 0);
      gpu_state_.clear();
    }
  }

  Int* keys_{nullptr};
  std::size_t key_count_{0};
  std::vector<std::uint64_t> gpu_state_;
  std::uint64_t groups_{0};
  std::string shard_;
};

bool pattern_matches(const std::string& pattern, const std::string& address) {
  const std::size_t wildcard = pattern.find('*');
  if (wildcard == std::string::npos || pattern.find('*', wildcard + 1) != std::string::npos ||
      address.size() != vanity_v2::kTronAddressLength) {
    return false;
  }
  const std::string prefix = pattern.substr(0, wildcard);
  const std::string suffix = pattern.substr(wildcard + 1);
  return address.compare(0, prefix.size(), prefix) == 0 &&
         address.compare(address.size() - suffix.size(), suffix.size(), suffix) == 0;
}

void validate_snapshot(const Snapshot& snapshot) {
  if (snapshot.tasks.empty()) return;
  const std::string task_class = snapshot.tasks.front().task_class;
  std::set<std::string> item_ids;
  for (const Task& task : snapshot.tasks) {
    if (task.task_class != task_class || task.item_id.empty() || task.lease_id.empty() ||
        !item_ids.insert(task.item_id).second) {
      throw std::invalid_argument("invalid mixed or duplicate core snapshot");
    }
    const std::size_t wildcard = task.pattern.find('*');
    if (task.pattern.empty() || task.pattern.front() != 'T' || wildcard == std::string::npos ||
        task.pattern.find('*', wildcard + 1) != std::string::npos) {
      throw std::invalid_argument("invalid task pattern");
    }
    const std::string prefix = task.pattern.substr(1, wildcard - 1);
    const std::string suffix = task.pattern.substr(wildcard + 1);
    if (!std::all_of(prefix.begin(), prefix.end(), vanity_v2::is_base58_char) ||
        !std::all_of(suffix.begin(), suffix.end(), vanity_v2::is_base58_char)) {
      throw std::invalid_argument("task pattern contains a non-Base58 character");
    }
    if (task_class == "P0") {
      if (!prefix.empty() || suffix.size() != 5) throw std::invalid_argument("invalid P0 task");
    } else {
      const auto parsed = vanity_v2::parse_pattern(task.pattern, 0);
      if ((task_class == "P1" && parsed.prefix.empty()) ||
          (task_class == "P2" && !parsed.prefix.empty())) {
        throw std::invalid_argument("task class does not match its pattern");
      }
    }
  }
  const std::size_t maximum = task_class == "P0" ? 8 : 16;
  if (snapshot.tasks.size() > maximum) throw std::invalid_argument("snapshot exceeds class limit");
}

class Scheduler {
 public:
  Scheduler(
      const Options& options, const AgeEncryptor& encryptor,
      vanity_v2::worker::DurableOutbox& outbox)
      : secp_(),
        gpu_(options.grid_x, options.grid_y, options.gpu_id, 2048, true),
        encryptor_(encryptor),
        outbox_(outbox) {
    secp_.Init();
    gpu_.SetSearchType(TRON_ADDR);
    gpu_.SetSearchMode(SEARCH_UNCOMPRESSED);
    if (!gpu_.SetTronGroupsPerLaunch(1)) throw std::runtime_error("failed to set GPU group size");
    lambda_.SetBase16(const_cast<char*>(
        "5363ad4cc05c30e0a5261c028812645a122e22ea20816678df02967c1b23bd72"));
    lambda2_.SetBase16(const_cast<char*>(
        "ac9c52b33fa3cf1f5ad9e3fd77ed9ba4a880b9fc8ec739c2e0cfc810b51283ce"));
    for (const auto& [item_id, lease_id] : outbox_.pending_item_leases()) {
      completed_leases_.insert(item_id + "\n" + lease_id);
    }
  }

  ~Scheduler() {
    vanity_v2::security::secure_zero(&lambda_, sizeof(lambda_));
    vanity_v2::security::secure_zero(&lambda2_, sizeof(lambda2_));
  }

  bool kernel_active() const { return kernel_active_; }

  void apply_snapshot(Snapshot snapshot) {
    validate_snapshot(snapshot);
    desired_.clear();
    for (Task& task : snapshot.tasks) {
      if (completed_leases_.count(completion_key(task)) == 0) desired_.push_back(std::move(task));
    }
    if (p0_rotation_ >= desired_.size()) p0_rotation_ = 0;
  }

  void clear_desired() { desired_.clear(); }

  void finish_group(CoreSocketServer& server) {
    if (!kernel_active_) return;
    std::vector<ITEM> found;
    if (!gpu_.Launch(found, true, false)) throw std::runtime_error("CUDA group launch failed");
    kernel_active_ = false;
    process_hits(found, server);
    stream(current_class_).advance(secp_, gpu_.GetGroupSize());
    if (current_class_ == StreamClass::kP0 && !launch_tasks_.empty()) ++p0_rotation_;
  }

  void start_next() {
    std::vector<Task> tasks;
    StreamClass next_class = StreamClass::kNone;
    for (const Task& task : desired_) {
      if (completed_leases_.count(completion_key(task)) == 0) tasks.push_back(task);
    }
    if (!tasks.empty()) {
      next_class = class_from_text(tasks.front().task_class);
      if (next_class == StreamClass::kP0) {
        p0_rotation_ %= tasks.size();
        tasks = {tasks[p0_rotation_]};
      }
    }

    if (next_class == StreamClass::kNone) {
      save_resident_stream();
      launch_tasks_.clear();
      return;
    }

    if (next_class != current_class_) {
      save_resident_stream();
      current_class_ = next_class;
    }
    set_gpu_patterns(next_class, tasks);
    SearchStream& selected = stream(next_class);
    if (!selected.initialized()) {
      std::vector<Point> points =
          selected.initialize(secp_, gpu_.GetNbThread(), gpu_.GetGroupSize());
      if (!gpu_.SetKeys(points.data())) throw std::runtime_error("failed to initialize GPU keys");
    } else if (!selected.gpu_state().empty()) {
      if (!gpu_.ImportKeyState(selected.gpu_state())) {
        throw std::runtime_error("failed to restore GPU search state");
      }
      selected.gpu_state().clear();
    } else {
      if (!gpu_.Run()) throw std::runtime_error("failed to queue the next GPU group");
    }
    launch_tasks_ = std::move(tasks);
    kernel_active_ = true;
  }

  void emit_progress(CoreSocketServer& server) {
    const auto now = std::chrono::steady_clock::now();
    if (now - last_progress_ < std::chrono::seconds(1) || desired_.empty()) return;
    last_progress_ = now;
    const StreamClass desired_class = class_from_text(desired_.front().task_class);
    SearchStream& selected = stream(desired_class);
    if (!selected.initialized()) return;
    const std::string cursor =
        std::to_string(selected.groups() * static_cast<std::uint64_t>(gpu_.GetGroupSize()));
    for (const Task& task : desired_) {
      if (completed_leases_.count(completion_key(task)) != 0) continue;
      server.queue_progress(Progress{task.item_id, task.lease_id, selected.shard(), cursor});
    }
  }

 private:
  static std::string completion_key(const Task& task) {
    return task.item_id + "\n" + task.lease_id;
  }

  SearchStream& stream(StreamClass task_class) {
    if (task_class == StreamClass::kP0) return p0_;
    if (task_class == StreamClass::kP1) return p1_;
    if (task_class == StreamClass::kP2) return p2_;
    throw std::logic_error("no search stream is selected");
  }

  void save_resident_stream() {
    if (current_class_ == StreamClass::kNone) return;
    SearchStream& current = stream(current_class_);
    if (current.initialized() && current.gpu_state().empty()) {
      if (!gpu_.ExportKeyState(current.gpu_state())) {
        throw std::runtime_error("failed to save GPU search state");
      }
    }
    current_class_ = StreamClass::kNone;
  }

  void set_gpu_patterns(StreamClass task_class, const std::vector<Task>& tasks) {
    if (task_class == StreamClass::kP0) {
      if (tasks.size() != 1 || !gpu_.SetTronPattern(tasks.front().pattern.c_str())) {
        throw std::runtime_error("failed to set a P0 GPU target");
      }
      return;
    }
    std::vector<std::string> patterns;
    patterns.reserve(tasks.size());
    for (const Task& task : tasks) patterns.push_back(task.pattern);
    if (!gpu_.SetTronPatternsV2(patterns)) {
      throw std::runtime_error("failed to set P1/P2 GPU targets");
    }
  }

  bool reconstruct_private_key(
      const ITEM& item, Int& base, const std::string& expected_address,
      std::array<std::uint8_t, 32>* output) {
    if (output == nullptr) return false;
    Int key(&base);
    if (item.incr < 0) {
      key.Add(static_cast<std::uint64_t>(-static_cast<std::int32_t>(item.incr)));
      if (key.IsGreaterOrEqual(&secp_.order)) key.Sub(&secp_.order);
      key.ModNegK1order();
    } else {
      key.Add(static_cast<std::uint64_t>(item.incr));
      if (key.IsGreaterOrEqual(&secp_.order)) key.Sub(&secp_.order);
    }
    if (item.endo == 1) {
      key.ModMulK1order(&lambda_);
    } else if (item.endo == 2) {
      key.ModMulK1order(&lambda2_);
    } else if (item.endo != 0) {
      vanity_v2::security::secure_zero(&key, sizeof(key));
      return false;
    }

    Point point = secp_.ComputePublicKey(&key);
    std::string address = secp_.GetTronAddress(point);
    if (address != expected_address) {
      key.ModNegK1order();
      Point opposite = secp_.ComputePublicKey(&key);
      address = secp_.GetTronAddress(opposite);
    }
    if (address != expected_address || key.IsZero()) {
      vanity_v2::security::secure_zero(&key, sizeof(key));
      return false;
    }
    key.Get32Bytes(output->data());
    vanity_v2::security::secure_zero(&key, sizeof(key));
    return true;
  }

  void process_hits(const std::vector<ITEM>& found, CoreSocketServer& server) {
    std::set<std::string> completed_in_group;
    SearchStream& active = stream(current_class_);
    for (const ITEM& item : found) {
      if (item.targetId >= launch_tasks_.size() ||
          item.thId >= static_cast<std::uint32_t>(gpu_.GetNbThread())) {
        throw std::runtime_error("GPU returned invalid hit metadata");
      }
      const Task& task = launch_tasks_[item.targetId];
      const std::string key = completion_key(task);
      if (completed_leases_.count(key) != 0 || !completed_in_group.insert(key).second) continue;
      const std::string address = secp_.GetAddress(TRON_ADDR, item.mode, item.hash);
      if (!pattern_matches(task.pattern, address)) {
        throw std::runtime_error("GPU hit failed independent pattern verification");
      }
      std::array<std::uint8_t, 32> private_key{};
      if (!reconstruct_private_key(item, active.key(item.thId), address, &private_key)) {
        vanity_v2::security::secure_zero(private_key.data(), private_key.size());
        throw std::runtime_error("GPU hit failed independent private-key verification");
      }
      std::string ciphertext;
      try {
        ciphertext = encryptor_.encrypt_private_key(private_key);
      } catch (...) {
        vanity_v2::security::secure_zero(private_key.data(), private_key.size());
        throw;
      }
      vanity_v2::security::secure_zero(private_key.data(), private_key.size());
      Hit hit{
          vanity_v2::security::random_uuid_v4(),
          vanity_v2::security::random_uuid_v4(),
          task.item_id,
          task.lease_id,
          address,
          std::move(ciphertext),
      };
      outbox_.store(vanity_v2::worker::DurableEncryptedResult{
          hit.result_id,
          hit.event_id,
          hit.item_id,
          hit.lease_id,
          hit.matched_address,
          hit.encrypted_private_key,
      });
      server.queue_hit(hit);
      completed_leases_.insert(key);
    }
  }

  Secp256K1 secp_;
  GPUEngine gpu_;
  const AgeEncryptor& encryptor_;
  vanity_v2::worker::DurableOutbox& outbox_;
  Int lambda_;
  Int lambda2_;
  SearchStream p0_;
  SearchStream p1_;
  SearchStream p2_;
  StreamClass current_class_{StreamClass::kNone};
  std::vector<Task> desired_;
  std::vector<Task> launch_tasks_;
  std::set<std::string> completed_leases_;
  std::size_t p0_rotation_{0};
  bool kernel_active_{false};
  std::chrono::steady_clock::time_point last_progress_{};
};

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options options = parse_options(argc, argv);
    vanity_v2::security::disable_process_dumps();
    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);
    signal(SIGPIPE, SIG_IGN);
    const std::string recipient = read_recipient_file(options.age_recipient_file);
    const AgeEncryptor encryptor(options.age_executable, recipient);
    vanity_v2::worker::DurableOutbox outbox(options.worker_database);
    outbox.initialize();
    CoreSocketServer server(options.socket_path);
    Scheduler scheduler(options, encryptor, outbox);

    std::cout << "vanity18035 CUDA owner ready" << std::endl;
    while (!stop_requested.load()) {
      const bool completed_group = scheduler.kernel_active();
      if (completed_group) {
        scheduler.finish_group(server);
      }
      server.poll_once(completed_group ? 0 : 100);
      if (!server.connected()) {
        scheduler.clear_desired();
      } else if (auto snapshot = server.take_snapshot()) {
        scheduler.apply_snapshot(std::move(*snapshot));
      }
      scheduler.emit_progress(server);
      scheduler.start_next();
      server.poll_once(0);
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "vanity18035 CUDA owner stopped: " << error.what() << std::endl;
    return 1;
  }
}
