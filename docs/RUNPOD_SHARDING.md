# RunPod Sharding Strategy

Goal: make product rule `suffix=5` feasible by running many independent GPU workers.

Python maps this to internal full-address `prefix_len=0` plus `suffix_len=5`.

## Search Space

`58^5 = 656,356,768`

Target rates:

- Average <= 5 seconds: about `131.27M complete TRON addresses/s`
- P90 <= 8 seconds: about `188.91M complete TRON addresses/s`

## Shard Rule

For `shard_count` workers and 0-based `shard_id`:

```text
candidate_scalar = start_counter + local_attempt * shard_count + shard_id + 1
```

Every worker gets a disjoint scalar sequence when `shard_id` is unique.

The controller must not launch two live workers with the same `(job_id, shard_id, shard_count, start_counter)`.

## Incremental Kernel Schedule

For a CUDA launch:

```text
global_idx = blockIdx.x * blockDim.x + threadIdx.x
total_threads = gridDim.x * blockDim.x
first_candidate = start_counter + global_idx * shard_count + shard_id + 1
step_scalar = total_threads * shard_count
candidate_k = first_candidate + k * step_scalar
```

For multiple batches:

```text
batch_start_counter = original_start_counter + launched_attempts * shard_count
```

The CPU-side schedule test `tests/verify_shard_schedule.cpp` validates that shard, batch, and thread-stride coverage has no duplicate candidates and no gaps for tested small configurations.

## Worker Payload

```json
{
  "mode": "benchmark",
  "target_address": "T...",
  "suffix": "86666",
  "kernel_mode": "incremental",
  "duration_seconds": 5,
  "max_attempts": 1024,
  "start_counter": 0,
  "shard_id": 0,
  "shard_count": 1
}
```

## Result Aggregation

The controller sums attempts across workers:

```text
total_addresses_per_second = sum(worker.attempts) / wall_clock_seconds
```

It must use complete TRON address attempts only, not hash attempts.

## Production Key Handling

Benchmark mode must never return plaintext private keys.

Production mode must encrypt a hit private key with the customer's `age` recipient before returning:

- `matched_address`
- `encrypted_private_key`

The controller must not store plaintext private keys or customer age identities.
