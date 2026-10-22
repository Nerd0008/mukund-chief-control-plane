#!/usr/bin/env python3
"""Fetch and extract plain text from a job posting URL.

Used by both the daily digest and the nightly pipeline to read full JDs
before the clearance/eligibility gates run. No browser, no login, no
JavaScript — just HTTP GET + HTML-to-text extraction.

Returns a dict with:
  - url: the URL that was fetched
  - status: HTTP status code
  - text: extracted plain text (or empty string on failure)
  - error: error message (or None)
  - fetch_state: transport only: "fetched", "bot_wall", "fetch_failed"
  - vacancy_status: independent OPEN / CLOSED / UNKNOWN with evidence
"""
from __future__ import annotations

import re
import json,time
from job_liveness import assess, closure_evidence
from application_deadlines import extract_application_deadline
import urllib.error
import urllib.request
from urllib.parse import urlparse
from application_links import extract as extract_links, public_url, aggregator, listing, title_matches, employer_matches, employer_name, fragment_route, canonical_posting_url, page_identity, mask_recommendations

MAX_BYTES = 512 * 1024  # 512 KB cap
TIMEOUT = 30  # seconds
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Tags whose content is typically the main job body
CONTENT_SELECTORS = (
    "article", "main", "[role=main]",
    ".job-description", ".job-description__content",
    ".description", ".details", ".details-body",
    "#job-description", "#jobDescription",
    ".posting-content", ".posting-content__text",
    ".ats-description", ".ats-job-description",
    ".greenhouse-job-description",
    "[data-testid=job-description]",
    ".jobsearch-JobComponent-description",
    ".job-details", ".job-details-body",
)

# Tags to strip before extraction
STRIP_TAGS = (
    "script", "style", "nav", "header", "footer",
    "form", "button", "select", "input", "textarea",
    "svg", "canvas", "video", "audio", "iframe",
    "noscript", "template",
)


def _html_to_text(html: str) -> str:
    """Extract readable text from HTML without external dependencies."""
    # Remove strip tags and their content
    for tag in STRIP_TAGS:
        html = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}>",
            " ",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
    # Remove HTML comments
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    # Replace <br>, <p>, <div>, <li>, <tr>, <h1-6> with newlines
    html = re.sub(
        r"<(?:br|/p|/div|/li|/tr|/h[1-6]|/section|/article)\b[^>]*>",
        "\n",
        html,
        flags=re.IGNORECASE,
    )
    # Remove all remaining tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    html = (
        html.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&#x27;", "'")
        .replace("&#x2F;", "/")
        .replace("&ndash;", "–")
        .replace("&mdash;", "—")
    )
    # Collapse whitespace
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n\s*\n", "\n\n", html)
    return html.strip()


def fetch_jd(url: str, timeout=None, *, _depth=0, _seen=None) -> dict:
    """Fetch a job posting URL and return extracted text.

    Returns a dict with keys: url, status, text, error, fetch_state.
    """
    started=time.monotonic()
    visited=set(_seen or ())
    if url in visited:
        return {'url':url,'text':'','vacancy_status':{'state':'UNKNOWN','evidence':'application-link cycle'}}
    visited.add(url)
    html=''
    request_timeout=TIMEOUT if timeout is None else max(0.1,float(timeout))
    result = {
        "url": url,
        "status": None,
        "text": "",
        "error": None,
        "fetch_state": "fetch_failed",
        "deadline": None,
        "vacancy_status": {"state":"UNKNOWN","evidence":"job not fetched"},
        "deadline_info": extract_application_deadline("", url),
    }

    if not public_url(url):
        result["error"] = "not a valid HTTP URL"
        return result

    source_url = url
    url = canonical_posting_url(url)
    result['retrieval_url'] = url
    parsed = urlparse(url)
    if not parsed.hostname:
        result["error"] = "no hostname in URL"
        return result

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=request_timeout) as resp:
            result["status"] = resp.status
            final_url=resp.geturl() if callable(getattr(resp,'geturl',None)) else url
            result['final_url']=final_url
            raw = resp.read(MAX_BYTES)
            charset = resp.headers.get_content_charset() or "utf-8"
            try:
                html = raw.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                html = raw.decode("utf-8", errors="replace")
            html=mask_recommendations(html)
            result["text"] = _html_to_text(html)
            identity = page_identity(html, final_url)
            if identity: result['discovered_posting'] = identity
            # JS ATS shells often publish the full JD only as JobPosting JSON-LD.
            # Preserve it for clearance/eligibility checks, not just title matching.
            structured=extract_links(html,final_url)['posting']
            if structured.get('description'):
                description=_html_to_text(str(structured['description']))
                if description not in result['text']:
                    result['text'] += '\n'+description
            result["fetch_state"] = "fetched"  # HTTP transport success, not vacancy availability.
            result["deadline_info"] = extract_application_deadline(result["text"], url)
            result["deadline"] = result["deadline_info"]["date"]
            result["vacancy_status"] = assess(html,result["text"],result["deadline_info"],final_url)
            result["is_closed"] = result["vacancy_status"]["state"]=="CLOSED"
    except urllib.error.HTTPError as e:
        result["status"] = e.code
        if e.code in (404,410):
            result["vacancy_status"]={"state":"CLOSED","evidence":f"job URL returned HTTP {e.code}"}
            result["is_closed"]=True
        if e.code in (403, 429):
            result["fetch_state"] = "bot_wall"
            result["error"] = f"HTTP {e.code} (bot wall)"
        else:
            result["error"] = f"HTTP {e.code}"
    except urllib.error.URLError as e:
        result["error"] = f"URL error: {e.reason}"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    if result['vacancy_status']['state']=='UNKNOWN':
        remaining=request_timeout-(time.monotonic()-started)
        if remaining>0.2:
            fallback=_active_ats_record(url,remaining)
            if not fallback and result.get('final_url') and result['final_url']!=url:
                remaining=request_timeout-(time.monotonic()-started)
                if remaining>0.2:fallback=_active_ats_record(result['final_url'],remaining)
            if fallback:
                result.update(fallback)
                if result['vacancy_status']['state']=='OPEN':
                    result.setdefault('resolved_url',url)
                    result.setdefault('application_url',url)
                    return result
    # Resolve only the target vacancy's explicit route, within the same elapsed budget.
    # Aggregator controls are discovery evidence; only the destination can prove OPEN.
    remaining=lambda:request_timeout-(time.monotonic()-started)
    if html and result['vacancy_status']['state']!='CLOSED' and not listing(result.get('final_url') or url):
        source=result.get('final_url') or url
        page=extract_links(html,source)
        if len(page['frames'])==1 and remaining()>0.2:
            frame=public_url(page['frames'][0],source)
            if frame and urlparse(frame).hostname==urlparse(source).hostname:
                try:
                    request=urllib.request.Request(frame,headers={'User-Agent':USER_AGENT})
                    with urllib.request.urlopen(request,timeout=remaining()) as response:
                        fragment=response.read(MAX_BYTES).decode('utf-8','replace')
                    if fragment_route(page,fragment,source,frame):
                        result['vacancy_status']={'state':'OPEN','page_title':page['title'],
                            'evidence':'employer application fragment contains form bound to exact JobPosting identifier'}
                        result['resolved_url']=source
                        result['application_url']=source+'#Apply'
                except (OSError,ValueError):pass
        if len(page['links'])>1:
            result['vacancy_status']={'state':'UNKNOWN','evidence':'multiple different application destinations; identity requires review','page_title':page['title']}
        elif len(page['links'])==1:
            link=page['links'][0];target=link['url']
            external=urlparse(source).hostname!=urlparse(target).hostname
            if (external or aggregator(source)) and _depth<2 and target not in visited and remaining()>0.2:
                # Workday /apply is the same posting's form; read the job landing instead.
                landing=target.removesuffix('/apply') if (urlparse(target).hostname or '').endswith('.myworkdayjobs.com') else target
                child=fetch_jd(landing,remaining(),_depth=_depth+1,_seen=visited)
                child_title=child.get('vacancy_status',{}).get('page_title') or ''
                title_ok=title_matches(page['title'],child_title)
                company_ok=employer_matches(source,link['label'],child.get('final_url') or landing,child.get('text') or '')
                resolution={'source_url':url,'outbound_url':target,'destination_url':child.get('final_url') or landing,
                            'employer':employer_name(link['label']),
                            'title_match':title_ok,'employer_match':company_ok,
                            'state':child.get('vacancy_status',{}).get('state','UNKNOWN')}
                result['application_resolution']=resolution
                if title_ok and company_ok and child.get('vacancy_status',{}).get('state') in ('OPEN','CLOSED'):
                    result.update({k:child[k] for k in ('text','deadline_info','deadline','vacancy_status','is_closed','validation_source','posting_identity') if k in child})
                    result['is_closed']=result['vacancy_status']['state']=='CLOSED'
                    if result['vacancy_status']['state']=='OPEN':
                        result['resolved_url']=child.get('resolved_url') or child.get('final_url') or landing
                        result['application_url']=child.get('application_url') or target
                else:
                    result['vacancy_status']={'state':'UNKNOWN','evidence':'application destination found but vacancy identity/availability not verified','page_title':page['title']}
            elif not external and not aggregator(source) and result['vacancy_status']['state']=='OPEN':
                result['resolved_url']=source
                result['application_url']=target
            elif external or aggregator(source):
                result['vacancy_status']={'state':'UNKNOWN','page_title':page['title'],
                    'evidence':'application-link hop/time budget exhausted or cycle detected'}
        result['is_closed']=result['vacancy_status']['state']=='CLOSED'
    if listing(result.get('final_url') or url):
        result['vacancy_status']={'state':'UNKNOWN','evidence':'category/search page is not an individual vacancy'}
        result['is_closed']=False
    return result


# ---------------------------------------------------------------------------
# deadline + liveness extraction
# ---------------------------------------------------------------------------


def extract_deadline(text: str):
    """Compatibility date-only API; structured JD deadline extraction is authoritative."""
    return extract_application_deadline(text)['date']


def is_job_closed(text: str) -> bool:
    """Check if the job page indicates the position is closed or filled."""
    return bool(closure_evidence(text))


def fetch_jds(urls: list[str], *, timeout: int = TIMEOUT) -> list[dict]:
    """Fetch multiple job URLs, return list of result dicts."""
    results = []
    for url in urls:
        results.append(fetch_jd(url,timeout=timeout))
    return results

def _active_ats_record(url,timeout):
    """One public read-only ATS lookup, only for known exact posting URL shapes."""
    parsed=urlparse(url);host=(parsed.hostname or '').lower();path=parsed.path
    endpoint=None;identity=None;vendor=None
    if host in ('job-boards.greenhouse.io','boards.greenhouse.io'):
        match=re.fullmatch(r'/([^/]+)/jobs/(\d+)/?',path)
        if match:endpoint=f'https://boards-api.greenhouse.io/v1/boards/{match[1]}/jobs/{match[2]}';identity=match[2];vendor='Greenhouse'
    elif host=='jobs.ashbyhq.com':
        match=re.fullmatch(r'/([^/]+)/([a-fA-F0-9-]{36})(?:/application)?/?',path)
        if match:endpoint=f'https://api.ashbyhq.com/posting-api/job-board/{match[1]}';identity=match[2];vendor='Ashby'
    elif host=='apply.workable.com':
        match=re.fullmatch(r'/([^/]+)/j/([A-Za-z0-9]+)(?:/apply)?/?',path)
        if match:endpoint=f'https://www.workable.com/api/accounts/{match[1]}?details=true';identity=match[2];vendor='Workable'
    elif host=='jobs.lever.co':
        match=re.fullmatch(r'/([^/]+)/([a-zA-Z0-9-]+)/?',path)
        if match:endpoint=f'https://api.lever.co/v0/postings/{match[1]}/{match[2]}?mode=json';identity=match[2];vendor='Lever'
    elif host=='jobs.smartrecruiters.com':
        match=re.fullmatch(r'/([^/]+)/(\d+)(?:-[^/]+)?/?',path)
        if match:
            endpoint=f'https://api.smartrecruiters.com/v1/companies/{match[1]}/postings/{match[2]}'
            identity=match[2];vendor='SmartRecruiters'
    elif host.endswith('.myworkdayjobs.com'):
        match=re.fullmatch(r'/(?:[a-z]{2}-[A-Z]{2}/)?([^/]+)/job/(.+?)(?:/apply)?/?',path)
        requisition=re.search(r'_(JR[-\w]+|R[-\w]+)$',match[2]) if match else None
        if match and requisition:
            tenant=host.split('.')[0]
            endpoint=f'https://{host}/wday/cxs/{tenant}/{match[1]}/job/{match[2]}'
            identity=requisition[1];vendor='Workday'
    if not endpoint:return None
    try:
        req=urllib.request.Request(endpoint,headers={'Accept':'application/json','User-Agent':USER_AGENT})
        with urllib.request.urlopen(req,timeout=timeout) as response:data=json.loads(response.read(MAX_BYTES).decode('utf-8'))
        if not isinstance(data,dict):return None
        if vendor in ('Ashby','Workable'):
            # Documented unauthenticated GET feeds of published jobs. Never infer
            # closure from absence (feeds can be partial/limited or unavailable).
            jobs=data.get('jobs')
            if not isinstance(jobs,list):return None
            matches=[]
            for job in jobs:
                if not isinstance(job,dict):continue
                if vendor=='Ashby':
                    joburl=job.get('jobUrl') or ''
                    if canonical_posting_url(joburl).rstrip('/')!=canonical_posting_url(url).removesuffix('/application').rstrip('/'):continue
                    if job.get('isListed') is not True or not public_url(job.get('applyUrl')):continue
                else:
                    if str(job.get('shortcode'))!=identity:continue
                    if job.get('state') and job['state']!='published':continue
                matches.append(job)
            if len(matches)!=1:return None
            job=matches[0];title=job.get('title');content=job.get('descriptionPlain') or job.get('description') or job.get('descriptionHtml')
            if not title or not content:return None
            text=_html_to_text(content);deadline=extract_application_deadline(text,url)
            state=assess('',text,deadline)
            if state['state']!='CLOSED':
                state={'state':'OPEN','evidence':f'{vendor} public published-jobs feed returned exact posting {identity}'}
            state['page_title']=title
            loc=job.get('location') or ''
            if isinstance(loc,dict):loc=', '.join(str(loc[k]) for k in ('city','country') if loc.get(k))
            return {'text':text,'deadline_info':deadline,'deadline':deadline['date'],
                'vacancy_status':state,'is_closed':state['state']=='CLOSED','validation_source':endpoint,
                'posting_identity':{'title':title,'location':loc},'application_url':job.get('applyUrl') or url}
        if vendor=='SmartRecruiters':
            if str(data.get('id'))!=identity or not data.get('name'):return None
            if (data.get('company') or {}).get('identifier')!=match[1]:return None
            sections=(data.get('jobAd') or {}).get('sections') or {}
            content='\n'.join(str(v.get('text') or '') for v in sections.values() if isinstance(v,dict))
            if not content:return None
            text=_html_to_text(content);deadline=extract_application_deadline(text,url)
            state=assess('',text,deadline)
            if state['state']!='CLOSED':
                state={'state':'OPEN','evidence':'SmartRecruiters public active posting API returned matching company and requisition '+identity}
            state['page_title']=data['name']
            return {'text':text,'deadline_info':deadline,'deadline':deadline['date'],
                    'vacancy_status':state,'is_closed':state['state']=='CLOSED','validation_source':endpoint,
                    'posting_identity':{'company':data['company'].get('name') or match[1],
                        'title':data['name'],'location':(data.get('location') or {}).get('fullLocation') or (data.get('location') or {}).get('city')}}
        if vendor=='Workday':
            info=data.get('jobPostingInfo') or {}
            if info.get('jobReqId')!=identity or not info.get('title'):return None
            content=info.get('jobDescription') or ''
            deadline=extract_application_deadline(_html_to_text(content),url)
            end_date=info.get('endDate')
            if end_date and re.fullmatch(r'\d{4}-\d{2}-\d{2}',end_date):
                deadline={'type':'EXACT','date':end_date,'source':'ATS','source_url':url,'evidence':'Workday endDate: '+end_date}
            state=assess('',_html_to_text(content),deadline)
            if state['state']!='CLOSED':
                if info.get('posted') is False:state={'state':'CLOSED','evidence':'Workday exact requisition is no longer posted'}
                elif info.get('canApply') is True and info.get('posted') is True:
                    state={'state':'OPEN','evidence':'Workday exact requisition is posted with canApply=true'}
                else:return None
            state['page_title']=info['title']
            return {'text':_html_to_text(content),'deadline_info':deadline,'deadline':deadline['date'],
                    'vacancy_status':state,'is_closed':state['state']=='CLOSED','validation_source':endpoint}
        if str(data.get('id'))!=identity:return None
        title=data.get('title') or data.get('text');content=data.get('content') or data.get('descriptionPlain') or data.get('description') or ''
        if not title:return None
        text=_html_to_text(content);deadline=extract_application_deadline(text,url)
        state=assess('',text,deadline)
        if state['state']!='CLOSED':state={'state':'OPEN','evidence':f'{vendor} public active posting API returned matching requisition {identity}','page_title':title}
        return {'text':text,'deadline_info':deadline,'deadline':deadline['date'],
                'vacancy_status':state,'is_closed':state['state']=='CLOSED','validation_source':endpoint}
    except (OSError,ValueError,TypeError):return None
