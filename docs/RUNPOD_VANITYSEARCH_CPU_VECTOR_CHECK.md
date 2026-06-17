# RunPod VanitySearch CPU Vector Check

## Purpose

Verify the local VanitySearch TRON CPU adapter on x86 Linux before spending time on GPU TRON hot-path work.

This is not a benchmark. It must not be used to claim TRON generation speed.

## Matching Rule

- Runtime API still uses full TRON Base58 `prefix_len=2` and `suffix_len=5`.
- The leading `T` is fixed for normal TRON addresses.
- Effective random search is therefore `T` plus 1 variable prefix character plus 5 suffix characters.
- Capacity math uses `58^6`.

## Local Patch Export

The VanitySearch candidate branch is kept separate because VanitySearch is GPLv3.

Export the local patch from the main repository:

```sh
scripts/export_vanitysearch_patch.sh
```

Default output:

```text
../vanitysearch_tron_cpu_prototype_20260617.patch
```

The script refuses to export if the candidate worktree is dirty.

## RunPod Pod Type

Use a normal GPU Pod or CPU-capable x86 Linux Pod, not Serverless.

Recommended:

- CUDA devel image is okay, but this step only needs CPU compile.
- Low-cost GPU is enough if a GPU Pod is easier to provision.
- Do not use expensive 5090/H100 for this step.
- Do not run long benchmark.

## RunPod Commands

On the Pod:

```sh
cd /workspace
git clone https://github.com/JeanLucPons/VanitySearch.git
cd VanitySearch
git checkout c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b
```

Copy the exported patch to the Pod, then:

```sh
git apply /workspace/vanitysearch_tron_cpu_prototype_20260617.patch
scripts/runpod_verify_tron_cpu_vectors.sh
```

Expected final line:

```text
tron_cpu_vectors_passed
```

## Forbidden During This Check

- Do not run vanity search.
- Do not run GPU benchmark.
- Do not generate customer keys.
- Do not use real private keys.
- Do not output WIF, HEX private key, mnemonic, seed, token, or secret.
- Do not connect to `47.80.70.211`.
- Do not use `47.80.70.211` for compile, CUDA, benchmark, or brute force.

## Pass Criteria

- Patch applies cleanly.
- CPU build succeeds on x86 Linux.
- All 4 public TEST_ONLY TRON vectors match.
- Output contains no forbidden key/secret markers.

## Next Step After Pass

Only after this passes:

1. Add TRON GPU address path to VanitySearch candidate.
2. Keep GPU output in benchmark mode address-only.
3. Validate hits on CPU.
4. Run a short low-cost GPU correctness/smoke test.
5. Run expensive GPU benchmark only after correctness passes.
