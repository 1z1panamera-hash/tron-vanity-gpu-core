# RunPod Flash Fallback Probe

This is a fallback route only. The preferred route remains RunPod Serverless GitHub integration because this repository already has a Dockerfile, RunPod handler, CUDA source, validation payloads, and result inspection tooling.

## Why This Exists

RunPod console currently blocks GitHub deployment until the user connects GitHub. Docker registry deployment is also blocked because no image has been built or pushed, and `47.80.70.211` must not be used as a Docker build host.

RunPod Flash may provide a smaller first probe from the local Mac, but it requires local installation and authentication:

```bash
pip install runpod-flash
flash login
```

`flash login` saves a RunPod API key locally. Codex must not read, print, copy, or commit that key.

## Probe Script

```text
flash/runpod_flash_cuda_probe.py
```

Default behavior is safe. Without explicit confirmation, it prints a JSON warning and exits without creating or starting a RunPod endpoint:

```bash
python3 flash/runpod_flash_cuda_probe.py
```

Confirmed use may create or start a RunPod Serverless endpoint and may spend credits:

```bash
python3 flash/runpod_flash_cuda_probe.py \
  --gpu-enum NVIDIA_A100_80GB_PCIe \
  --confirm-runpod-side-effect
```

The script checks only:

- `nvidia-smi`
- `nvcc --version`
- compilation of one tiny CUDA kernel
- execution of that tiny CUDA kernel

It does not:

- generate TRON addresses
- generate random private keys
- print or save private keys
- run vanity benchmark
- prove 10 second前2后5 performance

## GPU Enum Notes

Flash GPU enum names can differ from RunPod console labels. If an enum is unknown, the script exits and prints available enum examples from the installed `runpod-flash` package.

Use A100 first for the environment probe. RTX 5090-class testing should wait until the enum name and availability are confirmed.

## Pass Criteria

Continue only if the probe returns:

```text
passed = true
nvidia_smi.returncode = 0
nvcc_version.returncode = 0
compile.returncode = 0
run.returncode = 0
```

If any item fails, do not run vanity benchmark. Use the GitHub/Dockerfile route or adjust the remote CUDA environment first.

## Relationship To The Main Goal

This probe only answers whether RunPod Flash gives us a CUDA-capable environment. It is not the final GPU vanity worker. The final proof still requires:

- RunPod-side `validate_vectors` pass for the real CUDA worker.
- Controlled 10 second benchmark payloads.
- `addresses_per_second` evidence.
- Capacity math for TRON full Base58前2后5, approximately `58^6` effective search space.
