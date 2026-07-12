#include "worker_outbox.hpp"

#include <cassert>
#include <filesystem>
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

}  // namespace

int main() {
  char directory_template[] = "/tmp/vanity18035-outbox-XXXXXX";
  const char* directory = mkdtemp(directory_template);
  assert(directory != nullptr);
  chmod(directory, 0700);
  const std::string path = std::string(directory) + "/worker.sqlite3";
  vanity_v2::worker::DurableOutbox outbox(path);
  outbox.initialize();

  vanity_v2::worker::DurableEncryptedResult result{
      "result-1",
      "event-1",
      "item-1",
      "lease-1",
      std::string("T") + std::string(28, '1') + "Yqvi2",
      "-----BEGIN AGE ENCRYPTED FILE-----\ntest\n-----END AGE ENCRYPTED FILE-----\n",
  };
  assert(outbox.store(result));
  assert(!outbox.store(result));
  const auto pending = outbox.pending_item_leases();
  assert(pending.size() == 1);
  assert(pending[0].first == "item-1");
  assert(pending[0].second == "lease-1");

  auto conflict = result;
  conflict.event_id = "different-event";
  expect_error([&] { outbox.store(conflict); });

  auto plaintext = result;
  plaintext.result_id = "result-2";
  plaintext.event_id = "event-2";
  plaintext.encrypted_private_key = "plaintext";
  expect_error([&] { outbox.store(plaintext); });

  std::filesystem::remove_all(directory);
  return 0;
}
