"""Bounded query coverage and conservative posting-URL identity; no network or writes."""
import re
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode

def posting_key(url):
    value=str(url or '').strip()
    try:
        p=urlsplit(value)
        if p.scheme.lower() not in ('http','https') or not p.netloc:return ''
        query=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True)
               if not k.lower().startswith('utm_') and k.lower() not in ('gh_src','source','referrer')]
        # Preserve path/query value case and requisition IDs. Do not merge company/title alone.
        return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/'),urlencode(sorted(query)),''))
    except ValueError:return ''

def query_batches(profile,region,fallback,year):
    import owner_search_profile as osp
    disciplines=osp.discipline_terms(profile) if profile else []
    disciplines=disciplines or ['cyber security','information security','IT support']
    levels=('internship','graduate scheme','placement','junior','trainee','apprentice','off-cycle internship','entry level')
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
    # Preserve varied legacy query coverage, refresh stale years, and do not quote exact titles.
    for group in fallback:
        batch=[]
        for q in group:
            q=re.sub(r'\b20\d{2}\b',str(year),q).replace('"','')
            if q not in seen:batch.append(q);seen.add(q)
        if batch:batches.append(batch[:6])
    return [b for b in batches if b]
