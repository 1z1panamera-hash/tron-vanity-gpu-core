#include "worker_outbox.hpp"

#include <chrono>
#include <sqlite3.h>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

namespace vanity_v2::worker {
namespace {

class Database {
 public:
  explicit Database(const std::string& path) {
    const mode_t previous_umask = umask(0077);
    const int status = sqlite3_open_v2(
        path.c_str(), &database_, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX,
        nullptr);
    umask(previous_umask);
    if (status != SQLITE_OK) {
      const std::string message = database_ ? sqlite3_errmsg(database_) : "unknown error";
      if (database_) sqlite3_close(database_);
      database_ = nullptr;
      throw std::runtime_error("cannot open encrypted worker outbox: " + message);
    }
    sqlite3_busy_timeout(database_, 5000);
  }

  ~Database() {
    if (database_) sqlite3_close(database_);
  }
  Database(const Database&) = delete;
  Database& operator=(const Database&) = delete;
  sqlite3* get() const { return database_; }

  void execute(const char* sql) {
    char* error = nullptr;
    if (sqlite3_exec(database_, sql, nullptr, nullptr, &error) != SQLITE_OK) {
      const std::string message = error ? error : "unknown SQLite error";
      sqlite3_free(error);
      throw std::runtime_error("encrypted worker outbox failed: " + message);
    }
  }

 private:
  sqlite3* database_{nullptr};
};

class Statement {
 public:
  Statement(sqlite3* database, const char* sql) {
    if (sqlite3_prepare_v2(database, sql, -1, &statement_, nullptr) != SQLITE_OK) {
      throw std::runtime_error("cannot prepare encrypted worker outbox statement");
    }
  }
  ~Statement() { sqlite3_finalize(statement_); }
  Statement(const Statement&) = delete;
  Statement& operator=(const Statement&) = delete;
  sqlite3_stmt* get() const { return statement_; }

  void text(int index, const std::string& value) {
    if (sqlite3_bind_text(statement_, index, value.data(), static_cast<int>(value.size()),
                          SQLITE_TRANSIENT) != SQLITE_OK) {
      throw std::runtime_error("cannot bind encrypted worker outbox value");
    }
  }

 private:
  sqlite3_stmt* statement_{nullptr};
};

std::string parent_directory(const std::string& path) {
  const std::size_t slash = path.rfind('/');
  if (slash == std::string::npos) return ".";
  return slash == 0 ? "/" : path.substr(0, slash);
}

void validate_parent(const std::string& database_path) {
  const std::string parent = parent_directory(database_path);
  struct stat status {};
  if (stat(parent.c_str(), &status) != 0 || !S_ISDIR(status.st_mode) ||
      status.st_uid != geteuid() || (status.st_mode & 0077) != 0) {
    throw std::runtime_error("worker database directory must be owned by the worker and mode 0700");
  }
}

void validate_result(const DurableEncryptedResult& result) {
  if (result.result_id.empty() || result.event_id.empty() || result.item_id.empty() ||
      result.lease_id.empty()) {
    throw std::invalid_argument("encrypted worker result identifiers cannot be empty");
  }
  if (result.matched_address.size() != 34 || result.matched_address.front() != 'T') {
    throw std::invalid_argument("encrypted worker result has an invalid TRON address");
  }
  if (result.encrypted_private_key.rfind("-----BEGIN AGE ENCRYPTED FILE-----", 0) != 0 ||
      result.encrypted_private_key.size() > 64U * 1024U) {
    throw std::invalid_argument("worker outbox accepts only armored Age ciphertext");
  }
}

std::string column_text(sqlite3_stmt* statement, int column) {
  const auto* value = sqlite3_column_text(statement, column);
  const int length = sqlite3_column_bytes(statement, column);
  return value == nullptr ? std::string() :
      std::string(reinterpret_cast<const char*>(value), static_cast<std::size_t>(length));
}

}  // namespace

DurableOutbox::DurableOutbox(std::string database_path)
    : database_path_(std::move(database_path)) {
  if (database_path_.empty() || database_path_.front() != '/') {
    throw std::invalid_argument("worker database path must be absolute");
  }
}

void DurableOutbox::initialize() {
  validate_parent(database_path_);
  Database database(database_path_);
  database.execute("PRAGMA journal_mode=WAL");
  database.execute("PRAGMA synchronous=FULL");
  database.execute("PRAGMA foreign_keys=ON");
  database.execute(
      "CREATE TABLE IF NOT EXISTS result_outbox ("
      "result_id TEXT PRIMARY KEY,"
      "event_id TEXT NOT NULL UNIQUE,"
      "item_id TEXT NOT NULL,"
      "lease_id TEXT NOT NULL,"
      "matched_address TEXT NOT NULL,"
      "encrypted_private_key TEXT NOT NULL,"
      "attempts INTEGER NOT NULL DEFAULT 0,"
      "next_attempt_at REAL NOT NULL,"
      "last_error TEXT,"
      "created_at REAL NOT NULL)"
  );
  if (chmod(database_path_.c_str(), 0600) != 0) {
    throw std::runtime_error("cannot secure encrypted worker outbox permissions");
  }
}

bool DurableOutbox::store(const DurableEncryptedResult& result) {
  validate_result(result);
  Database database(database_path_);
  database.execute("BEGIN IMMEDIATE");
  try {
    Statement insert(
        database.get(),
        "INSERT OR IGNORE INTO result_outbox("
        "result_id,event_id,item_id,lease_id,matched_address,encrypted_private_key,"
        "attempts,next_attempt_at,created_at) VALUES(?,?,?,?,?,?,0,?,?)");
    insert.text(1, result.result_id);
    insert.text(2, result.event_id);
    insert.text(3, result.item_id);
    insert.text(4, result.lease_id);
    insert.text(5, result.matched_address);
    insert.text(6, result.encrypted_private_key);
    const double now = std::chrono::duration<double>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    sqlite3_bind_double(insert.get(), 7, now);
    sqlite3_bind_double(insert.get(), 8, now);
    if (sqlite3_step(insert.get()) != SQLITE_DONE) {
      throw std::runtime_error("cannot insert encrypted worker result");
    }
    const bool inserted = sqlite3_changes(database.get()) == 1;
    if (!inserted) {
      Statement existing(
          database.get(),
          "SELECT event_id,item_id,lease_id,matched_address,encrypted_private_key "
          "FROM result_outbox WHERE result_id=?");
      existing.text(1, result.result_id);
      if (sqlite3_step(existing.get()) != SQLITE_ROW ||
          column_text(existing.get(), 0) != result.event_id ||
          column_text(existing.get(), 1) != result.item_id ||
          column_text(existing.get(), 2) != result.lease_id ||
          column_text(existing.get(), 3) != result.matched_address ||
          column_text(existing.get(), 4) != result.encrypted_private_key) {
        throw std::runtime_error("encrypted worker result id conflicts with existing data");
      }
    }
    database.execute("COMMIT");
    return inserted;
  } catch (...) {
    try {
      database.execute("ROLLBACK");
    } catch (...) {
    }
    throw;
  }
}

std::vector<std::pair<std::string, std::string>> DurableOutbox::pending_item_leases() const {
  Database database(database_path_);
  Statement query(database.get(), "SELECT item_id,lease_id FROM result_outbox");
  std::vector<std::pair<std::string, std::string>> result;
  while (true) {
    const int status = sqlite3_step(query.get());
    if (status == SQLITE_DONE) break;
    if (status != SQLITE_ROW) throw std::runtime_error("cannot read encrypted worker outbox");
    result.emplace_back(column_text(query.get(), 0), column_text(query.get(), 1));
  }
  return result;
}

}  // namespace vanity_v2::worker
