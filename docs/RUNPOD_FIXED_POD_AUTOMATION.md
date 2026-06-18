# RunPod Fixed Pod Automation

Date: 2026-06-19 Asia/Shanghai

Purpose: optimize total workflow time, not just CUDA kernel time.

The fixed Pod automation creates a short-lived GPU Pod, runs the suffix-only
autotune, copies result files back, and then stops/deletes the Pod.

## Why This Exists

Manual console testing is too slow and error-prone:

- it requires manually finding available GPUs;
- it risks clicking "deploy when available";
- it risks leaving a Pod or volume running;
- it slows down repeated price/performance tests.

The automated path should become the default for fixed Pod speed testing.

## Dry Run

Dry run does not read `RUNPOD_API_KEY`, does not call RunPod, and does not create
resources:

```bash
scripts/runpod_fixed_pod_autotune_e2e.py --dry-run
```

## Execute

Execution is explicitly gated:

```bash
export RUNPOD_API_KEY="<do-not-save-this-in-files>"

ALLOW_RUNPOD_FIXED_POD_AUTOTUNE=1 \
  scripts/runpod_fixed_pod_autotune_e2e.py
```

Default behavior:

- GPU priority: RTX PRO 6000 / Blackwell, H200, H100, A100, L40S/A40, then
  opportunistic 5090/4090/3090.
- Creates one secure on-demand GPU Pod.
- Exposes only `22/tcp`.
- Uses 20GB container disk and 20GB Pod volume.
- Clones the GitHub repo on the Pod.
- Runs `scripts/runpod_gpu_pod_suffix_autotune.sh`.
- Copies `tron_suffix_autotune_result.tgz` back.
- Stops and deletes the Pod unless `--keep-pod` is set.

## Output

Local results are written under:

```text
runpod_results/fixed_pod_autotune/<utc-run-id>/
```

Important files:

- `plan.json`
- `pod_created.json`
- `pod_ready.json`
- `remote_stdout.txt`
- `remote_stderr.txt`
- `tron_suffix_autotune_result.tgz`
- extracted `runpod_results/suffix_autotune_*/speed_sweep_inspect.json`
- `result.json`

## Safety

- The script never prints or writes the RunPod API key.
- The script does not use customer suffixes.
- The default suffix remains `CDEFG`.
- The Pod is deleted by default.
- Use `--keep-pod` only for debugging and stop/delete manually afterwards.
- Do not run this on `47.80.70.211`.

## Notes

The script uses the official RunPod REST API:

- `POST /pods` to create a Pod.
- `GET /pods` to wait for `publicIp` and SSH port mapping.
- `POST /pods/{podId}/stop` for cleanup.
- `DELETE /pods/{podId}` for cleanup.

If image-only Pod creation does not expose SSH in a particular RunPod account,
pass a known SSH-enabled `--template-id` from the console template.
