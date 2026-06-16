# Local Light Validation 2026-06-17

Scope: local Mac only. No SSH to 47.80.70.211. No RunPod API call. No Docker build. No benchmark.

## Result

Passed.

## Checks Run

- `python3 -m py_compile app.py`
- JSON parse:
  - `RUNPOD_VALIDATE_PAYLOAD.json`
  - `RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json`
  - `src/GPU_CORE_CONTRACT.json`
  - `tests/phase0_test_vectors.json`
- `tests/verify_phase0_vectors.py`
- `tests/verify_core_algorithms.cpp`
- `tests/verify_device_compatible_algorithms.cpp`
- `tests/verify_secp256k1_full_chain.cpp`
- `tests/verify_secp256k1_device_compatible.cpp`
- `tests/verify_incremental_walking.cpp`
- `tests/verify_shard_schedule.cpp`
- `tests/compile_tron_gpu_core_host_stub.cpp`
- `tests/verify_core_algorithms.cpp`
- `tests/verify_device_compatible_algorithms.cpp`
- `tests/verify_secp256k1_full_chain.cpp`
- `tests/verify_secp256k1_device_compatible.cpp`
- Dockerfile source sanity:
  - `Dockerfile` and `Dockerfile.cuda-validate` are identical.
  - Docker COPY sources exist.
  - Docker COPY sources are not ignored by `.dockerignore`.

## Key Evidence

- Phase 0 vectors: 4/4 passed.
- C++ core algorithm validation: 4/4 passed.
- Device-compatible core validation: 4/4 passed.
- Host-side secp256k1 full chain: 4/4 passed.
- Device-compatible secp256k1 full chain: 4/4 passed.
- Incremental walking: 12 deterministic candidates checked, passed.
- Shard schedule: 15,145 candidates checked, passed.
- Host-stub benchmark path returned code `2` with the expected message that GPU benchmark requires nvcc build and explicit RunPod-side benchmark gate.
- GitHub/RunPod repository readiness:
  - standard `Dockerfile` exists at repo root,
  - `Dockerfile.cuda-validate` remains available as an equivalent backup,
  - `.gitignore` blocks build outputs, `.env`, logs, key-like files, and generated validation reports.

## Still Not Proven

- CUDA compilation with `nvcc`.
- CUDA `validate_vectors` execution on real RunPod GPU hardware.
- Real complete TRON `addresses_per_second`.
- RTX 5090/A100 capacity for prefix2 + suffix5 in 10 seconds.

## Next Allowed Step

Move to RunPod-only CUDA validation:

1. Put this `gpu-core` directory in a GitHub repository.
2. Use RunPod GitHub integration with Dockerfile path `Dockerfile`.
3. Create a RunPod Serverless endpoint from that repository.
4. Run `validate_vectors` mode first.
5. Run benchmark only if validation passes and `ALLOW_GPU_BENCHMARK=1` is explicitly set on RunPod.

Do not use 47.80.70.211 for compile, CUDA, Docker build, benchmark, or brute-force generation.
