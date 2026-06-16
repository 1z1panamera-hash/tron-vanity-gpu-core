#include <fstream>
#include <iostream>
#include <regex>
#include <sstream>
#include <string>
#include <vector>

#include "../src/tron_core_device.cuh"

struct VectorCase {
    std::string label;
    std::string public_key_uncompressed_hex;
    std::string keccak256_pubkey_without_04;
    std::string payload25_hex;
    std::string tron_base58_address;
    std::string prefix2;
    std::string suffix5;
};

uint8_t hex_value(char c) {
    if (c >= '0' && c <= '9') return static_cast<uint8_t>(c - '0');
    if (c >= 'a' && c <= 'f') return static_cast<uint8_t>(c - 'a' + 10);
    if (c >= 'A' && c <= 'F') return static_cast<uint8_t>(c - 'A' + 10);
    throw std::runtime_error("invalid hex");
}

std::vector<uint8_t> hex_to_bytes(const std::string& hex) {
    if (hex.size() % 2 != 0) throw std::runtime_error("invalid hex length");
    std::vector<uint8_t> out(hex.size() / 2);
    for (size_t i = 0; i < out.size(); ++i) {
        out[i] = static_cast<uint8_t>((hex_value(hex[i * 2]) << 4) | hex_value(hex[i * 2 + 1]));
    }
    return out;
}

std::string bytes_to_hex(const uint8_t* data, size_t len) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string out(len * 2, '0');
    for (size_t i = 0; i < len; ++i) {
        out[i * 2] = digits[data[i] >> 4];
        out[i * 2 + 1] = digits[data[i] & 0x0f];
    }
    return out;
}

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
            extract_string(obj, "public_key_uncompressed_hex"),
            extract_string(obj, "keccak256_pubkey_without_04"),
            extract_string(obj, "payload25_hex"),
            extract_string(obj, "tron_base58_address"),
            extract_string(obj, "prefix2"),
            extract_string(obj, "suffix5"),
        });
    }
    if (vectors.empty()) throw std::runtime_error("no vectors parsed");
    return vectors;
}

int main(int argc, char** argv) {
    const std::string path = argc >= 2 ? argv[1] : "tests/phase0_test_vectors.json";
    const auto vectors = parse_vectors(read_file(path));

    std::vector<std::string> failures;
    int passed = 0;

    uint8_t digest[32];
    if (!tron_device::keccak256_single_block(nullptr, 0, digest)) {
        failures.push_back("keccak empty failed");
    } else if (bytes_to_hex(digest, 32) != "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470") {
        failures.push_back("keccak empty mismatch");
    }
    if (!tron_device::sha256_single_block(nullptr, 0, digest)) {
        failures.push_back("sha256 empty failed");
    } else if (bytes_to_hex(digest, 32) != "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855") {
        failures.push_back("sha256 empty mismatch");
    }

    for (const auto& vector : vectors) {
        bool ok = true;
        auto fail = [&](const std::string& reason) {
            ok = false;
            failures.push_back(vector.label + ": " + reason);
        };

        if (vector.public_key_uncompressed_hex.rfind("04", 0) != 0) {
            fail("public key missing 04");
            continue;
        }

        const auto pubkey = hex_to_bytes(vector.public_key_uncompressed_hex.substr(2));
        if (pubkey.size() != 64) {
            fail("pubkey length mismatch");
            continue;
        }

        uint8_t payload25[25];
        uint8_t keccak_out[32];
        if (!tron_device::payload25_from_public_key64(pubkey.data(), payload25, keccak_out)) {
            fail("payload25_from_public_key64 failed");
            continue;
        }

        if (bytes_to_hex(keccak_out, 32) != vector.keccak256_pubkey_without_04) {
            fail("keccak mismatch");
        }
        if (bytes_to_hex(payload25, 25) != vector.payload25_hex) {
            fail("payload25 mismatch");
        }

        char address[tron_device::BASE58_MAX_LEN];
        int address_len = tron_device::base58_encode_payload25(payload25, address);
        if (address_len <= 0) {
            fail("base58 encode failed");
        } else if (std::string(address, address_len) != vector.tron_base58_address) {
            fail("base58 address mismatch");
        }

        const uint64_t suffix_expected =
            tron_device::suffix_value_from_base58_suffix(vector.suffix5.c_str(), static_cast<int>(vector.suffix5.size()));
        const uint64_t suffix_actual =
            tron_device::payload25_mod_suffix_base(payload25, static_cast<int>(vector.suffix5.size()));
        if (suffix_expected != suffix_actual) {
            fail("suffix modulo mismatch");
        }

        if (!tron_device::base58_prefix_range_filter(
                payload25,
                vector.prefix2.c_str(),
                static_cast<int>(vector.prefix2.size()),
                static_cast<int>(vector.tron_base58_address.size()))) {
            fail("prefix range mismatch");
        }

        if (!tron_device::address_matches_filter(
                payload25,
                vector.tron_base58_address.c_str(),
                static_cast<int>(vector.tron_base58_address.size()),
                2,
                5)) {
            fail("full filter mismatch");
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
    std::cout << "    \"Device-compatible core validation only; no CUDA kernel or benchmark is run.\",\n";
    std::cout << "    \"No random private keys are generated.\",\n";
    std::cout << "    \"This validates fixed-array Keccak, SHA256, payload25, Base58, prefix range, suffix modulo, and full confirm.\"\n";
    std::cout << "  ]\n";
    std::cout << "}\n";

    return failures.empty() ? 0 : 1;
}
