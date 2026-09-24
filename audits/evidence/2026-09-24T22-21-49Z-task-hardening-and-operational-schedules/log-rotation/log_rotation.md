# Log rotation / retention

- Run (UTC): 2026-09-24T22:21:53+00:00
- Mode: apply (live state modified: False)
- Policy: archive a log above 5000000 bytes; keep the newest 5 archives per log

| Log | Exists | Size (bytes) | Action |
|---|---|---|---|
| C:\Users\mukun\AppData\Local\hermes\logs\agent.log | True | 3951805 | no_rotation_needed |
| C:\Users\mukun\AppData\Local\hermes\logs\errors.log | True | 385007 | no_rotation_needed |
| C:\Users\mukun\AppData\Local\hermes\logs\gateway.log | True | 70884 | no_rotation_needed |
| C:\Users\mukun\AppData\Local\hermes\logs\gateway-error.log | True | 1126 | no_rotation_needed |
| C:\Users\mukun\AppData\Local\hermes\logs\gateway-stdio.log | True | 24407 | no_rotation_needed |
| C:\Users\mukun\AppData\Local\hermes\logs\gateway-exit-diag.log | True | 13926 | no_rotation_needed |
| C:\Users\mukun\AppData\Local\hermes\logs\update.log | True | 14628 | no_rotation_needed |
| C:\Users\mukun\AppData\Local\hermes\gateway-starts.log | True | 262 | no_rotation_needed |
| C:\Users\mukun\Documents\mukund-chief-control-plane\remote-queue\logs\queue.log | True | 65797 | no_rotation_needed |
| C:\Users\mukun\Documents\mukund-chief-control-plane\runtime\chief\logs\operational-services.log | True | 1510 | no_rotation_needed |

## Out of scope (recorded, never pruned)

- C:\Users\mukun\AppData\Local\hermes\logs\process-results: Hermes-managed process-result records (JSON store, not a log stream)
- C:\Users\mukun\AppData\Local\hermes\logs\update_receipts: Hermes-managed update receipts (JSON store, not a log stream)

Archives before/after: 0 / 0. Nothing outside the declared log paths was read, written or pruned.
