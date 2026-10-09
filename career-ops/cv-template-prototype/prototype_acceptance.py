"""Zero-provider offline format-engine exercise. NOT real LLM acceptance."""
import hashlib, json, pathlib, re, time
import pymupdf as fitz
from PIL import Image,ImageDraw
import cv_template as cv
from cv_compile_prototype import compile_prototype
HERE=pathlib.Path(__file__).parent
REPO=pathlib.Path(r'C:/Users/mukun/Documents/mukund-chief-control-plane')

def evidence_selection(request):
    """Deterministic source sentence selection, not model-generated paraphrasing."""
    terms=set(re.findall(r'[a-z]{3,}',request['jd'].lower()))
    sources=[s for s in cv.load_layout()['slots'] if s['bullet'] and s['variable']]
    best=max(sources,key=lambda s:len(terms&set(re.findall(r'[a-z]{3,}',s['text'].lower()))))
    sentence=best['text'][2:].split('. ')[0]
    if not sentence.endswith('.'):sentence+='.'
    profile=next(s for s in cv.load_layout()['slots'] if s['section']=='Professional Summary' and s['variable'])
    return {profile['id']:{'text':sentence,'sources':[best['id']]}}

def main():
    out=HERE/'output';out.mkdir(exist_ok=True)
    result=cv.reproduce(out/'original-content-reproduction.pdf')
    l=cv.load_layout();master=fitz.open(l['master_source']);repro=fitz.open(out/'original-content-reproduction.pdf')
    pics=[]
    for name,doc in [('original',master),('reproduction',repro)]:
        pix=doc[0].get_pixmap(matrix=fitz.Matrix(1.6,1.6));pics.append(Image.frombytes('RGB',[pix.width,pix.height],pix.samples))
    comparison=Image.new('RGB',(pics[0].width*2+30,pics[0].height+40),'#e6e6e6');draw=ImageDraw.Draw(comparison)
    draw.text((10,10),'OWNER MASTER (left) | FLOW TEMPLATE (right)',fill='black')
    comparison.paste(pics[0],(0,40));comparison.paste(pics[1],(pics[0].width+30,40));comparison.save(out/'side-by-side.png')
    text=cv.norm(master[0].get_text(sort=True)).replace('time- limited','time-limited')
    expected=cv.norm(' '.join(s['text'] for s in l['slots']))
    structural={'source_sha256':cv.digest(l['master_source']),'original_content_equal':text==expected,
        'source_page_count':len(master),'reproduction_page_count':len(repro),'page_dimensions':l['page'],
        'section_order':l['section_order'],'font_family':'Times New Roman (Windows TTF, embedded)',
        'slots':len(l['slots']),'variable_slots':sum(s['variable'] for s in l['slots']),
        'design_notes':['Source content is preserved; paragraphs flow within fixed slots.',
            'Line endings may differ where source used manually positioned lines.',
            'Skill values follow bold labels with normal spacing, not fixed value anchors.',
            'Education modules retain the source hard break; all editable body text flows.',
            'No claim of source pixel identity; this is a separate font-backed reconstruction.'],
        'validation':result,'owner_visual_acceptance':False,'hermes_deployment':'UNCHANGED'}
    if text!=expected:
        import difflib
        structural['text_diff']=list(difflib.unified_diff(text.split(' '),expected.split(' ')))
    (out/'structural-comparison.json').write_text(json.dumps(structural,indent=2,ensure_ascii=False),encoding='utf-8')
    cases=[
      ('SOC / incident response','career-ops/tests/fixtures/jd-information-security-analyst.txt',None),
      ('cyber GRC','career-ops/applications/2026-09-25-tesco-cyber-security-graduate-scheme/jd.txt',None),
      ('technology risk/audit','career-ops/applications/2026-10-03-pearson-internal-audit/jd.txt',None),
      ('security consulting',None,'Graduate security consultant: analyse risks, document security controls, communicate findings to stakeholders.'),
      ('IT support/security','career-ops/applications/2026-10-03-formula-1-it-support-analyst/jd.txt',None),
      ('graduate digital technology','career-ops/applications/2026-10-03-eversheds-sutherland-graduate-legal-technology-analyst/jd.txt',None),
      ('security engineering','career-ops/applications/2026-10-03-american-express-information-security-engineer-internship/jd.txt',None),
      ('general cyber graduate','career-ops/applications/2026-09-25-buuk-infrastructure-graduate-cyber-security-analyst/jd.txt',None)]
    evidence=[];before=cv.digest(HERE/'cv_template.py')
    for i,(family,path,fixture) in enumerate(cases):
        if path:
            raw=(REPO/path).read_bytes()
            try: jd=raw.decode('utf-8-sig')
            except UnicodeDecodeError: jd=raw.decode('cp1252')
        else: jd=fixture
        workspace=HERE/'case-output'/f'{i}-{time.time_ns()}'
        r=compile_prototype(jd,f'fixture-{i}',workspace,evidence_selection)
        evidence.append(dict(role_family=family,jd_source=path or 'synthetic offline security-consulting fixture',
            jd_sha256=hashlib.sha256(jd.encode()).hexdigest(),generation_mode='OFFLINE_EXTRACTIVE_FIXTURE_NO_MODEL',
            status=r['status'],total_seconds=r['elapsed_seconds'],content_generation_seconds=r.get('content_generation_seconds'),
            render_seconds=r.get('render_seconds'),validation_seconds=r.get('validation_seconds'),
            shortening_required=r.get('content_calls',0)>1,page_count=r.get('page_count'),model_calls=0,
            format_engine_unchanged=cv.digest(HERE/'cv_template.py')==before,reason=r.get('reason')))
    (out/'varied-jd-offline-timings.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps({'reproduction':result['status'],'original_content_equal':text==expected,'cases':evidence},indent=2))
if __name__=='__main__':main()
