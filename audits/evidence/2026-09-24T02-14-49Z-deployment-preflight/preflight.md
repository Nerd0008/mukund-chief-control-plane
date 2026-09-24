# Deployment preflight report

- Run (UTC): 2026-09-24T02:14:49+00:00 -> 2026-09-24T02:14:50+00:00
- Repository: `C:\Users\mukun\Documents\mukund-chief-control-plane`
- Runtime root: `C:\Users\mukun\AppData\Local\hermes\exec-brain`
- Provider calls spent: 0
- Network calls spent: 0
- Verdict: **GO**

| Check | Status | Detail |
|---|---|---|
| host.python>=3.11 | PASS | {"platform": "win32", "python_version": "3.11.16", "python_executable": "C:\\Users\\mukun\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe"} |
| repo.exec-brain module set complete | PASS | 34 modules present |
| runtime.module set complete | PASS | 34 modules present in runtime root |
| runtime.eb.py e3-* registration patch | PASS | patch present |
| state.databases present and integrity ok | PASS | 7 databases, all integrity_check=ok |
| scheduled tasks present and match manifest | PASS | 8 tasks match |
| python.third-party dependencies importable | PASS | {"openpyxl": "3.1.5", "yaml": "6.0.3"} |
| credentials.presence (owner-gated) | WARN | 7 API worker credential(s) absent: ['mistral-small-4', 'glm-53-flash', 'qwen38-27b', 'longcat-2.0', 'minimax-m3', 'step-37-flash', 'tencent-hunyuan-hy3'] — owner action, not an execution failure |
| acceptance.command targets exist | PASS | 9 command targets present |
| git.no secret-looking files tracked or staged | PASS | no match for secret filename patterns |
| topology.decision still pending (by design) | PASS | pending owner decisions: deployment architecture (laptop primary vs VPS primary); VPS host/account details; VPS cutover authorisation |

## How to read this

- `PASS` — verified against the live machine on this run.
- `WARN` — verified fact that is an owner-gated dependency, not a fault.
- `FAIL` — a real precondition failure; the cutover runbook's no-go list applies.

This report is read-only: it made no network call and read no credential value (presence and store name only).
