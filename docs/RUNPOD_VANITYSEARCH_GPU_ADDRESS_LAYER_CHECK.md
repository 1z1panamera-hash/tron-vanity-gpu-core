# RunPod VanitySearch TRON GPU Address Layer Check

## Purpose

This is the next low-cost RunPod gate for the VanitySearch adaptation path.

By default it checks only the GPU-side TRON address construction layer:

- Keccak-256 over the uncompressed secp256k1 public key without `04`
- TRON payload prefix `0x41`
- double-SHA256 checksum
- Base58Check encoding
- product matching rule: suffix-only last 5 Base58Check characters
- four public TEST_ONLY public-key vectors

It is not a search benchmark and cannot be used as an address generation speed result.

An optional smoke can also compile patched VanitySearch and run a bounded TRON wildcard GPU search startup check. A separate optional benchmark signal can run a 10 second bounded TRON pattern benchmark and print JSON. These are still not final Serverless average/P90 proof.

## Candidate Patch

Tracked patch in this repository:

```text
patches/vanitysearch_tron_gpu_suffix_only_20260618.patch
```

SHA-256:

```text
895c8a9fad06fe9a9de691920f21eb45919b1d6353ec440a78323b3b5ad6c841
```

Candidate branch head:

```text
0fa8a36 Switch TRON GPU pattern to suffix-only
```

The TRON GPU search path is being updated to parse `T*<five-char-suffix>` into the current suffix-only product rule. It must compute the double-SHA256 checksum before judging the last 5 Base58Check characters; matching from Keccak output alone is invalid.

The hot path now derives the TRON payload directly from VanitySearch's GPU x/y coordinate words, instead of first materializing a 64-byte public-key array and then hashing that array. The RunPod vector check compares the direct x/y Keccak absorption path with the public-key reference path through the `xy_payload_passed` field.

The previous prefix-gated checksum optimization was for the old rule and is historical. The current suffix-only path needs a new hot-path benchmark because removing prefix gating changes where checksum and suffix work are paid.

The optional pattern smoke sets `TRON_SUPPRESS_SECRET_OUTPUT=1` before running VanitySearch. If an accidental hit happens during the bounded smoke, WIF/HEX key material is suppressed instead of printed.

The optional bounded benchmark also sets `TRON_SUPPRESS_SECRET_OUTPUT=1`, limits runtime to 3-30 seconds, and reports `candidate_attempts_per_second_estimate` from VanitySearch's GPU Mkey/s output. The patch corrects TRON counters to count complete TRON address candidates (`STEP_SIZE * nbThread`) instead of the generic Bitcoin 6x endomorphism/symmetry count. It is a GPU Pod direction signal, not final production proof.

## RunPod Command

On a short-lived CUDA-capable RunPod Pod, from this repository:

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 CUDA_ARCH=sm_80 scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

Expected success marker:

```text
tron_gpu_address_layer_script_passed
tron_gpu_vector_fields_verified
```

Optional wildcard search startup smoke:

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 RUN_TRON_PATTERN_SMOKE=1 CUDA_ARCH=sm_80 scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

Expected extra success marker:

```text
tron_gpu_pattern_smoke_passed
```

Optional bounded pattern benchmark:

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 RUN_TRON_PATTERN_BENCHMARK=1 CUDA_ARCH=sm_80 scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

Expected extra success marker:

```text
tron_gpu_pattern_benchmark_passed
```

## Safety

- The script refuses to run unless `ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1` is set.
- The script verifies the patch SHA-256 before applying it.
- The script refuses to overwrite an existing work directory.
- The GPU vector check must report all current per-vector boolean gates as `true` before any benchmark result is trusted, especially suffix and full Base58Check confirmation gates.
- The wrapper parses the vector JSON and prints `tron_gpu_vector_fields_verified` only after those fields are confirmed.
- The optional wildcard smoke uses the strict suffix-only test pattern and suppresses key material if an accidental hit occurs.
- The optional wildcard smoke defaults to 5 seconds and may print a best-effort `tron_gpu_pattern_smoke_rate` line; this is only a startup signal.
- The optional bounded benchmark defaults to 10 seconds, refuses durations outside 3-30 seconds, and emits JSON for review.
- The optional bounded benchmark rate is corrected to complete TRON address candidates per second, not raw hash speed and not the old generic 6x VanitySearch counter.
- The suffix modulo prefilter is an optimization gate, not proof of final production speed.
- Do not run this on `47.80.70.211`.
- Do not run a search benchmark from this check.
- Do not treat this as proof of production speed.
- Do not output scalar material, mnemonic, seed, token, or secret values.

## Next Gate

After this passes on RunPod, inspect the bounded benchmark JSON locally and compare it with the `58^5` target space. If it is promising, replace this signal path with a dedicated benchmark-only worker and then run controlled GPU-class comparisons.

Local inspection command:

```bash
scripts/inspect_vanitysearch_benchmark.py vanitysearch_benchmark_stdout.txt
```
