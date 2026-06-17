# VanitySearch Prototype Status 2026-06-17

## Local Candidate Branch

This work is in the separate candidate source checkout, not in the main `tron-vanity-gpu-core` repository.

- Candidate path: `工作记录/candidate-cores/VanitySearch`
- Branch: `tron-cpu-address-prototype`
- Local commits:
  - `221922d Add local TRON CPU address prototype`
  - `55470e4 Add RunPod TRON CPU vector check`
- Upstream base: `c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b`
- Pushed to GitHub: no
- Exported local patch:
  - `工作记录/vanitysearch_tron_cpu_prototype_20260617.patch`
  - SHA-256: `22cc774726d904e01afecb83684303c750ea03ad565b9182469a270e0c7c6a6c`

Reason: VanitySearch is GPLv3. Keep derivative source separate until the license and distribution decision is explicit.

## What Changed In The Candidate Branch

- Added CPU-side Keccak-256 helper:
  - `hash/keccak256.h`
  - `hash/keccak256.cpp`
- Added `Secp256K1::GetTronAddress(Point &pubKey)`.
- Added command-line test entry:
  - `-ct privKey`
  - computes and prints only the TRON address.
  - does not print WIF, HEX private key, mnemonic, token, or secret.
- Added TRON address output to existing public-key/address inspection paths for local diagnosis.
- Added RunPod/x86 Linux correctness script:
  - `scripts/runpod_verify_tron_cpu_vectors.sh`
  - builds CPU VanitySearch,
  - runs 4 public TEST_ONLY TRON vectors,
  - fails if output contains `Priv`, `WIF`, `HEX`, `private_key`, `mnemonic`, `seed`, `token`, or `secret`.

## Intended Test

Use public TEST_ONLY Phase 0 vectors only.

Example shape:

```sh
./VanitySearch -ct 0000000000000000000000000000000000000000000000000000000000000001
```

Expected output shape:

```text
Addr (TRON): TMVQGm1qAQYVdetCeGRRkTWYYrLXuHK2HC
```

Do not use real customer private keys in this prototype.

Preferred RunPod check:

```sh
scripts/runpod_verify_tron_cpu_vectors.sh
```

RunPod handoff doc:

```text
docs/RUNPOD_VANITYSEARCH_CPU_VECTOR_CHECK.md
```

## Local Compile Result

Local Mac compile did not complete because the original VanitySearch Makefile defaults to x86 SSE flags:

```text
clang++: error: unsupported option '-mssse3' for target 'arm64-apple-darwin25.5.0'
```

This is a local Mac architecture/toolchain blocker, not a GPU benchmark result.

No search was run. No benchmark was run. No RunPod API call was made. `47.80.70.211` was not touched.

## Next RunPod Use Point

RunPod is next needed only for a short compile/correctness check on an x86 Linux CUDA image.

Recommended next pod:

- Normal GPU Pod, not Serverless.
- CUDA devel image similar to the A100 baseline image.
- Low-cost GPU is enough for compile/correctness.
- Do not start a long benchmark.
- Run only:
  - compile candidate branch,
  - `scripts/runpod_verify_tron_cpu_vectors.sh`,
  - optional 5-second upstream or TRON prototype smoke test after correctness passes.

## Not Yet Done

- GPU TRON Keccak path not implemented in VanitySearch.
- GPU TRON Base58Check prefix/suffix matcher not implemented in VanitySearch.
- Plaintext private-key output is not yet removed from normal VanitySearch match flow.
- No complete TRON addresses/s benchmark exists for the VanitySearch prototype.

## Stop Conditions

Stop before spending more GPU time if:

- CPU TRON vector output does not match Phase 0 vectors.
- The candidate branch cannot compile cleanly on RunPod x86 Linux.
- The normal match flow still prints plaintext private keys during TRON mode.
- Any result is only key/s or hash/s and not complete TRON address attempts/s.
