#include <fstream>
#include <iostream>
#include <regex>
#include <sstream>
#include <string>
#include <vector>

#include "../src/tron_core_algorithms.hpp"

struct VectorCase {
    std::string label;
    std::string public_key_uncompressed_hex;
    std::string keccak256_pubkey_without_04;
    std::string tron_hex_address;
    std::string payload25_hex;
    std::string tron_base58_address;
    std::string prefix2;
    std::string suffix5;
    std::string source;
    std::string warning;
};

std::string read_file(const std::string& path) {
    std::ifstream in(path);
    if (!in) {
        throw std::runtime_error("failed to open " + path);
    }
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

std::string extract_string(const std::string& object, const std::string& key) {
    std::regex re("\"" + key + "\"\\s*:\\s*\"([^\"]*)\"");
    std::smatch match;
    if (!std::regex_search(object, match, re)) {
        throw std::runtime_error("missing key: " + key);
    }
    return match[1].str();
}

std::vector<VectorCase> parse_vectors(const std::string& json) {
    std::vector<VectorCase> vectors;
    std::regex object_re("\\{[^{}]*\"label\"[^{}]*\\}");
    auto begin = std::sregex_iterator(json.begin(), json.end(), object_re);
    auto end = std::sregex_iterator();

    for (auto it = begin; it != end; ++it) {
        std::string obj = it->str();
        vectors.push_back(VectorCase{
            extract_string(obj, "label"),
            extract_string(obj, "public_key_uncompressed_hex"),
            extract_string(obj, "keccak256_pubkey_without_04"),
            extract_string(obj, "tron_hex_address"),
            extract_string(obj, "payload25_hex"),
            extract_string(obj, "tron_base58_address"),
            extract_string(obj, "prefix2"),
            extract_string(obj, "suffix5"),
            extract_string(obj, "source"),
            extract_string(obj, "warning"),
        });
    }

    if (vectors.empty()) {
        throw std::runtime_error("no vectors found");
    }
    return vectors;
}

int main(int argc, char** argv) {
    const std::string path = argc >= 2 ? argv[1] : "tests/phase0_test_vectors.json";
    const auto vectors = parse_vectors(read_file(path));

    int passed = 0;
    std::vector<std::string> failures;

    const auto keccak_empty = tron_core::keccak256(nullptr, 0);
    const std::string keccak_empty_hex = tron_core::bytes_to_hex(keccak_empty.data(), keccak_empty.size());
    if (keccak_empty_hex != "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470") {
        failures.push_back("keccak_empty mismatch");
    }

    const uint8_t empty[] = {};
    const auto sha_empty = tron_core::sha256(empty, 0);
    const std::string sha_empty_hex = tron_core::bytes_to_hex(sha_empty.data(), sha_empty.size());
    if (sha_empty_hex != "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855") {
        failures.push_back("sha256_empty mismatch");
    }

    for (const auto& vector : vectors) {
        bool ok = true;
        auto fail = [&](const std::string& reason) {
            ok = false;
            failures.push_back(vector.label + ": " + reason);
        };

        if (vector.source != "TEST_ONLY_PUBLIC_VECTOR") {
            fail("source mismatch");
        }
        if (vector.warning != "TEST_ONLY_PUBLIC_VECTOR_DO_NOT_USE_FOR_FUNDS") {
            fail("warning mismatch");
        }
        if (vector.public_key_uncompressed_hex.rfind("04", 0) != 0) {
            fail("public key does not start with 04");
        }

        const auto public_key = tron_core::hex_to_bytes(vector.public_key_uncompressed_hex.substr(2));
        const auto keccak = tron_core::keccak256(public_key.data(), public_key.size());
        const std::string keccak_hex = tron_core::bytes_to_hex(keccak.data(), keccak.size());
        if (keccak_hex != vector.keccak256_pubkey_without_04) {
            fail("keccak mismatch");
        }

        const std::string tron_hex = "41" + keccak_hex.substr(24);
        if (tron_hex != vector.tron_hex_address) {
            fail("tron hex mismatch");
        }

        const auto payload25 = tron_core::tron_hex_to_payload25(tron_hex);
        const std::string payload25_hex = tron_core::bytes_to_hex(payload25.data(), payload25.size());
        if (payload25_hex != vector.payload25_hex) {
            fail("payload25 mismatch");
        }

        const std::string address = tron_core::base58_encode(payload25.data(), payload25.size());
        if (address != vector.tron_base58_address) {
            fail("base58 address mismatch");
        }

        const auto decoded_payload = tron_core::base58_decode_payload25(address);
        if (decoded_payload != payload25) {
            fail("base58 decode mismatch");
        }

        if (vector.prefix2 != address.substr(0, 2)) {
            fail("prefix2 mismatch");
        }
        if (vector.suffix5 != address.substr(address.size() - 5)) {
            fail("suffix5 mismatch");
        }

        const uint64_t expected_suffix = tron_core::suffix_value_from_base58_suffix(vector.suffix5);
        const uint64_t actual_suffix = tron_core::payload25_mod_suffix_base(payload25, 5);
        if (expected_suffix != actual_suffix) {
            fail("suffix modulo mismatch");
        }

        if (!tron_core::base58_prefix_range_filter(payload25, vector.prefix2, static_cast<int>(address.size()))) {
            fail("prefix range mismatch");
        }

        if (!tron_core::address_matches_filter(payload25, address, 2, 5)) {
            fail("full filter mismatch");
        }

        if (ok) {
            ++passed;
        }
    }

    std::cout << "{\n";
    std::cout << "  \"vector_path\": \"" << path << "\",\n";
    std::cout << "  \"total_vectors\": " << vectors.size() << ",\n";
    std::cout << "  \"passed\": " << passed << ",\n";
    std::cout << "  \"failed\": " << failures.size() << ",\n";
    std::cout << "  \"failures\": [";
    for (size_t i = 0; i < failures.size(); ++i) {
        if (i) std::cout << ", ";
        std::cout << "\"" << failures[i] << "\"";
    }
    std::cout << "],\n";
    std::cout << "  \"notes\": [\n";
    std::cout << "    \"C++ core algorithm validation only; no benchmark is run.\",\n";
    std::cout << "    \"No random private keys are generated.\",\n";
    std::cout << "    \"This validates Keccak, SHA256 checksum, Base58Check, prefix range, suffix modulo, and full confirm.\"\n";
    std::cout << "  ]\n";
    std::cout << "}\n";

    return failures.empty() ? 0 : 1;
}
