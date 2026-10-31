"""Shared UK production discovery scope and auditable effective policy.

Collect broadly in both lanes, then apply the confirmed owner scope from the
canonical career policy. Legacy intern-only portals are overlaid per run.
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
    authority = {}
    if region == 'uk' and row.get('owner_policy_path'):
        import yaml
        source = Path(row['owner_policy_path'])
        owner_raw = source.read_bytes()
        owner = yaml.safe_load(owner_raw) or {}
        authority = {'rejection_policy': owner.get('rejection_policy', {}), 'owner_scope': owner['role_scope'], 'owner_policy_path': str(source),
                     'owner_policy_sha256': hashlib.sha256(owner_raw).hexdigest()}
    return {"schema_version": config["schema_version"], "region": region, **row, **authority,
            "policy_path": str(target), "policy_sha256": hashlib.sha256(raw).hexdigest(),
            "eligibility_source": "existing owner profile, regional policy and explicit vacancy evidence",
            "legacy_policy_conflicts": [] if authority else (["Legacy internship-only collection configuration differs from high_recall; owner scope is not configured."]
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
    from owner_rejection_policy import clearance_only
    if clearance_only(region):
        result['title_filter'] = {'positive': [], 'negative': []}
        result['location_filter']['block'] = []
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


def scope_evidence_decision(region, title, jd_text):
    """Owner scope is separate from title collection and mandatory experience.

    Internship/graduate titles retain all existing eligibility checks. Other IT
    roles need affirmative entry-level evidence in the vacancy JD; absence of an
    experience rejection is not affirmative evidence. Unclear leads need review.
    """
    policy = effective_policy(region)
    if not policy.get('owner_scope', {}).get('junior_it', {}).get('require_jd_evidence'):
        return True, 'regional JD scope inherited'
    if re.search(r'\b(?:intern(?:ship)?s?|placements?|graduates?|grad|summer analyst|summer vacation scheme)\b', str(title), re.I):
        return True, 'internship or graduate role; other eligibility checks still apply'
    text = str(jd_text or '')
    text = re.split(r'\b(?:similar|related|recommended)\s+(?:jobs|roles|offers)\b', text, maxsplit=1, flags=re.I)[0]
    experience = r'(?:(?:prior|previous|professional|commercial|industry|relevant|work)\s+){0,3}experience'
    no_experience = (
        rf'\bno\s+{experience}\s+(?:is\s+)?(?:required|needed|necessary)\b',
        rf'\b{experience}\s+(?:is\s+)?not\s+(?:required|needed|necessary)\b',
        rf"\b(?:do\s+not|don['’]t)\s+need\s+(?:any\s+)?{experience}\b",
        r'\b0\s*[-–—]\s*1\s+years?\s+(?:of\s+)?(?:(?:relevant|work|professional)\s+){0,2}experience\b',
        r'\b(?:suitable\s+for|open\s+to|welcom(?:e|es|ing))\s+(?:recent\s+|new\s+)?graduates?\b',
        r'\b(?:recent\s+|new\s+)?graduates?\s+(?:are\s+)?(?:welcome|eligible)\b',
        r'\b(?:this|the)\s+(?:role|position)\s+is\s+(?:an?\s+)?(?:internship|graduate\s+(?:role|position|scheme|programme|program))\b',
    )
    for sentence in re.split(r'[.;\n]', text):
        for pattern in no_experience:
            for match in re.finditer(pattern, sentence, re.I):
                prefix = sentence[max(0, match.start()-35):match.start()]
                if re.search(r"\b(?:not|never|cannot|don't|doesn't)\s+$", prefix, re.I):
                    continue
                return True, 'JD explicitly permits no prior experience or graduate entry'
        if not re.search(r'\b(?:internships?|placements?|graduate(?:[- ]level|\s+(?:programme|program|scheme))?)\b', sentence, re.I):
            continue
        if not re.search(r'\bexperience\b', sentence, re.I):
            continue
        if re.search(r"\b(?:not|never|cannot|doesn['’]t|don['’]t|do\s+not|does\s+not)\b", sentence, re.I):
            continue
        if re.search(r'\b(?:accepted|acceptable|sufficient|counts?|qualifies|equivalent)\b', sentence, re.I):
            return True, 'JD explicitly accepts internship or graduate-programme experience'
    return False, ('junior IT scope review-only: JD must explicitly permit no prior work experience '
                   'or internship/graduate-equivalent experience')
