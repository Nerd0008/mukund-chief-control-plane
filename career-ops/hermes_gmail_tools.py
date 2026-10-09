"""Native tools for the owner-approved local read-only Career Ops Gmail path."""
import functools,json,pathlib,subprocess,sys
HERE=pathlib.Path(__file__).resolve().parent
GUIDANCE=('Local Career Ops Gmail access exists independently of manage_connections. '
          'For Gmail access, application-email or newsletter-job requests use career_gmail_status first, '
          'then career_gmail_scan or career_gmail_jobs; the career-gmail-monitor skill documents the route. '
          'A missing Gmail connector is NOT evidence that local Gmail is unavailable. '
          'Do not request connector consent when local OAuth is ready. Gmail is strictly read-only; '
          'never send/reply/archive/delete/label or change read state. Manual scan is dry-run. '
          'Existing owner-approved hourly writes remain governed by Career Ops guards.')

def command(script,verb):
    result=subprocess.run([sys.executable,str(HERE/script),verb],cwd=str(HERE.parent),capture_output=True,text=True,encoding='utf-8',timeout=240)
    try:data=json.loads(result.stdout)
    except ValueError:return json.dumps({'ok':False,'error':'local monitor returned no valid status','exit_code':result.returncode})
    return json.dumps(data)

def status_tool(args,**kwargs):return command('career_mail_monitor.py','status')
def scan_tool(args,**kwargs):return command('career_mail_monitor.py','scan')
def jobs_tool(args,**kwargs):
    from career_job_mail import ROOT
    p=ROOT/'jobs.json'
    if not p.exists():return json.dumps({'available':False,'instruction':'Use the career-gmail-monitor newsletter discovery command.'})
    try:rows=json.loads(p.read_text(encoding='utf-8'))
    except ValueError:return json.dumps({'available':False,'error':'private job list unreadable'})
    limit=max(1,min(50,int(args.get('limit',20))));offset=max(0,int(args.get('offset',0)))
    return json.dumps({'available':True,'total':len(rows),'offset':offset,'jobs':[{k:j.get(k) for k in ['company','title','url','validation','needs_review']} for j in rows[offset:offset+limit]],'applications_submitted':0,'gmail_mutations':0})

def install_turn_guidance(turn):
    if getattr(turn,'_local_gmail_guidance_installed',False):return
    old=turn._run_agent
    @functools.wraps(old)
    async def run(self,message,context_prompt,history,*a,**kw):
        return await old(self,message,context_prompt+'\n'+GUIDANCE,history,*a,**kw)
    turn._run_agent=run;turn._local_gmail_guidance_installed=True

def register(ctx):
    from gateway.run_turn import GatewayTurnMixin
    install_turn_guidance(GatewayTurnMixin)
    ctx.register_system_prompt_section('career-local-gmail',GUIDANCE,max_chars=1200)
    for name,description,handler,props in [
        ('career_gmail_status','Check existing local Gmail OAuth and approved monitoring status. No connector needed; no secrets printed.',status_tool,{}),
        ('career_gmail_scan','Read new recruitment Gmail using existing local OAuth. DRY RUN only: no tracker/Calendar/checkpoint/Gmail writes.',scan_tool,{}),
        ('career_gmail_jobs','Read the private deduplicated newsletter job list. Unverified leads, not applications. No Gmail or tracker writes.',jobs_tool,{'limit':{'type':'integer','minimum':1,'maximum':50},'offset':{'type':'integer','minimum':0}})]:
        ctx.register_tool(name=name,toolset='career_gmail',schema={'name':name,'description':description,'parameters':{'type':'object','properties':props,'additionalProperties':False}},handler=handler)
