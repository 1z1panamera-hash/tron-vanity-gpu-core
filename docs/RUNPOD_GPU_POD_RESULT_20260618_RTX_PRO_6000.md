# RunPod GPU Pod Result - RTX PRO 6000

Date: 2026-06-18 Asia/Shanghai

## Scope

Normal RunPod GPU Pod check for the patched VanitySearch TRON GPU path.

Important: this result used the previous `prefix_after_t + suffix5` rule. It is historical evidence only. The current product rule is suffix-only last 5 characters, with search space `58^5`.

This was not a Serverless proof and not a production private key delivery test.

## Pod

- GPU model: NVIDIA RTX PRO 6000 Blackwell Server Edition
- Driver: 580.159.04
- CUDA compile path: CUDA 12.4 nvcc with `sm_90` plus `compute_90` PTX fallback
- Pod id: `17ee8rukp6l8vq`
- Pod name: `young_amber_crab`
- Template used: `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04`
- Repo commit tested: `73ac8ea82856328dce7f1fee62ae317f952982af`
- Pod status after test: stopped, then terminated
- Attached test network volume: deleted
- Balance observed: about `$9.69` before, about `$9.03` after

## Fixes Required During Test

- `nvcc` existed at `/usr/local/cuda-12.4/bin/nvcc`, but the image did not put it on `PATH`.
- CUDA 12.4 did not produce a directly runnable Blackwell image from `sm_90` SASS only.
- The patch now adds `compute_90` PTX fallback so the Blackwell driver can JIT.
- TRON wildcard mode previously hit an uninitialized `onlyFull` state and tried the wrong prefix table path.
- Benchmark output needed a pseudo-terminal capture to preserve VanitySearch progress speed lines.

## Vector Gate

Passed.

Required markers were present:

- `tron_gpu_address_layer_passed`
- `tron_gpu_address_layer_script_passed`
- `tron_gpu_vector_fields_verified`

Per-vector fields passed for 4 public TEST_ONLY vectors:

- `match_rule_passed`
- `wrong_rule_rejected`
- `prefix_possible_passed`
- `wrong_prefix_possible_rejected`
- `prefix_prefilter_passed`
- `wrong_prefix_prefilter_rejected`
- `suffix_prefilter_passed`
- `wrong_suffix_prefilter_rejected`
- `xy_payload_passed`

## Smoke

Passed.

- Smoke speed sample: about `88.07 Mkey/s`
- Sensitive output was suppressed with `TRON_SUPPRESS_SECRET_OUTPUT=1`

## 3 Second Benchmark

Passed as a bounded signal.

- Pattern: `TA*CDEFG`
- Candidate attempts per second estimate: `92,790,000`
- Expected mean seconds for 58^6: about `410.27`
- P90 seconds for 58^6: about `944.68`
- Required workers for mean <= 10s: `42`
- Required workers for P90 <= 15s: `63`

## 10 Second Benchmark

Passed as a bounded signal.

- Pattern: `TA*CDEFG`
- Candidate attempts per second estimate: `85,050,000`
- Expected mean seconds for 58^6: about `447.60`
- P90 seconds for 58^6: about `1030.65`
- Required workers for mean <= 10s: `45`
- Required workers for P90 <= 15s: `69`

## Suffix-Only Reinterpretation

If the same `85.05M` complete TRON candidates/s held under the new suffix-only rule, the rough search-space math would be:

- Search space: `58^5 = 656,356,768`
- Expected mean: about `7.72` seconds
- P90: about `17.77` seconds

That still misses the new target:

- Average <= 5 seconds needs about `131.27M` complete TRON candidates/s
- P90 <= 8 seconds needs about `188.91M` complete TRON candidates/s

This is only a reinterpretation. The actual suffix-only hot path must be patched and retested, because removing prefix gating can change per-candidate cost.

## Decision

This patched VanitySearch TRON path was correct enough to run vector and bounded benchmark checks for the previous rule, but it is not yet proven for the current suffix-only target.

Do not migrate this path to Serverless as the final production worker until the suffix-only path is tested and reaches average <= 5 seconds and P90 <= 8 seconds.

## Next Engineering Direction

The current bottleneck is the per-candidate TRON address layer inside the hot GPU loop:

- Keccak-256 over public key coordinates
- double SHA-256 checksum
- Base58Check or equivalent prefix/suffix filtering

Further work should focus on reducing the TRON hot-path cost before any more paid long benchmarks:

- avoid full Base58 work for most candidates,
- tighten prefix/suffix numeric filters before checksum,
- reduce register and stack pressure in `comp_keys_tron_pattern`,
- evaluate whether checksum/Base58 can be split into rarer confirmation work,
- test against a newer CUDA 12.8 image for native Blackwell codegen,
- compare H100/B200 only after the hot-path structure improves.

## Safety

- No customer pattern was used.
- No private key, token, mnemonic, seed, or secret was intentionally output.
- The benchmark used `TRON_SUPPRESS_SECRET_OUTPUT=1`.
- `47.80.70.211` was not used for compile, benchmark, or GPU work.
