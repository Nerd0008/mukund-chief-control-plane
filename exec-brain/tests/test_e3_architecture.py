import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("e3_architecture_audit", ROOT / "scripts/e3_architecture_audit.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def test_production_architecture_has_no_business_adapter_bypass():
    report = AUDIT.audit()
    assert report["pass"], report["failures"]
    assert report["provider_calls"] == 0


def test_discord_plugin_is_observer_only_and_chief_uses_service():
    plugin = (ROOT / "hermes-plugins/e3-discord-router/__init__.py").read_text(encoding="utf-8")
    chief = (ROOT / "exec-brain/chief_routing.py").read_text(encoding="utf-8")
    assert "orchestrate_and_execute" not in plugin
    assert '"action": "skip"' not in plugin
    assert "E3ApplicationService" not in chief  # injected boundary, not a provider binding
    assert "self.e3_service.execute" in chief


def test_runtime_provenance_detects_source_runtime_drift(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "e3_runtime_provenance", ROOT / "scripts/e3_runtime_provenance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.compare_runtime(tmp_path)
    assert report["read_only"] is True
    assert report["provider_calls"] == 0
    assert report["drift_count"] == len(report["modules"])


def test_chief_context_compiler_is_source_controlled_and_bounded():
    context = (ROOT / "exec-brain/chief_context.py").read_text(encoding="utf-8")
    assert "source_manifest" in context
    assert "max_chars" in context
    assert "inferences" in context
