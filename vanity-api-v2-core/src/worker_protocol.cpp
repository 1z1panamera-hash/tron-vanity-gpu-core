#include "worker_protocol.hpp"

#include <array>
#include <limits>
#include <stdexcept>
#include <utility>

namespace vanity_v2::worker {
namespace {

constexpr std::array<std::uint8_t, 4> kMagic{{'V', '3', '5', 'C'}};

class Writer {
 public:
  explicit Writer(MessageType type) {
    bytes_.insert(bytes_.end(), kMagic.begin(), kMagic.end());
    u8(kProtocolVersion);
    u8(static_cast<std::uint8_t>(type));
    u16(0);
  }

  void u8(std::uint8_t value) { bytes_.push_back(value); }

  void u16(std::uint16_t value) {
    bytes_.push_back(static_cast<std::uint8_t>(value >> 8));
    bytes_.push_back(static_cast<std::uint8_t>(value));
  }

  void u32(std::uint32_t value) {
    for (int shift = 24; shift >= 0; shift -= 8) {
      bytes_.push_back(static_cast<std::uint8_t>(value >> shift));
    }
  }

  void u64(std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
      bytes_.push_back(static_cast<std::uint8_t>(value >> shift));
    }
  }

  void string(const std::string& value, std::size_t maximum, const char* field) {
    if (value.size() > maximum || value.size() > std::numeric_limits<std::uint32_t>::max()) {
      throw std::invalid_argument(std::string(field) + " exceeds the protocol limit");
    }
    u32(static_cast<std::uint32_t>(value.size()));
    bytes_.insert(bytes_.end(), value.begin(), value.end());
  }

  std::vector<std::uint8_t> finish() {
    if (bytes_.size() > kMaxFrameSize) {
      throw std::invalid_argument("worker protocol frame exceeds the size limit");
    }
    return std::move(bytes_);
  }

 private:
  std::vector<std::uint8_t> bytes_;
};

class Reader {
 public:
  Reader(const std::vector<std::uint8_t>& bytes, MessageType expected) : bytes_(bytes) {
    if (bytes_.size() < 8 || bytes_.size() > kMaxFrameSize) {
      throw std::invalid_argument("invalid worker protocol frame size");
    }
    for (std::size_t index = 0; index < kMagic.size(); ++index) {
      if (bytes_[index] != kMagic[index]) throw std::invalid_argument("invalid protocol magic");
    }
    offset_ = 4;
    if (u8() != kProtocolVersion) throw std::invalid_argument("unsupported protocol version");
    if (u8() != static_cast<std::uint8_t>(expected)) {
      throw std::invalid_argument("unexpected worker protocol message type");
    }
    if (u16() != 0) throw std::invalid_argument("worker protocol reserved bits are nonzero");
  }

  std::uint8_t u8() {
    require(1);
    return bytes_[offset_++];
  }

  std::uint16_t u16() {
    require(2);
    const std::uint16_t value =
        (static_cast<std::uint16_t>(bytes_[offset_]) << 8) | bytes_[offset_ + 1];
    offset_ += 2;
    return value;
  }

  std::uint32_t u32() {
    require(4);
    std::uint32_t value = 0;
    for (int index = 0; index < 4; ++index) value = (value << 8) | bytes_[offset_++];
    return value;
  }

  std::uint64_t u64() {
    require(8);
    std::uint64_t value = 0;
    for (int index = 0; index < 8; ++index) value = (value << 8) | bytes_[offset_++];
    return value;
  }

  std::string string(std::size_t maximum, const char* field, bool allow_empty = true) {
    const std::uint32_t length = u32();
    if (length > maximum) {
      throw std::invalid_argument(std::string(field) + " exceeds the protocol limit");
    }
    if (!allow_empty && length == 0) {
      throw std::invalid_argument(std::string(field) + " cannot be empty");
    }
    require(length);
    std::string value(bytes_.begin() + static_cast<std::ptrdiff_t>(offset_),
                      bytes_.begin() + static_cast<std::ptrdiff_t>(offset_ + length));
    offset_ += length;
    return value;
  }

  void finish() const {
    if (offset_ != bytes_.size()) throw std::invalid_argument("trailing protocol data");
  }

 private:
  void require(std::size_t length) const {
    if (length > bytes_.size() - offset_) throw std::invalid_argument("truncated protocol frame");
  }

  const std::vector<std::uint8_t>& bytes_;
  std::size_t offset_{0};
};

void validate_class(const std::string& task_class) {
  if (task_class != "P0" && task_class != "P1" && task_class != "P2") {
    throw std::invalid_argument("invalid task class");
  }
}

void validate_address(const std::string& address) {
  if (address.size() != 34 || address.front() != 'T') {
    throw std::invalid_argument("invalid TRON address in hit frame");
  }
}

void validate_age(const std::string& ciphertext) {
  if (ciphertext.rfind("-----BEGIN AGE ENCRYPTED FILE-----", 0) != 0) {
    throw std::invalid_argument("hit frame does not contain armored Age ciphertext");
  }
}

}  // namespace

MessageType message_type(const std::vector<std::uint8_t>& payload) {
  if (payload.size() < 8 || payload.size() > kMaxFrameSize) {
    throw std::invalid_argument("invalid worker protocol frame size");
  }
  for (std::size_t index = 0; index < kMagic.size(); ++index) {
    if (payload[index] != kMagic[index]) throw std::invalid_argument("invalid protocol magic");
  }
  if (payload[4] != kProtocolVersion) throw std::invalid_argument("unsupported protocol version");
  const auto raw = static_cast<MessageType>(payload[5]);
  if (raw != MessageType::kSnapshot && raw != MessageType::kHit &&
      raw != MessageType::kProgress && raw != MessageType::kHitAck) {
    throw std::invalid_argument("unknown worker protocol message type");
  }
  return raw;
}

std::vector<std::uint8_t> encode_snapshot(const Snapshot& snapshot) {
  if (snapshot.tasks.size() > kMaxTasks) throw std::invalid_argument("snapshot has too many tasks");
  Writer writer(MessageType::kSnapshot);
  writer.u64(snapshot.revision);
  writer.u16(static_cast<std::uint16_t>(snapshot.tasks.size()));
  for (const Task& task : snapshot.tasks) {
    validate_class(task.task_class);
    writer.string(task.item_id, 128, "item_id");
    writer.string(task.task_class, 2, "task_class");
    writer.string(task.pattern, 64, "pattern");
    writer.string(task.lease_id, 128, "lease_id");
    writer.string(task.search_shard, 256, "search_shard");
    writer.string(task.search_cursor, 256, "search_cursor");
  }
  return writer.finish();
}

Snapshot decode_snapshot(const std::vector<std::uint8_t>& payload) {
  Reader reader(payload, MessageType::kSnapshot);
  Snapshot snapshot;
  snapshot.revision = reader.u64();
  const std::uint16_t count = reader.u16();
  if (count > kMaxTasks) throw std::invalid_argument("snapshot has too many tasks");
  snapshot.tasks.reserve(count);
  for (std::uint16_t index = 0; index < count; ++index) {
    Task task;
    task.item_id = reader.string(128, "item_id", false);
    task.task_class = reader.string(2, "task_class", false);
    validate_class(task.task_class);
    task.pattern = reader.string(64, "pattern", false);
    task.lease_id = reader.string(128, "lease_id", false);
    task.search_shard = reader.string(256, "search_shard");
    task.search_cursor = reader.string(256, "search_cursor");
    snapshot.tasks.push_back(std::move(task));
  }
  reader.finish();
  return snapshot;
}

std::vector<std::uint8_t> encode_hit(const Hit& hit) {
  validate_address(hit.matched_address);
  validate_age(hit.encrypted_private_key);
  Writer writer(MessageType::kHit);
  writer.string(hit.result_id, 128, "result_id");
  writer.string(hit.event_id, 128, "event_id");
  writer.string(hit.item_id, 128, "item_id");
  writer.string(hit.lease_id, 128, "lease_id");
  writer.string(hit.matched_address, 34, "matched_address");
  writer.string(hit.encrypted_private_key, 64U * 1024U, "encrypted_private_key");
  return writer.finish();
}

Hit decode_hit(const std::vector<std::uint8_t>& payload) {
  Reader reader(payload, MessageType::kHit);
  Hit hit;
  hit.result_id = reader.string(128, "result_id", false);
  hit.event_id = reader.string(128, "event_id", false);
  hit.item_id = reader.string(128, "item_id", false);
  hit.lease_id = reader.string(128, "lease_id", false);
  hit.matched_address = reader.string(34, "matched_address", false);
  hit.encrypted_private_key = reader.string(64U * 1024U, "encrypted_private_key", false);
  reader.finish();
  validate_address(hit.matched_address);
  validate_age(hit.encrypted_private_key);
  return hit;
}

std::vector<std::uint8_t> encode_progress(const Progress& progress) {
  Writer writer(MessageType::kProgress);
  writer.string(progress.item_id, 128, "item_id");
  writer.string(progress.lease_id, 128, "lease_id");
  writer.string(progress.search_shard, 256, "search_shard");
  writer.string(progress.search_cursor, 256, "search_cursor");
  return writer.finish();
}

Progress decode_progress(const std::vector<std::uint8_t>& payload) {
  Reader reader(payload, MessageType::kProgress);
  Progress progress;
  progress.item_id = reader.string(128, "item_id", false);
  progress.lease_id = reader.string(128, "lease_id", false);
  progress.search_shard = reader.string(256, "search_shard");
  progress.search_cursor = reader.string(256, "search_cursor");
  reader.finish();
  return progress;
}

std::vector<std::uint8_t> encode_hit_ack(const HitAck& ack) {
  Writer writer(MessageType::kHitAck);
  writer.string(ack.result_id, 128, "result_id");
  return writer.finish();
}

HitAck decode_hit_ack(const std::vector<std::uint8_t>& payload) {
  Reader reader(payload, MessageType::kHitAck);
  HitAck ack;
  ack.result_id = reader.string(128, "result_id", false);
  reader.finish();
  return ack;
}

}  // namespace vanity_v2::worker
