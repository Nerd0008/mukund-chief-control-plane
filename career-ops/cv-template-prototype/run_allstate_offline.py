"""Offline sample using curated source-grounded engineering wording."""
import json,pathlib,time
import pymupdf as fitz
from cv_compile_prototype import compile_prototype
from cv_content_adapter import resolve_plan
from run_allstate_sample import JD
HERE=pathlib.Path(__file__).parent
def reviewed_plan(request):
    bank=json.loads((HERE/'fact_bank.json').read_text(encoding='utf-8'))
    content=resolve_plan({'selections':{key:'engineering' for key in bank['slots']}})
    if request['mode']=='shorten':return {key:content[key] for key in request['affected']}
    return content
if __name__=='__main__':
    workspace=HERE/'sample-runs'/('allstate-offline-'+str(time.time_ns()))
    result=compile_prototype(JD,'allstate-product-engineer-offline',workspace,reviewed_plan)
    result.update(generation_mode='OFFLINE_CURATED_PLAN',model_calls=0,
        jd_url='https://www.allstate.jobs/job/23947981/graduate-product-engineer-opportunities-2027/')
    if result['delivery_allowed']:
        output=HERE/'output'/'Mukund_Didwania_Allstate_Product_Engineer_CV.pdf'
        output.write_bytes((workspace/'candidate.pdf').read_bytes());result['pdf_path']=str(output)
        fitz.open(output)[0].get_pixmap(matrix=fitz.Matrix(1.6,1.6)).save(HERE/'output'/'allstate-preview.png')
    (HERE/'output'/'allstate-sample-report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (HERE/'output'/'allstate-content.json').write_text((workspace/'content-draft.json').read_text(encoding='utf-8'),encoding='utf-8')
    print(json.dumps({key:result.get(key) for key in ['status','elapsed_seconds','content_calls','renders','model_calls','pdf_path']},indent=2))
