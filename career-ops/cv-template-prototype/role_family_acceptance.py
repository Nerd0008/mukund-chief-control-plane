"""Eight bounded native-provider content-planning acceptances; no agent loop."""
import hashlib,json,pathlib,time,re,sys
from cv_compile_prototype import compile_prototype
from cv_content_adapter import generate
import cv_template as cv
HERE=pathlib.Path(__file__).parent
REPO=pathlib.Path(r'C:/Users/mukun/Documents/mukund-chief-control-plane')
CASES=[
 ('SOC / incident response','career-ops/tests/fixtures/jd-information-security-analyst.txt',None),
 ('cyber GRC','career-ops/applications/2026-09-25-tesco-cyber-security-graduate-scheme/jd.txt',None),
 ('technology risk/audit','career-ops/applications/2026-10-03-pearson-internal-audit/jd.txt',None),
 ('security consulting',None,'Graduate security consultant: analyse risks, document security controls, communicate findings to stakeholders. Review controls and present clear evidence-based recommendations. Python and Windows knowledge desirable.'),
 ('IT support/security','career-ops/applications/2026-10-03-formula-1-it-support-analyst/jd.txt',None),
 ('graduate digital technology','career-ops/applications/2026-10-03-eversheds-sutherland-graduate-legal-technology-analyst/jd.txt',None),
 ('security engineering','career-ops/applications/2026-10-03-american-express-information-security-engineer-internship/jd.txt',None),
 ('general cyber graduate','career-ops/applications/2026-09-25-buuk-infrastructure-graduate-cyber-security-analyst/jd.txt',None)]
def offline_selection(request):
    from cv_content_adapter import resolve_plan
    bank=json.loads((HERE/'fact_bank.json').read_text(encoding='utf-8'))
    terms=set(re.findall(r'[a-z]{3,}',request['jd'].lower()))
    selection={k:max(variants,key=lambda name:len(terms&set(re.findall(r'[a-z]{3,}',variants[name]['text'].lower())))) for k,variants in bank['slots'].items()}
    result=resolve_plan({'selections':selection})
    return {key:result[key] for key in request['affected']} if request['mode']=='shorten' else result

def main():
    offline='--offline' in sys.argv
    results=[]; before=cv.digest(HERE/'cv_template.py')
    for n,(family,source,fixture) in enumerate(CASES):
        jd=(REPO/source).read_bytes().decode('utf-8-sig',errors='replace') if source else fixture
        folder=HERE/'case-output'/('live-'+str(n)+'-'+str(time.time_ns()))
        r=compile_prototype(jd,f'role-family-{n}',folder,offline_selection if offline else generate)
        results.append({k:r.get(k) for k in ['status','elapsed_seconds','content_generation_seconds','render_seconds','validation_seconds','content_calls','renders','page_count','reason','provider']})
        results[-1].update(role_family=family,jd_source=source or 'synthetic role-family fixture',
            jd_sha256=hashlib.sha256(jd.encode()).hexdigest(),workspace=str(folder),
            mode='OFFLINE_KEYWORD_SELECTION_NO_PROVIDER' if offline else 'NATIVE_PROVIDER',
            format_engine_unchanged=cv.digest(HERE/'cv_template.py')==before)
        (HERE/'output'/('role-family-offline-acceptance.json' if offline else 'role-family-live-acceptance.json')).write_text(json.dumps(results,indent=2),encoding='utf-8')
        print(json.dumps(results[-1]),flush=True)
        if r['status']!='PASS': break  # Diagnose, never blindly retry.
if __name__=='__main__': main()
