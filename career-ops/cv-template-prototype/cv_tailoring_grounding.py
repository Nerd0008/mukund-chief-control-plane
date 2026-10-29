"""Evidence and independent review receipts for role-specific CV wording.

No renderer changes. A generated paraphrase is accepted only with a locally
authenticated receipt produced after the independent review and canonical gate.
"""
import hashlib,hmac,json,os,pathlib,re,secrets,uuid

ROOT=pathlib.Path(os.environ.get('CV_TAILORING_REVIEW_ROOT',str(pathlib.Path(os.environ.get('LOCALAPPDATA',str(pathlib.Path.home())))/'hermes/runtime/career-ops/cv-tailoring-reviews')))

def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def norm(value):return ' '.join(str(value).split()).casefold()

def facts(layout):
    return {s['id']:s['text'].removeprefix('\u2022 ') for s in layout['slots'] if s['section']!='Header'}

def body(item):return {k:item[k] for k in ('text','sources','why') if k in item}

def parse_plan(plan,layout,jd):
    import cv_template as cv
    cv.register(layout)
    slots={s['id']:s for s in layout['slots'] if s['variable']}
    known=facts(layout)
    if not isinstance(plan,dict) or not isinstance(plan.get('content'),dict) or set(plan['content'])!=set(slots):
        raise ValueError('tailoring must provide every editable slot')
    requirements=plan.get('requirements')
    if not isinstance(requirements,list) or len(requirements)<3:raise ValueError('JD requirement mapping missing')
    ids=set()
    for row in requirements:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or row['id'] in ids:raise ValueError('invalid requirement identity')
        ids.add(row['id'])
        quote=row.get('quote','')
        if len(quote)<12 or norm(quote) not in norm(jd):raise ValueError('requirement quote not present in JD')
        if not isinstance(row.get('covered_by'),list) or any(k not in slots for k in row['covered_by']):raise ValueError('invalid requirement coverage')
    content={}
    for key,value in plan['content'].items():
        if not isinstance(value,dict) or not isinstance(value.get('text'),str) or not value['text'].strip():raise ValueError('blank tailored content')
        sources=value.get('sources')
        if not isinstance(sources,list) or not sources or any(s not in known for s in sources):raise ValueError('unknown candidate evidence')
        if not isinstance(value.get('why'),str) or len(value['why'])<10:raise ValueError('tailoring rationale missing')
        value=dict(value)
        candidates=[value['text'],*(value.get('alternatives') or [])]
        if len(candidates)>4 or any(not isinstance(t,str) for t in candidates):raise ValueError('invalid fit alternatives')
        for candidate in candidates:
            if slots[key]['bullet']:
                candidate=candidate.lstrip().removeprefix('\u2022').lstrip()
            paragraph=cv.paragraph(slots[key],candidate);paragraph.wrap(slots[key]['width'],1000)
            if len(paragraph.blPara.lines)==slots[key]['max_lines'] and all(getattr(line,'extraSpace',line[0] if isinstance(line,tuple) else 0)>=-.3 for line in paragraph.blPara.lines):
                value['text']=candidate;break
        evidence_text=' '.join(known[s] for s in sources)
        for number in re.findall(r'(?<![A-Za-z])\d+(?:\.\d+)?(?:%|\+)?',value['text']):
            if number not in evidence_text:raise ValueError('numeric claim absent from cited evidence')
        content[key]=body(value)
    return content,requirements

def review_result(review,content,requirements,layout):
    if not isinstance(review,dict) or review.get('verdict')!='pass':raise ValueError('independent factual/tailoring review did not pass')
    decisions=review.get('slots',{})
    if set(decisions)!=set(content):raise ValueError('review missing slot verdicts')
    source=facts(layout)
    for key,item in content.items():
        row=decisions[key]
        if row.get('supported') is not True or not isinstance(row.get('reason'),str) or len(row['reason'])<10:raise ValueError('unsupported tailored claim')
        evidence=row.get('evidence')
        if not isinstance(evidence,list) or not evidence:raise ValueError('review evidence missing')
        for e in evidence:
            quote=e.get('quote','');sid=e.get('source')
            if sid not in item['sources'] or len(quote)<8 or norm(quote) not in norm(source[sid]):raise ValueError('review quotation not in cited owner evidence')
    slots={s['id']:s for s in layout['slots']}
    changed_sections={slots[k]['section'] for k,v in content.items() if norm(v['text'])!=norm(slots[k]['text'].removeprefix('\u2022 '))}
    if len(changed_sections)<2 or not changed_sections.intersection({'Professional Summary','Technical Skills'}):
        raise ValueError('generic default or cosmetic-only project changes are not tailoring')
    tailoring=review.get('tailoring',{})
    mapped={r['id'] for r in requirements if r['covered_by']}
    if tailoring.get('substantial') is not True or len(str(tailoring.get('reason','')))<20 or len(mapped)<3:
        raise ValueError('generic or insufficiently tailored CV')
    if set(tailoring.get('requirement_ids',[]))!=mapped:raise ValueError('review did not assess mapped JD requirements')

def _key(create=False):
    path=ROOT/'authority.key'
    if create and not path.exists():
        ROOT.mkdir(parents=True,exist_ok=True)
        try:
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as f:f.write(secrets.token_bytes(32))
        except FileExistsError:pass
    data=path.read_bytes()
    if len(data)!=32:raise ValueError('invalid review authority')
    return data

def issue(content,requirements,layout,jd,review,provider,gate):
    review_result(review,content,requirements,layout)
    if not gate.get('available') or gate.get('exit_code')!=0 or gate.get('verdict')=='block':raise ValueError('canonical CV fact gate did not pass')
    payload={'version':1,'master_sha256':layout['master_sha256'],'facts_sha256':digest(facts(layout)),
             'jd_sha256':hashlib.sha256(jd.encode()).hexdigest(),'requirements':requirements,
             'slots':{k:digest(body(v)) for k,v in content.items()},'review':review,'provider':provider,
             'canonical_fact_gate':'PASS'}
    key=_key(True);identifier=digest(payload)
    envelope={'payload':payload,'mac':hmac.new(key,canonical(payload),hashlib.sha256).hexdigest()}
    target=ROOT/(identifier+'.json');temp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
    try:temp.write_text(json.dumps(envelope,ensure_ascii=True),encoding='utf-8');os.replace(temp,target)
    finally:temp.unlink(missing_ok=True)
    return {k:dict(v,review_receipt=identifier) for k,v in content.items()}

def valid_item(key,item,layout):
    identifier=item.get('review_receipt','')
    if not re.fullmatch('[a-f0-9]{64}',str(identifier)):return False
    try:
        envelope=json.loads((ROOT/(identifier+'.json')).read_text(encoding='utf-8'));payload=envelope['payload']
        if not hmac.compare_digest(envelope['mac'],hmac.new(_key(),canonical(payload),hashlib.sha256).hexdigest()):return False
        return (payload['master_sha256']==layout['master_sha256'] and payload['facts_sha256']==digest(facts(layout))
                and payload['slots'].get(key)==digest(body(item)) and payload['canonical_fact_gate']=='PASS')
    except (OSError,ValueError,KeyError,TypeError):return False


def matches_jd(content,jd):
    expected=hashlib.sha256(jd.encode()).hexdigest()
    if not content:return False
    try:
        for item in content.values():
            reference=item.get('review_receipt','')
            if not re.fullmatch('[a-f0-9]{64}',reference):return False
            envelope=json.loads((ROOT/(reference+'.json')).read_text(encoding='utf-8'))
            if not hmac.compare_digest(envelope['mac'],hmac.new(_key(),canonical(envelope['payload']),hashlib.sha256).hexdigest()):return False
            if envelope['payload']['jd_sha256']!=expected:return False
        return True
    except (OSError,KeyError,ValueError,TypeError):return False
