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

def build(spec_path):
    import build_cover,cv_workflow,pymupdf
    sys.path.insert(0,str(HERE/'cv-template-prototype'))
    from cv_writing_policy import check
    p=pathlib.Path(spec_path);s=json.loads(p.read_text());text='\n'.join(s['paragraphs'])
    if len(s['paragraphs'])!=5 or any(not t.strip() for t in s['paragraphs']):raise ValueError('five complete paragraphs required')
    if len(text)>2855:raise ValueError('cover letter exceeds 2855-character capacity')
    if check(text):raise ValueError('cover wording/encoding verification failed')
    gate=cv_workflow.fact_gate(cv_workflow.load_config(),text,label='cover',scratch=p.parent)
    if not gate.get('available') or gate.get('exit_code')!=0 or gate.get('verdict')=='block':raise ValueError('cover letter fact gate did not pass')
    before={str(f):digest(f) for f in dependencies()}
    if build_cover.build(s)!=0:raise ValueError('cover letter formatting verification failed')
    out=pathlib.Path(s['out'])
    with pymupdf.open(out) as pdf:
        extracted=' '.join(pdf[0].get_text().split())
        if pdf.page_count!=1 or any(' '.join(t.split()) not in extracted for t in [s['heading'],s['salutation']]+s['paragraphs']):raise ValueError('cover letter text extraction mismatch')
    if before!={str(f):digest(f) for f in dependencies()}:raise ValueError('immutable cover dependency changed')
    out.with_suffix('.verification.json').write_text(json.dumps({'status':'PASS','sha256':digest(out),'dependencies':before}))

def cover_tool(args,**kwargs):
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
    spec={'heading':'Application for '+str(args['role']),'salutation':'Dear '+str(args['company'])+' Recruitment Team,','paragraphs':args['paragraphs'],'out':str(out),'qa':str(workspace/'preview.png')}
    path=workspace/'content.json';path.write_text(json.dumps(spec,ensure_ascii=False),encoding='utf-8')
    try:
        remaining=min(45,state['deadline']-time.monotonic())
        if remaining<=0:raise ValueError('application deadline reached')
        run=subprocess.run([sys.executable,str(HERE/'hermes_cover_tool.py'),str(path)],capture_output=True,text=True,timeout=remaining)
        if run.returncode or not verified(out):return json.dumps({'status':'FAIL','reason':'cover content/fact/format verification failed','instruction':'No unverified PDF may be attached. No shell repair.'})
        try: exported=export_verified(out,str(args['company']),str(args.get('short_role') or args['role']))
        except (OSError,ValueError):return json.dumps({'status':'FAIL','reason':'verified cover export failed; check output folder access'})
        state['cover_succeeded']=True
        return json.dumps({'status':'PASS','verified_pdf':str(exported),'compiler_pdf':str(out),'verification_report':str(exported.with_suffix('.verification.json'))})
    except subprocess.TimeoutExpired:return json.dumps({'status':'FAIL','reason':'cover generation elapsed-time limit'})
if __name__=='__main__':
    try:build(sys.argv[1])
    except Exception:print('Cover verification failed');raise SystemExit(1)
