"""Bounded offline compiler harness; intentionally not a Hermes tool.

The future content adapter must be a picklable function taking one request.
It gets no filesystem/tool access from this interface. No provider is wired.
"""
import ctypes, hashlib, json, multiprocessing as mp, os, pathlib, time
from contextlib import contextmanager
import cv_template as cv

def dependency_paths():
    layout=cv.load_layout()
    paths=[cv.HERE/'layout.json',cv.HERE/'cv_template.py',pathlib.Path(__file__),pathlib.Path(layout['master_source'])]
    paths += [pathlib.Path('C:/Windows/Fonts')/f for f in layout['fonts'].values()]
    paths += [cv.HERE/name for name in ['cv_writing_policy.py','fact_bank.json','cv_content_adapter.py','approval.json','output/original-content-reproduction.pdf'] if (cv.HERE/name).exists()]
    return paths

@contextmanager
def protect(paths):
    handles=[]; before={str(p):cv.digest(p) for p in paths}
    try:
        if os.name=='nt':
            k=ctypes.WinDLL('kernel32',use_last_error=True)
            k.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
            k.CreateFileW.restype=ctypes.c_void_p
            k.CloseHandle.argtypes=[ctypes.c_void_p]
            for p in paths:
                h=k.CreateFileW(str(pathlib.Path(p).resolve()),0x80000000,1,None,3,0,None)
                if h==ctypes.c_void_p(-1).value: raise OSError('cannot lock immutable dependency')
                handles.append(h)
        yield before
        if any(cv.digest(p)!=before[str(p)] for p in paths): raise ValueError('immutable dependency changed')
    finally:
        if os.name=='nt':
            for h in handles: k.CloseHandle(h)

def save(path,obj):
    path=pathlib.Path(path); temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8'); temp.replace(path)

def worker(generator,request,workspace):
    w=pathlib.Path(workspace); stage='content_generation'; started=time.monotonic()
    content={}; calls=0; renders=0; timings={}; model_calls=0
    try:
        layout=cv.load_layout()
        save(w/'analysis.json',request)
        t=time.monotonic(); calls+=1; content=generator(request)
        timings['content_generation_seconds']=time.monotonic()-t
        provider_metadata=getattr(generator,'last_metadata',None)
        if provider_metadata:model_calls+=provider_metadata.get('model_calls',0)
        save(w/'content-draft.json',content)
        stage='fit_validation'; save(w/'stage.json',{'stage':stage})
        failures=cv.fit(layout,content)
        if failures:
            if any(f['reason']!='content capacity exceeded' for f in failures): raise ValueError(str(failures))
            stage='targeted_shortening'; save(w/'stage.json',{'stage':stage})
            affected=sorted({f['slot'] for f in failures}); calls+=1
            t=time.monotonic(); revised=generator(dict(request,mode='shorten',affected=affected,content=content))
            provider_metadata=getattr(generator,'last_metadata',None)
            if provider_metadata:model_calls+=provider_metadata.get('model_calls',0)
            timings['shortening_seconds']=time.monotonic()-t
            if set(revised)-set(affected): raise ValueError('shortening changed unaffected section')
            content.update(revised); save(w/'content-draft.json',content)
            if cv.fit(layout,content): raise ValueError('content still does not fit after one shortening pass')
        stage='render'; save(w/'stage.json',{'stage':stage})
        t=time.monotonic(); renders+=1; cv.render(layout,content,w/'candidate.pdf')
        timings['render_seconds']=time.monotonic()-t
        stage='validation'; save(w/'stage.json',{'stage':stage})
        t=time.monotonic(); result=cv.validate(layout,content,w/'candidate.pdf')
        timings['validation_seconds']=time.monotonic()-t
        result.update(timings,content_calls=calls,renders=renders,total_worker_seconds=time.monotonic()-started)
        if provider_metadata: result['provider']=dict(provider_metadata,model_calls=model_calls)
        save(w/'result.json',result)
    except Exception as e:
        save(w/'result.json',dict(status='FAIL',stage=stage,reason=str(e),content_calls=calls,renders=renders,
                                 provider=getattr(generator,'last_metadata',None)))

def compile_prototype(jd,job_id,workspace,generator,hard_seconds=180):
    started=time.monotonic(); layout=cv.load_layout()
    if not 0<hard_seconds<=180: raise ValueError('hard stop cannot exceed 180 seconds')
    if not jd.strip(): raise ValueError('empty JD')
    workspace=pathlib.Path(workspace).resolve()
    if workspace.exists() and any(workspace.iterdir()): raise ValueError('fresh bounded workspace required')
    workspace.mkdir(parents=True,exist_ok=True)
    paths=dependency_paths()
    request={'jd':jd,'job_id':job_id,'mode':'generate','capacities':[
        {k:s[k] for k in ['id','section','width','font_size','leading','max_lines','variable']} for s in layout['slots']],
        'verified_sources':[{k:s[k] for k in ['id','text']} for s in layout['slots']],
        'rule':'Use only evidenced source text; no new facts, markup, styles, or layout decisions.'}
    proc=None
    with protect(paths) as before:
        if cv.digest(layout['master_source'])!=layout['master_sha256']: raise ValueError('master hash mismatch')
        save(workspace/'stage.json',{'stage':'content_generation'})
        proc=mp.get_context('spawn').Process(target=worker,args=(generator,request,str(workspace)))
        proc.start(); proc.join(max(0,hard_seconds-(time.monotonic()-started)))
        if proc.is_alive():
            proc.terminate(); proc.join(1)
            if proc.is_alive(): proc.kill(); proc.join(1)
            stage=json.loads((workspace/'stage.json').read_text())['stage']
            result={'status':'FAIL','reason':'hard wall-clock timeout','stage':stage,'delivery_allowed':False}
        elif (workspace/'result.json').exists(): result=json.loads((workspace/'result.json').read_text())
        else: result={'status':'FAIL','reason':'worker exited without verified result','delivery_allowed':False}
        after={str(p):cv.digest(p) for p in paths}
        if before!=after: result={'status':'FAIL','reason':'immutable dependency changed'}
        elapsed=time.monotonic()-started
        if elapsed>=hard_seconds: result.update(status='FAIL',reason='hard wall-clock timeout')
        result.update(elapsed_seconds=elapsed,target_seconds=120,hard_seconds=hard_seconds,
                      hashes_before=before,hashes_after=after,delivery_allowed=result['status']=='PASS',
                      not_deployed=True,owner_visual_acceptance=False)
        if result['delivery_allowed']:
            result['pdf_path']=str(workspace/'candidate.pdf')
        save(workspace/'verification.json',result)
        return result

def delivery_allowed(pdf,output_root):
    """Revalidate actual bytes, evidence and all dependencies at attachment time."""
    try:
        pdf=pathlib.Path(pdf).resolve(); root=pathlib.Path(output_root).resolve()
        if not pdf.is_relative_to(root) or pdf.name!='candidate.pdf':return False
        report=json.loads((pdf.parent/'verification.json').read_text(encoding='utf-8'))
        if report.get('status')!='PASS' or not report.get('delivery_allowed'):return False
        if report.get('elapsed_seconds',181)>=180 or report.get('content_calls',3)>2 or report.get('renders',3)>2:return False
        hashes={str(p):cv.digest(p) for p in dependency_paths()}
        if report.get('hashes_before')!=hashes or report.get('hashes_after')!=hashes:return False
        if report.get('pdf_sha256')!=cv.digest(pdf):return False
        content=json.loads((pdf.parent/'content-draft.json').read_text(encoding='utf-8'))
        return cv.validate(cv.load_layout(),content,pdf)['status']=='PASS'
    except Exception:return False

