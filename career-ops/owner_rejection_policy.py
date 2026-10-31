"""Owner's 28 October rule: only explicit mandatory security clearance rejects.

Other checks remain evidence and review flags, never assertions of eligibility.
Collection targets and duplicate/record-integrity safeguards are separate.
"""
import functools
import inspect
import re

from clearance_screening import visible_text, is_readable


def clearance_only(region):
    from effective_search_policy import effective_policy
    return (region == 'uk' and effective_policy(region).get('rejection_policy', {}).get('mode')
            == 'explicit_required_security_clearance_only')


_LEVEL = r'(?:security[ -]+clearance|national[ -]+security[ -]+vetting|police[ -]+clearance|SC(?:[ -]+clearance)?|DV(?:[ -]+clearance)?|CTC(?:[ -]+clearance)?|NPPV(?:[ -]+clearance)?|developed vetting|security check clearance)'
_MANDATORY = r'(?:must|shall|will (?:be required to|need to)|requires?|required|requirements?|needs?|needed|essential|mandatory|condition of employment|subject to)'


def required_clearance_evidence(text):
    """Return exact requirement clauses, excluding optional/negated mentions.

    Citizenship, residency, work permission and BPSS alone are not clearance.
    Related-role sections are excluded; acronym-only company names do not count.
    """
    text = visible_text(text)
    if not is_readable(text):
        return []
    text = re.split(r'\b(?:similar|related|recommended)\s+(?:jobs|roles|offers)\b', text, maxsplit=1, flags=re.I)[0]
    evidence = []
    for clause in re.split(r'[.!?;\n]+|\bbut\b', text, flags=re.I):
        clause = ' '.join(clause.split())
        for match in re.finditer(r'\b' + _LEVEL + r'\b', clause, re.I):
            before, after = clause[max(0, match.start()-100):match.start()], clause[match.end():match.end()+100]
            local = before + match.group() + after
            if re.search(r'\b(?:no|without)\s+(?:existing\s+|prior\s+)?$', before, re.I):
                continue
            if re.search(r'\b(?:not required|not necessary|not essential|optional|desirable|preferred|advantageous)\b', after[:60], re.I):
                continue
            if re.search(r'\b(?:do not|don.t|will not|won.t|not)\s+(?:need|require|be required)(?:\s+to\s+(?:obtain|hold))?\s*(?:an?\s+)?$', before, re.I):
                continue
            # A mandatory word must bind to clearance, not an unrelated duty
            # elsewhere in the advert. Bare SC/DV additionally require vetting.
            binding = (re.search(_MANDATORY + r'\b[^,]{0,85}$', before, re.I)
                       or re.match(r'\s*(?:at\s+(?:SC|DV|CTC|NPPV)\s+level\s+)?(?:(?:is|will be|are)\s+)?' + _MANDATORY + r'\b', after, re.I)
                       or re.search(r'\b(?:eligible|able|ability|eligibility(?:\s+and\s+willingness)?)\s+to\s+(?:obtain|gain|hold|achieve)\s*(?:(?:UK|Government|HMG)\s+)*$', before, re.I)
                       or re.match(r'\s*:\s*(?:required|essential|mandatory)\b', after, re.I))
            bare = match.group().upper() in ('SC', 'DV', 'CTC', 'NPPV')
            if binding and (not bare or re.search(r'clearance|vetting|obtain|hold|cleared|eligible|undergo|achieve|gain', local, re.I)):
                evidence.append({'token': match.group().lower(), 'context': clause})
    return [dict(item) for item in {tuple(e.items()): e for e in evidence}.values()]


def apply_owner_gate(function):
    """Keep legacy diagnostics, converting every non-clearance reason to flags."""
    signature = inspect.signature(function)

    @functools.wraps(function)
    def gate(*args, **kwargs):
        bound = signature.bind(*args, **kwargs).arguments
        result = function(*args, **kwargs)
        if not clearance_only(bound['region']):
            return result
        rec = bound.get('rec', bound.get('record', {}))
        text = rec.get('jd_text') or rec.get('description') or rec.get('summary') or ''
        evidence = required_clearance_evidence(text)
        issues = [*rec.get('review_flags', []), *result.get('reasons', [])]
        issues.extend(f for f in result.get('flags', []) if re.search(r'UNKNOWN|UNVERIFIED|blocked|unavailable', f, re.I))
        flags = list(dict.fromkeys([*result.get('flags', []), *issues]))
        if not text.strip():
            issues.append('Clearance requirement unverified: readable JD needed')
        # Legacy clearance/citizenship diagnostics must not masquerade as a
        # confirmed requirement. Only the exact evidence below can reject.
        flags = [f.replace('clearance/citizenship requirement stated:', 'Clearance/citizenship mention needs review:') for f in flags]
        result.update(decision='rejected' if evidence else 'accepted',
                      reasons=['Explicit required security clearance: ' + e['context'] for e in evidence],
                      flags=flags, review_flags=compact_review_flags(issues), clearance_evidence=evidence,
                      rejection_policy='explicit_required_security_clearance_only',
                      eligibility_verified=False)
        return result
    return gate


def compact_review_flags(issues):
    """Keep notification text brief; the detailed checks remain in flags."""
    mappings = [
        (r'clearance|citizenship', 'Clearance or citizenship wording needs review'),
        (r'closed|filled|expired', 'Vacancy appears closed'),
        (r'deadline.*passed', 'Application deadline has passed'),
        (r'experience', 'Experience requirement needs review'),
        (r'student|university|return.to.study', 'Student requirement needs review'),
        (r'location|region|country', 'Location needs review'),
        (r'UNSCREENED|readable.*description', 'JD could not be verified'),
        (r'UNVERIFIED|transport|bot.wall', 'Availability unverified'),
        (r'work authorisation', 'Work permission needs review'),
    ]
    output=[]
    for issue in issues:
        label=next((label for pattern,label in mappings if re.search(pattern,issue,re.I)),issue)
        if label not in output: output.append(label)
    return output
