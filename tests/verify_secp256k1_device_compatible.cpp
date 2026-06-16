#include <fstream>
#include <iostream>
#include <regex>
#include <sstream>
#include <string>
#include <vector>

#include "../src/secp256k1_device.cuh"
#include "../src/tron_core_device.cuh"

struct VectorCase {
    std::string label;
    std::string private_key_hex;
    std::string public_key_uncompressed_hex;
    std::string payload25_hex;
    std::string tron_base58_address;
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

secp256k1_device::UInt256 scalar_from_hex(const std::string& hex) {
    if (hex.size() != 64) throw std::runtime_error("expected 32-byte scalar");
    auto bytes = hex_to_bytes(hex);
    secp256k1_device::UInt256 out;
    secp256k1_device::zero(out);
    for (int i = 0; i < 32; ++i) {
        int byte_from_right = 31 - i;
        int limb_index = i / 4;
        int shift = (i % 4) * 8;
        out.limb[limb_index] |= static_cast<uint32_t>(bytes[byte_from_right]) << shift;
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
            extract_string(obj, "private_key_hex"),
            extract_string(obj, "public_key_uncompressed_hex"),
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
    std::vector<std::string> failures;
    int passed = 0;

    for (const auto& vector : vectors) {
        bool ok = true;
        auto fail = [&](const std::string& reason) {
            ok = false;
            failures.push_back(vector.label + ": " + reason);
        };

        auto scalar = scalar_from_hex(vector.private_key_hex);
        uint8_t public_key64[64];
        if (!secp256k1_device::private_key_to_public_key64(scalar, public_key64)) {
            fail("private_key_to_public_key64 failed");
            continue;
        }

        const std::string pubkey_hex = "04" + bytes_to_hex(public_key64, 64);
        if (pubkey_hex != vector.public_key_uncompressed_hex) {
            fail("public key mismatch");
            continue;
        }

        uint8_t payload25[25];
        uint8_t keccak_out[32];
        if (!tron_device::payload25_from_public_key64(public_key64, payload25, keccak_out)) {
            fail("payload25_from_public_key64 failed");
            continue;
        }
        if (bytes_to_hex(payload25, 25) != vector.payload25_hex) {
            fail("payload25 mismatch");
        }

        char address[tron_device::BASE58_MAX_LEN];
        int address_len = tron_device::base58_encode_payload25(payload25, address);
        if (address_len <= 0) {
            fail("base58 encode failed");
        } else if (std::string(address, address_len) != vector.tron_base58_address) {
            fail("address mismatch");
        }

        if (!tron_device::address_matches_filter(
                payload25,
                vector.tron_base58_address.c_str(),
                static_cast<int>(vector.tron_base58_address.size()),
                2,
                5)) {
            fail("filter mismatch");
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
    std::cout << "    \"Device-compatible secp256k1 full-chain validation only; no CUDA kernel or benchmark is run.\",\n";
    std::cout << "    \"Only public TEST_ONLY vectors are used.\",\n";
    std::cout << "    \"This validates fixed-limb scalar to public key to TRON Base58 address.\"\n";
    std::cout << "  ]\n";
    std::cout << "}\n";

    return failures.empty() ? 0 : 1;
}
