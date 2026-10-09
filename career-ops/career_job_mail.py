"""Read-only Gmail newsletter discovery; never application or Calendar writes."""
from __future__ import annotations
import argparse,base64,datetime as dt,hashlib,json,os,re,tempfile
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,parse_qs,urlencode
from career_mail_parser import mail_fields
from career_google_clients import GmailReader
from career_google_auth import access_token,GoogleError
QUERY='{subject:"job alert" subject:"jobs for you" subject:"career opportunities" subject:vacancies subject:"new jobs" subject:newsletter subject:"talent community"}'
ROOT=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'hermes/runtime/career-ops/gmail-job-alerts'
JOB=re.compile(r'graduate|intern|engineer|analyst|consultant|developer|technician|security|apprentice|placement|manager|specialist|assistant|officer|associate|support',re.I)
class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.url=None;self.label=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.url=dict(attrs).get('href');self.label=[]
    def handle_data(self,data):
        if self.url:self.label.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.url:self.links.append((self.url,' '.join(' '.join(self.label).split())));self.url=None

def safe_url(value):
    p=urlsplit(unescape(value))
    if p.scheme not in {'http','https'} or not p.hostname or p.username:return None
    if re.search(r'unsubscribe|preferences|privacy|login|sign.?in',p.path,re.I):return None
    # Keep only explicit public posting identity parameters. No signed tokens.
    q=parse_qs(p.query);kept={k:v[0] for k,v in q.items() if k.lower() in {'jobid','job_id','requisitionid','gh_jid','postingid'} and re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',v[0])}
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/'),urlencode(sorted(kept.items())),''))

def extract(raw):
    m=mail_fields(raw);subject=m.get('subject','');body=m.get('body','')
    if not re.search(r'job|career|vacanc|recruit|hiring|opportunit|talent',subject+' '+body,re.I):return []
    html=[]
    def walk(part):
        if part.get('mimeType')=='text/html' and (part.get('body') or {}).get('data'):
            v=part['body']['data'];html.append(base64.urlsafe_b64decode(v+'='*(-len(v)%4)).decode('utf-8','replace'))
        for child in part.get('parts',[]):walk(child)
    if raw.get('payload'):walk(raw['payload'])
    parser=Links();parser.feed('\n'.join(html) or body)
    links=parser.links or [(u,'') for u in re.findall(r'https?://[^\s<>"\']+',body)]
    jobs=[]
    for u,label in links:
        url=safe_url(u)
        if not url or re.search(r'unsubscribe|preferences|privacy|view.{0,8}browser',label,re.I):continue
        title=label if JOB.search(label) and len(label)<200 else None
        if not title and not re.search(r'/jobs?[/\-]|/careers/[^/]+|/requisition/',url,re.I):continue
        # Do not follow mail tracking redirects or infer the employer from a sender.
        if re.search(r'/click|/track|/redirect',url,re.I):continue
        jobs.append({'job_id':hashlib.sha256(url.encode()).hexdigest()[:20],'company':None,'title':title,'url':url,
            'source':'gmail_job_alert','source_message_ids':[raw.get('id') or m.get('message_id')],
            'source_thread_ids':[raw.get('threadId') or m.get('thread_id')],
            'received_at':m.get('received_at'),'validation':'discovered_unverified','needs_review':True})
    return jobs

def merge(existing,messages):
    by={j['job_id']:dict(j) for j in existing};found=duplicates=0
    for m in messages:
        for j in extract(m):
            found+=1
            if j['job_id'] in by:
                duplicates+=1;old=by[j['job_id']]
                for key in ['source_message_ids','source_thread_ids']:old[key]=sorted(set(old[key]+j[key])-{None})
                if not old.get('title'):old['title']=j['title']
            else:by[j['job_id']]=j
    return list(by.values()),{'raw_job_links':found,'duplicates_collapsed':duplicates,'job_list_total':len(by)}

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
        os.replace(name,path)
    finally:
        if Path(name).exists():Path(name).unlink()

def compile_list(messages,root=ROOT):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);fd=os.open(root/'scan.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        p=root/'jobs.json';old=json.loads(p.read_text(encoding='utf-8')) if p.exists() else []
        jobs,counts=merge(old,messages);save(p,jobs)
        lines=['# Gmail job-alert discovery','Unverified postings; not applications. Company/eligibility requires checking.','']
        for j in jobs:lines.append(f"- {j['title'] or 'Title requires review'} | Employer requires review | {j['url']}")
        save(root/'summary.json',counts);(root/'job-list.md').write_text('\n'.join(lines),encoding='utf-8')
        return counts
    finally:os.close(fd);(root/'scan.lock').unlink()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['scan']);ap.add_argument('--days',type=int,default=30);ap.add_argument('--max-messages',type=int,default=150);a=ap.parse_args()
    try:
        window=GmailReader(access_token).read_window(days=a.days,max_messages=a.max_messages,query=QUERY)
        counts=compile_list(window['messages']);print(json.dumps(dict(messages_inspected=len(window['messages']),**counts,gmail_mutations=0,tracker_writes=0,model_calls=0,private_job_list=str(ROOT/'job-list.md'))));return 0
    except Exception as e:print(json.dumps({'ok':False,'error_type':type(e).__name__,'gmail_mutations':0}));return 1
if __name__=='__main__':raise SystemExit(main())
