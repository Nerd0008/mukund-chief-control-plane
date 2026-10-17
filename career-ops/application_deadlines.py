"""Evidence-based application deadlines from JD text; no network, model calls or writes."""
import datetime as dt
import re

MONTHS={name:i for i,name in enumerate(('january','february','march','april','may','june','july','august','september','october','november','december'),1)}
MONTHS.update({name[:3]:i for name,i in list(MONTHS.items())})
DATE=r'(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2}-\d{1,2}-\d{4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})'
ANCHOR=r'(?:applications?\s+(?:close|must\s+be\s+(?:received|submitted))|closing\s+date|application\s+deadline|deadline|apply\s+(?:by|before|no\s+later\s+than)|submit\s+your\s+application\s+by)'
FIXED=re.compile(r'\b'+ANCHOR+r'\s*(?:(?:is|on|by|before|:|-)\s*)*(?:(?:\d{1,2}:\d{2}\s*(?:am|pm)?\s*(?:BST|GMT|UTC)?\s+on\s+))?('+DATE+r')\b',re.I)
ROLLING=re.compile(r'\b(?:applications?[^.!?\n]{0,65}(?:rolling\s+basis|as\s+(?:they\s+are\s+)?received|as\s+we\s+receive\s+them)|(?:rolling|ongoing)\s+(?:applications?|recruitment|deadline)|(?:role|vacancy|applications?)[^.!?\n]{0,35}(?:open\s+until\s+filled|may\s+close\s+early)|(?:reserve\s+the\s+right\s+to\s+close)[^.!?\n]{0,35}(?:early|earlier))\b',re.I)

def parse_date(text):
    text=re.sub(r'(\d)(st|nd|rd|th)\b',r'\1',text.strip(),flags=re.I).replace(',','')
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',text):return dt.date.fromisoformat(text)
        m=re.fullmatch(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',text)
        if m:
            day,month,year=map(int,m.groups())
            if day<=12 and month<=12 and day!=month:return None
            return dt.date(year,month,day)
        m=re.fullmatch(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})',text)
        if m:return dt.date(int(m[3]),MONTHS[m[2].lower()],int(m[1]))
        m=re.fullmatch(r'([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})',text)
        if m:return dt.date(int(m[3]),MONTHS[m[1].lower()],int(m[2]))
    except (ValueError,KeyError):pass
    return None

def extract_application_deadline(text,source_url=None):
    text=str(text or '');dates={};ambiguous=False
    for match in FIXED.finditer(text):
        prefix=text[max(0,match.start()-25):match.start()].lower()
        if re.search(r'(?:assessment|interview|test|exam)\s*$',prefix):continue
        date=parse_date(match[1])
        if date:dates[date.isoformat()]=match.group(0)
        else:ambiguous=True
    rolling=[]
    for match in ROLLING.finditer(text):
        if re.search(r'\b(?:not|never)\b',match.group(0),re.I):continue
        rolling.append(match.group(0))
    if len(dates)==1 and not ambiguous:
        date=next(iter(dates));kind='EXACT';evidence=dates[date];reason='explicit application closing date'
    elif len(dates)>1 or ambiguous:
        date=None;kind='UNKNOWN';evidence='';reason='ambiguous or conflicting application dates'
    elif rolling:
        date=None;kind='ROLLING';evidence=rolling[0];reason='explicit rolling or early-close wording'
    else:
        date=None;kind='UNKNOWN';evidence='';reason='no reliable application deadline in available JD text'
    return {'type':kind,'date':date,'rolling':bool(rolling),'evidence':evidence,'source':'JD',
            'source_url':source_url,'reason':reason}

def deadline_from_value(value):
    if isinstance(value,dt.datetime):value=value.date()
    if isinstance(value,dt.date):return {'type':'EXACT','date':value.isoformat()}
    text=str(value or '').strip()
    if text.upper()=='ROLLING':return {'type':'ROLLING','date':None}
    date=parse_date(text)
    return {'type':'EXACT','date':date.isoformat()} if date else {'type':'UNKNOWN','date':None}

def deadline_label(info):
    return info.get('date') if info.get('type')=='EXACT' else ('ROLLING' if info.get('type')=='ROLLING' else 'UNKNOWN')

def deadline_priority(record,today=None):
    today=today or dt.date.today();info=record.get('deadline_info') or deadline_from_value(record.get('deadline'))
    date=parse_date(info.get('date') or '')
    if date:
        days=(date-today).days
        if days<0:return (4,date)
        if days<=7:return (0,date)
    if info.get('type')=='ROLLING' or (info.get('type')=='EXACT' and info.get('rolling')):return (1,dt.date.max)
    return (2,date) if date else (3,dt.date.max)
