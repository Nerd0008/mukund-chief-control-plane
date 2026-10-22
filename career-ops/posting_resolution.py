"""Bounded employer/ATS recovery using the existing public-search provider.

Search results are leads. Only independently fetched, identity-matched live
postings can replace a source URL. No account, browser, submission or outreach.
"""
import time
import json, hashlib, os, uuid, re
from pathlib import Path
from urllib.parse import urlsplit

from application_links import public_url, aggregator, listing, title_matches, tokens


def official_destination(url, company):
    host=(urlsplit(url).hostname or '').lower().removeprefix('www.')
    ats=('smartrecruiters.com','myworkdayjobs.com','greenhouse.io','lever.co',
         'ashbyhq.com','workable.com','teamtailor.com','trac.jobs','jobs.nhs.uk',
         'icims.com','recruitee.com','bamboohr.com','oraclecloud.com','successfactors.com')
    if any(host==x or host.endswith('.'+x) for x in ats): return True
    # Employer site itself: exact brand/domain label, not text copied by a job board.
    brand=''.join(sorted(tokens(company)-{'ltd','limited','plc','inc','group'}))
    compact=''.join(t for t in company.casefold() if t.isalnum())
    return bool(brand and any(label.replace('-', '') in (brand,compact) for label in host.split('.')[:-1]))


def same_role(expected, actual):
    aliases={'internship':'intern','grad':'graduate'}
    levels={'junior','senior','lead','principal','manager','director','intern','graduate','placement'}
    level=lambda title:{aliases.get(t,t) for t in tokens(title)} & levels
    return title_matches(expected,actual) and level(expected)==level(actual)


class PostingResolver:
    def __init__(self, provider, *, max_queries=4, budget_seconds=180,
                 deadline=None, fetcher=None, state_path=None):
        self.state_path = Path(state_path) if state_path else None
        try:
            self.state=json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path else {}
            if not isinstance(self.state,dict): self.state={}
        except (OSError,ValueError): self.state={}
        self.provider = provider
        self.max_queries = max_queries
        self.budget_seconds = budget_seconds
        self.deadline = deadline
        self.fetcher = fetcher
        self.started = None
        self.queries = 0
        self.cache = {}
        self.evidence = []

    def state_key(self, record):
        from application_links import canonical_posting_url
        return hashlib.sha256(canonical_posting_url(record.get('url') or '').encode()).hexdigest()

    def priority(self, record):
        # Never-attempted sources take precedence over previously failed lookups.
        return (self.state.get(self.state_key(record)) or {}).get('attempted_at',0)

    def __call__(self, record, source):
        identity = source.get('discovered_posting') or {}
        company = identity.get('company') or record.get('company')
        title = identity.get('title') or record.get('title')
        location = identity.get('location') or record.get('location')
        if title and not location:
            suffix=re.fullmatch(r'(.+?) in ([A-Z].+)', title)
            if suffix: title,location=suffix.groups()
        if not company or not title or not location: return None
        previous=self.state.get(self.state_key(record)) or {}
        ttl=900 if previous.get('result') else 3600
        identity_key=[company.casefold(),title.casefold(),location.casefold()]
        if previous.get('identity_key')==identity_key and 0 <= time.time()-previous.get('attempted_at',0) < ttl:
            return previous.get('result')
        # Ignore embellished search-result company strings; do not guess a brand.
        if any(x in company for x in ('|', ' — ')): return None
        key = (company.casefold(), title.casefold(), location.casefold())
        if key in self.cache: return self.cache[key]
        if self.started is None: self.started = time.monotonic()
        remaining = self.budget_seconds - (time.monotonic() - self.started)
        if self.deadline is not None: remaining = min(remaining, self.deadline-time.time())
        if remaining < 5 or self.queries >= self.max_queries: return None
        query = f'"{company}" "{title}" {location} careers apply -site:linkedin.com'
        self.queries += 1
        try:
            result = self.provider.research([{'query_id': f'posting-recovery-{self.queries}',
                                             'query': query}], limit_per_query=3,
                                            timeout=max(1, min(60, int(remaining))))
        except Exception as error:
            result = {'queries': [], 'failure_type': type(error).__name__}
        accepted = {}
        attempts = []
        from jd_fetcher import fetch_jd
        fetcher = self.fetcher or fetch_jd
        for item in result.get('queries') or []:
            if not item.get('web_search_observed'): continue
            for hit in (item.get('results') or [])[:3]:
                url = public_url(hit.get('url'))
                if not url or aggregator(url) or listing(url) or not official_destination(url,company): continue
                left = self.budget_seconds - (time.monotonic()-self.started)
                if self.deadline is not None: left = min(left, self.deadline-time.time())
                if left < 1: break
                try: page = fetcher(url, timeout=min(12, left))
                except Exception as error:
                    attempts.append({'url':url,'state':'UNKNOWN','failure_type':type(error).__name__})
                    continue
                status = page.get('vacancy_status') or {}
                actual = page.get('posting_identity') or page.get('discovered_posting') or {}
                page_title = actual.get('title') or status.get('page_title')
                # Source can contain a location suffix, but intake years must agree.
                same_title = same_role(title, page_title)
                wanted = tokens(company)-{'ltd','limited','plc','inc','group'}
                found = tokens(actual.get('company') or '')-{'ltd','limited','plc','inc','group'}
                same_company = bool(wanted and wanted == found)
                actual_place = tokens(actual.get('location') or '')
                source_place = tokens(location)-{'england','united','kingdom','gb','uk'}
                same_place = bool(source_place and source_place & actual_place)
                attempts.append({'url': url, 'state': status.get('state'),
                                 'title_match': same_title, 'company_match': same_company,
                                 'location_match': same_place})
                if status.get('state') != 'OPEN' or not (same_title and same_company and same_place): continue
                destination = page.get('resolved_url') or url
                from tracker_writer import normalize_url
                accepted[normalize_url(destination)] = {**page, 'resolved_url': destination,
                    'posting_identity': actual, 'application_resolution': {
                        'source_url': record.get('url'), 'destination_url': destination,
                        'employer': actual['company'], 'title_match': True,
                        'employer_match': True, 'location_match': True, 'state': 'OPEN',
                        'method': 'observed public search + independently verified posting'}}
        # Several requisitions sharing a title must never be chosen arbitrarily.
        resolved = next(iter(accepted.values())) if len(accepted) == 1 else None
        self.cache[key] = resolved
        self.state[self.state_key(record)]={'attempted_at':time.time(),'identity_key':identity_key,'result':resolved}
        if self.state_path:
            self.state_path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.state_path.with_name(self.state_path.name+'.'+uuid.uuid4().hex+'.tmp')
            try:
                temp.write_text(json.dumps(self.state,ensure_ascii=True),encoding='utf-8')
                os.replace(temp,self.state_path)
            finally: temp.unlink(missing_ok=True)
        self.evidence.append({'company': company, 'title': title,
            'search_observed': any(q.get('web_search_observed') for q in result.get('queries') or []),
            'attempts': attempts, 'failure_type': result.get('failure_type'), 'distinct_matches': len(accepted),
            'resolved': bool(resolved)})
        return resolved
