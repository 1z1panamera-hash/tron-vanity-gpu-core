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

An optional smoke can also compile patched VanitySearch and run a bounded TRON wildcard GPU search startup check. That smoke is still not a speed result.

## Candidate Patch

Tracked patch in this repository:

```text
patches/vanitysearch_tron_gpu_suffix_prefilter_20260618.patch
```

SHA-256:

```text
f90f69c0001d16f94a4175d369635814e3247895bb16e7676097f94c8de32fad
```

Candidate branch head:

```text
ff43325 Add TRON suffix modulo GPU prefilter
```

The TRON GPU search path now parses `T<one-char>*<five-char-suffix>` into a dedicated product rule, passes the suffix target into the kernel as a precomputed Base58 value, and uses a suffix-5 modulo prefilter before full Base58 confirmation. This avoids passing a host string pointer into the kernel and reduces full Base58 work for most candidates.

## RunPod Command

On a short-lived CUDA-capable RunPod Pod, from this repository:

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 CUDA_ARCH=sm_80 scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

Expected success marker:

```text
tron_gpu_address_layer_script_passed
```

Optional wildcard search startup smoke:

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 RUN_TRON_PATTERN_SMOKE=1 CUDA_ARCH=sm_80 scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

Expected extra success marker:

```text
tron_gpu_pattern_smoke_passed
```

## Safety

- The script refuses to run unless `ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1` is set.
- The script verifies the patch SHA-256 before applying it.
- The script refuses to overwrite an existing work directory.
- The optional wildcard smoke uses a long default suffix to avoid accidental hits and plaintext hit output.
- The suffix prefilter is an optimization gate, not proof of final production speed.
- Do not run this on `47.80.70.211`.
- Do not run a search benchmark from this check.
- Do not treat this as proof of production speed.
- Do not output scalar material, mnemonic, seed, token, or secret values.

## Next Gate

After this passes on RunPod, measure the patched VanitySearch path with short bounded runs on a GPU Pod, then continue optimizing the secp256k1 and TRON address hot path. Do not treat this address-layer check as a benchmark.
