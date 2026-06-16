# Device Algorithm Status

Date: 2026-06-17

This file tracks migration from host-side C++ algorithms to CUDA-compatible fixed-array algorithms.

## Added

- `src/tron_core_device.cuh`
- `tests/verify_device_compatible_algorithms.cpp`

## Implemented In Device-Compatible Form

- Keccak-256 single-block path for 64-byte public keys.
- SHA-256 single-block path for 21-byte payload and 32-byte digest.
- TRON payload25 generation from uncompressed public key without `04`.
- Base58Check encoding for payload25.
- Base58 suffix modulo filter.
- Base58 prefix range filter.
- Full prefix/suffix confirmation after filters.

## Validation Rule

The verifier must pass the Phase 0 public vectors before any CUDA kernel uses these functions.

## Still Missing

- Actual CUDA kernel integration.
- GPU secp256k1 scalar multiplication.
- Candidate scalar sharding in device code.
- RunPod image build and benchmark.

This remains correctness work, not GPU performance evidence.
