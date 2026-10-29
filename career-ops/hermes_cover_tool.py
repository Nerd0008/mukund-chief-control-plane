"""Bounded native cover-letter render through the established format/fact gate."""
import json,pathlib,subprocess,sys,uuid,hashlib,os
HERE=pathlib.Path(__file__).resolve().parent
EXPORT_ROOT=pathlib.Path.home()/'Downloads/codex/_cover'
ROOT=pathlib.Path(os.environ['LOCALAPPDATA'])/'hermes/runtime/career-ops/cover-compiled'
def digest(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def dependencies():return [HERE/'build_cover.py',HERE/'hermes_cover_tool.py',HERE/'cv_tailor.py',HERE/'cv_golden.py',pathlib.Path('C:/Windows/Fonts/times.ttf'),pathlib.Path('C:/Windows/Fonts/timesbd.ttf')]
def verified(path):
    p=pathlib.Path(path)
    if p.resolve().is_relative_to(EXPORT_ROOT.resolve()):
        try:
            receipt=json.loads(p.with_suffix('.verification.json').read_text())
            source=pathlib.Path(receipt['source'])
            return source.resolve().is_relative_to(ROOT.resolve()) and verified(source) and receipt['sha256']==digest(p)==digest(source)
        except Exception:return False
    if not p.resolve().is_relative_to(ROOT.resolve()):return False
    try:
        report=json.loads(p.with_suffix('.verification.json').read_text())
        return report['status']=='PASS' and report['sha256']==digest(p) and report['dependencies']=={str(f):digest(f) for f in dependencies()}
    except Exception:return False

def export_verified(source,company,role):
    import re,shutil
    source=pathlib.Path(source)
    if not verified(source):raise ValueError('unverified cover cannot be exported')
    company=re.sub(r'\b(?:limited|ltd|plc|incorporated|inc|llc|corp|corporation)\b\.?','',company,flags=re.I)
    def safe(value,limit):
        words=re.findall(r'[A-Za-z0-9]+',value)
        if not words:raise ValueError('company and role required')
        return '_'.join(words[:limit])
    target=EXPORT_ROOT/('Mukund_'+safe(company,4)+'_'+safe(role,2)+'_Cover_Letter.pdf')
    EXPORT_ROOT.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        shutil.copyfile(source,temporary)
        if digest(temporary)!=digest(source):raise ValueError('cover export hash mismatch')
        os.replace(temporary,target)
    finally:
        if temporary.exists():temporary.unlink()
    target.with_suffix('.verification.json').write_text(json.dumps({'source':str(source.resolve()),'sha256':digest(target)}),encoding='utf-8')
    if not verified(target):raise ValueError('exported cover verification failed')
    return target

def cover_fact_result(gate,text):
    """Exclude only tool mentions wholly inside explicit absence-of-experience clauses."""
    import re
    gate=dict(gate)
    prefix=re.compile(r"(?im)(?:^|(?<=[.!?;\n]))\s*I\s+(?:(?:do not|don't)\s+(?:yet\s+)?have\s+(?:professional\s+)?experience\s+(?:with|supporting|using|of|in)|have\s+no\s+(?:professional\s+)?experience\s+(?:with|supporting|using|of|in)|(?:have not|haven't)\s+(?:yet\s+)?(?:worked with|used|administered|managed|supported))\b")
    boundary=re.compile(r"[.!?;\n]|\b(?:but|however|although|whereas|nevertheless|yet)\b|\b(?:and\s+)?I\s+(?:have|use|used|manage|managed|administer|support|am|led|lead|built|work|worked)\b|\band\s+(?:use|used|manage|managed|administer|support|have|am|led|lead|built|work|worked)\b",re.I)
    prefixes=list(prefix.finditer(text))
    def wholly_negative(fact):
        if fact.get('kind')!='tool':return False
        value=str(fact.get('value','')).strip()
        if not value:return False
        pattern=re.escape(value).replace(r'\ ',r'\s+')
        mentions=list(re.finditer(r'(?<!\w)'+pattern+r'(?!\w)',text,re.I))
        if not mentions:return False
        for mention in mentions:
            scopes=[m for m in prefixes if m.end()<=mention.start()]
            if not scopes or boundary.search(text[scopes[-1].end():mention.start()]):return False
        return True
    if gate.get('available') and gate.get('exit_code')==1:
        blocked=gate.get('unsupportedFacts',[]);remaining=[f for f in blocked if not wholly_negative(f)]
        if len(remaining)!=len(blocked):
            gate['unsupportedFacts']=remaining
            gate['negation_correction']='Explicit lack of tool experience is not a positive skill claim'
            if not remaining and not gate.get('invented') and not gate.get('forbidden'):
                gate.update(verdict='pass',exit_code=0)
    return gate


def fact_failure_details(gate):
    return {'stage':'fact_verification','reason':'cover letter fact gate did not pass',
            'issues':[{ 'category':key,'kind':str(item.get('kind',''))[:60],'value':str(item.get('value',''))[:120]}
                      for key in ('unsupportedFacts','invented','forbidden') for item in gate.get(key,[]) if isinstance(item,dict)],
            'gate_available':bool(gate.get('available'))}

def build(spec_path):
    import build_cover,cv_workflow,pymupdf
    sys.path.insert(0,str(HERE/'cv-template-prototype'))
    from cv_writing_policy import check
    p=pathlib.Path(spec_path);s=json.loads(p.read_text(encoding='utf-8'));text='\n'.join(s['paragraphs'])
    if len(s['paragraphs'])!=5 or any(not t.strip() for t in s['paragraphs']):raise ValueError('five complete paragraphs required')
    if len(text)>2855:raise ValueError('cover letter exceeds 2855-character capacity')
    if check(text):raise ValueError('cover wording/encoding verification failed')
    gate=cv_workflow.fact_gate(cv_workflow.load_config(),text,label='cover',scratch=p.parent)
    gate=cover_fact_result(gate,text)
    if not gate.get('available') or gate.get('exit_code')!=0 or gate.get('verdict')=='block':
        p.with_name('failure.json').write_text(json.dumps(fact_failure_details(gate)),encoding='utf-8')
        raise ValueError('cover letter fact gate did not pass')
    before={str(f):digest(f) for f in dependencies()}
    if build_cover.build(s)!=0:raise ValueError('cover letter formatting verification failed')
    out=pathlib.Path(s['out'])
    with pymupdf.open(out) as pdf:
        extracted=' '.join(pdf[0].get_text().split())
        if pdf.page_count!=1 or any(' '.join(t.split()) not in extracted for t in [s['heading'],s['salutation']]+s['paragraphs']):raise ValueError('cover letter text extraction mismatch')
    if before!={str(f):digest(f) for f in dependencies()}:raise ValueError('immutable cover dependency changed')
    out.with_suffix('.verification.json').write_text(json.dumps({'status':'PASS','sha256':digest(out),'dependencies':before}))

def _cover_tool(args,**kwargs):
    from hermes_cv_compiler_guard import JOB,activate_job
    import time
    state=JOB.get()
    if state is None:return json.dumps({'status':'FAIL','reason':'native application turn required'})
    activate_job(state)
    if state['deadline'] <= time.monotonic():return json.dumps({'status':'FAIL','reason':'application deadline reached'})
    if state.get('cover_succeeded'):return json.dumps({'status':'FAIL','reason':'verified cover already produced'})
    fingerprint=hashlib.sha256(json.dumps(args,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
    attempts=state.setdefault('cover_content_attempts',[])
    if fingerprint in attempts:return json.dumps({'status':'FAIL','reason':'unchanged rejected cover; correct the content before retrying'})
    if len(attempts)>=2:return json.dumps({'status':'FAIL','reason':'cover correction budget exhausted (2 attempts)'})
    attempts.append(fingerprint)
    workspace=ROOT/uuid.uuid4().hex;workspace.mkdir(parents=True)
    out=workspace/'Mukund_Cover_Letter.pdf'
    paragraphs=args['paragraphs']
    (workspace/'content-draft-input.json').write_text(json.dumps({'paragraphs':paragraphs},ensure_ascii=False),encoding='utf-8')
    from workflow_control import CONTENT_WORKER
    worker=state.get('content_worker') or CONTENT_WORKER.get() or 'auto'
    if worker=='codex':
        if state.get('cover_routing_failed'):return json.dumps({'status':'FAIL','reason':'cover_worker_already_failed','instruction':'Stop this request; no automatic retry.'})
        try:
            from cover_content_adapter import plan
            paragraphs,receipt=plan(paragraphs,args['company'],args['role'],
                timeout=min(60,state['deadline']-time.monotonic()),worker='codex')
            (workspace/'routing.json').write_text(json.dumps(receipt),encoding='utf-8')
        except Exception as exc:
            from workflow_routing import failure_code
            state['cover_routing_failed']=True
            return json.dumps({'status':'FAIL','stage':'content_generation','reason':failure_code(exc),'instruction':'Stop this request; no PDF or automatic retry.'})
    spec={'heading':'Application for '+str(args['role']),'salutation':'Dear '+str(args['company'])+' Recruitment Team,','paragraphs':paragraphs,'out':str(out),'qa':str(workspace/'preview.png')}
    path=workspace/'content.json';path.write_text(json.dumps(spec,ensure_ascii=False),encoding='utf-8')
    try:
        remaining=min(45,state['deadline']-time.monotonic())
        if remaining<=0:raise ValueError('application deadline reached')
        run=subprocess.run([sys.executable,str(HERE/'hermes_cover_tool.py'),str(path)],capture_output=True,text=True,timeout=remaining)
        if run.returncode or not verified(out):
            detail_path=workspace/'failure.json'
            details=json.loads(detail_path.read_text(encoding='utf-8')) if detail_path.exists() else {'reason':'cover content/format verification failed'}
            return json.dumps({'status':'FAIL',**details,'instruction':'Correct only the reported issues within the existing two-attempt budget. No unverified PDF, shell repair, or Codex counter reset. A new owner-requested build has a fresh request budget.'})
        try: exported=export_verified(out,str(args['company']),str(args.get('short_role') or args['role']))
        except (OSError,ValueError):return json.dumps({'status':'FAIL','reason':'verified cover export failed; check output folder access'})
        state['cover_succeeded']=True
        return json.dumps({'status':'PASS','verified_pdf':str(exported),'compiler_pdf':str(out),'verification_report':str(exported.with_suffix('.verification.json'))})
    except subprocess.TimeoutExpired:return json.dumps({'status':'FAIL','reason':'cover generation elapsed-time limit'})
def cover_tool(args,**kwargs):
    from hermes_cv_compiler_guard import JOB
    import application_package_state as package
    state=JOB.get()
    if state and state.get('resuming') and not state.get('cover_called') and state.get('cover_args')==args and 'cover' in package.accepted(state):
        state['cover_called']=True
        return json.dumps(state['results']['cover'])
    response=_cover_tool(args,**kwargs)
    if state:
        state['cover_called']=True
        package.record(state,'cover',args,json.loads(response))
    return response


if __name__=='__main__':
    try:build(sys.argv[1])
    except Exception:print('Cover verification failed');raise SystemExit(1)
