# 47.80.70.211 Server Preflight

Purpose: prevent 47.80.70.211 from being used as a build, CUDA, brute-force, or benchmark machine.

Run this lightweight read-only preflight before any future operation on 47.80.70.211.
If it is slow, times out, or shows unexpected high load, stop and report before doing any task work.

## Hard Boundary

- 47.80.70.211 is only the controller/API and project archive server.
- RunPod is the GPU worker and brute-force environment.
- Do not run C++ validation, CUDA compile, Docker build, benchmark, or brute-force generation on 47.80.70.211.
- Do not restart, modify, or delete `tron-monitor`, `tron-resource-watch`, or `tron-usdt-approve-tool` unless the user explicitly confirms that exact action.

## Read-Only Preflight

```bash
date
uptime
free -h
df -h
ps -eo pid,ppid,pcpu,pmem,etime,cmd --sort=-pcpu | head -25
ss -lntup | grep -E ':(8000|8001|18022|18030)\b' || true
docker ps
systemctl is-active tron-usdt-approve-tool.service || true
ps auxww | grep -E '/opt/vanity-address-api/gpu-core|verify_(core_algorithms|device_compatible_algorithms|secp256k1_full_chain|secp256k1_device_compatible|incremental_walking|shard_schedule)|compile_tron_gpu_core_host_stub|g\+\+.*gpu-core|benchmark|nvcc' | grep -v grep || true
```

## Stop Conditions

Stop before doing task work if any of these are true:

- SSH is slow or times out during banner exchange.
- Load is high for this 2 CPU server.
- Available memory is low enough that swap pressure or `kswapd` is visible.
- Unexpected `gpu-core`, compile, benchmark, or `nvcc` process is running.
- Protected ports `8000`, `8001`, or `18022` are missing.
- Docker is not responding quickly.
- `tron-usdt-approve-tool.service` is not `active`.

## Allowed After Clean Preflight

Only light controller/archive operations are allowed:

- Read project docs.
- Copy already prepared files.
- Update approved project documentation.
- Run small read-only status checks.

Builds, compiles, validation binaries, CUDA, benchmark, and brute-force work must be moved to RunPod or another explicitly approved build machine.
