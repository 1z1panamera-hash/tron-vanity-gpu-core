# RunPod Worker v2 isolated release gate

This branch prepares a replacement worker for the 18030 RunPod path. It does
not update the production endpoint or the 43 host service.

## Core routing

| Assigned GPU | Selected core | Default grid |
|---|---|---|
| RTX 5090, compute capability 12.0 | Round51 optimized `sm_120` | `160,128` |
| RTX PRO 6000 Blackwell, compute capability 12.0 | Round51 optimized `sm_120` | `160,128` |
| RTX 4090 or another supported non-Blackwell GPU | Existing multi-architecture worker | existing profile |

The image contains both binaries. Automatic selection is based on compute
capability, with GPU-name inference only as a compatibility fallback. If the
Round51 process has a hard startup/runtime failure early enough in the same
request, the worker retries with the existing binary using only the remaining
request time. A normal no-hit timeout never triggers duplicate computation.

The matched candidate still passes VanitySearch's CPU private-key/address
reconstruction before the wrapper receives it. The wrapper retains the
existing per-request Age recipient validation and encrypts the internal key
before returning the response.

## Provenance

- Upstream VanitySearch commit: `c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b`.
- Round51 source archive SHA-256 used to import the optimization patches:
  `aa809d7f61ce8373447fc8decd7031506a343ff7cd54812acfb6408451610191`.
- Exact Round51 build: `STEP_SIZE=16384`, `NVCC_MAXRREGCOUNT=172`, native
  `sm_120` plus `compute_120` PTX.
- Existing legacy worker remains a fat binary for
  `sm_80,sm_86,sm_89,sm_90,sm_120`.

## Isolated endpoint configuration

- New endpoint and new template only; never edit endpoint `mf8hnwrsf293e1`.
- Queue-based endpoint (`/run` and `/status`) to preserve the existing 18030
  retry and idempotency model.
- Flex Workers, `workersMin=0`, `workersMax=1`, `idleTimeout=5` seconds.
- FlashBoot enabled.
- GPU priority: RTX 5090, RTX PRO 6000 Blackwell, then RTX 4090.
- Minimum CUDA version 12.8.
- Runtime variables: `ALLOW_GPU_FIND=1`, `GPU_WORKER_BACKEND=auto`,
  `VANITYSEARCH_CORE_VARIANT=auto`.
- No customer recipient is stored in the template. Every test or production
  request supplies its own Age public recipient.

## Mandatory gates before production cutover

1. Local syntax, response-contract, dispatch, fallback, and patch-stack checks.
2. Immutable GHCR image build from the exact commit.
3. Isolated endpoint health confirms the assigned GPU and selected core.
4. Real suffix-only hit with a temporary test Age recipient; decrypt only in
   the test environment and verify address/key correspondence without logging
   the plaintext value.
5. One cold sample plus at least ten warm samples; record compute time,
   end-to-end time, GPU type, selected core, and ciphertext validation.
6. Explicit user approval before updating the production template/endpoint.

Production 18030 and 18035/Vast remain unchanged until all gates pass.
