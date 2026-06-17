# TRON Vanity GPU Core

This directory is the implementation track for making TRON Base58 suffix-only last-5 matching feasible within the current target window: average <= 5 seconds and P90 <= 8 seconds.

Current status:

- Phase 0 CPU reference is complete.
- Phase 0 public test vectors are copied into `tests/phase0_test_vectors.json`.
- Host-side C++ validation for Keccak/SHA256/Base58/filter logic is available in `tests/verify_core_algorithms.cpp`.
- Host-side C++ secp256k1 full-chain validation is available in `tests/verify_secp256k1_full_chain.cpp`.
- Host-side incremental public-key walking validation is available in `tests/verify_incremental_walking.cpp`.
- Host-side batch inversion validation is available in `tests/verify_batch_inversion.cpp`.
- Host-side batch point-add validation is available in `tests/verify_batch_point_add.cpp`.
- CPU shard schedule validation is available in `tests/verify_shard_schedule.cpp`.
- CUDA vector validation source path exists, but has not been compiled on real GPU hardware yet.
- A gated sharded benchmark smoke path exists. Its default `kernel_mode` is `incremental`, using per-thread public-key walking after base scalar setup and cooperative block-level batch inversion for stride point additions. It must not be used to report GPU speed until RunPod vector validation passes first.
- Runtime CUDA compile supports explicit `CUDA_ARCH` plus fallback candidates for A100 (`sm_80`) and RTX 5090-class (`sm_120`) testing.
- Current priority is a speed sprint: pause age/find delivery work until the GPU path is stable above `200M attempts/s`; `300M+ attempts/s` is the preferred buffer before Serverless migration.

## Target

Default matching rule:

- full TRON Base58Check address suffix 5 only
- `prefix_len = 0`
- `suffix_len = 5`
- no prefix-after-`T` match

Search space:

```text
58^5 = 656,356,768
```

Target thresholds:

- Average <= 5 seconds: about `131.27M addresses/s`
- P90 <= 8 seconds: about `188.91M addresses/s`
- Engineering pass gate: at least `200M attempts/s`
- Preferred speed before Serverless migration: `300M+ attempts/s`

## Required GPU Chain

The GPU worker must implement complete address generation:

1. secp256k1 private scalar to public key.
2. Keccak-256 over uncompressed public key without `04`.
3. TRON hex address: `0x41 + last20(keccak)`.
4. Base58Check payload: `0x41 + address20 + checksum4`.
5. Base58 suffix modulo filter over the complete 25-byte payload, including checksum.
6. Full Base58Check confirmation for candidates that pass filters.

Hash-only speed is not TRON address generation speed.
The last 5 Base58Check characters depend on checksum, so matching cannot be decided from Keccak output alone.

## Safety Boundary

- Do not output plaintext `private_key` in benchmark mode.
- Do not write RunPod API keys to files.
- Do not read `.env`, token, password, or secret files.
- Do not use unreviewed external binary generators.
- Production hit handling is paused during the speed sprint; do not add delivery logic until the GPU path is stable above the `200M attempts/s` engineering minimum.

## Directory Layout

- `app.py`: RunPod Serverless worker entrypoint skeleton.
- `requirements.txt`: Python runtime dependency list for the RunPod wrapper.
- `Dockerfile`: preferred RunPod GitHub integration Dockerfile.
- `Dockerfile.cuda-validate`: equivalent named backup for validate-only deployments.
- `RUNPOD_VALIDATE_PAYLOAD.json`: first RunPod request; validates CUDA against Phase 0 vectors.
- `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json`: first tiny benchmark request after validation passes and `ALLOW_GPU_BENCHMARK=1` is set.
- `RUNPOD_A100_BENCHMARK_10S_PAYLOAD.json`: 10 second A100 comparison payload, only after validation and smoke pass.
- `RUNPOD_RTX5090_BENCHMARK_10S_PAYLOAD.json`: 10 second RTX 5090-class comparison payload, only after validation and smoke pass.
- `src/tron_gpu_core.cu`: CUDA implementation contract and CLI skeleton.
- `src/GPU_CORE_CONTRACT.json`: required input/output contract.
- `tests/phase0_test_vectors.json`: authoritative Phase 0 public vectors.
- `tests/verify_phase0_vectors.py`: no-dependency vector sanity checker.
- `tests/verify_incremental_walking.cpp`: checks walked public keys against direct scalar multiplication for small deterministic candidates.
- `tests/verify_batch_inversion.cpp`: checks device-compatible batch inversion against individual field inversions.
- `tests/verify_batch_point_add.cpp`: checks same-stride affine point additions using one batch inversion against direct `point_add`.
- `tests/verify_shard_schedule.cpp`: checks shard, batch, and thread-stride candidate coverage.
- `scripts/local_preflight.sh`: local no-server, no-RunPod preflight before pushing to GitHub.
- `scripts/public_repo_audit.py`: local audit before exposing the repository to GitHub/RunPod.
- `scripts/prepare_github_push.sh`: dry-run-first helper for setting GitHub remote and pushing only after explicit confirmation.
- `scripts/inspect_runpod_result.py`: local JSON inspector for RunPod validate/benchmark responses.
- `scripts/capacity_math.py`: local worker-count/probability calculator for measured complete TRON address speed.
- `scripts/runpod_gpu_pod_suffix_speed_sweep.sh`: gated normal RunPod GPU Pod speed sweep/profiler helper for suffix-only optimization.
- `scripts/runpod_gpu_pod_suffix_speed_test.sh`: gated one-command GPU Pod speed test that runs the sweep and immediately inspects the result.
- `scripts/inspect_suffix_speed_sweep.py`: local inspector for speed sweep result directories, including `200M/300M` decisions and GPU utilization checks.
- `examples/`: local sample RunPod responses for the result inspector.
- `docs/GITHUB_READY_MANIFEST.md`: exact GitHub repository readiness and first RunPod request checklist.
- `docs/RUNPOD_CONSOLE_CHECKLIST.md`: shortest RunPod console validation checklist.
- `docs/RUNPOD_RESULT_INSPECTION.md`: how to inspect RunPod outputs before deciding the next gate.
- `docs/RUNPOD_ACTION_NOW.md`: shortest current RunPod validation action; use this before any benchmark.
- `docs/RUNPOD_DEPLOYMENT_ROUTE_DECISION_20260617.md`: current RunPod deployment route gate, including GitHub/Docker/Flash status.
- `docs/RUNPOD_FLASH_FALLBACK_PROBE.md`: optional Flash CUDA environment probe, only after explicit user confirmation.
- `docs/RUNPOD_RESPONSE_INTAKE.md`: where to save RunPod response JSON and how to inspect it locally.
- `docs/RUNPOD_VALIDATE_TROUBLESHOOTING.md`: what to do if RunPod build, compile, or vector validation fails.
- `docs/RUNPOD_SHARDING.md`: multi-worker sharding strategy.
- `docs/GPU_CORE_REVIEW_CHECKLIST.md`: review gates before benchmark.
- `docs/BUILD_AND_RUNPOD_GATE.md`: build and RunPod execution gate.
- `docs/RUNPOD_GITHUB_DEPLOY_PATH.md`: preferred no-local-Docker deployment path using RunPod GitHub integration.
- `docs/RUNPOD_GITHUB_UPLOAD_CHECKLIST.md`: public/private GitHub upload gate after RunPod authorization.
- `docs/RUNPOD_BENCHMARK_GATE.md`: benchmark smoke-test gate and sharding rules.
- `docs/RUNPOD_SUFFIX_ONLY_GPU_POD_NEXT.md`: current suffix-only GPU Pod vector/smoke/benchmark sequence.
- `docs/RUNPOD_A100_RTX5090_COMPARISON.md`: exact A100 and RTX 5090-class comparison sequence.
- `docs/RUNPOD_FIRST_TEST_SEQUENCE.md`: RunPod-first validation and benchmark order that avoids using 47.80.70.211 as a test machine.
- `docs/SERVER_PREFLIGHT_47.md`: mandatory lightweight read-only preflight before any future operation on 47.80.70.211.
- `docs/LOCAL_LIGHT_VALIDATION_20260617.md`: latest local no-benchmark validation evidence before RunPod CUDA validation.
- `docs/REMOTE_47_RECOVERY_RUNBOOK.md`: recovery checklist for SSH banner timeout and residual validation processes.
- `docs/PERFORMANCE_CORE_PLAN.md`: next performance direction using incremental public-key walking.

## Current Gate

Before any real benchmark:

1. Build the CUDA validate image only after explicit approval.
2. Run `validate_vectors` mode against Phase 0 vectors on RunPod.
3. Only if validation passes, set `ALLOW_GPU_BENCHMARK=1` for an approved short smoke benchmark.
4. Start with `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json`.
5. Only after smoke benchmark passes, compare A100 and RTX 5090-class capacity with the 10 second payloads.
6. Treat current benchmark numbers as staging data until the CUDA core is optimized and independently reviewed.

If smoke speed is far below the suffix-only target, do not scale from the scalar kernel.
Use the incremental kernel first; it now includes cooperative block-level batch inversion for stride point additions. If it is still too slow, the next core step is suffix-only checksum/Base58 hot-path optimization, projective/precomputed-window point walking, then lower-level field arithmetic optimization.

Before any future operation on 47.80.70.211, run `docs/SERVER_PREFLIGHT_47.md` first. If the preflight is slow or abnormal, stop and report instead of continuing.
