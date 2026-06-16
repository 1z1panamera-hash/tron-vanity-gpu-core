# 47.80.70.211 Recovery Runbook

Purpose: recover confidence after SSH banner timeout without touching production services.

For normal future access, run `docs/SERVER_PREFLIGHT_47.md` before doing any task work on this server.

## Current Symptom

- TCP port 22 is reachable.
- SSH can connect to port 22 but times out during banner exchange.
- Ports 8000, 8001, and 18022 were reachable by TCP from local checks.
- Do not assume the business services are broken only because SSH is slow.

## Do Not Do

- Do not restart `tron-monitor`.
- Do not restart `tron-resource-watch`.
- Do not restart `tron-usdt-approve-tool`.
- Do not restart Docker.
- Do not prune Docker.
- Do not delete files.
- Do not run GPU, CUDA, benchmark, or C++ validation on this server.

## First Read-Only Checks After SSH Recovers

Run only one command at a time:

```bash
uptime
free -h
ps -eo pid,ppid,pcpu,pmem,etime,cmd --sort=-pcpu | head -20
ps auxww | grep -E 'verify_(device_compatible|secp256k1)|compile_tron_gpu_core_host_stub|g\\+\\+' | grep -v grep || true
ss -lntup | grep -E ':(8000|8001|18022|18030)\\b' || true
docker ps
```

## If Residual Validation Processes Exist

If the only high-CPU processes are clearly from this gpu-core validation work, for example:

- `verify_secp256k1_full_chain`
- `verify_secp256k1_device_compatible`
- `verify_device_compatible_algorithms`
- `g++ -std=c++17 -O2 tests/verify_...`

then ask the user before killing them. Do not kill unrelated production processes.

## 18030 Note

After the 2026-06-17 reboot recovery, `ss` did not show 18030 listening.
Confirm again before using the suggested vanity-address-api controller port:

```bash
ss -lntup | grep -E ':18030\\b' || true
```

Do not bind or change 18030 until protected ports 8000, 8001, and 18022 are confirmed healthy.

## Future Rule

47.80.70.211 is not a build machine for gpu-core.
All CUDA compile, GPU validation, and benchmark work must move to RunPod or another explicit GPU/build environment.
