"""One vacancy, one identity — however many links point at it.

A single vacancy is reachable by an employer ATS URL, a Workday requisition URL, an
aggregator listing and a re-seller link. URL normalisation alone cannot see that these
describe one vacancy, so the same role appears as several tracker rows and can be offered
again after it has already been applied to.

Identity therefore carries two things:

* the normalised URL (``tracker_writer.normalize_url`` / ``career_search_recall.posting_key``),
  which merges the *same* posting reached with different tracking parameters; and
* the ATS requisition ID, scoped to the employer, which merges *different* URLs that name
  the same requisition (``careers.americanexpress.com/.../job/26013761`` and
  ``egug.fa.us2.oraclecloud.com/.../job/26013761``).

Requisition keys are employer-scoped on purpose. Two unrelated employers can both use the
number ``12345``; merging them would silently drop a real vacancy, which is worse than
leaving a duplicate for review. Company/title is deliberately NOT an identity: the
existing recall design records "do not merge company/title alone", because the same title
can be two genuinely different postings at different sites.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

# Requisition identifiers, most specific first. Each pattern captures exactly one group.
_REQUISITION_PATTERNS = (
    # Workday: .../job/<location>/<slug>_JR-0000129173  or  ..._R0004565
    re.compile(r'_([A-Za-z]{1,4}-?\d{4,})(?:[/?#]|$)'),
    # Oracle / Taleo / PeopleSoft candidate experience: /job/26013761
    re.compile(r'/(?:job|jobs|postings|positions|requisitions|vacancies)/(\d{5,})(?:[/?#]|$)'),
    # Greenhouse / Lever style: /jobs/8066856  or  /jobs/8325019-soc-analyst
    re.compile(r'/jobs/(\d{5,})(?:[-/?#]|$)'),
    # SmartRecruiters / Cornerstone style numeric posting: /744000153148930-slug
    re.compile(r'/(\d{9,})(?:[-/?#]|$)'),
    # Pinpoint and other UUID-keyed postings
    re.compile(r'/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:[/?#]|$)'),
    # Explicit job-id query parameters: gh_jid=8113704, job_id=..., jid=...
    re.compile(r'[?&](?:gh_jid|job_id|jobid|jid)=([A-Za-z0-9_-]{4,})', re.I),
)

# Hosts that only re-list or re-sell another employer's vacancy. Their URLs name no
# requisition of their own, so a re-listed vacancy collapses onto its employer row only
# once the employer destination has been resolved.
AGGREGATOR_HOSTS = frozenset({
    'jointheintake.com', 'brightnetwork.co.uk', 'gradcracker.com', 'simplify.jobs',
    'canarywharfian.co.uk', 'jobserve.com', 'targetjobs.co.uk', 'prosple.com',
    'himalayas.app', 'themuse.com', 'builtinlondon.uk', 'tsenta.com', 'bebee.com',
    'cv-library.co.uk', 'reed.co.uk', 'indeed.com', 'linkedin.com',
    'apprenticewizard.co.uk', 'thejobsboard.co.uk', 'jobijoba.co.uk',
    'dataanalystjobs.co.uk', 'jobleads.com', 'computerjobs.com', 'dijobs.co.uk',
    'grb.uk.com', 'studysmarter.co.uk', 'uptree.co', 'creonjobs.com', 'norrsken.org',
    'dawncapital.com', 'zerogravity.co.uk', 'swiftcruit.ai', 'hubmub.com',
    'placemently.io', 'william-alexander.com', 'calvoracares.co.uk',
    'ernestgordonrecruitment.com', 'sandersonplc.com', 'circlerecruitment.com',
    'constantrecruitment.co.uk', 'jobtrain.co.uk',
})


def _host(url) -> str:
    try:
        return (urlsplit(str(url or '')).hostname or '').lower().removeprefix('www.')
    except ValueError:
        return ''


def requisition_id(url) -> str:
    """The ATS requisition identifier for a posting URL, or '' when it names none."""
    text = str(url or '')
    if not text:
        return ''
    for pattern in _REQUISITION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).upper()
    return ''


def is_aggregator(url) -> bool:
    """True when the URL only re-lists another employer's vacancy."""
    host = _host(url)
    if not host:
        return False
    return host in AGGREGATOR_HOSTS or any(
        host.endswith('.' + listed) for listed in AGGREGATOR_HOSTS)


def company_key(name) -> str:
    """Employer name reduced to a comparison key."""
    return re.sub(r'[^a-z0-9]', '', str(name or '').lower())


def identity_keys(company, url, resolved_url=None) -> set:
    """Every requisition-scoped identity this posting is known by.

    ``resolved_url`` is the employer destination after an aggregator link has been
    followed. Including it lets a re-listed vacancy collapse onto its employer row
    without ever merging two different employers that happen to share a number.
    """
    keys = set()
    employer = company_key(company)
    for candidate in (url, resolved_url):
        if not candidate:
            continue
        identifier = requisition_id(candidate)
        if not identifier:
            continue
        # Employer-scoped key: the safe, collision-free form.
        if employer:
            keys.add(f'req:{employer}:{identifier}')
        else:
            # No employer on the record: keep a bare key so two employer-less rows
            # naming the same requisition still collapse, and never match a row
            # that does carry an employer.
            keys.add(f'req:?:{identifier}')
    return keys


def same_posting(left, right) -> bool:
    """True when two records describe the same vacancy.

    ``left``/``right`` are mappings carrying at least ``url``; ``company`` and
    ``resolved_url`` are used when present.
    """
    if not left or not right:
        return False
    return bool(identity_keys(left.get('company'), left.get('url'), left.get('resolved_url'))
                & identity_keys(right.get('company'), right.get('url'), right.get('resolved_url')))
