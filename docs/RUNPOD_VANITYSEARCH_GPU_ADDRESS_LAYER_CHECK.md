# RunPod VanitySearch TRON GPU Address Layer Check

## Purpose

This is the next low-cost RunPod gate for the VanitySearch adaptation path.

It checks only the GPU-side TRON address construction layer:

- Keccak-256 over the uncompressed secp256k1 public key without `04`
- TRON payload prefix `0x41`
- double-SHA256 checksum
- Base58Check encoding
- product matching rule: fixed `T` + `prefix_after_t` 1 char + suffix 5 chars
- four public TEST_ONLY public-key vectors

It is not a search benchmark and cannot be used as an address generation speed result.

## Candidate Patch

Tracked patch in this repository:

```text
patches/vanitysearch_tron_gpu_address_layer_20260618.patch
```

SHA-256:

```text
a988726c561760768ba20d3b7354b497a27fa59e437c08046f73d1136e0825fc
```

Candidate branch head:

```text
98a05c7 Add TRON GPU product rule vector checks
```

## RunPod Command

On a short-lived CUDA-capable RunPod Pod, from this repository:

```bash
ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 CUDA_ARCH=sm_80 scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
```

Expected success marker:

```text
tron_gpu_address_layer_script_passed
```

## Safety

- The script refuses to run unless `ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1` is set.
- The script verifies the patch SHA-256 before applying it.
- The script refuses to overwrite an existing work directory.
- Do not run this on `47.80.70.211`.
- Do not run a search benchmark from this check.
- Do not treat this as proof of production speed.
- Do not output scalar material, mnemonic, seed, token, or secret values.

## Next Gate

After this passes on RunPod, wire `GPU/GPUTron.h` into VanitySearch's existing point-walking kernel and add TRON prefix-after-T plus suffix filtering.
