# Core Algorithm Status

Date: 2026-06-17

This status file tracks progress from CPU reference toward a real CUDA core.

## Completed In Host-Validated C++

- Keccak-256 with Ethereum/TRON padding.
- SHA-256.
- TRON payload25 checksum: `0x41 + address20 + checksum4`.
- Base58Check encoding and payload25 decoding.
- Base58 suffix modulo filter.
- Base58 prefix range filter.
- Full Base58Check confirm after filters.
- Phase 0 vector validation entrypoint: `tests/verify_core_algorithms.cpp`.

## secp256k1 Host Reference

`src/secp256k1_host_reference.hpp` now provides a pure C++ host-side correctness reference. It is validated by `tests/verify_secp256k1_full_chain.cpp` against Phase 0 vectors.

This is not the GPU implementation.

## Still Not Completed

- Actual CUDA kernel execution of secp256k1 on GPU hardware.
- candidate scalar sharding inside GPU kernel.
- RunPod image build.
- RunPod benchmark.

## Device-Compatible Progress

`src/tron_core_device.cuh` now contains fixed-array implementations intended for CUDA device use:

- Keccak-256 single-block path for public keys.
- SHA-256 single-block path for payload/checksum.
- payload25 generation from public key.
- Base58Check encoding.
- suffix modulo filter.
- prefix range filter.
- full prefix/suffix confirm.

These functions are validated from host C++ by `tests/verify_device_compatible_algorithms.cpp`.

## Rule

No GPU speed number is acceptable until:

1. device code implements the full chain,
2. Phase 0 vectors pass,
3. benchmark reports complete TRON `addresses_per_second`,
4. output contains no plaintext key material or credential material.
