"""Reviewed CV-specific guidance, loaded for every planning and validation pass.

This is a style reference, not an AI detector or a guarantee of authorship.
No network fetch is required during a bounded CV job.
"""
import re

SOURCE = 'https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing'
VERSION = '2026-10-09.2'
GUIDANCE = (
    'Write specific, restrained professional language grounded in verified evidence. '
    'Prefer concrete actions, technologies and supported outcomes over promotional adjectives. '
    'Avoid inflated significance, vague claims, repetitive stock phrases, contrived contrasts '
    'and formulaic lists. Avoid self-praise such as results-driven or passionate professional, '
    'claims of proven excellence without concrete evidence, vague business impact and repeated sentence openings. '
    'Do not include chatbot replies, disclaimers, placeholders, citations '
    'or Markdown in CV content. Keep template-defined emphasis only. '
    'Owner style preference: no semicolons or em dashes in tailored content. Use clear sentences. '
    'Technical terms, qualifications, factual lists and numeric/date ranges remain allowed. '
    'Do not invent achievements or remove mandatory qualifications to satisfy style guidance.'
)

def policy():
    return {'version': VERSION, 'source': SOURCE, 'guidance': GUIDANCE,
            'mode': 'reviewed_local_reference', 'not_an_ai_detector': True}

def encoding_errors(text):
    errors=[]
    if any(ord(c)<32 and c not in "\n\t" for c in text) or any(0x7f<=ord(c)<=0x9f or 0xd800<=ord(c)<=0xdfff for c in text):
        errors.append("invalid control or Unicode character")
    if "\ufffd" in text or re.search(r"(?:\u00e2\u20ac|\u00c3[\u0080-\u00bf]|\u00c2[\u0080-\u00bf])",text):
        errors.append("suspected UTF-8 decoding corruption")
    return errors

def check(text):
    # Narrow, explainable checks; no probabilistic detector or broad word blacklist.
    patterns = {
        'owner punctuation preference': r'[;\u2014]',
        'chatbot boilerplate': r'\b(as an ai(?: language model)?|here is your (?:tailored )?cv|i hope this helps)\b',
        'placeholder': r'\[(?:insert|your|company name|role name)[^\]]*\]|\b(?:lorem ipsum|TODO)\b',
        'generic self-praise': r'\b(?:results[- ]driven|highly motivated|dynamic professional|passionate (?:professional|individual)|proven track record|exceptional ability|uniquely positioned|strong interest in|seasoned expert)\b',
        'vague impact': r'\b(?:drive meaningful impact|deliver transformative results|unlock potential|foster innovation|seamlessly leverage|elevate (?:business|organisations?))\b',
        'promotional filler': r'\b(?:ever[- ]evolving landscape|game[- ]changing|unparalleled expertise|testament to my|pivotal role in shaping|delve into)\b',
        'contrived contrast': r'\bnot (?:just|only)\b[^.!?]{0,100}\bbut (?:also|rather)\b',
    }
    return encoding_errors(text)+[reason for reason, pattern in patterns.items() if re.search(pattern, text, re.I)]

