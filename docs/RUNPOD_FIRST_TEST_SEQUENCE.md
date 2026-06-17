# RunPod First Test Sequence

This sequence avoids using 47.80.70.211 for build, compile, or benchmark work.

Preferred deployment path: RunPod GitHub integration, documented in `docs/RUNPOD_GITHUB_DEPLOY_PATH.md`.

## Goal

Measure whether RunPod GPUs can move toward the TRON full Base58 prefix2 + suffix5 target.

The first RunPod tests are not production key generation. They are:

1. CUDA compile and Phase 0 vector validation.
2. Tiny benchmark smoke test.
3. A100 short benchmark.
4. RTX 5090 short benchmark, if available.
5. Capacity calculation for 10 second probability targets.

## Required Image

Build from:

```bash
Dockerfile
```

`Dockerfile.cuda-validate` is an equivalent named backup for validate-only deployments.

The image must include:

- `app.py`
- `requirements.txt`
- `src/`
- `tests/phase0_test_vectors.json`

Do not put RunPod API keys, Docker passwords, private keys, tokens, or secrets in the image or project files.

If deploying through GitHub integration, set Dockerfile path to `Dockerfile`.

## Endpoint Environment

For validation only:

```text
ALLOW_RUNTIME_NVCC=1
```

Optional GPU-specific runtime compile override:

```text
CUDA_ARCH=sm_80
```

for A100, or:

```text
CUDA_ARCH=sm_120
```

for RTX 5090-class GPUs. If this is not set, the worker tries `native`, `sm_120`, then `sm_80`.

For the first benchmark smoke test, only after validation passes:

```text
ALLOW_RUNTIME_NVCC=1
ALLOW_GPU_BENCHMARK=1
```

## Request 1: Validate Vectors

Use `RUNPOD_VALIDATE_PAYLOAD.json`.

Expected response:

- `mode = validate_vectors`
- `phase0_vectors.passed = true`
- `compile.ready = true`
- `gpu_binary.returncode = 0`
- `passed = true`

If this fails, do not run benchmark.

## Request 2: Benchmark Smoke

Use `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json`.

First benchmark limits:

- `duration_seconds = 5`
- `max_attempts = 1024`
- `shard_count = 1`
- `shard_id = 0`

Expected response:

- `mode = benchmark`
- `benchmark_result.kernel_mode = incremental_public_key_walk`
- `benchmark_result.gpu_name` is present
- `benchmark_result.attempts` is positive
- `benchmark_result.addresses_per_second` is present
- no `private_key`, `mnemonic`, `seed`, `token`, or `secret`

This is only a smoke test. It is not a 10 second production capacity claim.

## Request 3: A100 Short Benchmark

Only after smoke passes, increase carefully:

- use `RUNPOD_A100_BENCHMARK_10S_PAYLOAD.json`
- `duration_seconds = 10`
- `max_attempts = 10000000000`
- still no production private key return

Record:

- GPU type
- attempts
- elapsed seconds
- addresses_per_second
- keys_per_second

## Request 4: RTX 5090 Short Benchmark

Repeat the same request on RTX 5090-class hardware with `RUNPOD_RTX5090_BENCHMARK_10S_PAYLOAD.json` if RunPod provides it.

Do not compare hash speed. Compare complete TRON `addresses_per_second`.
Do not compare `scalar` mode against production targets except as a sanity baseline.

## Capacity Formula

Default rule: full TRON Base58 `prefix_len=2` + `suffix_len=5`.

The leading `T` is fixed for normal TRON addresses, so the random part is only `T` after 1 variable prefix character plus 5 suffix characters.

Effective random search space:

```text
58^6 = 38,068,692,544
```

For total cluster speed `R` addresses/second and time `t = 10` seconds:

```text
hit_probability = 1 - exp(-(R * t) / 58^6)
```

Targets:

- 50% in 10s: about 2.64B addresses/s
- 90% in 10s: about 8.77B addresses/s
- 95% in 10s: about 11.40B addresses/s
- 99% in 10s: about 17.53B addresses/s

Required worker count:

```text
workers = ceil(target_total_addresses_per_second / measured_single_worker_addresses_per_second)
```

## Current Limitation

The current CUDA code uses deterministic scalar candidates and now defaults to incremental public-key walking.
If measured speed is too low, the next implementation step is a precomputed-window point walking core and lower-level field arithmetic optimization, not more server-side testing.
