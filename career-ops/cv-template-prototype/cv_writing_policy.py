"""Reviewed CV-specific guidance, loaded for every planning and validation pass.

This is a style reference, not an AI detector or a guarantee of authorship.
No network fetch is required during a bounded CV job.
"""
import re

SOURCE = 'https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing'
VERSION = '2026-10-09.1'
GUIDANCE = (
    'Write specific, restrained professional language grounded in verified evidence. '
    'Prefer concrete actions, technologies and supported outcomes over promotional adjectives. '
    'Avoid inflated significance, vague claims, repetitive stock phrases, contrived contrasts '
    'and formulaic lists. Do not include chatbot replies, disclaimers, placeholders, citations '
    'or Markdown in CV content. Keep template-defined emphasis only. '
    'Technical terms, qualifications, factual lists and ordinary punctuation remain allowed. '
    'Do not invent achievements or remove mandatory qualifications to satisfy style guidance.'
)

def policy():
    return {'version': VERSION, 'source': SOURCE, 'guidance': GUIDANCE,
            'mode': 'reviewed_local_reference', 'not_an_ai_detector': True}

def check(text):
    # Narrow, explainable checks; no probabilistic detector or broad word blacklist.
    patterns = {
        'chatbot boilerplate': r'\b(as an ai(?: language model)?|here is your (?:tailored )?cv|i hope this helps)\b',
        'placeholder': r'\[(?:insert|your|company name|role name)[^\]]*\]|\b(?:lorem ipsum|TODO)\b',
        'promotional filler': r'\b(?:ever[- ]evolving landscape|game[- ]changing|unparalleled expertise|testament to my|pivotal role in shaping|delve into)\b',
        'contrived contrast': r'\bnot (?:just|only)\b[^.!?]{0,100}\bbut (?:also|rather)\b',
    }
    return [reason for reason, pattern in patterns.items() if re.search(pattern, text, re.I)]
