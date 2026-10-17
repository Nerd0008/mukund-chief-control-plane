"""Vacancy status and fresh delivery evidence. HTTP success is not vacancy status."""
import datetime as dt,hashlib,json,os,pathlib,re,time,uuid
from urllib.parse import urlsplit

CACHE_PATH=pathlib.Path(r'C:/Users/mukun/AppData/Local/hermes/runtime/career-ops/vacancy-status.json')
TTL_SECONDS=900
CLOSED=re.compile(r'\b(?:(?:this\s+)?(?:job|vacancy|role|position|opportunity)\s+(?:(?:has|is)\s+)?(?:now\s+)?(?:expired|closed|filled|no\s+longer\s+available)|applications?\s+(?:(?:are|have)\s+)?(?:now\s+)?(?:closed|ended)|no\s+longer\s+accepting\s+applications|closed\s+for\s+applications|(?:deadline\s+has\s+passed|application\s+period\s+has\s+ended)|(?:position|role)\s+has\s+been\s+filled)\b',re.I)

def closure_evidence(text):
    # Do not let unrelated recommendations close the target posting.
    target=re.split(r'\b(?:similar\s+(?:roles|jobs)|related\s+(?:roles|jobs))\b',text or '',maxsplit=1,flags=re.I)[0]
    match=CLOSED.search(target)
    return match.group(0) if match else None

def assess(html,text,deadline_info):
    closed=closure_evidence(text)
    if closed:return {'state':'CLOSED','evidence':closed}
    date=(deadline_info or {}).get('date')
    if date and date<dt.date.today().isoformat():return {'state':'CLOSED','evidence':'application deadline passed: '+date}
    if re.search(r'access denied|verify (?:you are|that you are) human|captcha|just a moment|enable javascript',text or '',re.I):
        return {'state':'UNKNOWN','evidence':'challenge or inaccessible job content'}
    # Structured expiry is authoritative even when the human-readable date is missing.
    for raw in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',html or '',re.I|re.S):
        try:
            data=json.loads(raw);items=data if isinstance(data,list) else data.get('@graph',[data])
            postings=[item for item in items if isinstance(item,dict) and item.get('@type')=='JobPosting']
            if len(postings)!=1:continue
            expiry=postings[0].get('validThrough')
            if expiry:
                if 'T' in str(expiry):
                    stamp=dt.datetime.fromisoformat(str(expiry).replace('Z','+00:00'))
                    expired=stamp.tzinfo is not None and stamp<dt.datetime.now(dt.timezone.utc)
                else:expired=dt.date.fromisoformat(str(expiry))<dt.date.today()
                if expired:return {'state':'CLOSED','evidence':'JobPosting validThrough has passed'}
        except (ValueError,TypeError,AttributeError):continue
    # Positive application control on the target section, not a footer recommendation.
    target=re.split(r'\b(?:similar\s+(?:roles|jobs)|related\s+(?:roles|jobs))\b',html or '',maxsplit=1,flags=re.I)[0]
    apply=re.search(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>\s*(?:<[^>]+>\s*)*(?:apply\s+(?:now|for\s+this\s+(?:job|role|position))|apply)(?:\s*<[^>]+>)*\s*</a>',target,re.I)
    h1=re.search(r'<h1\b[^>]*>(.*?)</h1>',target,re.I|re.S)
    title=re.sub('<[^>]+>',' ',h1.group(1)).strip() if h1 else ''
    overlay=re.search(r'data-careersite--jobs--form-overlay-job-application-url-value=["\']([^"\']+)["\']',target,re.I)
    job_id=re.search(r'data-careersite--jobs--form-overlay-job-id-value=["\'](\d+)["\']',target,re.I)
    if overlay and job_id and title and '/jobs/'+job_id[1] in overlay[1] and overlay[1].endswith('/applications/new'):
        return {'state':'OPEN','evidence':'Teamtailor target application overlay matches job ID '+job_id[1],'page_title':title}
    if apply and title and apply.group(1).lower().startswith(('http://','https://','/')):
        return {'state':'OPEN','evidence':'target job title and active application link','page_title':title}
    return {'state':'UNKNOWN','evidence':'no current positive vacancy availability evidence','page_title':title}

def identity_key(record):
    from career_search_recall import posting_key
    return hashlib.sha256(json.dumps([posting_key(record.get('url')),str(record.get('company') or '').casefold(),str(record.get('title') or record.get('job_title') or '').casefold()]).encode()).hexdigest()

def load_cache():
    try:
        data=json.loads(CACHE_PATH.read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):return {}

def save_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True,exist_ok=True)
    lock=CACHE_PATH.with_suffix('.lock');fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    temp=CACHE_PATH.with_suffix('.'+uuid.uuid4().hex+'.tmp')
    try:
        combined=load_cache();combined.update(cache)
        temp.write_text(json.dumps(combined,ensure_ascii=True),encoding='utf-8');os.replace(temp,CACHE_PATH)
    finally:
        temp.unlink(missing_ok=True);os.close(fd);lock.unlink()

def record_verification(record,result,cache=None):
    info=dict(result.get('vacancy_status') or {'state':'UNKNOWN','evidence':'missing vacancy status'})
    if info.get('state')=='OPEN' and info.get('page_title'):
        expected=set(re.findall(r'[a-z0-9]+',str(record.get('title') or record.get('job_title') or '').lower()))
        actual=set(re.findall(r'[a-z0-9]+',info['page_title'].lower()))
        if expected and len(expected&actual)/len(expected)<0.75:
            info={'state':'UNKNOWN','evidence':'destination title does not match tracker role'}
    info['checked_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    info['deadline_info']=result.get('deadline_info') or {'type':'UNKNOWN','date':None}
    key=identity_key(record)
    if cache is not None:cache[key]=info
    else:
        try:save_cache({key:info})
        except OSError:info['cache_persisted']=False
    return info

def fresh_status(record,cache,now=None):
    from application_deadlines import deadline_priority
    if deadline_priority(record)[0]==4:return {'state':'CLOSED','evidence':'stored application deadline passed'}
    info=cache.get(identity_key(record)) or {}
    if not isinstance(info,dict):info={}
    if deadline_priority({'deadline_info':info.get('deadline_info') or {}})[0]==4:
        return {'state':'CLOSED','evidence':'verified application deadline passed'}
    try:
        checked=dt.datetime.fromisoformat(info['checked_at']);age=((now or dt.datetime.now(dt.timezone.utc))-checked).total_seconds()
        if 0<=age<=TTL_SECONDS:return info
    except (KeyError,ValueError,TypeError):pass
    return {'state':'UNKNOWN','evidence':'fresh vacancy verification unavailable'}

def refresh(records,limit=30,budget_seconds=60,fetcher=None):
    from jd_fetcher import fetch_jd
    fetcher=fetcher or fetch_jd;cache=load_cache();updates={};start=time.monotonic();checked=0
    records=sorted(records,key=lambda rec:str((cache.get(identity_key(rec)) or {}).get('checked_at','')) if isinstance(cache.get(identity_key(rec)),dict) else '')
    for rec in records:
        if checked>=limit or time.monotonic()-start>=budget_seconds:break
        old=cache.get(identity_key(rec))
        try:
            age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(old['checked_at'])).total_seconds()
            if 0<=age<=TTL_SECONDS:continue
        except (TypeError,KeyError,ValueError):pass
        remaining=budget_seconds-(time.monotonic()-start)
        if remaining<1:break
        try:result=fetcher(rec['url'],timeout=min(8,remaining))
        except Exception:result={'vacancy_status':{'state':'UNKNOWN','evidence':'availability check failed'}}
        record_verification(rec,result,updates);checked+=1
    if updates:
        try:save_cache(updates)
        except OSError:return {'checked':checked,'cache_error':'availability cache could not be updated; stale evidence remains withheld'}
    return {'checked':checked,'cached':len(cache),'updates':len(updates)}
