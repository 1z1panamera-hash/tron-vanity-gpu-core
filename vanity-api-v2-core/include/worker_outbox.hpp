#ifndef VANITY_API_V2_WORKER_OUTBOX_HPP
#define VANITY_API_V2_WORKER_OUTBOX_HPP

#include <string>
#include <utility>
#include <vector>

namespace vanity_v2::worker {

struct DurableEncryptedResult {
  std::string result_id;
  std::string event_id;
  std::string item_id;
  std::string lease_id;
  std::string matched_address;
  std::string encrypted_private_key;
};

class DurableOutbox {
 public:
  explicit DurableOutbox(std::string database_path);

  void initialize();
  bool store(const DurableEncryptedResult& result);
  std::vector<std::pair<std::string, std::string>> pending_item_leases() const;

 private:
  std::string database_path_;
};

}  // namespace vanity_v2::worker

#endif
