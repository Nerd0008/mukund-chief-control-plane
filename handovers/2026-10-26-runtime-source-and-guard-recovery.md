# Runtime source and guard recovery — 26 October 2026

Branch: `fix/e3-whole-repo-architecture`. No main merge.

## Reproduced causes

1. `exec-brain/tests/test_eb.py::TestMatrix::test_t13_no_gateway_modification` failed on `hermes_cli.main_router.py`. Its duplicated tuple had not tracked legitimate router deployments and stopped at the first unexpected basename.
2. `exec-brain/tests/test_governor.py` failed collection with `ModuleNotFoundError: governor`. The 28,315-byte governor was runtime-only. Its CLI `eb.py` and probe dependency `adapters.py` were also absent from tracked source. Deleting the test would hide the recovery defect.
3. Independently reproduced five failures in `scripts/tests/test_deploy_e3_runtime.py`: deployment lacked the declared newer-runtime protection, its reporting field and explicit overwrite opt-in. Disposable-runtime testing proved differing newer code could be overwritten.

## Repairs and boundaries

- Recovered `governor.py`, `adapters.py` and `eb.py` from the existing runtime into repository source. Original private copies and SHA-256/mtime inventory are under `Documents/Codex/runtime-governor-recovery-20261026`. No credential/configuration/database exports are included in Git. Source code content is identical after CRLF/LF normalization; live files remain byte-for-byte unchanged.
- `scripts/runtime_contract.py` derives its source set from the deployer's `E3_MODULES`, plus the three recovered E1/E2 modules and existing legacy test aliases. Future E3 deployment declarations require no second allowlist edit. Private configuration names, known database basenames/sidecars and approved runtime directories are explicitly declared; their contents are not read.
- Unexpected entries are reported together. Arbitrary `.db`, root `.bak`, undeclared Python/cache files, symlinks and file/directory type mismatches fail closed. A missing declared source also fails.
- E1 unit tests run the repository CLI against disposable databases. The runtime guard runs in a disposable fixture by default; `EB_TEST_LIVE=1` retains the real inventory/hook check. The read-only CLI `python scripts/runtime_contract.py` checks live inventory directly.
- Governor tests import repository source and isolate credential checks, provider HTTP/process probes and publication/ledger paths under both pytest and standalone unittest. They no longer depend on the machine's provider accounts.
- Deployment treats line-ending-only differences as equivalent, preserves differing newer runtime modules by default, reports skipped modules, and requires explicit `--allow-runtime-newer` for backup-backed overwrite. E1/E2 are not automatically redeployed by the E3 deployer.

## Validation

- Before repair: governor collection failed; live T13 failed; deployment tests were 5 failed / 1 passed.
- Focused E1/E2/contract/deployment: **91 passed**.
- Full `exec-brain/tests` plus deployment/contract and affected Career Ops owner-policy/CV/cover integration: **674 passed, 0 failed** (79.02 seconds). One pre-existing collection warning concerns a helper class named `TestCase` with a constructor; it is not a failed test.
- Final governor isolation: **45 passed** under pytest; **45 passed** under standalone unittest.
- Explicit live T13: **1 passed**. Live inventory CLI: `ok=true`, no unexpected entries, wrong types or missing source.
- Production deployment dry run: no copies, no skipped newer files, existing E3 CLI binding already patched.
- No runtime source, credentials, database, tracker, Calendar, provider selection, CV layout, gateway or scheduled-task configuration changed. No restart required. Unrelated dirty runtime files remain unstaged.

## Original runtime source hashes

- `governor.py`: `4ff3631c928e911599c19563f136178f4488b5bcff2f09c22ba0ec4b29e773fb`
- `adapters.py`: `f23c0c419065495eb7b9a55350885325484d98831c28716d9fd4fc5d193c3cdc`
- `eb.py`: `a724319950f4020e9d2552205481b171d5ec6dc18f06ac3a2a406a744d8f22ea`
