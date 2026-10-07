"""Evidence-ranked matching; no edit-distance, semantic model, or company-only merge."""
import re
from urllib.parse import urlsplit
from email.utils import parseaddr
from career_mail_parser import parse_message, mail_fields, identity_key
from career_mail_rules import company_key, company_aliases, role_key

PLATFORMS=('workday','workable','lever','teamtailor','canditech','hirevue','successfactors','greenhouse','smartrecruiters','jobtrain','oraclecloud','groupgti','hackerrank')

def has_phrase(phrase,text):
    return ' '+identity_key(phrase)+' ' in ' '+identity_key(text)+' '

def has_full_role(phrase,text):
    def normalize(v):
        return re.sub(r'\bcyber security\b','cybersecurity',identity_key(v))
    return ' '+normalize(phrase)+' ' in ' '+normalize(text)+' '

def company_named(record,mail):
    text=mail['subject']+'\n'+mail['body']
    if any(has_phrase(a,text) for a in company_aliases(record['company'])):return True
    host=str(record.get('canonical_job_host') or '').removeprefix('www.').lower()
    if not host or host in {'myworkday.com','myworkdayjobs.com','greenhouse.io','jobs.lever.co','smartrecruiters.com'}:return False
    _,sender=parseaddr(mail.get('from') or '')
    domains=[sender.rsplit('@',1)[-1].lower()]
    domains += [(urlsplit(u).hostname or '').removeprefix('www.').lower() for u in re.findall(r'https?://[^\s<>"\']+',text)]
    return any(d==host or d.endswith('.'+host) for d in domains)


def clean_role(value):
    value=re.sub(r'\s+',' ',value or '')
    value=re.sub(r'(?i)^(?:(?:the|our) )?(?:(?:role|position) of |(?:role|position) )','',value or '').strip()
    value=re.sub(r'(?i)(?:opportunity|vacancy|role)$','',value).strip()
    value=re.sub(r'(?i)^(?:the|our)\s+','',value)
    value=re.sub(r'(?i)\s+(?:ID )?[A-Z]{0,4}-?\d{5,}\s*$','',value).strip()
    return value

def fields(raw,records):
    signal=parse_message(raw)
    if signal is None:return None
    mail=mail_fields(raw);subject=mail['subject'];body=mail['body'];text=subject+'\n'+body
    signal['role']=clean_role(signal.get('role')) or None
    if signal.get('role') and len(role_key(signal['role']).split())<2:signal['role']=None
    explicit_company=bool(re.search(r'(?im)^\s*(?:company|employer)\s*:',text))
    if signal.get('company') and ',' in signal['company']:signal['company']=signal['company'].split(',')[0].strip()
    if str(signal.get('company') or '').startswith('Finance at '):signal['company']=signal['company'][len('Finance at '):]
    evidence=signal.setdefault('identity_evidence',[])
    # Employer explicitly named in the subject outranks names in privacy footers.
    subject_employer=None
    for pattern in [r'(?i)^(?:thank you for applying to|your application (?:with|to)|confirming your) ([^!\n]+?)(?: job application)?[!]?$' ,r'(?i)^next step with ([^!\n]+)[!]?$']:
        m=re.search(pattern,subject)
        if m and not re.search(r'(?i)programme|internship|campus|join us',m.group(1)):
            subject_employer=m.group(1).strip();break
    if subject_employer and not explicit_company:
        signal['company']=subject_employer;explicit_company=True;evidence.append('explicit employer subject')
    named_explicit=bool(signal.get('company'))
    known=[]
    for record in records:
        # Canonical employer variants are audited by the matcher: collisions remain review-only.
        if any(has_phrase(a,subject) for a in company_aliases(record['company'])):known.append(record['company'])
    if not known:
        for record in records:
            if company_named(record,mail):known.append(record['company'])
    families={company_key(c.split('(')[0].split('/')[0]) for c in known}
    if len(families)==1 and known and (not signal.get('company') or any(company_key(signal['company']) in company_aliases(c) for c in known)):
        signal['company']=known[0].split('(')[0].split('/')[0].strip();evidence.append('employer named in subject/body and canonical employer index')
    signal['employer_named_candidates']=sorted(set(known))
    # Explicit employer phrases for employers absent from the tracker.
    if not signal.get('company'):
        for pattern in [r'thank you for (?:your application|applying) to ([^\n.!?]{2,90})',r'thank you for your interest in ([^\n.!?]{2,90}?)(?: and| where|,|\n|$)',r'(?:career at|invited by) ([^\n.!?]{2,80}?)(?: to |\n|$)']:
            m=re.search(pattern,text,re.I)
            if m:
                value=m.group(1).strip()
                if not re.search(r'(?i)programme|join us|role|position|internship|^us$|^our |^the engineering',value) and len(value.split())<=7:
                    signal['company']=value;evidence.append('explicit employer phrase');break
    if not signal.get('company'):
        m=re.search(r'(?i)^(?:your application (?:with|to)|confirming your) (.+?)(?: job application)?$',subject)
        if m:signal['company']=m.group(1).strip();evidence.append('explicit employer in subject')
        else:
            pieces=re.split(r'\s+[–—-]\s+',subject)
            if len(pieces)>=2:
                if re.search(r'(?i)^(?:application received|thank)',pieces[-1]):signal['company']=pieces[0].strip()
                elif not re.search(r'(?i)application|thank|update',subject):signal['company']=pieces[-1].strip()
    if not signal.get('role'):

        for pattern in [r'for the position of\s+([^.!?]{2,180}?)(?: has been| that requires| and are currently|\n\n|$)',r'interest in [^\n.!?]+ and the\s+([^\n.!?]{2,180}?) role',r'time to apply for\s+([^\n.!?]{2,180}?)(?:, one of|\n|$)',r'join us as a\s+([^\n.!?]{2,180})(?:\n|$)',r'application to (?:the\s+)?([^\n.!?]{2,180})(?:\n|$)']:
            m=re.search(pattern,text,re.I)
            if m:
                signal['role']=clean_role(m.group(1));evidence.append('explicit portal position phrase');break
    if not signal.get('role'):
        m=re.search(r'\b(?:R\d{6,}|WD\d{6,}|JR-\d{6,})\s+([^\n]{3,180})',subject)
        if m:
            value=m.group(1)
            if signal.get('company') and value.lower().startswith(str(signal['company']).lower()+' '):value=value[len(signal['company']):].strip()
            signal['role']=clean_role(value);evidence.append('role named after explicit requisition reference')
    # Trim explicit employer and portal reference from a captured role.
    if signal.get('role') and signal.get('company'):
        value=signal['role']
        if re.search(r'(?i)\s+at\s+',value): value=re.split(r'(?i)\s+at\s+',value)[0]
        signal['role']=clean_role(value).strip(' ,')
    if not signal.get('role'):
        m=re.search(r'(?i)\b(?:role|position) of\s+([^.!?]{2,160}?)(?:\n\n|Your application| at |$)', ' '.join(text.split()))
        if m:signal['role']=clean_role(m.group(1));evidence.append('wrapped role-of phrase')
    # Subject "Employer - Role - Thank you ..." / "Role - Employer".
    parts=re.split(r'\s+[–—-]\s+',subject)
    if len(parts)>=2 and signal.get('company'):
        for i,part in enumerate(parts):
            if company_key(part) in company_aliases(signal['company']):
                adjacent=parts[i+1] if i==0 else parts[i-1]
                if not re.search(r'(?i)application|thank|update|received',adjacent):
                    signal['role']=clean_role(adjacent);evidence.append('employer/role subject layout')
    if not signal.get('company') and signal.get('role'):
        paired=[r for r in records if role_key(signal['role'])==role_key(r['role']) and company_named(r,mail)]
        if len(paired)==1:
            signal['company']=paired[0]['company'];evidence.append('unique named employer and complete canonical role')
    if not signal.get('company') and not signal.get('role'):
        named_pairs=[r for r in records if company_named(r,mail) and has_full_role(r['role'],text)]
        if len(named_pairs)==1:
            signal.update(company=named_pairs[0]['company'],role=named_pairs[0]['role']);evidence.append('canonical employer host and complete named role')
    # Candidate full role is actually mentioned, not inferred from a unique company.
    if signal.get('company') and not signal.get('role'):
        possible={r['role'] for r in records if company_key(signal['company']) in company_aliases(r['company']) and has_full_role(r['role'],text)}
        if len(possible)==1:signal['role']=possible.pop();evidence.append('full canonical role named in subject/body')
    # Portal references are retained only from explicit application/requisition evidence.
    refs=re.findall(r'(?i)\b(?:WD\d{6,}|JR-\d{6,}|R-\d{6,}|R\d{6,}|[A-Z]{3}\d{4}[A-Z]{2}|SYS-\d{4,})\b',subject+'\n'+body)
    if not signal.get('application_identity') and len(set(refs))==1:
        signal['application_identity']=refs[0];signal['reference_type']='requisition';evidence.append('explicit portal requisition reference')
    sender=mail.get('from') or ''
    if signal.get('role') and len(role_key(signal['role']).split())<2:signal['role']=None
    context=raw.get('_identity_context') or {}
    for field in ('company','role','region'):
        if not signal.get(field) and context.get(field):
            signal[field]=context[field];evidence.append(context.get('method','message thread/reference context')+' supplied '+field)
    signal['platform_sender']=any(p in sender.lower() for p in PLATFORMS)
    return signal

def compatible(signal,record):
    if signal.get('region') and signal['region']!=record.get('region'):return False
    cities=('london','chester','burgess hill','knutsford','ipswich','dubai','singapore','tokyo')
    supplied={c for c in cities if has_phrase(c,signal.get('role') or '')}
    canonical={c for c in cities if has_phrase(c,record.get('role') or '')}
    if supplied and canonical and supplied!=canonical:return False
    if signal.get('application_identity') and record.get('application_identity') and signal['application_identity']!=record['application_identity']:return False
    if signal.get('company') and company_key(signal['company']) not in company_aliases(record['company']):return False
    return True

def resolve(raw,records):
    signal=fields(raw,records)
    if signal is None:return None,[],None
    # Strong evidence first. Candidate/person IDs alone are not application IDs.
    ref=signal.get('application_identity')
    reference=[r for r in records if ref and signal.get('reference_type')!='candidate' and (r.get('application_identity')==ref or ref in r.get('job_reference_ids',[]))]
    thread=[r for r in records if signal['gmail_thread_id'] in r.get('thread_ids',[])]
    if reference:return signal,[r for r in reference if compatible(signal,r)],'application/reference ID'
    if thread:
        consistent=[r for r in thread if compatible(signal,r) and (not signal.get('role') or role_key(signal['role'])==role_key(r['role']))]
        if consistent:return signal,consistent,'Gmail thread'
        # Gmail can group same-subject receipts for different roles at one employer.
        # A contradictory thread must not override a distinct complete identity.
        alternatives=[r for r in records if compatible(signal,r) and signal.get('company') and signal.get('role') and role_key(signal['role'])==role_key(r['role'])]
        if alternatives:return signal,alternatives,'company + normalized full role (reused thread)'
        return signal,thread,'Gmail thread' 
    candidates=[r for r in records if compatible(signal,r) and signal.get('company') and signal.get('role') and role_key(signal['role'])==role_key(r['role'])]
    return signal,candidates,'company + normalized full role' if candidates else None

def review_reason(signal,records):
    reasons=[]
    if signal.get('platform_sender'):reasons.append('recruitment platform sender; employer/role must be established from message evidence')
    if not signal.get('company'):reasons.append('company extraction failure: no unique explicit employer')
    if not signal.get('role'):reasons.append('role extraction failure: no complete role title')
    if not signal.get('region'):reasons.append('canonical region missing')
    employer=[r for r in records if signal.get('company') and company_key(signal['company']) in company_aliases(r['company'])]
    if employer and signal.get('role'):reasons.append('title variation or a different role: no unique full-role equivalence')
    if signal.get('company') and signal.get('role') and not employer:reasons.append('no canonical employer/role pair; likely new application')
    return reasons
