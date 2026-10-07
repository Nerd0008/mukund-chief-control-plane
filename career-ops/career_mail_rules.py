"""Deterministic second-pass rules. No network, model or mailbox mutations."""
import datetime as dt
import re
import unicodedata
from html import unescape
from html.parser import HTMLParser

class VisibleMail(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.hidden = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in {'style','script','head'}: self.hidden += 1
        if tag in {'br','p','div','li','tr','td','h1','h2'}: self.out.append('\n')
        if tag in {'span','a','b','strong'}: self.out.append(' ')
        if tag=='img':
            alt=dict(attrs).get('alt','')
            if len(alt)<=100 and alt:self.out.append(' '+alt+' ')
    def handle_endtag(self, tag):
        if tag in {'style','script','head'}: self.hidden = max(0, self.hidden-1)
        if tag in {'p','div','li','tr','td','h1','h2'}: self.out.append('\n')
        if tag in {'span','a','b','strong'}: self.out.append(' ')
    def handle_data(self,data):
        if not self.hidden:self.out.append(data)

def visible(text):
    text = unescape(text or '')
    if re.search(r'<(?:html|body|p|div|span|a|style|table|br)\b',text,re.I):
        parser=VisibleMail();parser.feed(text);text=''.join(parser.out)
    text=re.sub(r'[ \t\xa0\u202f]+',' ',text)
    return re.sub(r'\n[ \t]*\n+', '\n',text)

def key(text):
    return ' '.join(re.findall(r'[^\W_]+',unicodedata.normalize('NFKC',str(text or '')).casefold()))

SUFFIXES={'ltd','limited','plc','llp','group','careers','uk'}
def company_key(text):
    words=key(text).split()
    while len(words)>1 and words[-1] in SUFFIXES:words.pop()
    if len(words)>1 and words[0]=='the':words.pop(0)
    return ' '.join(words)

def company_aliases(text):
    aliases=[text]
    if '/' in str(text):aliases.extend(str(text).split('/'))
    if '(' in str(text):aliases.append(str(text).split('(')[0])
    return {company_key(a) for a in aliases if company_key(a)}

LOCATIONS=r'London|Chester|Burgess Hill|Knutsford|Ipswich|United Kingdom|UK|Dubai|Singapore|Japan|Tokyo'
def role_key(text):
    value=visible(str(text or '')).replace('\u2014','-').replace('\u2013','-')
    value=re.sub(r'(?i)^(?:(?:the|our)\s+)?(?:(?:role|position)\s+of\s+|(?:role|position)\s+)','',value)
    value=re.sub(r'(?i)\s+(?:role|vacancy|opportunity)$','',value)
    value=re.sub(r'(?i)\s*(?:[-,]|\()\s*(?:'+LOCATIONS+r')(?:\s*\))?\s*$','',value)
    value=key(value)
    value=re.sub(r'\bgrad\b','graduate',value)
    value=re.sub(r'\binterns?\b','internship',value)
    value=re.sub(r'\bcyber security\b','cybersecurity',value)
    if re.search(r'\b(?:graduate|internship|placement)\b',value):
        value=re.sub(r'\b(?:programme|program)\b','',value)
    # Word order varies in employer titles; retain every substantive qualifier,
    # cohort/year, seniority, location not explicitly removed, and duration.
    return ' '.join(sorted(value.split()))

MONTHS={n.lower():i for i,n in enumerate('January February March April May June July August September October November December'.split(),1)}
MONTHS.update({n[:3]:i for n,i in list(MONTHS.items())})
ZONES={'UTC':dt.timezone.utc,'GMT':dt.timezone.utc,'BST':dt.timezone(dt.timedelta(hours=1)),
       'JST':dt.timezone(dt.timedelta(hours=9)),'SGT':dt.timezone(dt.timedelta(hours=8)),'GST':dt.timezone(dt.timedelta(hours=4))}
DATE=r'(?:(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s*,?\s*(\d{4})|([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})|(\d{4})-(\d{2})-(\d{2}))'
TIME=r'(?<!\d)(\d{1,2})(?::(\d{2}))\s*(am|pm)?\b|(?<!\d)(\d{1,2})\s*(am|pm)\b'

def deadline(text,received_at,message_id,thread_id):
    text=visible(text)
    numbers={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'fourteen':14}
    text=re.sub(r'\n(?=\s*(?:\d|'+ '|'.join(numbers) +r')\b)',' ',text,flags=re.I)
    text=re.sub(r'(?i)(?<=\s)('+ '|'.join(numbers) +r')(?=\s+(?:hours?|days?))',lambda m:str(numbers[m.group().lower()]),text)
    base={'source_message_id':message_id,'source_thread_id':thread_id,'kind':None,'value':None,'timezone':None,'needs_review':False}
    clauses=[]
    # Only action timing, not employer-response estimates or generic FAQs.
    for sentence in re.split(r'(?<=[.!?])\s+|\n',text):
        if re.search(r'(?i)deadline|expires?\b|complete.{0,70}(?:by|before|within|no later|next)|(?:assessment|interview|test|link).{0,90}(?:active for|within|next)|(?:interview).{0,50}(?:scheduled|on\s+\d)|\b(?:by|before|no later than)\s+\d',sentence):
            if re.search(r'(?i)we (?:aim|will|try).{0,50}(?:respond|contact)|hear(?:d)? from us|assessment outcomes|valid for.{0,20}months',sentence):continue
            clauses.append(sentence)
    candidates=[]
    reasons=[]
    for clause in clauses:
        relative=list(re.finditer(r'(?i)(?:within|(?:within )?the next|active for)\s+(\d+)\s*(business\s+|working\s+)?(hours?|days?)',clause))
        for m in relative:
            if m.group(2):reasons.append('business-day deadline needs a holiday/calendar policy');continue
            if re.search(r'(?i)of receiving (?:the |an? )?(?:invite|invitation|assessment link)|after (?:the |an? )?(?:invite|invitation)',clause) and not re.search(r'(?i)you are invited|invitation to|here is your',text.split('\n',1)[0]):
                reasons.append('relative period starts at a separate invitation, not this email');continue
            try:
                received=dt.datetime.fromisoformat(received_at.replace('Z','+00:00'))
                if received.tzinfo is None:raise ValueError()
                delta=dt.timedelta(hours=int(m.group(1))) if m.group(3).lower().startswith('hour') else dt.timedelta(days=int(m.group(1)))
                candidates.append({**base,'kind':'DERIVED','value':(received+delta).isoformat(),'date_only':False,'timezone':str(received.tzinfo),'reason':f'email received timestamp plus {m.group(1)} calendar {m.group(3)}','evidence_type':'received_email_relative'})
            except (ValueError,AttributeError):reasons.append('relative deadline lacks a reliable received timestamp')
        dates=list(re.finditer(DATE,clause,re.I))
        for match in dates:
            a,b,c,d,e,f,g,h,i=match.groups()
            try:
                date=dt.date(int(c or f or g),MONTHS[(b or d).lower()] if b or d else int(h),int(a or e or i))
                # Ignore year digits as times by removing the complete date first.
                remainder=clause[:match.start()]+' '+clause[match.end():]
                times=list(re.finditer(TIME,remainder,re.I))
                if len(times)>1:reasons.append('multiple times require owner review');continue
                if not times:
                    # Explicit date-only deadline is reliable, interview time is not.
                    if 'interview' in clause.lower() and not re.search(r'(?i)deadline|complete|expires',clause):reasons.append('interview date lacks a reliable time');continue
                    candidates.append({**base,'kind':'EXACT','value':date.isoformat(),'date_only':True,'reason':'explicit date-only deadline'})
                    continue
                tm=times[0];hour=int(tm.group(1) or tm.group(4));minute=int(tm.group(2) or 0);ampm=(tm.group(3) or tm.group(5) or '').lower()
                if ampm:
                    if not 1<=hour<=12:raise ValueError()
                    hour=hour%12+(12 if ampm=='pm' else 0)
                zone_match=re.search(r'\b(UTC|GMT|BST|JST|SGT|GST)\b',remainder,re.I)
                if not zone_match:reasons.append('deadline time has no unambiguous timezone');continue
                zone=zone_match.group().upper();stamp=dt.datetime.combine(date,dt.time(hour,minute),ZONES[zone])
                candidates.append({**base,'kind':'EXACT','value':stamp.isoformat(),'date_only':False,'timezone':zone,'reason':'explicit date, time and timezone','timing_kind':'INTERVIEW' if 'interview' in clause.lower() and not re.search(r'(?i)deadline|complete|expires',clause) else 'DEADLINE'})
            except (ValueError,KeyError):reasons.append('invalid or unsupported deadline date')
        if not dates and not relative:
            if re.search(r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:'+ '|'.join(MONTHS) +r')\b',clause,re.I):reasons.append('deadline date has no explicit year')
            elif re.search(r'(?i)\b(?:by|before|no later than|deadline|expires|active for)\b',clause):reasons.append('deadline wording contains no supported unambiguous date')
    if reasons:return {**base,'needs_review':True,'reason':'; '.join(dict.fromkeys(reasons))}
    if len({x['value'] for x in candidates})>1:return {**base,'needs_review':True,'reason':'multiple conflicting deadlines; owner review required'}
    if candidates:return candidates[0]
    if re.search(r'(?i)complete (?:as soon as|by next)|complete within|deadline|expires',text):return {**base,'needs_review':True,'reason':'deadline wording contains no supported unambiguous date'}
    return base
