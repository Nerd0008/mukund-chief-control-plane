"""Identify explicit student-only vacancy requirements without inventing status."""
import re
from pathlib import Path

REQUIREMENT = re.compile(
    r"\bcurrently\s+(?:enrolled|studying|pursuing)\b"
    r"|\bpenultimate\s+year\b"
    r"|\bmust\s+be\s+(?:a\s+)?(?:current\s+)?student\b"
    r"|\bmust\s+be\s+working\s+towards\b"
    r"|\bonly\s+consider\s+applicants\s+enrolled\b"
    r"|\breturn(?:ing)?\s+to\s+(?:university|study|school)\b", re.I)


def current_student_confirmed():
    """Completed qualifications alone do not establish present enrolment."""
    import yaml
    import owner_search_profile as owner
    path = owner.profile_path().parents[2] / 'mukund-chief-of-staff/career-system/profile.yaml'
    try:
        profile = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except (OSError, ValueError):
        return False
    return any(isinstance(item, dict) and (item.get('currently_enrolled') is True
        or item.get('status') in ('in_progress', 'currently_enrolled'))
        for item in profile.get('education', []))


def student_requirement(text):
    if not isinstance(text, str) or current_student_confirmed():
        return ''
    text = re.split(r'\b(?:similar|related|recommended)\s+(?:jobs|roles|offers)\b', text, maxsplit=1, flags=re.I)[0]
    for match in REQUIREMENT.finditer(text):
        sentence = re.split(r'[.;\n]', text[max(0, match.start()-90):match.end()+150])
        local = next((part for part in sentence if match.group(0).casefold() in part.casefold()), '')
        # Explicitly inclusive alternatives are not a current-student requirement.
        if re.search(r'\b(?:or\s+(?:recent\s+)?graduates?|graduates?\s+(?:are\s+)?(?:welcome|eligible)|students?\s+and\s+(?:recent\s+)?graduates?)\b', local, re.I):
            continue
        return 'student-status requirement needs confirmation (review-only): ' + match.group(0)
    return ''
