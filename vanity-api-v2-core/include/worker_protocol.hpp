#ifndef VANITY_API_V2_WORKER_PROTOCOL_HPP
#define VANITY_API_V2_WORKER_PROTOCOL_HPP

#include <cstdint>
#include <string>
#include <vector>

namespace vanity_v2::worker {

constexpr std::uint8_t kProtocolVersion = 1;
constexpr std::size_t kMaxTasks = 16;
constexpr std::size_t kMaxFrameSize = 128U * 1024U;

enum class MessageType : std::uint8_t {
  kSnapshot = 1,
  kHit = 2,
  kProgress = 3,
  kHitAck = 4,
};

struct Task {
  std::string item_id;
  std::string task_class;
  std::string pattern;
  std::string lease_id;
  std::string search_shard;
  std::string search_cursor;
};

struct Snapshot {
  std::uint64_t revision{0};
  std::vector<Task> tasks;
};

struct Hit {
  std::string result_id;
  std::string event_id;
  std::string item_id;
  std::string lease_id;
  std::string matched_address;
  std::string encrypted_private_key;
};

struct Progress {
  std::string item_id;
  std::string lease_id;
  std::string search_shard;
  std::string search_cursor;
};

struct HitAck {
  std::string result_id;
};

std::vector<std::uint8_t> encode_snapshot(const Snapshot& snapshot);
Snapshot decode_snapshot(const std::vector<std::uint8_t>& payload);

std::vector<std::uint8_t> encode_hit(const Hit& hit);
Hit decode_hit(const std::vector<std::uint8_t>& payload);

std::vector<std::uint8_t> encode_progress(const Progress& progress);
Progress decode_progress(const std::vector<std::uint8_t>& payload);

std::vector<std::uint8_t> encode_hit_ack(const HitAck& ack);
HitAck decode_hit_ack(const std::vector<std::uint8_t>& payload);

MessageType message_type(const std::vector<std::uint8_t>& payload);

}  // namespace vanity_v2::worker

#endif
