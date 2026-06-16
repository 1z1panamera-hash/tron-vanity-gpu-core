#include <fstream>
#include <iostream>
#include <regex>
#include <sstream>
#include <string>
#include <vector>

#include "../src/secp256k1_host_reference.hpp"
#include "../src/tron_core_algorithms.hpp"

struct VectorCase {
    std::string label;
    std::string private_key_hex;
    std::string public_key_uncompressed_hex;
    std::string keccak256_pubkey_without_04;
    std::string tron_hex_address;
    std::string payload25_hex;
    std::string tron_base58_address;
};

std::string read_file(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("failed to open " + path);
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

std::string extract_string(const std::string& object, const std::string& key) {
    std::regex re("\"" + key + "\"\\s*:\\s*\"([^\"]*)\"");
    std::smatch match;
    if (!std::regex_search(object, match, re)) throw std::runtime_error("missing key: " + key);
    return match[1].str();
}

std::vector<VectorCase> parse_vectors(const std::string& json) {
    std::vector<VectorCase> vectors;
    std::regex object_re("\\{[^{}]*\"label\"[^{}]*\\}");
    auto begin = std::sregex_iterator(json.begin(), json.end(), object_re);
    auto end = std::sregex_iterator();
    for (auto it = begin; it != end; ++it) {
        const std::string obj = it->str();
        vectors.push_back(VectorCase{
            extract_string(obj, "label"),
            extract_string(obj, "private_key_hex"),
            extract_string(obj, "public_key_uncompressed_hex"),
            extract_string(obj, "keccak256_pubkey_without_04"),
            extract_string(obj, "tron_hex_address"),
            extract_string(obj, "payload25_hex"),
            extract_string(obj, "tron_base58_address"),
        });
    }
    if (vectors.empty()) throw std::runtime_error("no vectors parsed");
    return vectors;
}

int main(int argc, char** argv) {
    const std::string path = argc >= 2 ? argv[1] : "tests/phase0_test_vectors.json";
    const auto vectors = parse_vectors(read_file(path));
    int passed = 0;
    std::vector<std::string> failures;

    for (const auto& vector : vectors) {
        bool ok = true;
        auto fail = [&](const std::string& reason) {
            ok = false;
            failures.push_back(vector.label + ": " + reason);
        };

        const std::string pubkey =
            secp256k1_host::private_key_hex_to_public_key_uncompressed(vector.private_key_hex);
        if (pubkey != vector.public_key_uncompressed_hex) {
            fail("public key mismatch");
            continue;
        }

        const auto public_key_bytes = tron_core::hex_to_bytes(pubkey.substr(2));
        const auto keccak = tron_core::keccak256(public_key_bytes.data(), public_key_bytes.size());
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

        if (ok) ++passed;
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
    std::cout << "    \"Host-side secp256k1 full chain validation only; no benchmark is run.\",\n";
    std::cout << "    \"Only public TEST_ONLY vectors are used.\",\n";
    std::cout << "    \"This validates private scalar to public key to TRON Base58 address.\"\n";
    std::cout << "  ]\n";
    std::cout << "}\n";

    return failures.empty() ? 0 : 1;
}
