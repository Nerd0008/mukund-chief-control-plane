"""Shared UK production discovery scope and auditable effective policy.

Preserve the existing direct/unified high-recall scope. Legacy intern-only
portal rules remain visible as conflicts and available for explicit diagnostics.
No candidate work-authorisation, education, clearance or experience fact is set here.
"""
from pathlib import Path
import hashlib
import json
import re
import sys

HERE = Path(__file__).resolve().parent
POLICY_PATH = HERE / "search_policy.json"


def effective_policy(region="uk", *, path=None):
    target = Path(path or POLICY_PATH)
    raw = target.read_bytes()
    config = json.loads(raw)
    row = config.get("regions", {}).get(region, {"mode": "inherit"})
    return {"schema_version": config["schema_version"], "region": region, **row,
            "policy_path": str(target), "policy_sha256": hashlib.sha256(raw).hexdigest(),
            "eligibility_source": "existing owner profile, regional policy and explicit vacancy evidence",
            "legacy_policy_conflicts": (["Installed portal and older Chief-of-Staff policy say internship-only; current direct and unified production mode is high_recall. Scope confirmation remains recorded separately."]
                                        if region == "uk" and row.get("mode") == "high_recall" else [])}


def role_decision(region, title):
    policy = effective_policy(region)
    if policy["mode"] == "inherit":
        return True, "regional role scope inherited"
    if re.search(r"\bapprentice(?:ship)?\b", str(title), re.I):
        return False, "apprenticeships excluded by effective search policy"
    sys.path.insert(0, str(HERE / "discovery"))
    from title_policy import title_decision
    decision = title_decision(str(title or ""), policy["mode"])
    return decision["decision"] == "pass", str(decision.get("reason") or decision.get("reasons") or "effective role policy")



def discovery_portals(config, region):
    """Use permissive collection hints; shared evidence gates decide eligibility."""
    import copy
    result = copy.deepcopy(config)
    policy = effective_policy(region)
    if policy['mode'] != 'high_recall':
        return result
    sys.path.insert(0, str(HERE / 'discovery'))
    from title_policy import LEVEL_TERMS
    result.setdefault('title_filter', {})['positive'] = [term for term in LEVEL_TERMS
                                                      if 'apprentice' not in term]
    # A city-only provider record must reach the evidence gate, not disappear
    # in a country-keyword collection filter. Explicit foreign blocks remain.
    result.setdefault('location_filter', {})['allow'] = []
    result['location_filter']['always_allow'] = []
    return result


from contextlib import contextmanager


@contextmanager
def discovery_environment(region, lane_env, career_root):
    """A per-run overlay; never modify the owner's installed portals file."""
    import tempfile
    import yaml
    env = dict(lane_env)
    original = Path(env.get('CAREER_OPS_PORTALS', 'portals.yml'))
    if not original.is_absolute():
        original = Path(career_root) / original
    if effective_policy(region)['mode'] != 'high_recall' or not original.is_file():
        yield env
        return
    config = yaml.safe_load(original.read_text(encoding='utf-8')) or {}
    directory = HERE.parent / 'runtime/career-ops/effective-portals'
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', prefix=region+'-',
                                     encoding='utf-8', dir=directory, delete=False) as handle:
        yaml.safe_dump(discovery_portals(config, region), handle, sort_keys=False)
        overlay = Path(handle.name)
    assert overlay.resolve().parent == directory.resolve()
    env['CAREER_OPS_PORTALS'] = str(overlay)
    try:
        yield env
    finally:
        overlay.unlink(missing_ok=True)
