"""Natural owner instructions; consent still requires authenticated exact-post context."""
import re
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

LONDON = ZoneInfo('Europe/London')
DAYS = ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')


def interpret(text, *, now=None):
    text = str(text or '').strip()
    text = re.sub(r'(?s)^\[Replying to: .*?\]\s*\n\s*','',text,count=1).strip()
    result = {'approved':False,'skip_image':False,'publish_now':False,'publish_at':None,'override':False}
    if not text or len(text)>20000:
        return result
    # Negation applies to the action, not to a date or an optional image.
    if re.search(r"\b(?:do not|don't|don’t|never|cannot|can't|can’t)\s+(?:approve|publish|post|schedule)\b|\bnot\s+approved\b|\bunapproved\b",text,re.I):
        return result
    if re.match(r'(?i)^(?:no(?!\s+(?:image|picture|photo))[,.! ]|no$|nope\b|wait\b|hold\b|stop\b|cancel\b|reject\b|not\s+(?:ready|yet)\b)',text):
        return result
    if re.search(r'\b(?:if|unless|provided|once|after|until)\b',text,re.I):
        return result  # conditional consent is not executable consent
    if re.search(r'\b(?:both|all|two|three)\s+(?:posts?|drafts?|versions?)\b',text,re.I):
        return result
    edits = re.sub(r"\b(?:do not|don't|don’t)\s+(?:change|rewrite|edit|revise)\b",'',text,flags=re.I)
    if re.search(r'\b(?:rewrite|revise|change|edit|fix)\b',edits,re.I):
        return result
    polite = r'(?:(?:please|yes|yeah|yep|okay|ok|perfect|great)[,!\\.\\s]+)*'
    start = r"(?:i\s+approve\b|approved?\b|(?:can|could|would)\s+you\s+(?:please\s+)?(?:publish|post|schedule)\b|(?:publish|post|schedule)\s+(?:it|this|the|my|missed|tuesday|wednesday|thursday)\b|go\s+ahead\b|looks\s+(?:good|great|fine|perfect)\b)"
    affirmative = bool(re.match('(?i)^'+polite+start,text))
    affirmative |= bool(re.fullmatch(r'(?i)(?:yes|yeah|yep|okay|ok|perfect|looks good|go ahead)[!. ]*',text))
    affirmative |= bool(re.search(r'\bI\s+approve\s+(?:this|the|it|that)\b',text))
    affirmative |= bool(re.match(r'(?i)^(?:the\s+)?(?:tuesday|wednesday|thursday)(?:\x27s)?\s+(?:post\s+)?(?:is\s+)?approved\b',text))
    if '?' in text and not re.match(r'(?i)^(?:please\s+)?(?:can|could|would)\s+you\s+(?:please\s+)?(?:publish|post|schedule)\b',text):
        affirmative = False
    settings_only = bool(re.match(r'(?i)^(?:tomorrow\b|today\b|(?:skip|omit|without|no)\s+(?:the\s+|an?\s+)?image\b)',text)) and '?' not in text
    if not affirmative and not settings_only:
        return result
    result['approved'] = affirmative
    result['skip_image'] = bool(re.search(r'\b(?:skip|omit|without|no)\s+(?:the\s+|an?\s+)?images?\b|\b(?:do not|don.t)\s+(?:generate|include|use|add)\s+(?:an?\s+|the\s+)?images?\b',text,re.I))
    result['override'] = bool(re.search(r'\b(?:despite|anyway|override|publish\s+(?:the\s+)?missed|publish\s+right\s+now|publish\s+now)\b',text,re.I))
    now = (now or datetime.now(LONDON)).astimezone(LONDON)
    target = None
    if re.search(r'\btomorrow\b',text,re.I):
        target = now.date()+timedelta(days=1)
    elif re.search(r'\btoday\b',text,re.I) and not re.search(r'\bnot\s+today\b',text,re.I):
        target = now.date()
    named = re.search(r'\b(?:on|for)\s+(?:next\s+)?('+ '|'.join(DAYS) +r')\b',text,re.I)
    if named and target is None:
        shift = (DAYS.index(named.group(1).lower())-now.weekday())%7
        target = now.date()+timedelta(days=shift or 7)
    clock = re.search(r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b',text,re.I)
    if target is not None:
        hour,minute = 8,0
        if clock:
            hour,minute = int(clock.group(1)),int(clock.group(2) or 0)
            suffix = (clock.group(3) or '').lower()
            if suffix:
                if not 1<=hour<=12:raise ValueError('Please give a valid publication time.')
                hour = hour%12+(12 if suffix=='pm' else 0)
            if not 0<=hour<=23 or not 0<=minute<=59:raise ValueError('Please give a valid publication time.')
        result['publish_at'] = datetime.combine(target,time(hour,minute),LONDON).isoformat()
    result['publish_now'] = bool(re.search(r'\b(?:publish|post)\s+(?:it\s+|this\s+post\s+)?now\b',text,re.I) and not re.search(r'\bnot\s+now\b',text,re.I) and target is None)
    return result


def is_instruction(text):
    """Approval instructions are not new public post presentations."""
    return bool(re.search(r'\b(?:approval system|approval verifier|approval instructions|send exactly|reply with|reply naturally|please confirm|your approval|once you send|to approve|review checks|fact.check gate)\b',text,re.I))


def has_draft_body(text):
    # An actual changed draft remains a barrier, even if surrounded by instructions.
    blocks = re.findall(r'```[^\n]*\n([\s\S]*?)```',text)
    blocks += ['\n'.join(re.findall(r'(?m)^> ?(.*)$',text))]
    for block in blocks:
        block = re.sub(r'APPROVE LINKEDIN [0-9a-f]{64}(?: OVERRIDE FACTCHECK)?','',block,flags=re.I).strip()
        if block and not re.fullmatch(r'(?i)(?:approved?|yes|publish it|go ahead|looks good)',block):
            return True
    if is_instruction(text):
        return False
    return bool(re.search(r'(?i)\b(?:final text|revised post|updated post|here is (?:the|your) post)\s*:',text)
                or re.search(r'APPROVE LINKEDIN [0-9a-f]{64}',text,re.I)
                or (len(text)>300 and '\n\n' in text))
