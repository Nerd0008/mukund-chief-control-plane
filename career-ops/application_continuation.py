"""Resolve document continuations only against a bound application.

Drafting permission never certifies eligibility and never authorizes submission.
"""
import hashlib
import re
import time


def text(message):
    from application_package_flow import owner_text
    return owner_text(message).replace('\u2019', "'").strip()


def cancelled(message):
    return bool(re.fullmatch(r"(?i)\s*(?:please\s+)?(?:stop|cancel|abandon)(?:\s+(?:this|the|current))?(?:\s+(?:application|package|draft|job))?[.!\s]*", text(message)))


def drafting_permission(message):
    value=text(message)
    if not value or len(value)>500 or '[Content of ' in str(message) or cancelled(message):
        return False
    if re.search(r"(?i)\b(?:do not|don't|dont|not|cannot|can't|never|stop|cancel|pause)\b|\b(?:submit|publish|email|recruiter|linkedin|reply|invoice|report|posts?|article|story|blog|essay|message)\b",value):
        return False
    if re.match(r'(?i)^(?:why|how|what|when|where|does|did|is|can it)\b',value):
        return False
    # Context supplies the object, not facts: "draft anyway" and "go ahead"
    # refer to the saved documents, not to enrolment/legal declarations.
    if re.fullmatch(r"(?i)(?:(?:okay|ok|yes|yeah|sure|please)[,\s]+)*(?:go ahead|proceed|do it|make it|carry on)[.!\s]*",value):
        return True
    return bool(re.search(r'(?i)\b(?:draft|write|generate|build|create|produce)\b',value)
                and (re.search(r"(?i)\b(?:okay|ok|fine|anyway|still|understand|go ahead|proceed|please|just)\b",value)
                     or re.fullmatch(r'(?i)(?:draft|write|generate|build)(?:\s+(?:it|them|both|the documents|the cv|the cover letter))?[.!\s]*',value)))


def recover_intake(history):
    """Recover only the latest relevant user input, never jump across a topic."""
    from application_package_flow import jd_payload, owner_text
    import application_package_state as package
    for item in reversed((history or [])[-12:]):
        if item.get('role')!='user':continue
        value=item.get('content') or ''
        if package.retry(value) or drafting_permission(value):continue
        jd=jd_payload(value)
        if jd:return {'jd':jd,'source':'history_recovery','owner_request':owner_text(value)}
        # Never silently reach beyond a later job link or unrelated user task.
        break
    return None


def context_matches(history, stored):
    """A short retry/acknowledgement must not cross a different owner task."""
    users=[item.get('content') or '' for item in (history or []) if item.get('role')=='user']
    if not stored or not users:return True
    import application_package_state as package
    from application_package_flow import jd_payload, wants_documents
    last=users[-1]
    latest_jd=jd_payload(last)
    saved_jd=(stored.get('intake') or {}).get('jd')
    if latest_jd and saved_jd and latest_jd.strip()!=saved_jd.strip():return False
    clarification=(stored.get('intake') or {}).get('owner_clarification')
    return bool(package.retry(last) or drafting_permission(last) or latest_jd
                or wants_documents(last) or (clarification and text(last)==clarification))


def resume(message, history, stored):
    import application_package_state as package
    permission=drafting_permission(message)
    if not permission:
        if not package.retry(message):return None
        # Existing complete checkpoints use the normal resume path. Recover
        # legacy missing intake here without changing old compiler receipts.
        if (stored.get('intake') or {}).get('jd'):return None
    if not context_matches(history,stored):return None
    intake=dict(stored.get('intake') or {}) if stored else {}
    if not intake.get('jd'):
        intake=recover_intake(history) or {}
    if not intake.get('jd'):return None
    digest=hashlib.sha256(intake['jd'].encode()).hexdigest()
    if intake.get('jd_sha256') and intake['jd_sha256']!=digest:return None
    intake['jd_sha256']=digest
    if permission:
        intake['document_authorization']={'scope':'draft_documents_only','message':text(message),
            'jd_sha256':digest,'approved_at':time.time(),'eligibility_confirmed':False}
    return intake


def draft_authorized(intake):
    proof=intake.get('document_authorization') or {}
    return (proof.get('scope')=='draft_documents_only' and proof.get('eligibility_confirmed') is False
            and proof.get('jd_sha256')==hashlib.sha256(str(intake.get('jd','')).encode()).hexdigest())
