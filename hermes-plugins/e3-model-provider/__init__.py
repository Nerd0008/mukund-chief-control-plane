"""Hermes user model-provider plugin for the source-controlled E3 boundary."""
from __future__ import annotations

import os
from pathlib import Path

from providers import register_provider
from providers.base import ProviderProfile


class E3Profile(ProviderProfile):
    def get_model_context_length(self, model: str) -> int | None:
        """Declare the local E3 boundary's context bound to Hermes.

        E3 is an in-process routing boundary, so Hermes must not try to
        resolve ``e3-auto`` against a network provider catalog (which can
        otherwise produce an OpenRouter metadata warning).  The bound is the
        same conservative limit used by the E3 runtime.
        """
        return 256_000

    def create_client(self, **_kwargs):
        import sys
        configured = os.environ.get("HERMES_E3_RUNTIME_ROOT", "").strip()
        if configured:
            runtime = Path(configured).expanduser()
        else:
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            runtime = (Path(local_appdata) / "hermes" / "exec-brain"
                       if local_appdata else Path.home() / ".hermes" / "exec-brain")
        required = ("e3_service.py", "chief_routing.py", "department_dispatch.py")
        missing = [name for name in required if not (runtime / name).is_file()]
        if missing:
            raise RuntimeError(f"E3 runtime root is incomplete: {runtime} ({', '.join(missing)})")
        if str(runtime) not in sys.path:
            sys.path.insert(0, str(runtime))
        from hermes_e3_provider import E3ModelClient
        from e3_service import E3ApplicationService
        from department_dispatch import CareerOpsDepartment, DefaultDepartmentDispatcher
        source_root = os.environ.get("MUKUND_CHIEF_REPO_ROOT", "").strip()
        candidates = ([Path(source_root).expanduser()] if source_root else []) + [
            Path.home() / "Documents" / "mukund-chief-control-plane",
            Path.home() / "Documents" / "Codex" / "mukund-chief-control-plane-owner-decisions",
            runtime.parent,
        ]
        repo_root = next((candidate for candidate in candidates
                          if (candidate / "career-ops").is_dir()), runtime.parent)
        dispatcher = DefaultDepartmentDispatcher(
            career_ops=CareerOpsDepartment(repo_root=repo_root, allow_external=True))
        return E3ModelClient(E3ApplicationService(), department_dispatcher=dispatcher)


register_provider(E3Profile(
    name="e3",
    aliases=("chief-e3",),
    display_name="Chief E3",
    description="Hermes tool loop backed by E3 Stage-2 selection",
    auth_type="none",
    env_vars=(),
    base_url="e3://local",
    supports_health_check=False,
    supports_model_listing=False,
    fallback_models=("e3-auto",),
))
