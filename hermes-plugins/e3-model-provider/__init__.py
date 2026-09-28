"""Hermes user model-provider plugin for the source-controlled E3 boundary."""
from __future__ import annotations

from pathlib import Path

from providers import register_provider
from providers.base import ProviderProfile


class E3Profile(ProviderProfile):
    def create_client(self, **_kwargs):
        import sys
        runtime = Path(__file__).resolve().parents[2] / "exec-brain"
        if str(runtime) not in sys.path:
            sys.path.insert(0, str(runtime))
        from e3_service import E3ApplicationService
        from hermes_e3_provider import E3ModelClient
        return E3ModelClient(E3ApplicationService())


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
