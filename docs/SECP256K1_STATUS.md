# secp256k1 Status

Date: 2026-06-17

This file tracks the secp256k1 portion of the GPU core.

## Added

- `src/secp256k1_host_reference.hpp`
- `tests/verify_secp256k1_full_chain.cpp`

## Completed

- Pure C++ host-side secp256k1 scalar multiplication reference.
- Phase 0 public test vectors can be verified from fixed TEST_ONLY scalar to:
  - uncompressed public key,
  - Keccak-256,
  - TRON hex address,
  - payload25,
  - Base58Check TRON address.

## Not Completed

- CUDA kernel integration.
- GPU benchmark.

## Device-Compatible Follow-Up

`src/secp256k1_device.cuh` now contains a fixed-limb migration of this reference. It is correctness-oriented and not yet performance-oriented.

## Rule

This is correctness reference work only. It is not performance evidence and must not be used to claim 5090/A100 speed.
