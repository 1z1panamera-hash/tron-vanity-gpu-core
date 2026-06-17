# RunPod VanitySearch TRON GPU Address Layer Check

## Purpose

This is the next low-cost RunPod gate for the VanitySearch adaptation path.

By default it checks only the GPU-side TRON address construction layer:

- Keccak-256 over the uncompressed secp256k1 public key without `04`
- TRON payload prefix `0x41`
- double-SHA256 checksum
- Base58Check encoding
- product matching rule: fixed `T` + `prefix_after_t` 1 char + suffix 5 chars
- four public TEST_ONLY public-key vectors

It is not a search benchmark and cannot be used as an address generation speed result.

An optional smoke can also compile patched VanitySearch and run a bounded TRON wildcard GPU search startup check. A separate optional benchmark signal can run a 10 second bounded TRON pattern benchmark and print JSON. These are still not final Serverless average/P90 proof.

## Candidate Patch

Tracked patch in this repository:

```text
patches/vanitysearch_tron_gpu_payload21_word_bounds_20260618.patch
```

SHA-256:

```text
b307d8a10f78135befd763cc470a59aa958d6bb6e117c8f9340646ac88fde81c
```

Candidate branch head:

```text
4cd2de7 Use word bounds for TRON payload21 prefix gate
```

The TRON GPU search path now parses `T<one-char>*<five-char-suffix>` into a dedicated product rule, precomputes the `T` + `prefix_after_t` Base58 value range and suffix-5 value, checks whether the 21-byte TRON payload can possibly fall in the prefix range before computing the double-SHA256 checksum, then applies exact prefix range, suffix modulo, and full Base58 confirmation. This avoids passing host string pointers into the kernel and skips checksum/modulo/Base58 work for most non-matching candidates.

The hot path now derives the TRON payload directly from VanitySearch's GPU x/y coordinate words, instead of first materializing a 64-byte public-key array and then hashing that array. The RunPod vector check compares the direct x/y Keccak absorption path with the public-key reference path through the `xy_payload_passed` field.

The checksum-before gate now uses precomputed 3-word possible prefix bounds for the 21-byte payload. This keeps the exact 25-byte `T + prefix_after_t` range for post-checksum confirmation, while replacing the per-candidate byte-loop/synthetic checksum-tail comparison with three high-aligned 64-bit word comparisons in the hot reject path.

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
- The GPU vector check must report all per-vector boolean gates as `true` before any benchmark result is trusted: `xy_payload_passed`, `prefix_possible_passed`, `wrong_prefix_possible_rejected`, `prefix_prefilter_passed`, `wrong_prefix_prefilter_rejected`, `suffix_prefilter_passed`, and `wrong_suffix_prefilter_rejected`.
- The wrapper parses the vector JSON and prints `tron_gpu_vector_fields_verified` only after those fields are confirmed.
- The optional wildcard smoke uses the strict product-rule pattern and suppresses key material if an accidental hit occurs.
- The optional wildcard smoke defaults to 5 seconds and may print a best-effort `tron_gpu_pattern_smoke_rate` line; this is only a startup signal.
- The optional bounded benchmark defaults to 10 seconds, refuses durations outside 3-30 seconds, and emits JSON for review.
- The optional bounded benchmark rate is corrected to complete TRON address candidates per second, not raw hash speed and not the old generic 6x VanitySearch counter.
- The checksum-gated prefix range and suffix modulo prefilters are optimization gates, not proof of final production speed.
- Do not run this on `47.80.70.211`.
- Do not run a search benchmark from this check.
- Do not treat this as proof of production speed.
- Do not output scalar material, mnemonic, seed, token, or secret values.

## Next Gate

After this passes on RunPod, inspect the bounded benchmark JSON locally and compare it with the `58^6` target space. If it is promising, replace this signal path with a dedicated benchmark-only worker and then run controlled GPU-class comparisons.

Local inspection command:

```bash
scripts/inspect_vanitysearch_benchmark.py vanitysearch_benchmark_stdout.txt
```
