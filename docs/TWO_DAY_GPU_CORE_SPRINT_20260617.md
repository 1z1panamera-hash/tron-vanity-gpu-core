# Two-Day GPU Core Sprint 2026-06-17

## Goal

Try to find or build a viable high-performance GPU core for TRON vanity address generation.

Target matching rule:

- Full TRON Base58 address prefix length: 2, including fixed leading `T`
- Full TRON Base58 address suffix length: 5
- Effective random search: `T` plus 1 variable prefix character plus 5 suffix characters
- Effective random search space: about `58^6 = 38,068,692,544`, not `58^7`

Hard speed target:

- Practical target: at least 1 billion complete TRON address attempts/s per strong GPU before scaling out.
- User target: about 5 billion complete TRON address attempts/s if possible.
- Do not count raw hash/s as address/s.

## Current Result

The current in-house CUDA core is not viable for production speed.

- A100-SXM4-80GB: about 33,098.886491 addresses/s
- RTX PRO 6000 Blackwell Server Edition: about 112,930.931302 addresses/s

This implementation remains useful only as:

- TRON correctness scaffold
- RunPod handler scaffold
- test-vector reference

Do not continue spending RunPod benchmark time on the current core without replacing the hot path.

## VanitySearch Baseline Result

Unmodified upstream `VanitySearch` was compiled on a RunPod A100 CUDA image and tested only as a Bitcoin vanity baseline.

- GPU: NVIDIA A100-SXM4-80GB
- Source commit: `c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b`
- Compile result: success with CUDA 12.4 and `sm_80`
- Short observed speed: about `4.1` to `4.8` billion keys/s

This is not TRON address speed. It is evidence that a mature point-walking vanity architecture can reach the required performance class, while the current in-house CUDA core cannot.

Next work should focus on adapting a mature architecture to complete TRON address generation and matching, not further tuning the current slow kernel.

## Hard Boundaries

- Do not run GPU, brute force, CUDA compile, or high benchmark on `47.80.70.211`.
- `47.80.70.211` is controller/API/archive only.
- Do not output or store plaintext private keys.
- Do not read or output secrets, tokens, or `.env`.
- RunPod expensive GPUs are used only for short benchmarks after low-cost correctness checks.

## Candidate Audit

### VanitySearch

- Source: `https://github.com/JeanLucPons/VanitySearch`
- Local audit copy: `工作记录/candidate-cores/VanitySearch`
- Audited commit: `c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b`
- License: GPLv3
- Strengths:
  - Full CUDA vanity-search style project.
  - Contains optimized secp256k1, point walking, endomorphism-related paths, GPU Base58, and GPU prefix lookup.
  - README reports hundreds of MKey/s on old GTX 1050 Ti class hardware, so the algorithmic structure is much closer to the needed class than the current in-house core.
- Problems:
  - Bitcoin address pipeline uses SHA256 + RIPEMD160, not TRON Keccak-256.
  - Prefix search is Bitcoin-address oriented and validates Bitcoin address forms.
  - It prints and writes WIF/HEX private key by default when a match is found.
  - GPLv3 means derivative distribution must respect GPL obligations.
- Fastest use:
  - Use as first technical baseline for performance architecture.
  - Adapt or prototype a TRON mode that replaces Hash160 with Keccak-256 + TRON Base58Check.
  - Remove direct private key output from production path; hit handling must go through age encryption.

### BitCrack

- Source: `https://github.com/brichard19/BitCrack`
- Local audit copy: `工作记录/candidate-cores/BitCrack`
- Audited commit: `6bf8059ef075eb1622298395866b0bd02375e1d9`
- License: MIT
- Strengths:
  - CUDA and OpenCL secp256k1 implementation.
  - Uses point walking and batch inversion style iteration.
  - Permissive license is better for product integration.
- Problems:
  - Designed for known Bitcoin address/hash target lookup, not vanity prefix/suffix search.
  - Uses SHA256 + RIPEMD160, not TRON Keccak-256.
  - Main CLI prints private key on hit.
  - Adapting to full TRON Base58 prefix/suffix matching likely requires more structural changes than VanitySearch.
- Fastest use:
  - Keep as MIT reference for point walking and batch inversion.
  - Consider only if VanitySearch license or structure blocks product path.

### Profanity-style Projects

- Current judgment: do not use as production baseline unless a complete, current, auditable source tree is found.
- Reasons:
  - Many public variants are archived, incomplete, or historically unsafe.
  - Some forks rely on external binaries or unsafe private key output flows.
  - Private key generation code must be auditable.

## Fastest Technical Route

Primary route:

1. Use VanitySearch as performance baseline and architecture reference.
2. Build a minimal TRON mode:
   - secp256k1 public key generation stays GPU-side.
   - Replace `HASH160(public_key)` with `Keccak256(uncompressed_public_key[1:65])`.
   - Build TRON payload: `0x41 + last20(keccak)`.
   - Compute double-SHA256 checksum for Base58Check.
   - Match full Base58 prefix/suffix.
3. For production hit handling:
   - Do not print plaintext private key in logs.
   - Return hit only to a controlled wrapper.
   - Encrypt private key with customer age recipient before returning to controller.

Backup route:

1. Use BitCrack MIT CUDA point-walking implementation as the math base.
2. Add TRON Keccak + Base58 prefix/suffix matching.
3. Build a new minimal CLI/serverless worker wrapper.

## Two-Day Work Plan

### Day 1

- Audit VanitySearch CUDA hot path and isolate files needed for GPU generation.
- Add a TRON CPU reference adapter around the candidate core for known test vectors.
- Draft exact patch points for:
  - Keccak-256 device implementation
  - TRON address bytes
  - Base58Check prefix/suffix matcher
  - private-key output removal
- Prepare low-cost RunPod GPU Pod build checklist.
- Completed upstream VanitySearch A100 baseline; see `docs/RUNPOD_VANITYSEARCH_BASELINE_20260617.md`.
- Created a local VanitySearch CPU TRON address prototype branch, exported a local patch, and added a RunPod vector-check script; see `docs/VANITYSEARCH_PROTOTYPE_STATUS_20260617.md` and `docs/RUNPOD_VANITYSEARCH_CPU_VECTOR_CHECK.md`.

### Day 2

- Compile candidate on low-cost GPU Pod.
- Run correctness checks only.
- Run short 5-10 second benchmark only if correctness passes.
- If speed is below 1e8 complete TRON address attempts/s on a strong GPU, stop and report route as not viable.
- If speed is above 1e8, continue optimization and test 4090/5090/A100/Blackwell short benchmark.

## RunPod Usage Points

Use RunPod only at these points:

1. Low-cost GPU Pod compile test.
2. Correctness test with public vectors.
3. Short benchmark after correctness passes.
4. Expensive GPU benchmark only after low-cost compile and correctness pass.

Do not use RunPod Serverless for iterative CUDA debugging. Use a normal GPU Pod first.

## Stop Conditions

Stop and report before spending more if:

- Candidate source is incomplete or cannot be audited.
- CUDA compile requires unsafe binary blobs.
- Correctness vector fails.
- Private key output cannot be controlled.
- Full TRON address/s remains below 1e8 after adapting a mature core.

## Current Decision

Best first attempt: `VanitySearch` based TRON mode prototype.

Reason: it is already a CUDA vanity-search architecture, while BitCrack is a keyspace/target lookup architecture.
