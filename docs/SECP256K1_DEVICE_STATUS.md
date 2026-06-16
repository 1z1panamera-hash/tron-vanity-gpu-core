# secp256k1 Device-Compatible Status

Date: 2026-06-17

This file tracks the fixed-limb migration step for secp256k1.

## Added

- `src/secp256k1_device.cuh`
- `tests/verify_secp256k1_device_compatible.cpp`

## Implemented

- Fixed `UInt256` / `UInt512` arithmetic.
- Field addition, subtraction, multiplication, reduction, and inversion.
- secp256k1 point addition and scalar multiplication.
- Public key derivation from fixed TEST_ONLY scalar.
- Full chain into existing device-compatible TRON payload/Base58/filter layer.

## Validation

The verifier must pass Phase 0 public vectors:

```text
tests/verify_secp256k1_device_compatible.cpp
```

## Still Missing

- Actual CUDA kernel using this code on GPU.
- Performance-oriented secp256k1 implementation.
- Sharded candidate generation.
- RunPod image build and benchmark.

This is correctness migration work, not GPU performance evidence.
