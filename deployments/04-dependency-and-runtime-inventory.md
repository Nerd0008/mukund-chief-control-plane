# 04 — Dependency and runtime inventory

Generated from the live machine by `scripts/deployment_inventory.py`
(read-only, no network call, no credential value). Raw evidence:
`deployments/inventory-2026-09-24T02-13-33Z.json`.

---

## 1. Runtime versions

| Component | Version | Path |
|---|---|---|
| Python (the runtime interpreter) | **3.11.16** | `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe` |
| Python (bare `python` on PATH) | 3.11.16 | same venv is not on PATH; verify with `python --version` |
| Python (`python3` on PATH) | 3.14.6 | **not supported for this runtime** — do not run repo scripts with it |
| Node.js (Hermes runtime) | v22.23.2 | `%LOCALAPPDATA%\hermes\node\node.exe` |
| Hermes Agent | v0.21.4 (2026.9.21), upstream `d2ef7db7`, install method git | `%LOCALAPPDATA%\hermes\hermes-agent` |
| Codex CLI worker | 0.155.0-alpha.16.3 | `%LOCALAPPDATA%\OpenAI\Codex\bin\80f78947ad880e6e\codex.exe` |
| OS | Windows 11 (`10.0.26200`), AMD64 | — |

`uv` is present at `%LOCALAPPDATA%\hermes\bin\uv.exe` (a viable, faster way to
recreate the Python environment on a destination node).

## 2. Python packages

The control-plane code is deliberately near-stdlib. Third-party imports actually
found in the runtime code (`exec-brain/`, `career-ops/`, `company-watch/`,
`remote_queue/`, `remote-queue/`, `scripts/`):

| Package | Version installed | Used for |
|---|---|---|
| `openpyxl` | 3.1.5 | Career Ops tracker/workbook writes — the deterministic replacement for the removed `@oai/artifact-tool` Excel path. **Required.** |
| `PyYAML` | 6.0.3 | config/profile YAML parsing (Career Ops, regional search config). **Required.** |

Not required by the runtime code (present only as Hermes' own dependencies, do
not rely on them): `ruamel.yaml` 0.18.17, `ruamel.yaml.clib` 0.2.15.

Everything else the runtime imports is Python 3.11 standard library
(`sqlite3`, `json`, `urllib`, `ctypes`, `hashlib`, `subprocess`, `argparse`,
`pathlib`, `csv`, `unittest`, …). `mailbox` and `remote_queue` reported by the
scanner are stdlib / local package respectively, not external dependencies.

Minimum viable destination environment:

```bash
uv venv --python 3.11.16 <venv>
uv pip install --python <venv>/Scripts/python.exe -r requirements.lock
```

The repository now carries a top-level reproducible dependency manifest and a
hash-pinned lock (added 2026-09-24 by the release-reproducibility task):

| Artifact | Contents |
|---|---|
| `requirements.txt` | Direct dependencies — `openpyxl==3.1.5`, `PyYAML==6.0.3` (runtime) and `pytest==9.1.1` (test-only). |
| `requirements.lock` | Generated hash-pinned transitive closure for CPython 3.11 (9 packages incl. `et-xmlfile`, `colorama`, `iniconfig`, `packaging`, `pluggy`, `pygments`). |
| `scripts/dependency_inventory.py` | AST-based inventory of every top-level import; `--check` fails on an undeclared third-party import. |
| `docs/SETUP.md` | Clean-clone/setup path, per-area test commands, and the machine-local provisioning checklist with deterministic probes. |
| `docs/RELEASE.md` | Release identity, archive build/verify procedure and its limits. |

Regenerate the lock after changing `requirements.txt`:

```bash
uv pip compile requirements.txt --python-version 3.11 --python-platform windows \
    --generate-hashes -o requirements.lock
```

## 3. Background jobs / scheduled tasks

Inventoried live (see `06-service-definitions.md` for definitions): 8 Chief tasks
plus 1 legacy task. All 8 Chief tasks: state `Enabled`, logon mode
`Interactive only` (`InteractiveToken`), user `mukun`.

| Task | Extra observed config |
|---|---|
| `Hermes_Gateway` | logon trigger, restart-on-failure (1 min), StartWhenAvailable true |
| `HermesRemoteQueuePoller` | time trigger repeating every 2 min; no restart-on-failure |
| `ChiefDiscordSync` | time trigger repeating every 30 min |
| `ChiefCareerBrief` | daily calendar trigger 07:00 |
| `ChiefCareerScan-UK` | daily calendar trigger 23:45 |
| `ChiefCareerScan-Dubai` | daily calendar trigger 23:50 |
| `ChiefCareerScan-Japan` | daily calendar trigger 23:55 |
| `ChiefCareerScan-Singapore` | daily calendar trigger 00:00 |

Hermes-internal cron store (not a Windows task): `%LOCALAPPDATA%\hermes\cron\`
(`executions.db` + output dir) — currently empty of user jobs, inspected
2026-09-24.

## 4. Ports / network

- **Inbound: none.** No Chief or Hermes component listens on a socket; no
  `api_server` host/port is configured. No inbound firewall rule is needed.
- **Outbound: TCP 443 only** — provider APIs, GitHub, Discord gateway.
  Full endpoint list: `01-deployment-manifest.md` §5.
- No proxy, VPN or tunnel is required by the runtime. `gateway.trust_env: true`
  means standard `HTTP(S)_PROXY` env vars would be honoured if present.
- DNS: nothing custom; standard resolver.

## 5. State paths inventoried

| Path | Kind | Size (2026-09-24) | integrity_check |
|---|---|---|---|
| `%LOCALAPPDATA%\hermes\exec-brain\exec_brain.db` | sqlite | 77 KB | ok |
| `%LOCALAPPDATA%\hermes\exec-brain\governor.db` | sqlite | 77 KB | ok |
| `%LOCALAPPDATA%\hermes\exec-brain\orchestration.db` | sqlite | 217 KB | ok |
| `%LOCALAPPDATA%\hermes\exec-brain\chain-head.json` | json | 49 B | n/a |
| `%LOCALAPPDATA%\hermes\exec-brain\gov-chain-head.json` | json | 109 B | n/a |
| `%LOCALAPPDATA%\hermes\exec-brain\deepseek-config.json` | json | 119 B | n/a (budget only, no key) |
| `%LOCALAPPDATA%\hermes\state.db` | sqlite | ~45 MB | ok (owner conversations — local only) |
| `%LOCALAPPDATA%\hermes\kanban.db` | sqlite | 116 KB | ok |
| `%LOCALAPPDATA%\hermes\shared-state.db` | sqlite | 152 KB | ok |
| `%LOCALAPPDATA%\hermes\cron\executions.db` | sqlite | 24 KB | ok |

## 6. Test suites available for acceptance

| Area | Suites |
|---|---|
| `exec-brain/tests/` | 12 modules (E1, E2, E3 core/extended/execution/rehearsal/qualification/google-protocol/shadow, E4/E5, E4/E5 drills) |
| `remote_queue/tests/` | 4 modules (queue, bridge watchdog, console quickedit, worker retry) |
| `career-ops/tests/` | 10 modules |
| Aggregate runner | `scripts/evidence_runner.py` — 15 suites, last known full-green baseline **438/438** |

Acceptance commands and expected outputs: `09-acceptance-and-health-commands.md`.
