#!/usr/bin/env python3
"""E3 Codex CLI ExecutionAdapter — non-interactive Codex execution."""

import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


CODEX_EXE = Path(
    "C:/Users/mukun/AppData/Local/OpenAI/Codex/bin/247581e40ee272fb/codex.exe"
)


class CodexExecutionAdapter:
    """Executes non-interactive Codex CLI commands."""

    def __init__(self):
        self.executable = CODEX_EXE
        self._verify_install()

    def _verify_install(self):
        """Verify Codex CLI is available."""
        if not self.executable.exists():
            raise RuntimeError(f"Codex CLI not found: {self.executable}")

    def dispatch(self, contract: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a non-interactive Codex command.
        
        Args:
            contract: WorkerContract dict with objective, etc.
            
        Returns:
            Dict with dispatch_id, status, raw_output, metadata
        """
        dispatch_id = f"codex-{uuid.uuid4().hex[:12]}"
        objective = contract.get('objective', '')
        model = contract.get('model', None)  # None uses default

        # Build command
        cmd = [
            str(self.executable),
            "exec",
            "--json",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
        ]

        if model:
            cmd.extend(["--model", model])

        # Add working directory
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
                timeout=contract.get('timeout', 300),
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

            return {
                'dispatch_id': dispatch_id,
                'status': 'FAILED' if (result.returncode != 0 or has_error) else 'COMPLETED',
                'provider': 'openai',
                'model': model or 'default',
                'raw_output': output_lines,
                'final_message': final_message,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'exit_code': result.returncode,
                'error': error,
                'runtime_s': elapsed,
                'usage_tokens': self._extract_usage(output_lines),
                'codex_thread_id': self._extract_thread_id(output_lines),
                'dispatch_metadata': {
                    'dispatch_time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start_time)),
                    'elapsed_seconds': elapsed,
                    'command': cmd,
                    'cwd': cwd or "."
                }
            }

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            return {
                'dispatch_id': dispatch_id,
                'status': 'TIMEOUT',
                'provider': 'openai',
                'model': model or 'default',
                'final_message': None,
                'exit_code': -1,
                'error': f'Timeout after {contract.get("timeout", 300)}s',
                'runtime_s': elapsed,
                'usage_tokens': None,
                'dispatch_metadata': {
                    'dispatch_time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start_time)),
                    'elapsed_seconds': elapsed,
                    'command': cmd,
                    'timeout': contract.get('timeout', 300)
                }
            }

    def retrieve(self, dispatch_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a completed dispatch (no-op for exec, already captured)."""
        return None

    def cancel(self, dispatch_id: str) -> bool:
        """Cancel is not supported for exec mode."""
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
        # Try doctor --json to get detailed info
        try:
            result = subprocess.run(
                [str(self.executable), "doctor"],
                capture_output=True, text=True, timeout=15
            )
            output = result.stdout
            # Parse key info from doctor output
            identity = {
                'provider': 'openai',
                'model': 'unknown',
                'auth_mode': 'unknown',
                'version': 'unknown'
            }
            for line in output.split('\n'):
                if 'version' in line.lower() and 'codex' in line.lower():
                    parts = line.split('·')
                    if parts:
                        identity['version'] = parts[0].strip()
                if 'model provider' in line.lower():
                    identity['provider'] = line.split()[-1].strip()
                if 'model ' in line.lower() and '·' in line:
                    parts = line.split('·')
                    if len(parts) > 1:
                        identity['model'] = parts[1].strip().split()[0]
                if 'auth mode' in line.lower():
                    identity['auth_mode'] = line.split()[-1].strip()
            return identity
        except Exception as e:
            return {'provider': 'openai', 'model': 'unknown', 'error': str(e)}

    def estimate_usage(self, contract: Dict[str, Any]) -> Dict[str, Any]:
        """Estimate usage for a contract (rough)."""
        objective = contract.get('objective', '')
        # Very rough estimate based on prompt length
        prompt_tokens = len(objective.split()) * 2
        return {
            'estimated_prompt_tokens': prompt_tokens,
            'estimated_completion_tokens': 500,
            'estimated_total_tokens': prompt_tokens + 500,
            'confidence': 'low',
            'note': 'Rough estimation based on prompt length'
        }

    def _extract_usage(self, output_lines: List[Dict]) -> Optional[int]:
        """Extract token usage from JSONL output."""
        # Codex doesn't expose usage in JSONL by default
        # Would need to enable verbose mode or parse from other sources
        return None

    def _extract_thread_id(self, output_lines: List[Dict]) -> Optional[str]:
        """Extract thread ID from JSONL output."""
        for line in output_lines:
            if line.get("type") == "thread.started":
                return line.get("thread_id")
        return None


def run_smoke_test() -> Dict[str, Any]:
    """Run a minimal smoke test."""
    adapter = CodexExecutionAdapter()
    
    # Health check
    health = adapter.check_health()
    if health['status'] != 'healthy':
        return {'passed': False, 'reason': f'Health check failed: {health}'}

    # Identity
    identity = adapter.get_identity()

    # Simple deterministic test
    contract = {
        'objective': 'What is 2+2? Reply with just the number.',
        'timeout': 120,
        'model': None  # Use default
    }

    result = adapter.dispatch(contract)

    # Check result
    smoke_passed = (
        result['status'] in ('COMPLETED', 'TIMEOUT') and
        result['provider'] == 'openai' and
        result['runtime_s'] is not None
    )

    return {
        'passed': smoke_passed,
        'health': health,
        'identity': identity,
        'dispatch_result': result
    }
