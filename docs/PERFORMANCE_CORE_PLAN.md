# Performance Core Plan

Goal: move from correctness-first CUDA code toward a worker that can realistically approach TRON suffix-only product rule `suffix=5 chars` within 5 seconds on average, with P90 no more than 8 seconds, using RunPod GPUs.

The product no longer matches any prefix after fixed `T`. It matches only the last 5 Base58Check characters. The Python wrapper maps product input to internal full-address `prefix_len=0`, `suffix_len=5` for the CUDA binary. Capacity math is therefore `58^5`.

The speed sprint passed on 2026-06-18 with about `1.543B attempts/s` on RTX PRO 6000 Blackwell. Treat `200M attempts/s` as the minimum engineering pass gate and `300M+ attempts/s` as the preferred regression buffer. Current priority has shifted to Serverless migration: patched VanitySearch worker packaging, production `find`, age-encrypted return, and cold/warm end-to-end timing.

## Why Current Code Is Not Enough

The current benchmark smoke path computes each candidate as:

```text
private scalar -> secp256k1 scalar multiply -> public key -> TRON address
```

That is correct for validation, but it is too expensive for the final target.
It is useful for proving the chain, not for claiming RTX 5090/A100 capacity.

## Required Performance Direction

Use incremental public-key walking:

```text
base_private = shard_seed + shard_offset
base_public = base_private * G
candidate_i_private = base_private + i
candidate_i_public = base_public + i * G
```

Then each next candidate can be derived with elliptic-curve point addition instead of a full scalar multiplication.

## Current Implementation Status

- `src/tron_gpu_core.cu` now has an `incremental` benchmark mode.
- `app.py` passes `kernel_mode`, defaulting to `incremental`.
- `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json` sets `kernel_mode = incremental`.
- Current incremental mode computes one base scalar multiplication per CUDA thread.
- The stride point is precomputed once per kernel launch on the host and passed through `BenchmarkConfig`.
- Subsequent candidates in the same thread use elliptic-curve point addition by that shared stride point.
- Attempts are accumulated per CUDA thread and committed to the global counter once per thread, avoiding one global atomic operation per candidate in the incremental benchmark loop.
- Prefix range bounds and suffix target values are precomputed once in `BenchmarkConfig`, so each candidate avoids reparsing target Base58 prefix/suffix strings inside the GPU loop.
- The incremental CUDA benchmark kernel now uses cooperative block-level batch inversion for same-stride point additions, so a block can share one inversion pass across point updates while each CUDA thread still computes its own point output.
- The VanitySearch TRON suffix-only patch now avoids per-candidate payload25 assembly for the common non-hit path. It computes checksum4, compares the last-5 Base58 value with a payload21+checksum chunked modulo path, and only builds payload25/Base58 when a rare suffix candidate passes.
- The suffix modulo path now uses fixed-modulus reduction for `58^5`, replacing the hot `% 656356768` operation with reciprocal high-multiply plus bounded subtraction.
- The hot checksum path now keeps the second SHA256 result as a big-endian 32-bit word, avoiding a per-candidate `checksum4[4]` local array and full second digest writeback before suffix comparison.
- The checksum path now builds the two fixed-length SHA256 message schedules directly for `payload21` and the 32-byte first digest, avoiding generic `block[64]` zero/copy/parse work.
- The second SHA256 message schedule now reuses the first digest state directly, avoiding an extra `first[8]` temporary array in the checksum hot path.
- The direct x/y Keccak path now packs public-key coordinates into Keccak state lanes directly, replacing per-byte absorption calls for the 64-byte public key body.
- The GPU hit path now returns the 20-byte TRON address body directly after suffix match instead of doing full Base58 confirmation in the kernel. CPU-side verification still reconstructs the full TRON address before accepting a hit.
- The VanitySearch patch exposes `STEP_SIZE` as a compile-time Makefile override so RunPod sweeps can test larger per-thread batches without editing source code.
- `tests/verify_incremental_walking.cpp` validates that walked public keys match direct scalar multiplication for small deterministic candidates.
- `tests/verify_batch_inversion.cpp` validates the device-compatible batch inversion primitive used by the benchmark kernel.
- `tests/verify_batch_point_add.cpp` validates that same-stride affine point additions can share one batch inversion while matching direct `point_add` outputs.

This is the first performance-oriented implementation path. It still needs RunPod `nvcc` compilation and CUDA vector validation before benchmark results are trusted.

## GPU Work per Candidate

The target fast path should do:

1. Increment public key using point addition or a precomputed window table.
2. Keccak-256 of uncompressed public key without `04`.
3. TRON payload and double-SHA256 checksum.
4. Base58 suffix modulo filter over the full payload including checksum.
5. Full Base58Check confirmation only for candidates passing filters.

## Sharding

Workers must not overlap.

Recommended shard model:

```text
global_worker_id = endpoint_worker_index or externally assigned shard_id
candidate_range = [start_counter + global_worker_id * stride, ...)
```

Each RunPod worker gets:

- `job_id`
- `suffix`
- derived `target_address`
- derived full-address `prefix_len = 0`
- derived `suffix_len = 5`
- `start_counter`
- `shard_id`
- `shard_count`
- `duration_seconds`

## Active Hit Delivery Work

Age/find delivery work has resumed now that the suffix-only speed gate is above the `200M attempts/s` engineering minimum. The current production flow must remain simple:

1. VanitySearch handles the CUDA-heavy suffix-only search.
2. The C++ worker emits a compact internal JSON hit only when explicitly requested.
3. `app.py` parses that internal hit and age-encrypts the key value.
4. The API response returns only `matched_address`, `encrypted_private_key`, and non-sensitive metadata.

The continuing performance focus is:

1. secp256k1 point walking and point-add throughput.
2. Larger `STEP_SIZE` and grid/batch settings that actually saturate the GPU.
3. GPU utilization proof with `nvidia-smi`; low utilization means kernel launch, batch size, or occupancy is still wrong.
4. Profiler-driven bottleneck isolation with `nsys` or `nvprof`.
5. Suffix-only checksum/Base58 hot-path reduction.
6. Repeat short RunPod GPU Pod measurements after each change.

## Validation Gates

Before claiming performance:

1. Phase 0 public vectors pass on CPU reference.
2. CUDA `validate_vectors` passes on RunPod.
3. Host-side incremental walking validation passes.
4. Benchmark smoke emits `gpu_name` and complete `addresses_per_second`.
5. A100 and RTX 5090 tests use the same target rule and output schema.
6. The output is inspected for absence of `private_key`, `mnemonic`, `seed`, `token`, and `secret`.
7. Final performance evidence must report mean time to match and P90 time to match for the `58^5` rule.

## If Smoke Speed Is Low

Do not scale worker count from the `scalar` kernel mode.
Use `incremental` mode first. It now includes cooperative block-level batch inversion. If incremental mode is still too slow, the next step is suffix-only checksum/Base58 hot-path reduction, projective/precomputed-window point walking, then lower-level field arithmetic optimization, then measure again.

Use `scripts/runpod_gpu_pod_suffix_speed_sweep.sh` on a normal RunPod GPU Pod to compare grid settings and optionally collect `nsys` / `nvprof` output. This script is gated by `ALLOW_RUNPOD_SUFFIX_SPEED_SWEEP=1` and must not be run on `47.80.70.211`.
