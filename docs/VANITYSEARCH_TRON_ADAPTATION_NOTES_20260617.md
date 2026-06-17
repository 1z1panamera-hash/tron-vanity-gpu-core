# VanitySearch TRON Adaptation Notes 2026-06-17

## Decision

Use `VanitySearch` as the first performance architecture to test, not as a direct production drop-in.

Reason: it is already a CUDA vanity-search architecture with secp256k1 point walking and GPU prefix lookup. The current in-house core is too slow to keep optimizing.

## Source Snapshot

- Upstream: `https://github.com/JeanLucPons/VanitySearch`
- Local audit copy: `工作记录/candidate-cores/VanitySearch`
- Audited commit: `c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b`
- License: GPLv3

## Important License Note

Do not copy VanitySearch source into the main `tron-vanity-gpu-core` repository until the distribution/license decision is explicit.

For the first two-day sprint, keep it as a local candidate source and document patch points. If we create a derivative and distribute it, GPLv3 obligations apply.

## Hot Path Observed

Main GPU flow:

- `GPU/GPUCompute.h`
  - `ComputeKeysComp`
  - `CheckHashComp`
  - `CheckPoint`
- `GPU/GPUHash.h`
  - SHA256 + RIPEMD160 device implementation
  - `_GetHash160Comp`
  - `_GetHash160`
- `GPU/GPUBase58.h`
  - `_GetAddress`
  - GPU-side Base58Check for Bitcoin P2PKH/P2SH
- `GPU/GPUEngine.cu`
  - kernel launch selection
  - result extraction
- `Vanity.cpp`
  - CPU-side verification and final private-key output
- `SECP256K1.cpp`
  - CPU-side address construction and verification

## TRON Changes Needed

### Device Hot Path

Replace Bitcoin Hash160 path:

```text
public_key -> SHA256 -> RIPEMD160 -> Bitcoin payload -> Base58Check
```

with TRON path:

```text
uncompressed public_key[1:65] -> Keccak-256 -> last 20 bytes -> 0x41 payload -> Base58Check
```

Required device additions:

- Keccak-256 implementation for 64-byte uncompressed public key body.
- TRON payload builder: 21 bytes, first byte `0x41`.
- Existing double-SHA256 checksum logic can be reused for Base58Check checksum.
- Prefix/suffix matcher must compare full TRON Base58 address, not only hash prefix.

### Matching Rule

Default production rule:

- `prefix_len = 2`
- `suffix_len = 5`
- Prefix is counted on the full TRON Base58 address, usually including leading `T`.

For `TX8888888888888888888888888886666`, target prefix/suffix are:

- prefix: `TX`
- suffix: `86666`

### CPU Verification

Every GPU hit must be verified on CPU using the existing Phase 0 reference logic before returning a result.

Required CPU check:

```text
candidate private scalar -> secp256k1 public key -> TRON Base58Check address -> exact prefix/suffix match
```

### Private Key Handling

VanitySearch currently prints/writes WIF/HEX private keys on match. That cannot be used as-is.

Production wrapper rules:

- No plaintext private key in stdout.
- No plaintext private key in logs.
- No plaintext private key persisted to files.
- Hit must be passed to age encryption flow before returning to controller.
- Benchmark mode must not return private key at all.

## Patch Strategy

### Phase A: Build Baseline Unmodified

Use a low-cost RunPod GPU Pod.

Goal:

- Confirm upstream compiles with modern CUDA.
- Run upstream `-check` if available.
- Record baseline MKey/s on a cheap card.

Do not run production TRON benchmark in this phase.

Status on 2026-06-17:

- A40 base Ubuntu image lacked `nvcc`, so it was stopped and terminated.
- A100 CUDA image compiled upstream VanitySearch successfully.
- Upstream Bitcoin vanity baseline on A100 reached about `4.1` to `4.8` billion keys/s.
- This validates the architecture class, but does not count as TRON address/s.
- Detailed record: `docs/RUNPOD_VANITYSEARCH_BASELINE_20260617.md`.

### Phase B: CPU TRON Mode Skeleton

Add a local TRON address function to candidate branch:

- public key to TRON address
- known test vectors
- exact prefix/suffix matching

This can be checked without GPU.

Status on 2026-06-17:

- Local candidate branch `tron-cpu-address-prototype` was created under `工作记录/candidate-cores/VanitySearch`.
- Local commit `221922d` adds CPU-side Keccak-256, `Secp256K1::GetTronAddress`, and a `-ct` command that prints only a TRON address.
- Mac ARM local compile is blocked by upstream Makefile x86 `-mssse3`; this needs a short RunPod x86 Linux compile/correctness check.
- Detailed record: `docs/VANITYSEARCH_PROTOTYPE_STATUS_20260617.md`.

### Phase C: GPU TRON Hash Path

Add device Keccak and TRON address payload path.

Minimum target:

- GPU result candidates must pass CPU verification.
- Benchmark reports `complete_tron_addresses_per_second`.

### Phase D: Short GPU Benchmark

Only after correctness:

- 5-second cheap GPU benchmark
- 10-second strong GPU benchmark if cheap GPU result is promising

Stop if strong GPU remains below `1e8` complete TRON address attempts/s.

## Expected Risk

- Keccak on GPU may become the new hot-path cost.
- Full Base58 suffix matching is more expensive than Bitcoin hash-prefix lookup.
- Prefix/suffix matching may require generating full Base58 for candidates, reducing speed.
- Claims like `80B/s` may not be complete TRON Base58 address attempts/s.

## Current Recommendation

Proceed with VanitySearch only as a performance-prototype branch.

Do not productize until:

- License decision is explicit.
- Private key output is removed or encrypted.
- CPU test vectors verify every GPU hit.
- RunPod benchmark reports complete TRON address attempts/s.
