# RunPod VanitySearch TRON GPU Address Layer Check

## Purpose

This is the next low-cost RunPod gate for the VanitySearch adaptation path.

It checks only the GPU-side TRON address construction layer:

- Keccak-256 over the uncompressed secp256k1 public key without `04`
- TRON payload prefix `0x41`
- double-SHA256 checksum
- Base58Check encoding
- four public TEST_ONLY public-key vectors

It is not a search benchmark and cannot be used as an address generation speed result.

## Candidate Patch

Local patch:

```text
工作记录/vanitysearch_tron_gpu_address_layer_20260617.patch
```

SHA-256:

```text
9b70fda59b3edec26e4ee11cfb28267ca1c2432df17f0f44e12ff1a9722d40f8
```

Candidate branch head:

```text
4c93837 Add TRON GPU address layer vector check
```

## RunPod Command

On a short-lived CUDA-capable RunPod Pod, from the patched VanitySearch candidate repository:

```bash
CUDA_ARCH=sm_80 scripts/runpod_verify_tron_gpu_address_layer.sh
```

Expected success marker:

```text
tron_gpu_address_layer_script_passed
```

## Safety

- Do not run this on `47.80.70.211`.
- Do not run a search benchmark from this check.
- Do not treat this as proof of production speed.
- Do not output scalar material, mnemonic, seed, token, or secret values.

## Next Gate

After this passes on RunPod, wire `GPU/GPUTron.h` into VanitySearch's existing point-walking kernel and add TRON prefix-after-T plus suffix filtering.
