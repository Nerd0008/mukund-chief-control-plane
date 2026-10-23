"""Bounded query coverage and conservative posting-URL identity; no network or writes."""
import re
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode

def posting_key(url):
    value=str(url or '').strip()
    try:
        p=urlsplit(value)
        if p.scheme.lower() not in ('http','https') or not p.netloc:return ''
        if p.hostname=='jobs.smartrecruiters.com':
            from tracker_writer import normalize_url
            return normalize_url(value)
        query=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True)
               if not k.lower().startswith('utm_') and k.lower() not in ('gh_src','source','referrer')]
        # Preserve path/query value case and requisition IDs. Do not merge company/title alone.
        return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/'),urlencode(sorted(query)),''))
    except ValueError:return ''

def query_batches(profile,region,fallback,year):
    import owner_search_profile as osp
    disciplines=osp.discipline_terms(profile) if profile else []
    disciplines=disciplines or ['cyber security','information security','IT support']
    uk_scope = str(region).strip().casefold() in ('uk', 'the uk', 'united kingdom', 'the united kingdom')
    levels=('internship','graduate scheme','placement','junior','trainee','off-cycle internship','entry level')
    if not uk_scope:levels=levels+('apprentice',)
    # Each batch is different, with no-year/current-year/next-year coverage.
    batches=[];seen=set()
    for i,level in enumerate(levels):
        batch=[]
        for j in range(min(6,len(disciplines))):
            discipline=disciplines[(i+j)%len(disciplines)]
            scope=('',str(year),str(year+1))[(i+j)%3]
            q=' '.join(x for x in (discipline,level,region,scope) if x)
            if q not in seen:batch.append(q);seen.add(q)
        batches.append(batch)
    # Reach less prominent employer/ATS boards as well as broad web results.
    for sites in (('jobs.ashbyhq.com','apply.workable.com'),
                  ('job-boards.greenhouse.io','jobs.lever.co'),
                  ('myworkdayjobs.com','jobs.smartrecruiters.com'),
                  ('jobs.nhs.uk','findajob.dwp.gov.uk')):
        batch=[]
        for site in sites:
            for discipline in ('security analyst','cyber security','IT support'):
                batch.append(f'site:{site} {discipline} (junior OR graduate OR internship OR trainee) {region}')
        batches.append(batch)
    # Preserve varied legacy query coverage, refresh stale years, and do not quote exact titles.
    for group in fallback:
        batch=[]
        for q in group:
            if re.search(r"\bapprentice(?:ship)?\b", q, re.I):continue
            q=re.sub(r'\b20\d{2}\b',str(year),q).replace('"','')
            if q not in seen:batch.append(q);seen.add(q)
        if batch:batches.append(batch[:6])
    return [b for b in batches if b]


def select_batches(total, count, offset):
    """The logged offset is the actual first batch; no permanently pinned batch 0."""
    return [(offset+i)%total for i in range(min(max(0,count),total))] if total else []
