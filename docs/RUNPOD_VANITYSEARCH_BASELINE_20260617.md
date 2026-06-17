# RunPod VanitySearch Baseline 2026-06-17

## Purpose

Measure a mature GPU vanity-search architecture before spending more time on the current in-house CUDA core.

This test used upstream `VanitySearch` unchanged, so the result is a Bitcoin vanity baseline, not TRON vanity speed.

## Boundaries

- Did not connect to `47.80.70.211`.
- Did not run compile, CUDA, benchmark, or brute force on `47.80.70.211`.
- Did not output private keys.
- Did not read or output secrets, tokens, or `.env`.
- Pods were stopped and terminated after the test.
- Attached temporary RunPod volumes were deleted with the pods.

## Candidate Source

- Upstream: `https://github.com/JeanLucPons/VanitySearch`
- Commit tested: `c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b`
- License: GPLv3

## Pod 1: A40 Base Image Check

- Pod name: `tron-vanity-a40-baseline`
- GPU: NVIDIA A40
- Image: `runpod/base:1.0.3-ubuntu2204`
- Result: stopped early because the image did not provide `nvcc`.

This pod was not useful for CUDA compile testing and was terminated.

## Pod 2: A100 CUDA Baseline

- Pod name: `tron-vanity-a100-cuda-baseline`
- GPU: NVIDIA A100-SXM4-80GB
- Image: `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04`
- `nvcc`: `/usr/local/cuda-12.4/bin/nvcc`
- CUDA compiler version: 12.4
- Compile target: `sm_80`

Compile command:

```sh
make gpu=1 CUDA=/usr/local/cuda-12.4 CXXCUDA=/usr/bin/g++ CCAP=8.0 all
```

Compile result: success.

## Short Baseline Result

Command shape:

```sh
timeout 12s stdbuf -oL ./VanitySearch -gpu -stop 1zzzzzzzzzzzzzz
```

Sensitive output was filtered:

- `Base Key` redacted.
- Private key / WIF / HEX output lines suppressed.

Observed A100 speed lines:

```text
4765.19 Mkey/s total, 4755.71 Mkey/s GPU
4252.77 Mkey/s total, 4246.14 Mkey/s GPU
4195.21 Mkey/s total, 4189.52 Mkey/s GPU
4166.43 Mkey/s total, 4161.21 Mkey/s GPU
```

Practical observed range:

- About `4.1` to `4.8` billion keys/s on one A100 for upstream Bitcoin compressed vanity mode.

## Interpretation

This proves that the mature VanitySearch architecture can reach billion-class key walking on A100-class hardware.

It does not prove TRON speed, because TRON mode still needs:

- Keccak-256 over uncompressed public key bytes.
- TRON payload generation with `0x41`.
- Base58Check full TRON address generation.
- Full prefix/suffix match on TRON Base58.
- CPU verification of every GPU hit.
- Private key output removal or age-encrypted hit handling.

The prior in-house CUDA core result was far too slow:

- A100-SXM4-80GB: about `33,098.886491` complete TRON addresses/s.
- RTX PRO 6000 Blackwell Server Edition: about `112,930.931302` complete TRON addresses/s.

Therefore the next useful path is not more tuning of the current in-house kernel. The next useful path is adapting or reusing a mature point-walking vanity architecture.

## Cost Control

The observed account balance moved from about `$9.84` to about `$9.73` during this investigation, roughly `$0.11`.

Do not keep GPU pods running between tests.

## Next Step

Create a controlled VanitySearch TRON prototype branch:

1. Keep upstream source separate until GPLv3 distribution decision is explicit.
2. Replace Bitcoin Hash160 address path with TRON Keccak/Base58Check path.
3. Disable plaintext private-key output in benchmark mode.
4. Verify every GPU hit against Phase 0 CPU TRON test vectors.
5. Run a short low-cost GPU benchmark before any expensive 4090/5090/H100/A100 test.
