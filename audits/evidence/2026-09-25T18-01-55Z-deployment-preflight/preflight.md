# Deployment preflight report

- Run (UTC): 2026-09-25T18:01:55+00:00 -> 2026-09-25T18:01:57+00:00
- Repository: `C:\Users\mukun\Documents\Codex\mukund-chief-control-plane-owner-decisions`
- Runtime root: `C:\Users\mukun\AppData\Local\hermes\exec-brain`
- Provider calls spent: 0
- Network calls spent: 0
- Verdict: **GO**

| Check | Status | Detail |
|---|---|---|
| host.python>=3.11 | PASS | {"platform": "win32", "python_version": "3.14.6", "python_executable": "C:\\Users\\mukun\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe"} |
| repo.exec-brain module set complete | PASS | 34 modules present |
| runtime.module set complete | PASS | 34 modules present in runtime root |
| runtime.eb.py e3-* registration patch | PASS | patch present |
| state.databases present and integrity ok | PASS | 7 databases, all integrity_check=ok |
| scheduled tasks present and match manifest | PASS | 8 tasks match |
| python.third-party dependencies importable | PASS | {"openpyxl": "3.1.5", "yaml": "6.0.3"} |
| credentials.presence | PASS | all API worker credentials present |
| acceptance.command targets exist | PASS | 10 command targets present |
| git.no secret-looking files tracked or staged | PASS | no match for secret filename patterns |
| topology.decision still pending (by design) | PASS | pending owner decisions: deployment architecture (laptop primary vs VPS primary); VPS host/account details; VPS cutover authorisation |

## How to read this

- `PASS` — verified against the live machine on this run.
- `WARN` — verified fact that is an owner-gated dependency, not a fault.
- `FAIL` — a real precondition failure; the cutover runbook's no-go list applies.

This report is read-only: it made no network call and read no credential value (presence and store name only).
