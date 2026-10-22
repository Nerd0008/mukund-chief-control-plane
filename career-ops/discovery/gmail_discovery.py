"""Gmail newsletter intake for the existing daily discovery/tracker funnel."""
import datetime as dt,html,ipaddress,json,re,socket,time,urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from career_job_mail import ROOT,safe_url,save
from application_links import canonical_posting_url, page_identity


def public_url(url):
    p=urlsplit(url)
    if p.scheme not in {'http','https'} or not p.hostname or p.username or p.port not in (None,80,443):raise ValueError('non-public posting URL')
    if not all(ipaddress.ip_address(a[4][0]).is_global for a in socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM)):raise ValueError('non-public address')

class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        public_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(url,timeout=8):
    url=canonical_posting_url(url)
    public_url(url)
    opener=urllib.request.build_opener(PublicRedirect)
    request=urllib.request.Request(url,headers={'User-Agent':'CareerOpsReadOnly/1.0'})
    with opener.open(request,timeout=timeout) as r:
        if r.status!=200:raise ValueError('posting unavailable')
        return r.read(2_000_000).decode('utf-8','replace')

def posting(page):
    nodes=[]
    def walk(v):
        if isinstance(v,list):
            for item in v:walk(item)
        elif isinstance(v,dict):
            kind=v.get('@type',[]);kind=[kind] if isinstance(kind,str) else kind
            if 'JobPosting' in kind:nodes.append(v)
            if '@graph' in v:walk(v['@graph'])
    for data in re.findall(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',page,re.I|re.S):
        try:walk(json.loads(data))
        except (ValueError,TypeError):continue
    if len(nodes)!=1:return None
    j=nodes[0];org=j.get('hiringOrganization') or {};locations=j.get('jobLocation') or [];locations=[locations] if isinstance(locations,dict) else locations
    parts=[]
    for loc in locations:
        a=loc.get('address') or {}
        for key in ('addressLocality','addressRegion','addressCountry'):
            value=a.get(key);value=value.get('name') if isinstance(value,dict) else value
            if isinstance(value,str):parts.append(value)
    company=org.get('name') if isinstance(org,dict) else None
    if not company or not j.get('title') or not parts:return None
    expires=j.get('validThrough')
    if expires:
        try:
            stamp=dt.datetime.fromisoformat(expires.replace('Z','+00:00'))
            if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=dt.timezone.utc)
            if stamp<dt.datetime.now(dt.timezone.utc):return None
        except ValueError:return None
    description=html.unescape(re.sub('<[^>]+>',' ',j.get('description') or ''))
    return {'company':company,'title':j['title'],'location':', '.join(parts),'description':description[:12000],
            'posted_date':j.get('datePosted'),'employment_type':j.get('employmentType')}

def collect(region,args,*,root=ROOT,fetcher=fetch):
    root=Path(root);path=root/'jobs.json';cache_path=root/'validated-postings.json'
    if not path.exists():return {'lane':'gmail_job_alerts','available':False,'block':{'source':'gmail_job_alert','candidates':[],'coverage':{'available':False,'reason':'no newsletter list yet'}}}
    jobs=json.loads(path.read_text(encoding='utf-8'));cache=json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    live=not getattr(args,'no_live',False) and not getattr(args,'no_validate',False)
    cap=min(20,max(0,getattr(args,'max_urls',20)));end=time.monotonic()+min(90,max(0,getattr(args,'budget_seconds',90)))
    if getattr(args,"gmail_deadline",None) is not None:end=min(end,time.monotonic()+max(0,args.gmail_deadline-time.time()))
    attempts=0;out=[];today=dt.datetime.now(dt.timezone.utc).date().isoformat()
    # Never-checked links come before yesterday's already-checked links.
    def priority(job):
        try: received=dt.datetime.fromisoformat(job.get('received_at') or '').timestamp()
        except (ValueError,TypeError): received=0
        return (cache.get(job['job_id'],{}).get('checked_day',''), -received)
    jobs=sorted(jobs,key=priority)
    for j in jobs:
        cid=j['job_id'];item=cache.get(cid,{})
        if item.get('checked_day')!=today and live and attempts<cap and time.monotonic()<end:
            attempts+=1
            try:
                page=fetcher(j['url'],timeout=min(8,max(1,end-time.monotonic())))
                meta=posting(page)
                discovered=page_identity(page,canonical_posting_url(j['url']))
                item={'checked_day':today,'posting':meta,'discovered':discovered,'state':'validated_live' if meta else 'needs_review'}
            except Exception as e:item={'checked_day':today,'posting':None,'state':'unavailable','error_type':type(e).__name__}
            cache[cid]=item
        meta=item.get('posting') if item.get('checked_day')==today else None
        rec={**(meta or item.get('discovered') or {'company':j.get('company'),'title':j.get('title')}),'url':safe_url(canonical_posting_url(j['url'])),
             'source':'gmail_job_alert','fetch_state':'validated_live' if meta else 'discovered_unverified',
             'result_kind':'job_posting' if meta else 'unknown','_collection_source':'gmail_job_alert'}
        received=j.get('received_at')
        try:
            stamp=dt.datetime.fromisoformat(str(received).replace('Z','+00:00'))
            if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=dt.timezone.utc)
            age=(dt.datetime.now(dt.timezone.utc)-stamp).total_seconds()/3600
        except (ValueError,TypeError):age=float('inf')
        rec['source_generated_at']=received
        rec['historical_seed']=age<0 or age>getattr(args,'ingest_stale_hours',26)
        out.append(rec)
    if live:save(cache_path,cache)
    validated=sum(c['fetch_state']=='validated_live' for c in out)
    return {'lane':'gmail_job_alerts','available':True,'block':{'source':'gmail_job_alert','candidates':out,
        'coverage':{'available':True,'kind':'read-only Gmail newsletter job links','candidates':len(out),
                    'verified_postings':validated,'needs_review':len(out)-validated,'posting_get_attempts':attempts,
                    'region':region,'note':'Same daily eligibility/dedupe funnel and canonical writer; no application status inferred'}}}
