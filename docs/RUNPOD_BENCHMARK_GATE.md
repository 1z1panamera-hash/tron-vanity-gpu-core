# RunPod Benchmark Gate

This document defines the first GPU benchmark gate for the TRON vanity worker.

## Current Status

- `validate_vectors` must pass on RunPod before any benchmark request is accepted as meaningful.
- `benchmark` is blocked unless the worker environment sets `ALLOW_GPU_BENCHMARK=1`.
- The current benchmark path counts complete TRON address attempts:
  - secp256k1 private scalar to public key
  - Keccak-256
  - TRON payload/checksum
  - Base58Check
  - prefix/suffix match
- Default `kernel_mode` is `incremental`, which uses one base scalar multiplication per thread and then point addition by stride.
- Incremental stride point is precomputed once per kernel launch on the host and passed to the kernel, so each CUDA thread does not repeat the same stride scalar multiplication.
- Incremental mode counts attempts with per-thread local accumulation, then one global atomic add per thread; this keeps the benchmark from measuring global atomic contention as the main bottleneck.
- Benchmark filters use precomputed Base58 prefix bounds and suffix target values from `BenchmarkConfig`; candidate loops must not reparse the target address for every candidate.
- Incremental point walking now uses cooperative block-level batch inversion for same-stride point additions, reducing the per-candidate affine inversion bottleneck while keeping per-thread point-output arithmetic parallel. `tests/verify_batch_inversion.cpp` and `tests/verify_batch_point_add.cpp` validate the primitive, and `src/tron_gpu_core.cu` wires it into the incremental benchmark kernel.
- `kernel_mode=scalar` is retained only as a correctness/performance comparison path.
- Input `kernel_mode=incremental` is expected to produce `benchmark_result.kernel_mode=incremental_public_key_walk`.
- Input `kernel_mode=scalar` is expected to produce `benchmark_result.kernel_mode=scalar_multiply_per_candidate`.
- It must report `addresses_per_second` and `keys_per_second`.
- It must not report hash-only speed as TRON address generation speed.

## Smoke Payload

Use `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json` only after CUDA vector validation passes.

The first benchmark request must stay small:

- `duration_seconds`: 5
- `max_attempts`: 1024
- `kernel_mode`: `incremental`
- `shard_id`: 0
- `shard_count`: 1

This first run is a container/handler/kernel smoke test, not a real 5090/A100 speed number.

The batch-inversion kernel path still needs RunPod `nvcc` compilation and `validate_vectors` success before any benchmark result is trusted.

## Sharding Rule

Each worker uses:

```text
candidate = start_counter + global_index * shard_count + shard_id + 1
```

This prevents overlap between workers when all workers share the same `start_counter` and `shard_count`, and each worker receives a unique `shard_id`.

## Safety Rules

- Do not output private key material.
- Do not output mnemonic, seed, token, secret, or API key material.
- Do not write RunPod API keys into files.
- Do not run this on 47.80.70.211.
- Do not run this on the local Mac.
- Do not increase `duration_seconds` or `max_attempts` until the small smoke test succeeds.

## Limitation

The current scalar generator is deterministic and intended for benchmark staging.
Production worker design still needs a final seed/shard policy and age encryption on match.
