# RunPod Suffix-Only Speed Sweep Result - RTX PRO 6000

Date: 2026-06-18 Asia/Shanghai

## Scope

Normal RunPod GPU Pod speed sweep for the current product rule:

- Match only the last 5 characters of the full TRON Base58Check address.
- No prefix after fixed `T` is matched.
- Search space: `58^5 = 656,356,768`.
- This is a GPU Pod speed signal, not a Serverless cold-start or P90 production proof.

## Pod

- GPU model: NVIDIA RTX PRO 6000 Blackwell Server Edition
- Driver: 580.126.09
- VRAM: 97,887 MiB
- CUDA toolkit path: `/usr/local/cuda-12.8`
- CUDA arch used: `sm_120`
- Pod id: `7sujnox2s2u8u2`
- Pod name: `clever_sapphire_finch`
- Template used: `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`
- Repo commit tested: `e12424dd5159d47d7730397b940ef05d8ae4080a`
- Pod status after test: stopped, then terminated
- Non-network volume: removed with pod termination

## Compatibility Fixes During Test

The RunPod image had CUDA 12.8 available, but `nvcc` was not on `PATH`.

The upstream VanitySearch source also needed C++ header compatibility fixes for the newer compiler:

- `Timer.h`
- `hash/sha256.h`
- `hash/sha512.h`

These fixes were added to the RunPod speed sweep script before patching VanitySearch. They do not change the TRON matching algorithm.

The benchmark safety scanner was also updated to allow the fixed environment variable name `TRON_SUPPRESS_SECRET_OUTPUT`; other sensitive output markers remain blocked.

## Vector Gate

Passed.

Required markers were present:

- `tron_gpu_address_layer_passed`
- `tron_gpu_address_layer_script_passed`

Per-vector public TEST_ONLY checks passed for 4 vectors:

- suffix match rule
- wrong suffix rejection
- fast suffix prefilter
- checksum-word suffix prefilter
- direct x/y Keccak payload path

## Speed Sweep

Command family:

```bash
ALLOW_RUNPOD_SUFFIX_SPEED_TEST=1 CUDA_ARCH=sm_120 BENCHMARK_SECONDS=3 \
  scripts/runpod_gpu_pod_suffix_speed_test.sh
```

Default sweep dimensions:

```text
SWEEP_STEP_SIZES="1024 2048 4096"
SWEEP_GRIDS="8,128 16,128 32,128 64,128 128,128"
```

Best result:

- `STEP_SIZE=4096`
- `grid=128,128`
- `candidate_attempts_per_second_estimate=1,543,280,000`
- Equivalent shorthand: about `1.543B attempts/s`

Other top results:

- `STEP_SIZE=2048`, `grid=128,128`: about `1.52654B attempts/s`
- `STEP_SIZE=1024`, `grid=128,128`: about `1.52652B attempts/s`
- `STEP_SIZE=4096`, `grid=64,128`: about `838.74M attempts/s`
- `STEP_SIZE=2048`, `grid=64,128`: about `838.75M attempts/s`
- `STEP_SIZE=1024`, `grid=64,128`: about `801.00M attempts/s`

## Goal Math

Using search space `58^5 = 656,356,768` and best speed `1,543,280,000 attempts/s`:

- Expected mean time: about `0.43s`
- P90 time: about `0.98s`

Target:

- Average <= 5s: passed
- P90 <= 8s: passed
- Engineering minimum `200M attempts/s`: passed
- Preferred `300M+ attempts/s`: passed

## Comparison With Historical 85.05M/s

Historical reference:

- Previous RTX PRO 6000 Blackwell result: about `85.05M complete TRON candidates/s`
- That result used the older `prefix_after_t + suffix5` rule and is historical evidence only.

Current suffix-only result:

- `1.54328B attempts/s`
- Relative improvement versus `85.05M/s`: about `18.15x`

## Decision

The suffix-only hot path is fast enough to move from CUDA speed sprint to Serverless migration preparation.

Do not treat this as final production proof yet. Remaining proof required:

- package this high-speed patched VanitySearch path into the Serverless image,
- ensure Python handler calls the high-speed binary rather than the older self-written scaffold,
- add/restore age encryption on the production find path,
- run a short Serverless smoke test,
- run repeated Serverless find tests to measure cold start, warm start, average, and P90.

## Safety

- No customer suffix was used.
- Benchmark used suffix `CDEFG`.
- `TRON_SUPPRESS_SECRET_OUTPUT=1` was used.
- No private key, mnemonic, seed, token, or secret was intentionally output.
- `47.80.70.211` was not used for compile, benchmark, or GPU work.
- The temporary RunPod Pod was stopped and terminated after the test.
