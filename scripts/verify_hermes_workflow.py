"""Repeatable offline acceptance check. Never claims live model acceptance."""
import argparse,json,pathlib,subprocess,sys,tempfile,os,xml.etree.ElementTree as ET

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir',type=pathlib.Path)
    parser.add_argument('--latest',action='store_true',help='Inspect the latest real request instead of running offline tests')
    parser.add_argument('--session-id',help='Optionally restrict evidence to one native session')
    args=parser.parse_args()
    if args.latest:
        home=pathlib.Path(os.environ.get('HERMES_HOME',str(pathlib.Path.home()/'AppData/Local/hermes')))
        result=latest_report(home,args.session_id)
        print(json.dumps(result,indent=2))
        return 1 if result['status']=='BLOCKED' else 0
    root=pathlib.Path(__file__).resolve().parents[1]
    out=args.report_dir or pathlib.Path(tempfile.mkdtemp(prefix='hermes-verification-'))
    out.mkdir(parents=True,exist_ok=True)
    tests=['career-ops/tests/test_owner_context_contract.py',
           'exec-brain/tests/test_controller_admission_contract.py',
           'exec-brain/tests/test_router_selection_cache.py',
           'exec-brain/tests/test_gateway_lifecycle_contract.py',
           'exec-brain/tests/test_workflow_stage_contract.py',
           'exec-brain/tests/test_chief_context.py']
    xml=out/'results.xml'
    command=[sys.executable,'-m','pytest',*tests,'-q','-p','no:cacheprovider',
             '--basetemp',str(out/'tmp'),'--junitxml',str(xml)]
    run=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
    (out/'pytest.txt').write_text(run.stdout+run.stderr,encoding='utf-8')
    result={'status':'PASS' if run.returncode==0 else 'FAIL','mode':'offline-real-boundaries',
            'live_model_acceptance':False,'production_deployment_verified':False,
            'provider_calls':0,'report':str(out),'cases':[]}
    if xml.exists():
        for case in ET.parse(xml).iter('testcase'):
            result['cases'].append({'test':case.get('name'),
                'passed':case.find('failure') is None and case.find('error') is None and case.find('skipped') is None})
    result['passed']=sum(c['passed'] for c in result['cases'])
    (out/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    return run.returncode

"""Read code-written evidence for the latest lead request; never grade its answer."""
import hashlib,json,pathlib,sqlite3,time

def latest_report(home,session_id=None):
    home=pathlib.Path(home)
    path=home/'runtime/owner-context/requirements.sqlite3'
    if not path.is_file():return {'status':'NO_EVIDENCE','answer_correctness_verified':False}
    con=sqlite3.connect('file:'+path.as_posix()+'?mode=ro',uri=True)
    try:
        if session_id:
            key=hashlib.sha256(session_id.encode()).hexdigest()
            row=con.execute('SELECT status,updated,detail FROM context_events WHERE session_key=? ORDER BY updated DESC LIMIT 1',(key,)).fetchone()
        else:row=con.execute('SELECT status,updated,detail FROM context_events ORDER BY updated DESC LIMIT 1').fetchone()
    except sqlite3.Error:return {'status':'NO_EVIDENCE','answer_correctness_verified':False}
    finally:con.close()
    if not row:return {'status':'NO_EVIDENCE','answer_correctness_verified':False}
    detail=json.loads(row[2]);operation=detail.get('operation_id');workers=[]
    receipt_root=home/'runtime/router-brain/workflows'
    if operation and receipt_root.is_dir():
        for file in receipt_root.glob('*.json'):
            if file.stat().st_mtime<row[1]-180:continue
            try:record=json.loads(file.read_text(encoding='utf-8'))
            except (OSError,ValueError):continue
            if record.get('operation_id')==operation and record.get('stage')!='context':
                workers.append({k:record[k] for k in ('workflow','stage','status','error','selected_provider','selected_model') if k in record})
    blocked=row[0]=='CONTEXT_FAILED' or any(w.get('status') in ('FAILED','BLOCKED','STAGE_FAILED') for w in workers)
    completed=any(w.get('status')=='COMPLETED' for w in workers)
    age=round(max(0,time.time()-row[1]),1)
    status='BLOCKED' if blocked else 'PATH_VERIFIED_ANSWER_NOT_GRADED' if row[0]=='CONTEXT_VERIFIED' and completed else 'NOT_YET_PROVEN'
    if age>1800:status='STALE_EVIDENCE'
    return {'status':status,'context_status':row[0],'age_seconds':age,
            'coverage_complete':detail.get('coverage_complete',False),
            'sources':[{k:s[k] for k in ('file','sha256','source_bytes','included_bytes','complete') if k in s} for s in detail.get('sources',[])],
            'worker_attempts':workers,'answer_correctness_verified':False}

if __name__=='__main__':raise SystemExit(main())
