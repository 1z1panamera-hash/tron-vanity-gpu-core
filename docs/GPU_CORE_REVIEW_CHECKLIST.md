# GPU Core Review Checklist

Do not run real speed tests until every item is satisfied.

## Correctness

- Host-side C++ core algorithm validation passes Phase 0 vectors.
- Device-compatible fixed-array core algorithm validation passes Phase 0 vectors.
- Host-side C++ secp256k1 full-chain validation passes Phase 0 vectors.
- Device-compatible fixed-limb secp256k1 full-chain validation passes Phase 0 vectors.
- secp256k1 scalar multiplication is implemented or integrated from auditable source.
- CUDA `validate_vectors_kernel` compiles with `nvcc`.
- CUDA `validate_vectors_kernel` passes Phase 0 vectors on GPU hardware.
- Keccak-256 is Keccak, not NIST SHA3-256.
- TRON address uses `0x41 + last20(keccak(pubkey_without_04))`.
- Checksum is first 4 bytes of double SHA256 over 21-byte TRON payload.
- Base58 suffix modulo matches Phase 0 reference.
- Base58 prefix range matches Phase 0 reference.
- Full Base58Check confirmation is kept after filters.
- Phase 0 public vectors pass exactly.

## Benchmark Integrity

- `attempts` counts complete TRON addresses, not hashes.
- `addresses_per_second` equals `attempts / elapsed_seconds`.
- Result includes elapsed time.
- GPU name should be added when reliable runtime detection is available.
- Result does not include plaintext private key.
- Result does not include mnemonic, seed, token, or secret.
- Benchmark is blocked unless `ALLOW_GPU_BENCHMARK=1` is explicitly set on the approved RunPod endpoint.

## Security

- No unreviewed external binaries.
- No `.env` or API key reads in worker code.
- RunPod API key is never written to project files.
- Production output uses age encryption before returning key material.
- Logs do not print key material.

## Operations

- 47.80.70.211 is not used for GPU or brute-force generation.
- 47.80.70.211 only stores project files and coordinates API work.
- Existing ports 8000, 8001, and 18022 are not affected.
