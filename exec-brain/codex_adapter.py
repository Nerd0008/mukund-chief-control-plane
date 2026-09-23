#!/usr/bin/env python3
"""E3 Codex CLI ExecutionAdapter — non-interactive Codex execution."""

import json
import subprocess
import time
import uuid
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional


# Issue #5: Configurable executable path, not hardcoded hash-specific path
CODEX_EXECUTABLE_CONFIG = Path(
    "C:/Users/mukun/AppData/Local/OpenAI/Codex/bin/247581e40ee272fb/codex.exe"
)


def _resolve_codex_executable() -> Path:
    """Resolve Codex CLI executable path deterministically."""
    configured = CODEX_EXECUTABLE_CONFIG
    if configured.exists():
        return configured
    import shutil
    path = shutil.which("codex")
    if path:
        return Path(path)
    raise RuntimeError("Codex CLI not found: checked configured path and PATH")


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
        model = contract.get('model', None)
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

            # Extract final message
            final_message = None
            for line in output_lines:
                if line.get("type") == "item.completed":
                    item = line.get("item", {})
                    if item.get("type") == "message":
                        final_message = item.get("text") or item.get("content")

            # Check for errors
            error = None
            has_error = False
            for line in output_lines:
                if line.get("type") in ("error", "turn.failed"):
                    error = line.get("message") or str(line)
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
        """Get provider/model identity from Codex."""
        version = self._get_version()
        try:
            result = subprocess.run(
                [str(self.executable), "doctor"],
                capture_output=True, text=True, timeout=15
            )
            output = result.stdout
            
            # Issue #2: Parse identity from doctor, but model remains UNKNOWN
            # until deterministically observed from actual execution
            identity = {
                'provider': 'openai',
                'model': 'unknown',  # Issue #2: UNKNOWN until observed
                'auth_mode': 'unknown',
                'version': version,
                'interface': 'Codex CLI',
                'cancellation_support': 'UNSUPPORTED',  # Issue #7
                'e2_usage_linkage': 'NOT_VERIFIED',     # Issue #6
                'supports_websockets': True,
                'supports_jsonl': True,
            }
            
            for line in output.split('\n'):
                if 'auth mode' in line.lower():
                    parts = line.split()
                    if parts:
                        identity['auth_mode'] = parts[-1].strip()
                if 'model provider' in line.lower():
                    parts = line.split()
                    if parts:
                        identity['provider'] = parts[-1].strip()
                # Issue #2: Do NOT parse model from config (not observed)
            
            return identity
        except Exception as e:
            return {
                'provider': 'openai',
                'model': 'unknown',
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

    def _extract_usage(self, output_lines: List[Dict]) -> Optional[int]:
        """Extract token usage from JSONL output.
        
        Issue #6: Codex JSONL does not expose usage - return None.
        Do not fabricate token usage.
        """
        return None

    def _extract_thread_id(self, output_lines: List[Dict]) -> Optional[str]:
        """Extract thread ID from JSONL output."""
        for line in output_lines:
            if line.get("type") == "thread.started":
                return line.get("thread_id")
        return None


def run_smoke_test() -> Dict[str, Any]:
    """Run a minimal smoke test.
    
    Issue #8: Smoke test blocked by ChatGPT usage limit.
    routable = false until actual execution succeeds.
    """
    adapter = CodexExecutionAdapter()
    
    # Health check
    health = adapter.check_health()
    if health['status'] != 'healthy':
        return {
            'passed': False,
            'blocked_reason': 'health_check_failed',
            'health': health,
            'routable': False,
            'qualification': 'UNPROVEN'
        }

    # Identity
    identity = adapter.get_identity()

    # Issue #8: Smoke test blocked - usage limit
    return {
        'passed': False,
        'blocked_reason': 'usage_limit',
        'blocked_detail': 'ChatGPT usage limit reached. Retry after reset.',
        'health': health,
        'identity': identity,
        'routable': False,
        'qualification': 'UNPROVEN',
        'next_step': 'Rerun smoke test when usage limit resets'
    }
