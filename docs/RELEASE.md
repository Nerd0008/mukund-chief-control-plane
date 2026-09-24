# RELEASE — identity, archives and reproducibility

This document defines what a "release" of this control plane is, how its
identity is proven, and — just as importantly — what a release archive cannot
carry.

## 1. What a release is

A release is a **committed revision of this repository** plus its pinned
dependency set. It is identified by:

| Identity element | Where it is recorded |
|---|---|
| Commit SHA / branch / commit subject / commit date | `release-manifest.json` → `repository` |
| Dirty state of the authoring worktree (+ modified tracked paths) | `release-manifest.json` → `repository` |
| Supported Python | `release-manifest.json` → `python` (`3.11.16`, line `3.11.x`; 3.14.x explicitly unsupported) |
| Direct dependencies | `requirements.txt` (sha256 in the manifest) |
| Fully pinned, hash-verified dependency closure | `requirements.lock` (sha256 in the manifest) |
| Important deployable artifacts | `release-manifest.json` → `artifacts` (path + sha256 + size + category) |
| Whole shipped tree | `release-manifest.json` → `source_tree` (file count + aggregate sha256) |
| Acceptance evidence | `release-manifest.json` → `acceptance_evidence` (identifiers under `audits/evidence/`) |

Generate it with:

```bash
python scripts/release_manifest.py --out release/release-manifest.json
python scripts/release_manifest.py --verify --out release/release-manifest.json
```

`release/` is git-ignored: the manifest is a **build output**. The durable
identity record for an accepted run lives under `audits/evidence/`.

`scripts/release_manifest.py` hashes the files it finds in the tree it is
pointed at, so run it from a clean clone or checkout (line endings are pinned by
`.gitattributes`). `scripts/make_release_archive.py` instead computes the
manifest from the **exported committed bytes**, which is the authoritative path
for a shipped archive.

## 2. Archive guarantees

```bash
python scripts/make_release_archive.py --out release/chief-<sha>.zip
python scripts/verify_release_archive.py release/chief-<sha>.zip \
    --expect-commit <sha> --expect-lock-sha256 <sha256> [--repo <path>]
```

How the archive is produced:

1. `git archive` exports the **committed tree only** — no `.git`, no untracked
   files, no ignored files. Private runtime data (owner application data,
   Hermes state databases, credential stores) therefore cannot be packaged even
   by accident.
2. Line endings are pinned to the **committed bytes**: the export forces
   `core.autocrlf=false -c core.eol=lf`, and `.gitattributes` sets
   `* text=auto eol=lf`. Without this, `git archive` inherited a Windows host's
   `core.autocrlf=true` and rewrote CRLF, so the exported bytes — and therefore
   every content hash recorded in the manifest — differed from the repository's
   committed blobs and from an export made on Linux. With it, an archive's
   `requirements.lock` hash equals `git show <commit>:requirements.lock | sha256`
   on any platform, so `--expect-lock-sha256` (or any blob-derived hash) can
   actually bind an archive to a commit.
3. The release manifest is computed **from the exported tree itself**, so every
   hash provably describes bytes that are inside the archive.
4. `release-manifest.json` and `ARCHIVE-README.txt` are injected into the ZIP.
5. The finished ZIP is re-opened, extracted to a temporary directory and
   re-verified before the command reports success.

Verification is independent of the archive's own claims: hashes are recomputed
from the ZIP bytes. It fails on

- a missing `release-manifest.json` (no identity — refuse),
- any artifact hash mismatch, or a listed artifact that is absent,
- a dependency-manifest or lock hash mismatch,
- an aggregate source-tree hash mismatch (which also proves no file was added
  or removed),
- a `.git` entry or a directory that looks like Git history,
- a hard-excluded secret-like path (`.env*`, `*.pem`, `*.key`, `*.ppk`,
  `id_rsa*`, `authorized_keys`, `known_hosts`, `auth.json`, `*.db`,
  `*.sqlite3`, `*.session`, `cookies*`),
- a recorded dirty worktree,
- a commit that does not exist in `--repo` when that option is supplied.

**No Git history is fabricated.** A ZIP cannot carry `.git`; the archive proves
identity through the recorded commit SHA plus content hashes, and the archive
README says so explicitly. To turn an archive back into a working revision:
clone the repository and check out the manifest's `commit_sha`.

## 3. Reproducibility from a clean clone or archive

Confirmed reproducible **without** machine-local state:

- the pinned interpreter environment (`uv venv --python 3.11.16` + install from
  `requirements.lock`, all packages hash-verified);
- `scripts/dependency_inventory.py --check` (every third-party import declared);
- `scripts/codex_identity_contract_check.py` (identity contract + audit
  reproduction, no CLI and no network needed);
- the E3 baseline suite and the 21-suite repository evidence runner;
- `scripts/release_manifest.py` and the archive build/verify tooling.

**Deliberately machine-local** (documented with a deterministic probe in
`docs/SETUP.md` §5) — these cannot be reproduced from a source archive and are
never in one:

| Item | Deterministic probe |
|---|---|
| Hermes runtime root (`%LOCALAPPDATA%\hermes\exec-brain\`: `eb.py`, `governor.py`, `adapters.py`) | `scripts/deployment_preflight.py` (module-set check) — without it the E1/E2 suites are truthfully `unavailable` |
| Provider credentials (Windows Credential Manager / env vars) | `scripts/e3_credential_presence_probe.py` (presence only, no network) |
| Hermes state databases | `scripts/deployment_preflight.py` (`PRAGMA integrity_check`) |
| Codex CLI executable + login (`%USERPROFILE%\.codex\auth.json`) | `scripts/codex_identity_contract_check.py` → `codex_local_facts` (presence only) |
| Owner application data under `runtime/` | `git check-ignore -v <path>` |
| Windows scheduled tasks | `scripts/deployment_preflight.py` (task check) |

## 4. Codex identity contract (portable behaviour)

`codex doctor --json` may or may not report a provider; the contract is:

| Field | Meaning | Source |
|---|---|---|
| `configured_provider`, `configured_model` | what the CLI is *configured* to use — a declaration, not evidence | `config.load` |
| `provider`, `provider_provenance` | provider identity **only when a live probe reports it** (`observed:network.websocket_reachability`); otherwise `unknown` / `unknown` | `network.websocket_reachability` |
| `model` | execution-observed served model — always `unknown` (the CLI does not expose it) | never fabricated |

A configured provider is never promoted to the observed identity, and UNKNOWN is
never converted to `openai`. Routability still requires a successful execution
plus a verified E2 request record, and qualification still requires
evidence-backed benchmark results — this remediation did not relax either.

Recorded compatibility payloads (checked offline on every run):
`exec-brain/tests/fixtures/codex_doctor_provider_openai.json`,
`codex_doctor_provider_unknown.json`,
`codex_doctor_configured_provider_only.json`.

## 5. Isolated-environment acceptance evidence

Run from a clean isolated interpreter created from the pinned artifacts
(`uv venv --python 3.11.16`, install from `requirements.lock`, no repository
packages on `PYTHONPATH` except the suite import roots), on 2026-09-24.

| Acceptance | Result |
|---|---|
| E3 baseline (`exec-brain/tests/test_e3.py`, isolated 3.11.16) | **58 collected / 58 passed / 0 failed / 0 skipped** |
| Repository evidence runner (`scripts/evidence_runner.py`, 21 suites) | **21 suites run / 21 passed / 0 failed / 0 unavailable; 583 collected / 583 passed** |
| Codex identity contract (`scripts/codex_identity_contract_check.py`) | contract holds; audit failure reproduced as a correction; providers covered `["openai", "unknown"]` |
| Dependency honesty (`scripts/dependency_inventory.py --check`) | OK — every third-party import declared |

Evidence: `audits/evidence/2026-09-24T15-45-00Z-isolated-release-reproducibility/`
(`evidence.json` + `evidence.md` record the exact interpreter path, per-suite
counts and the code SHA the run was executed at).

The recorded run is bound to code SHA `e9d2195`. The same suite was re-executed
unchanged at the archive commit in the same pinned interpreter and returned
identical totals: **21 suites / 583 collected / 583 passed / 0 failed /
0 unavailable**. The intervening commits touch release/state documentation, the
archive export tooling and `.gitattributes` only — no tested behaviour changed.

Note on counts: the audit's 579-collected figure is superseded. The current
count is **583 collected** (the E3 baseline grew from 54 to 58 tests as part of
this remediation: five truthful-contract Codex tests replaced one incorrect
exact-match test). The number is reported as measured, not forced to the old
value.

### What the isolated run does *not* prove

E1/E2 suites pass here because this host's machine-local Hermes runtime root is
present. On a bare clone without it, those two suites are recorded `unavailable`
(this is the truthful outcome, not a failure). Provider credentials, Hermes
state databases and the Codex login remain machine-local and are verified by the
probes listed in §3, not by the archive.
