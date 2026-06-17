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
patches/vanitysearch_tron_gpu_safe_smoke_20260618.patch
```

SHA-256:

```text
b791ee6b28f1bba9b9f9371ea345af5c4199585135ef1ee93784c6e1b73e893b
```

Candidate branch head:

```text
d79918f Suppress TRON secrets in bounded GPU smoke
```

The TRON GPU search path now parses `T<one-char>*<five-char-suffix>` into a dedicated product rule, precomputes the `T` + `prefix_after_t` Base58 value range and suffix-5 value, checks whether the 21-byte TRON payload can possibly fall in the prefix range before computing the double-SHA256 checksum, then applies exact prefix range, suffix modulo, and full Base58 confirmation. This avoids passing host string pointers into the kernel and skips checksum/modulo/Base58 work for most non-matching candidates.

The optional pattern smoke sets `TRON_SUPPRESS_SECRET_OUTPUT=1` before running VanitySearch. If an accidental hit happens during the bounded smoke, WIF/HEX key material is suppressed instead of printed.

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
- The optional wildcard smoke uses the strict product-rule pattern and suppresses key material if an accidental hit occurs.
- The optional wildcard smoke defaults to 5 seconds and may print a best-effort `tron_gpu_pattern_smoke_rate` line; this is only a startup signal.
- The checksum-gated prefix range and suffix modulo prefilters are optimization gates, not proof of final production speed.
- Do not run this on `47.80.70.211`.
- Do not run a search benchmark from this check.
- Do not treat this as proof of production speed.
- Do not output scalar material, mnemonic, seed, token, or secret values.

## Next Gate

After this passes on RunPod, measure the patched VanitySearch path with short bounded runs on a GPU Pod, then continue optimizing the secp256k1 and TRON address hot path. Do not treat this address-layer check as a benchmark.
