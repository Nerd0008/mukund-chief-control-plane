"""One bounded live sample, no Discord/Hermes deployment."""
import json,pathlib,time
from cv_compile_prototype import compile_prototype
from cv_content_adapter import generate
HERE=pathlib.Path(__file__).parent
# Paraphrased role requirements, not a full scraped webpage dump.
JD=('Allstate Graduate Product Engineer Opportunities 2027, Belfast, R35761. '
    'Build applications and systems across the technology stack. Relevant technologies: '
    'Java, Python, JavaScript, cloud platforms, APIs, databases, DevOps and front/back-end frameworks. '
    'Collaborate to clarify product requirements, prioritise features, create user-centric solutions, '
    'measure outcomes and improve iteratively. Strong programming and system-design fundamentals, '
    'clear communication, curiosity and collaboration. Practical IT-related degree, 2:1/commendation; '
    'completed within the last two years or completing by September 2027; less than one year relevant '
    'post-graduation experience; UK right to work without sponsorship. Structured early-career training '
    'includes AI literacy. Evidence source: https://www.allstate.jobs/job/23947981/graduate-product-engineer-opportunities-2027/')
if __name__=='__main__':
    workspace=HERE/'sample-runs'/('allstate-'+str(time.time_ns()))
    r=compile_prototype(JD,'allstate-product-engineer',workspace,generate)
    print(json.dumps(r,indent=2))
