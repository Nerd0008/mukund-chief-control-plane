# SETUP — clean clone to a verified environment

This document is the authoritative setup path for the **repository**. It
deliberately separates three things that are easy to conflate:

1. **Repository dependencies** — declared, pinned and fully reproducible from a
   clean clone or a release archive (`requirements.txt` / `requirements.lock`).
2. **Machine-local runtime** — the Hermes runtime root, its state databases, the
   Codex CLI login, provider credentials and Windows scheduled tasks. These are
   *deliberately* not in the repository and cannot be reproduced from an archive.
3. **Owner data** — application/inbox/CV/watchlist runtime trees that are
   `.gitignore`d because they carry Mukund's own data.

If a step is in (2) or (3), the probe column below tells you how to check it
deterministically instead of assuming.

---

## 1. Prerequisites

| Requirement | Value | Notes |
|---|---|---|
| Python | **3.11.16** (3.11.x line) | The supported interpreter for this release. 3.14.x is explicitly *not* supported — `deployments/04-dependency-and-runtime-inventory.md` §1 records that bare `python3` on the authoring host is 3.14.6 and must not be used for repo scripts. |
| `uv` (recommended) | any recent | Resolves and installs the hash-pinned lock. Verified with uv 0.12.18. |
| `pip` (fallback) | any recent | `pip install -r requirements.lock` also works when the lock is used from a matching platform. |
| git | any recent | Needed for commit identity in the release manifest; an exported archive works without git. |
| Codex CLI | 0.155.0-alpha.16.3 on the authoring host | Only needed to exercise the Codex worker itself. Its identity contract is tested offline from fixtures. |
| OS | Windows 10/11 x64 | Credential presence probes use Windows Credential Manager and `cmdkey`. Non-Windows hosts can run every suite; credential probes report `absent`. |

## 2. Clean clone and pinned environment

```bash
git clone https://github.com/Nerd0008/mukund-chief-control-plane.git
cd mukund-chief-control-plane
```

Create the isolated interpreter and install **from the lock** (never from an
unpinned `pip install`):

```bash
# uv (creates/downloads exactly CPython 3.11.16)
uv venv --python 3.11.16 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.lock   # Windows
uv pip install --python .venv/bin/python        -r requirements.lock   # POSIX
```

```bash
# pip fallback (interpreter must already be 3.11.x)
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock            # Windows
.venv/bin/python        -m pip install -r requirements.lock            # POSIX
```

`.venv/` is ignored by git; a virtual environment is never part of a release.

### What the lock contains

`requirements.txt` is the human-readable direct-dependency manifest;
`requirements.lock` is the generated, **hash-pinned transitive closure** for
CPython 3.11 (`uv pip compile requirements.txt --python-version 3.11
--python-platform windows --generate-hashes -o requirements.lock`).

| Package | Version | Role |
|---|---|---|
| `openpyxl` | 3.1.5 | Career Ops / Company Watch workbook writes (runtime) |
| `PyYAML` | 6.0.3 | config / profile / schedule YAML parsing (runtime) |
| `pytest` | 9.1.1 | `career-ops/tests/`, `company-watch/tests/` (test-only) |

Transitive pins: `et-xmlfile`, `colorama`, `iniconfig`, `packaging`, `pluggy`,
`pygments`. Everything else the repository imports is the Python 3.11 standard
library.

Regenerate/verify the inventory at any time:

```bash
python scripts/dependency_inventory.py           # human summary
python scripts/dependency_inventory.py --check    # exit 1 if an import is undeclared
```

The checker classifies each top-level import as stdlib, repository-local,
declared third-party, or machine-local-runtime, and fails on anything
undeclared. It reports `eb`, `governor` and `adapters` as machine-local runtime
modules (see §5).

## 3. Verify the checkout

```bash
python scripts/dependency_inventory.py --check
python scripts/codex_identity_contract_check.py
python scripts/release_manifest.py --out release/release-manifest.json
```

`release_manifest.py` records commit SHA, dirty state, supported Python, lock
hash, artifact hashes, a source-tree hash and the acceptance-evidence
identifiers. Re-check its internal consistency with:

```bash
python scripts/release_manifest.py --verify --out release/release-manifest.json
```

## 4. Running the suites

`exec-brain/` suites are `unittest`-style and are run as scripts with
`exec-brain` on `PYTHONPATH`. `career-ops/` and `company-watch/` suites are
`pytest`-style.

```bash
# E3 baseline (unittest, 58 tests)
PYTHONPATH=exec-brain python exec-brain/tests/test_e3.py

# Full repository acceptance / evidence runner (21 suites, per-suite counts)
python scripts/evidence_runner.py --label <label> --out-dir audits/evidence/<stamp>-<label>

# Career Ops + Company Watch (pytest)
python -m pytest career-ops/tests/ -q
python -m pytest company-watch/tests/ -q
```

The evidence runner records the code SHA, interpreter, exact command and
collected/passed/failed/error/skipped counts **per suite** and writes
`evidence.json` + `evidence.md`. It never infers a result: a suite that does not
produce a summary line is recorded as `unavailable`, not as passing.

E1/E2 suites (`test_eb.py`, `test_governor.py`) import `eb.py` / `governor.py`
/ `adapters.py` from the machine-local runtime root
(`%LOCALAPPDATA%\hermes\exec-brain\`). Without that root they are reported
`unavailable` with the guard note — that is the truthful result on a bare clone.

## 5. Machine-local provisioning (NOT reproducible from an archive)

| Dependency | Why it is local | Deterministic probe | Expected on a provisioned host |
|---|---|---|---|
| Hermes runtime root `%LOCALAPPDATA%\hermes\exec-brain\` (`eb.py`, `governor.py`, `adapters.py`, live adapters) | Live runtime state; evolves independently of this curated repository | `python scripts/deployment_preflight.py` (check 2) | PASS, or E1/E2 suites report `unavailable` |
| Provider credentials (Windows Credential Manager targets `deepseek`, `mistral`, `gemini-api`, … or env vars) | Secrets are never committed and never printed | `python scripts/e3_credential_presence_probe.py` | per-provider `present` / `absent`; value never read |
| Hermes state databases (`exec_brain.db`, `governor.db`, `orchestration.db`, `state.db`, …) | Raw high-frequency/owner data | `python scripts/deployment_preflight.py` (check 3) — runs `PRAGMA integrity_check` | `ok` per database |
| Codex CLI login (`%USERPROFILE%\.codex\auth.json`) | Personal ChatGPT/agent login | `python scripts/codex_identity_contract_check.py` → `codex_local_facts` | `login_store_present: true` (content never read) |
| Codex CLI executable | Installed per host under `%LOCALAPPDATA%\OpenAI\Codex\bin\*\codex.exe`, hash-specific dirs go stale | `python scripts/codex_identity_contract_check.py` → `codex_local_facts.cli_resolved` / `cli_version` | resolved + version reported |
| Owner application data (`runtime/career-ops/`, `runtime/company-watch/`, `runtime/linkedin/`, `runtime/chief/`) | Names Mukund's applications, employers, drafts and contacts | `git check-ignore -v <path>` | matches a `.gitignore` rule (never committed) |
| Windows scheduled tasks (`Hermes_Gateway`, `ChiefDiscordSync`, `ChiefCareerScan-*`, …) | Host provisioning, not source code | `python scripts/deployment_preflight.py` (check 4) | present/enabled per `deployments/06-service-definitions.md` |
| Host/package inventory | Machine-specific | `python scripts/deployment_inventory.py` | writes `deployments/inventory-<stamp>.json` |

All four probes are read-only, make **no network call**, and never read a
credential value.

## 6. Codex worker identity contract (portable)

`codex doctor --json` is not guaranteed to report a provider. The adapter
therefore records, with explicit provenance:

* `configured_provider` / `configured_model` — the CLI's own configuration
  declaration (`config.load`). A declaration, never execution evidence.
* `provider` — set **only** from a live probe that actually reports one
  (`network.websocket_reachability`), with
  `provider_provenance = "observed:network.websocket_reachability"`;
  otherwise `"unknown"` with `provider_provenance = "unknown"`.
* `model` — the execution-observed served model. The CLI does not expose it, so
  it is always `"unknown"`.

A configured provider is never promoted to the observed identity: UNKNOWN is
never converted to `openai`. Routability still requires a successful execution
plus verified E2 linkage, and qualification still requires benchmark evidence —
neither was relaxed.

Compatibility fixtures (offline, no CLI needed):
`exec-brain/tests/fixtures/codex_doctor_provider_openai.json`,
`codex_doctor_provider_unknown.json`,
`codex_doctor_configured_provider_only.json`.

```bash
python scripts/codex_identity_contract_check.py    # fixtures + audit reproduction + local facts
```

## 7. Release archive

```bash
python scripts/make_release_archive.py --out release/chief-<sha>.zip
python scripts/verify_release_archive.py release/chief-<sha>.zip \
    --expect-commit <sha> --expect-lock-sha256 <sha256>
```

The archive is exported with `git archive` (no `.git`, no untracked or ignored
files, so private runtime data cannot be included), then a
`release-manifest.json` computed **from the exported tree itself** is injected
and the finished ZIP is re-verified before the command reports success. See
`docs/RELEASE.md`.

## 8. Known limits

* A source archive carries no Git history by design; identity is proven by the
  recorded commit SHA plus content hashes, never by fabricating history.
* E1/E2 suites require the machine-local runtime root; on a bare clone they are
  `unavailable` rather than failing falsely.
* Tests that assert an *absence* of credentials (e.g. the "without credentials"
  adapter tests) inject that absence explicitly, so a provisioned host key can
  never change their result.
