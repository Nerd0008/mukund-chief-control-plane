"""Independent current-verifier check of the completed sample, no model call."""
import json,pathlib
import pymupdf as fitz
import cv_template as cv
HERE=pathlib.Path(__file__).parent
if __name__=='__main__':
    runs=sorted((HERE/'sample-runs').glob('allstate-[0-9]*'))
    good=[];failures=[]
    for w in runs:
        r=json.loads((w/'verification.json').read_text(encoding='utf-8'))
        if r['status']=='PASS': good.append((w,r))
        else: failures.append({'status':r['status'],'reason':r.get('reason'),'elapsed_seconds':r['elapsed_seconds'],'model_calls':1})
    w,r=good[-1];content=json.loads((w/'content-draft.json').read_text(encoding='utf-8'))
    current=cv.validate(cv.load_layout(),content,w/'candidate.pdf')
    assert current['status']=='PASS',current
    out=HERE/'output';pdf=out/'Mukund_Didwania_Allstate_Product_Engineer_CV.pdf'
    pdf.write_bytes((w/'candidate.pdf').read_bytes())
    fitz.open(pdf)[0].get_pixmap(matrix=fitz.Matrix(1.6,1.6)).save(out/'allstate-preview.png')
    summary={**current,'successful_run_seconds':r['elapsed_seconds'],
        'content_generation_seconds':r['content_generation_seconds'],'render_seconds':r['render_seconds'],
        'validation_seconds':r['validation_seconds'],'provider':r['provider'],
        'successful_run_model_calls':1,'total_live_model_calls':len(good)+len(failures),'failed_attempts':failures,
        'earlier_successful_attempts':[{'seconds':v['elapsed_seconds'],'provider':v.get('provider')} for _,v in good[:-1]],
        'renders':r['renders'],'shortening_pass':False,'template_visual_approved':True,
        'layout_sha256':cv.digest(HERE/'layout.json'),'verifier_sha256':cv.digest(HERE/'cv_template.py'),
        'fact_bank_sha256':cv.digest(HERE/'fact_bank.json'),
        'changes':sum(cv.norm(cv.expected_text(s))!=cv.norm(cv.expected_text(s,content.get(s['id'],{}).get('text'))) for s in cv.load_layout()['slots']),
        'master_unchanged':cv.digest(cv.load_layout()['master_source'])==cv.load_layout()['master_sha256'],
        'hermes_deployed':False,'jd_url':'https://www.allstate.jobs/job/23947981/graduate-product-engineer-opportunities-2027/'}
    (out/'allstate-sample-report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (out/'allstate-content.json').write_text(json.dumps(content,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(summary,indent=2))
