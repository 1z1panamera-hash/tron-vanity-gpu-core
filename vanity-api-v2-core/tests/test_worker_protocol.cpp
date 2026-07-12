#include "worker_protocol.hpp"

#include <cassert>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

using vanity_v2::worker::Hit;
using vanity_v2::worker::HitAck;
using vanity_v2::worker::MessageType;
using vanity_v2::worker::Progress;
using vanity_v2::worker::Snapshot;
using vanity_v2::worker::Task;

namespace {

template <typename Function>
void expect_invalid(Function function) {
  bool threw = false;
  try {
    function();
  } catch (const std::invalid_argument&) {
    threw = true;
  }
  assert(threw);
}

}  // namespace

int main() {
  Snapshot snapshot;
  snapshot.revision = 42;
  snapshot.tasks.push_back(Task{
      "item-1", "P1", "TLU*Yqvi2", "lease-1", "shard-1", "2048"});
  const auto encoded_snapshot = vanity_v2::worker::encode_snapshot(snapshot);
  assert(vanity_v2::worker::message_type(encoded_snapshot) == MessageType::kSnapshot);
  const Snapshot decoded_snapshot = vanity_v2::worker::decode_snapshot(encoded_snapshot);
  assert(decoded_snapshot.revision == 42);
  assert(decoded_snapshot.tasks.size() == 1);
  assert(decoded_snapshot.tasks[0].pattern == "TLU*Yqvi2");

  Hit hit{
      "result-1",
      "event-1",
      "item-1",
      "lease-1",
      std::string("T") + std::string(28, '1') + "Yqvi2",
      "-----BEGIN AGE ENCRYPTED FILE-----\ntest\n-----END AGE ENCRYPTED FILE-----\n"};
  const auto encoded_hit = vanity_v2::worker::encode_hit(hit);
  assert(vanity_v2::worker::message_type(encoded_hit) == MessageType::kHit);
  assert(vanity_v2::worker::decode_hit(encoded_hit).matched_address == hit.matched_address);

  Progress progress{"item-1", "lease-1", "shard-1", "4096"};
  const auto encoded_progress = vanity_v2::worker::encode_progress(progress);
  assert(vanity_v2::worker::message_type(encoded_progress) == MessageType::kProgress);
  assert(vanity_v2::worker::decode_progress(encoded_progress).search_cursor == "4096");

  const auto encoded_ack = vanity_v2::worker::encode_hit_ack(HitAck{"result-1"});
  assert(vanity_v2::worker::message_type(encoded_ack) == MessageType::kHitAck);
  assert(vanity_v2::worker::decode_hit_ack(encoded_ack).result_id == "result-1");

  auto truncated = encoded_snapshot;
  truncated.pop_back();
  expect_invalid([&] { vanity_v2::worker::decode_snapshot(truncated); });

  auto trailing = encoded_snapshot;
  trailing.push_back(0);
  expect_invalid([&] { vanity_v2::worker::decode_snapshot(trailing); });

  Snapshot too_many;
  too_many.tasks.resize(17, snapshot.tasks[0]);
  expect_invalid([&] { vanity_v2::worker::encode_snapshot(too_many); });

  Snapshot bad_class = snapshot;
  bad_class.tasks[0].task_class = "PX";
  expect_invalid([&] { vanity_v2::worker::encode_snapshot(bad_class); });

  Hit plaintext = hit;
  plaintext.encrypted_private_key = "private-key";
  expect_invalid([&] { vanity_v2::worker::encode_hit(plaintext); });

  return 0;
}
