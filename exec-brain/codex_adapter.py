#!/usr/bin/env python3
"""E3 Codex CLI ExecutionAdapter — non-interactive Codex execution."""

import json
import os
import re
import shutil
import subprocess
import time
import uuid
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Issue #5 (revised 2026-09-23): stable, hash-agnostic executable resolution.
# The previous value was a hardcoded hash-specific path
# (bin/247581e40ee272fb/codex.exe) that went stale after a Codex update and
# made the whole adapter unimportable ("Codex CLI not found"). Resolution order:
#   1. explicit override: CODEX_EXECUTABLE (env) / CODEX_CLI_PATH (env)
#   2. PATH via shutil.which("codex")
#   3. validated installed builds under %LOCALAPPDATA%\OpenAI\Codex\bin\*\codex.exe
# Every candidate must pass `codex.exe --version` before it is accepted, and only
# the resolved path/version are ever recorded — never credentials.
CODEX_EXECUTABLE_ENV = ("CODEX_EXECUTABLE", "CODEX_CLI_PATH")
CODEX_BIN_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"


def _default_model() -> str:
    """Model slug for dispatches that do not name one.

    The CLI must always be told which model to use. `~/.codex/config.toml` is
    written by the Codex desktop app and can name a slug the CLI rejects outright
    ("not supported when using Codex with a ChatGPT account"), which makes every
    dispatch fail behind an otherwise clean exit code. Override with
    CODEX_MODEL / CAREER_OPS_CODEX_MODEL.
    """
    return (os.environ.get("CODEX_MODEL") or os.environ.get("CAREER_OPS_CODEX_MODEL")
            or "gpt-6-sol")


def _codex_version_of(exe: Path) -> Optional[str]:
    """Return the CLI version string if `exe` is a working Codex CLI, else None."""
    try:
        if not exe.is_file():
            return None
        result = subprocess.run(
            [str(exe), "--version"], capture_output=True, text=True, timeout=20
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    version = (result.stdout or "").strip()
    return version or None


def _version_sort_key(version: str) -> Tuple:
    """Deterministic ordering key: numeric parts first, then the raw string."""
    nums = tuple(int(n) for n in re.findall(r"\d+", version)[:6])
    return (nums, version)


def _installed_codex_candidates() -> List[Path]:
    """Installed Codex builds under the Codex bin root, in stable order."""
    try:
        if not CODEX_BIN_ROOT.is_dir():
            return []
        return [
            child / "codex.exe"
            for child in sorted(CODEX_BIN_ROOT.iterdir())
            if (child / "codex.exe").is_file()
        ]
    except Exception:
        return []


def _resolve_codex_executable() -> Path:
    """Resolve the Codex CLI executable deterministically.

    Order: explicit override -> PATH -> validated installed bin candidates.
    A candidate is only accepted after `--version` succeeds. When several
    installed builds validate, the highest validated version wins (ties broken
    by path) so the choice is deterministic and recorded.
    """
    for name in CODEX_EXECUTABLE_ENV:
        override = os.environ.get(name)
        if not override:
            continue
        candidate = Path(override)
        if _codex_version_of(candidate) is None:
            raise RuntimeError(
                f"Codex CLI not found: {name} is set to {override!r} but "
                f"`--version` did not succeed"
            )
        return candidate

    on_path = shutil.which("codex")
    if on_path:
        candidate = Path(on_path)
        if _codex_version_of(candidate) is not None:
            return candidate

    validated = [
        (p, v)
        for p, v in ((p, _codex_version_of(p)) for p in _installed_codex_candidates())
        if v is not None
    ]
    if validated:
        validated.sort(key=lambda pv: (_version_sort_key(pv[1]), str(pv[0])))
        return validated[-1][0]

    raise RuntimeError(
        "Codex CLI not found: checked "
        f"{' / '.join(CODEX_EXECUTABLE_ENV)} override, PATH, and "
        f"{CODEX_BIN_ROOT}/*/codex.exe (none validated via --version)"
    )



# Issue #3: Safe default execution profile
SAFE_EXECUTION_PROFILE = {
    "sandbox": "workspace-write",
    "skip_git_repo_check": True,
    "enable_approvals": True,
}

# Unsafe profile - explicitly named, disabled by default
UNSAFE_EXECUTION_PROFILE = {
    "sandbox": "danger-full-access",
    "skip_git_repo_check": True,
    "enable_approvals": False,
    "requires_isolated_execution_policy": True,
}


# Provenance labels for identity fields. Kept as constants so tests and callers
# never have to match on a string literal by hand.
PROVENANCE_OBSERVED_WS = "observed:network.websocket_reachability"
PROVENANCE_UNKNOWN = "unknown"


def parse_doctor_identity(report: Dict[str, Any],
                          version: str = "unknown",
                          executable_name: Optional[str] = None,
                          executable_dir: Optional[str] = None) -> Dict[str, Any]:
    """Parse a `codex doctor --json` payload into a truthful identity record.

    Provenance contract (2026-09-24 release-reproducibility remediation):

    * ``configured_provider`` / ``configured_model`` come from the CLI's own
      configuration report (``config.load``). They are *declarations* — what the
      CLI is told to use — and are never promoted to observed identity.
    * ``provider`` is only filled when a live probe actually reports a provider
      (``network.websocket_reachability`` handshake). Otherwise it stays
      ``unknown`` and ``provider_provenance`` records that the CLI did not
      report it. A configured value is never copied into ``provider``: turning
      an unreported provider into ``openai`` would fabricate provider identity.
    * ``model`` is the execution-observed served model. The Codex CLI does not
      expose it, so it always stays ``unknown``.

    Splitting the parse out of the adapter is deliberate: it makes the contract
    testable from recorded payloads without executing or even installing Codex.
    """
    checks = report.get("checks") or {}

    def _details(check_id):
        entry = checks.get(check_id) or {}
        return (entry.get("details") or {}) if isinstance(entry, dict) else {}

    def _truthy(value):
        # `codex doctor --json` reports these as strings ("true"/"false").
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() == "true"

    identity: Dict[str, Any] = {
        "provider": "unknown",
        "provider_provenance": PROVENANCE_UNKNOWN,
        "configured_provider": "unknown",
        "model": "unknown",  # execution-observed model: not exposed by the CLI
        "configured_model": "unknown",
        "auth_mode": "unknown",
        "version": version,
        "interface": "Codex CLI",
        "cancellation_support": "UNSUPPORTED",  # Issue #7
        "e2_usage_linkage": "NOT_VERIFIED",     # Issue #6
        "supports_websockets": True,
        "supports_jsonl": True,
    }

    auth = _details("auth.credentials")
    auth_check = checks.get("auth.credentials") or {}
    identity["auth_configured"] = auth_check.get("status") == "ok"
    if auth.get("stored auth mode"):
        identity["auth_mode"] = auth["stored auth mode"]
    identity["auth_storage_mode"] = auth.get("auth storage mode", "unknown")
    identity["stored_api_key"] = _truthy(auth.get("stored API key"))

    # config.load is NOT execution evidence: recorded separately, never
    # promoted to the execution-observed model identity.
    config = _details("config.load")
    identity["configured_model"] = config.get("model", "unknown")
    if config.get("model provider"):
        identity["configured_provider"] = config["model provider"]

    # Only a live observation may populate the observed provider identity.
    ws_check = checks.get("network.websocket_reachability") or {}
    ws = _details("network.websocket_reachability")
    identity["websocket_reachable"] = ws_check.get("status") == "ok"
    identity["server_model_present"] = _truthy(ws.get("server model present"))
    if ws.get("model provider"):
        identity["provider"] = ws["model provider"]
        identity["provider_provenance"] = PROVENANCE_OBSERVED_WS
    if ws.get("provider name"):
        identity["observed_provider_name"] = ws["provider name"]

    identity["cli_version"] = report.get("codexVersion", version)
    if executable_name is not None:
        identity["resolved_executable_name"] = executable_name
    if executable_dir is not None:
        identity["resolved_executable_dir"] = executable_dir
    return identity


class CodexExecutionAdapter:
    """Executes non-interactive Codex CLI commands."""

    def __init__(self, execution_profile: str = "safe"):
        self.executable = _resolve_codex_executable()
        self.execution_profile = execution_profile
        self._profile_config = self._resolve_profile(execution_profile)

    def _resolve_profile(self, profile_name: str) -> Dict[str, Any]:
        """Resolve execution profile."""
        if profile_name == "safe":
            return SAFE_EXECUTION_PROFILE.copy()
        elif profile_name == "unsafe":
            return UNSAFE_EXECUTION_PROFILE.copy()
        else:
            raise ValueError(f"Unknown execution profile: {profile_name}")

    def dispatch(self, contract: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a non-interactive Codex command.
        
        Args:
            contract: WorkerContract dict with objective, etc.
            
        Returns:
            Dict with dispatch_id, status, raw_output, metadata
        """
        dispatch_id = f"codex-{uuid.uuid4().hex[:12]}"
        contract_id = contract.get('contract_id', 'unknown')
        objective = contract.get('objective', '')
        model = contract.get('model', None) or _default_model()
        timeout = contract.get('timeout', 300)

        # Build command with safe profile defaults
        cmd = [
            str(self.executable),
            "exec",
            "--json",
            "--skip-git-repo-check",
        ]

        # Issue #3: Sandbox mode from profile (safe by default)
        sandbox_mode = self._profile_config.get("sandbox", "workspace-write")
        if sandbox_mode == "danger-full-access":
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            cmd.extend(["--sandbox", sandbox_mode])

        if model:
            cmd.extend(["--model", model])

        cwd = contract.get('working_directory')
        if cwd:
            cmd.extend(["--cd", cwd])

        cmd.append(objective)

        # Execute
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd or "."
            )
            elapsed = time.time() - start_time

            # Parse JSONL output
            output_lines = []
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        try:
                            output_lines.append(json.loads(line))
                        except json.JSONDecodeError:
                            output_lines.append({"type": "raw", "content": line})

            # Extract final message.
            # `codex exec --json` (0.155.x) emits thread.started / turn.started /
            # item.* / turn.completed; the assistant reply is the item.completed
            # item of type "agent_message" (older builds used "message").
            # turn.completed also carries `last_agent_message` as a fallback.
            final_message = None
            for line in output_lines:
                if line.get("type") == "item.completed":
                    item = line.get("item", {})
                    if item.get("type") in ("agent_message", "message"):
                        message = item.get("text") or item.get("content")
                        if isinstance(message, list):
                            message = "".join(
                                part.get("text", "") for part in message
                                if isinstance(part, dict)
                            )
                        if message:
                            final_message = message
            if not final_message:
                for line in output_lines:
                    if line.get("type") == "turn.completed":
                        last = line.get("last_agent_message")
                        if isinstance(last, str) and last.strip():
                            final_message = last

            # Check for errors
            error = None
            has_error = False
            for line in output_lines:
                if line.get("type") in ("error", "turn.failed"):
                    error = line.get("message") or str(line)
                    has_error = True
                    break
                if line.get("type") == "item.completed":
                    item = line.get("item", {})
                    if item.get("type") == "error":
                        error = item.get("message") or str(item)
                        has_error = True
                        break

            # Issue #4: Sanitized dispatch metadata - no raw command with objective
            objective_hash = hashlib.sha256(objective.encode()).hexdigest()[:12]
            sanitized_summary = objective[:50] + "..." if len(objective) > 50 else objective

            return {
                'dispatch_id': dispatch_id,
                'status': 'FAILED' if (result.returncode != 0 or has_error) else 'COMPLETED',
                'provider': 'openai',
                'model': model or 'unknown',
                'raw_output': output_lines,
                'final_message': final_message,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'exit_code': result.returncode,
                'error': error,
                'runtime_s': elapsed,
                'usage_tokens': self._extract_usage(output_lines),
                'codex_thread_id': self._extract_thread_id(output_lines),
                # Issue #4: Sanitized metadata
                'dispatch_metadata': {
                    'dispatch_time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start_time)),
                    'elapsed_seconds': elapsed,
                    'objective_hash': objective_hash,
                    'objective_summary': sanitized_summary,
                    'cli_flags': ['--json', '--skip-git-repo-check', '--sandbox', sandbox_mode],
                    'working_directory': cwd or ".",
                    'execution_profile': self.execution_profile,
                    'timeout': timeout,
                    'contract_id': contract_id,
                    'resolved_executable': str(self.executable),
                    'resolved_version': self._get_version(),
                }
            }

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            objective_hash = hashlib.sha256(objective.encode()).hexdigest()[:12]
            sanitized_summary = objective[:50] + "..." if len(objective) > 50 else objective

            return {
                'dispatch_id': dispatch_id,
                'status': 'TIMEOUT',
                'provider': 'openai',
                'model': model or 'unknown',
                'final_message': None,
                'exit_code': -1,
                'error': f'Timeout after {timeout}s',
                'runtime_s': elapsed,
                'usage_tokens': None,
                'dispatch_metadata': {
                    'dispatch_time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start_time)),
                    'elapsed_seconds': elapsed,
                    'objective_hash': objective_hash,
                    'objective_summary': sanitized_summary,
                    'cli_flags': ['--json', '--skip-git-repo-check', '--sandbox', sandbox_mode],
                    'working_directory': cwd or ".",
                    'execution_profile': self.execution_profile,
                    'timeout': timeout,
                    'contract_id': contract_id,
                    'resolved_executable': str(self.executable),
                    'resolved_version': self._get_version(),
                }
            }

    def retrieve(self, dispatch_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a completed dispatch (no-op for exec, already captured)."""
        return None

    def cancel(self, dispatch_id: str) -> bool:
        """Cancel is not supported for exec mode.
        
        Issue #7: Honestly report cancellation support as UNSUPPORTED.
        """
        return False

    def check_health(self) -> Dict[str, str]:
        """Check if Codex CLI is healthy."""
        try:
            result = subprocess.run(
                [str(self.executable), "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return {'status': 'healthy', 'version': result.stdout.strip()}
            return {'status': 'unhealthy', 'error': result.stderr}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}

    def get_identity(self) -> Dict[str, Any]:
        """Get provider/model identity from Codex.

        Delegates parsing to `parse_doctor_identity`, which keeps configured
        declarations (`config.load`) separate from provider identity actually
        observed by a live probe (`network.websocket_reachability`) and reports
        UNKNOWN when the CLI does not report either. Never fabricates a provider
        or a served model.
        """
        version = self._get_version()
        try:
            result = subprocess.run(
                [str(self.executable), "doctor", "--json"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                return {
                    'provider': 'unknown',
                    'provider_provenance': PROVENANCE_UNKNOWN,
                    'configured_provider': 'unknown',
                    'model': 'unknown',
                    'configured_model': 'unknown',
                    'version': version,
                    'interface': 'Codex CLI',
                    'cancellation_support': 'UNSUPPORTED',
                    'e2_usage_linkage': 'NOT_VERIFIED',
                    'error': f"doctor --json exit {result.returncode}",
                }
            report = json.loads(result.stdout)
            return parse_doctor_identity(
                report,
                version=version,
                executable_name=self.executable.name,
                executable_dir=self.executable.parent.name,
            )
        except Exception as e:
            return {
                'provider': 'unknown',
                'provider_provenance': PROVENANCE_UNKNOWN,
                'configured_provider': 'unknown',
                'model': 'unknown',
                'configured_model': 'unknown',
                'version': version,
                'cancellation_support': 'UNSUPPORTED',
                'e2_usage_linkage': 'NOT_VERIFIED',
                'error': str(e)
            }

    def estimate_usage(self, contract: Dict[str, Any]) -> Dict[str, Any]:
        """Estimate usage for a contract (rough)."""
        objective = contract.get('objective', '')
        prompt_tokens = len(objective.split()) * 2
        return {
            'estimated_prompt_tokens': prompt_tokens,
            'estimated_completion_tokens': 500,
            'estimated_total_tokens': prompt_tokens + 500,
            'confidence': 'low',
            'note': 'Rough estimation based on prompt length'
        }

    def _get_version(self) -> str:
        """Get Codex CLI version."""
        try:
            result = subprocess.run(
                [str(self.executable), "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip().replace('codex-cli ', '')
        except Exception:
            pass
        return 'unknown'

    def _extract_usage(self, output_lines: List[Dict]) -> Optional[Dict[str, Any]]:
        """Extract provider-returned token usage from JSONL output, if exposed.

        `codex exec --json` (0.155.x) reports usage on the terminal
        `turn.completed` event:

            {"type": "turn.completed",
             "usage": {"input_tokens": .., "cached_input_tokens": ..,
                       "output_tokens": .., "reasoning_output_tokens": ..}}

        Only token fields the provider actually returns are kept; a request with
        no usage block yields None. Never fabricate or estimate a missing value.
        """
        for line in output_lines:
            for candidate in (
                line,
                line.get("usage"),
                line.get("item"),
                (line.get("item") or {}).get("usage") if isinstance(line.get("item"), dict) else None,
            ):
                if not isinstance(candidate, dict):
                    continue
                tokens = {
                    k: v
                    for k, v in candidate.items()
                    if isinstance(v, int) and ("token" in k or k in ("input", "output"))
                }
                if tokens:
                    return tokens
        return None

    def _extract_thread_id(self, output_lines: List[Dict]) -> Optional[str]:
        """Extract thread ID from JSONL output."""
        for line in output_lines:
            if line.get("type") == "thread.started":
                return line.get("thread_id")
        return None


# ─── E2 linkage (public interface only) ──────────────────────────

# The E2 runtime (governor.py + governor.db) lives next to this module in the
# deployed runtime root; in the repository checkout it does not. E3 must never
# SQL-write governor.db directly — it only ever calls the public E2 function.
E2_RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"


def _governor_dir() -> Path:
    here = Path(__file__).resolve().parent
    if (here / "governor.py").exists():
        return here
    return E2_RUNTIME_ROOT


def report_usage_to_e2(result: Dict[str, Any]) -> Optional[str]:
    """Report observed usage through the E2 governor.record_request() interface.

    Returns the E2 request id, or None when E2 is unavailable. Raises only on
    programming errors; provider data absent means tokens are recorded as None
    (never fabricated).
    """
    import sys

    gov_dir = _governor_dir()
    if not (gov_dir / "governor.py").exists():
        return None
    if str(gov_dir) not in sys.path:
        sys.path.insert(0, str(gov_dir))
    import governor

    usage = result.get("usage") or {}
    status = "success" if result.get("status") == "COMPLETED" else "error"
    latency_ms = int((result.get("runtime_s") or 0) * 1000)

    con = governor.connect_gov()
    try:
        return governor.record_request(
            con,
            provider="openai-codex-cli",
            model=result.get("model") if result.get("model") != "unknown" else None,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            monetary_cost="unknown",  # ChatGPT subscription: no per-request cost exposed
            status=status,
            error_code=result.get("error") if status == "error" else None,
            latency_ms=latency_ms,
        )
    finally:
        con.close()


# ─── Bounded readiness smoke ─────────────────────────────────────

# One deterministic, harmless, non-interactive prompt: no tool use, no file
# access, no repository change. Exactly one of these is spent per re-validation.
SMOKE_OBJECTIVE = (
    "Respond with exactly the single word READY and nothing else. "
    "Do not run any commands, do not read or write any files, "
    "and do not use any tools."
)


def run_smoke_test(adapter: Optional[Any] = None,
                   workdir: Optional[str] = None) -> Dict[str, Any]:
    """Run exactly one harmless deterministic non-interactive Codex execution.

    Readiness only: a PASS here proves execution readiness, not capability.
    Qualification stays UNPROVEN until cold-start/task-role benchmark evidence
    exists, and `routable` additionally requires a verified E2 request record.
    """
    if adapter is None:
        adapter = CodexExecutionAdapter()

    health = adapter.check_health()
    if health['status'] != 'healthy':
        return {
            'passed': False,
            'blocked_reason': 'health_check_failed',
            'health': health,
            'routable': False,
            'qualification': 'UNPROVEN',
        }

    identity = adapter.get_identity()

    contract = {
        'contract_id': 'codex-readiness-smoke',
        'objective': SMOKE_OBJECTIVE,
        'timeout': 180,
    }
    if workdir:
        contract['working_directory'] = workdir

    result = adapter.dispatch(contract)

    final_message = (result.get('final_message') or '').strip()
    usage = result.get('usage_tokens')
    passed = (
        result.get('status') == 'COMPLETED'
        and not result.get('error')
        and final_message != ''
    )

    e2_request_id = None
    e2_error = None
    if passed:
        try:
            e2_request_id = report_usage_to_e2(result)
            if e2_request_id is None:
                e2_error = 'E2 governor runtime not found'
        except Exception as e:  # noqa: BLE001 - reported, not swallowed
            e2_error = f"{type(e).__name__}: {e}"

    return {
        'passed': passed,
        'dispatch_id': result.get('dispatch_id'),
        'exit_code': result.get('exit_code'),
        'final_message': final_message,
        'blocked_reason': None if passed else (
            result.get('error') or f"exit_code={result.get('exit_code')}"
        ),
        'raw_output': result.get('raw_output'),
        'health': health,
        'identity': identity,
        'usage': usage,
        'usage_exposed': usage is not None,
        'thread_id': result.get('codex_thread_id'),
        'dispatch_metadata': result.get('dispatch_metadata'),
        'e2_request_id': e2_request_id,
        'e2_usage_linkage': 'VERIFIED' if e2_request_id else 'NOT_VERIFIED',
        'e2_error': e2_error,
        'routable': bool(passed and e2_request_id),
        'qualification': 'UNPROVEN',  # smoke readiness is not qualification
    }

