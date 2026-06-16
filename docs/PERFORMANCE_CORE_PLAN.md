# Performance Core Plan

Goal: move from correctness-first CUDA code toward a worker that can realistically approach TRON prefix2 + suffix5 within 10 seconds using RunPod GPUs.

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
- Current incremental mode computes one base scalar multiplication and one stride scalar multiplication per CUDA thread.
- Subsequent candidates in the same thread use elliptic-curve point addition by stride.
- Attempts are accumulated per CUDA thread and committed to the global counter once per thread, avoiding one global atomic operation per candidate in the incremental benchmark loop.
- `tests/verify_incremental_walking.cpp` validates that walked public keys match direct scalar multiplication for small deterministic candidates.

This is the first performance-oriented implementation path. It still needs RunPod `nvcc` compilation and CUDA vector validation before benchmark results are trusted.

## GPU Work per Candidate

The target fast path should do:

1. Increment public key using point addition or a precomputed window table.
2. Keccak-256 of uncompressed public key without `04`.
3. TRON payload and double-SHA256 checksum.
4. Base58 suffix modulo filter.
5. Base58 prefix range filter.
6. Full Base58Check confirmation only for candidates passing filters.

## Sharding

Workers must not overlap.

Recommended shard model:

```text
global_worker_id = endpoint_worker_index or externally assigned shard_id
candidate_range = [start_counter + global_worker_id * stride, ...)
```

Each RunPod worker gets:

- `job_id`
- `target_address`
- `prefix_len`
- `suffix_len`
- `start_counter`
- `shard_id`
- `shard_count`
- `duration_seconds`

## Production Hit Handling

For production, a hit must use age encryption before returning key material:

1. Worker finds `matched_address`.
2. Worker reconstructs the matching private scalar.
3. Worker encrypts private key using customer `age recipient`.
4. Worker returns only:
   - `matched_address`
   - `encrypted_private_key`

The worker must not log plaintext key material.
47.80.70.211 must not store plaintext key material or customer age identity.

## Validation Gates

Before claiming performance:

1. Phase 0 public vectors pass on CPU reference.
2. CUDA `validate_vectors` passes on RunPod.
3. Host-side incremental walking validation passes.
4. Benchmark smoke emits `gpu_name` and complete `addresses_per_second`.
5. A100 and RTX 5090 tests use the same target rule and output schema.
6. The output is inspected for absence of `private_key`, `mnemonic`, `seed`, `token`, and `secret`.

## If Smoke Speed Is Low

Do not scale worker count from the `scalar` kernel mode.
Use `incremental` mode first. If incremental mode is still too slow, the next step is a precomputed-window point walking core and lower-level field arithmetic optimization, then measure again.
