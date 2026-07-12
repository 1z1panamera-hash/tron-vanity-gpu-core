# Vast Fixed Host Shortlist

Read-only refresh: 2026-07-12

Query:

```text
gpu_name=RTX_5090 num_gpus=1 datacenter=true static_ip=true
direct_port_count>=1 rentable=true reliability>=0.99 cuda_vers>=13.0
disk_space>=60 gpu_max_power>=550
```

The `datacenter=true` filter is the Vast Secure Cloud filter. Vast documents
Secure Cloud as vetted datacenter providers and recommends static-IP offers for
IP allowlisting:

- https://docs.vast.ai/host/datacenter-status
- https://docs.vast.ai/guides/reference/faq/security

## Current Candidates

| Rank | Offer | Location | USD/hour | Reliability | Driver | Power | PCIe | Static IP |
| ---: | ---: | --- | ---: | ---: | --- | ---: | ---: | --- |
| 1 | 44516885 | India | 0.6694 | 0.9983215 | 595.58.03 | 575W | 5.0 / 54.2GB/s | yes |
| 2 | 43634628 | Maryland, US | 0.8423 | 0.9993219 | 580.95.05 | 575W | 5.0 / 47.4GB/s | yes |
| 3 | 40986213 | Maryland, US | 0.8685 | 0.9994965 | 580.105.08 | 575W | 4.0 / 27.0GB/s | yes |
| 4 | 44256144 | Maryland, US | 1.0023 | 0.9912436 | 595.71.05 | 575W | 5.0 / 54.9GB/s | yes |

## Selection Rule

1. Refresh immediately before rental because marketplace offers can disappear.
2. Start with offer 44516885 on On-demand only.
3. Verify the pinned worker image, non-root GPU access, outbound source IPv4,
   43 round-trip latency, P0 latency, 24-hour stability, and restart recovery.
4. Consider a reserved term only after the exact host passes those gates.

No offer was rented during this refresh, and no paid Vast resource remains
active from the RTX 5090 core tests.
