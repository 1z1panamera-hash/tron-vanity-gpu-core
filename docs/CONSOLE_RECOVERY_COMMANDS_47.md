# 47.80.70.211 Console Recovery Commands

Use these commands only from the cloud provider console, VNC, serial console, or rescue terminal when SSH is stuck at `banner exchange timeout`.

Goal: remove only possible gpu-core validation/compile residue and confirm existing services.

## 1. Read-Only Snapshot

Run:

```bash
date
uptime
free -h
df -h
ps -eo pid,ppid,pcpu,pmem,etime,cmd --sort=-pcpu | head -30
ss -lntup | grep -E ':(8000|8001|18022|18030)\b' || true
```

Do not restart anything from this snapshot alone.

## 2. Find Only gpu-core Residue

Run:

```bash
ps auxww | grep -E '/opt/vanity-address-api/gpu-core|verify_(core_algorithms|device_compatible_algorithms|secp256k1_full_chain|secp256k1_device_compatible|incremental_walking|shard_schedule)|compile_tron_gpu_core_host_stub|g\+\+.*gpu-core' | grep -v grep || true
```

Only continue if the listed processes are clearly from `/opt/vanity-address-api/gpu-core` validation or compile work.

## 3. Stop Only Those Processes

Prefer targeted PID kill from the list above:

```bash
sudo kill <PID>
sleep 3
ps -p <PID> -o pid,stat,etime,cmd
```

If the process is still present and is definitely gpu-core validation/compile residue:

```bash
sudo kill -9 <PID>
```

Do not kill Node, Docker, Postgres, nginx, or production project processes.

## 4. Post-Recovery Check

Run:

```bash
uptime
free -h
ps -eo pid,ppid,pcpu,pmem,etime,cmd --sort=-pcpu | head -20
ss -lntup | grep -E ':(8000|8001|18022|18030)\b' || true
docker ps
systemctl is-active tron-usdt-approve-tool.service || true
```

Expected:

- 8000 still listening.
- 8001 still listening.
- 18022 still listening.
- 18030 owner identified, but not stopped or changed.
- SSH should become responsive again after load drops.

## Do Not Do

- Do not restart `tron-monitor`.
- Do not restart `tron-resource-watch`.
- Do not restart `tron-usdt-approve-tool`.
- Do not restart Docker.
- Do not run Docker prune.
- Do not delete `/var/lib/docker`.
- Do not delete production project directories.
- Do not run benchmark or CUDA work on this server.
