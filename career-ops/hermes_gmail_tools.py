"""Native tools for the owner-approved local read-only Career Ops Gmail path."""
import functools,json,pathlib,subprocess,sys
HERE=pathlib.Path(__file__).resolve().parent
GUIDANCE=('Local Career Ops Gmail access exists independently of manage_connections. '
          'For Gmail access, application-email or newsletter-job requests use career_gmail_status first, '
          'then career_gmail_scan or career_gmail_jobs; the career-gmail-monitor skill documents the route. '
          'A missing Gmail connector is NOT evidence that local Gmail is unavailable. '
          'Do not request connector consent when local OAuth is ready. Gmail is strictly read-only; '
          'never send/reply/archive/delete/label or change read state. Manual scan is dry-run. '
          'Existing owner-approved hourly writes remain governed by Career Ops guards. '
          'For open/valid/expired/completed assessment requests call career_gmail_assessments, not incremental scan. '
          'Return only OPEN, EXPIRED, COMPLETED or UNKNOWN with evidence. No deadline is UNKNOWN, never valid. '
          'Exclude newsletters. Do not add unrelated CV or tracker blockers. Do not delete scan locks.')

LANGUAGE_POLICY=('Owner communication language: English by default on every chat and scheduled job. '
    'Write explanations, summaries, tool-progress text and final answers in English unless the owner explicitly requests another language. '
    'Quoted foreign-language source text and proper names may remain unchanged, but explain them in English. '
    'Do not copy the language of old assistant messages or tool output into your response. '
    'Do not blame Windows locale/encoding for coherent foreign-language prose generated in your own answer without evidence.')

def install_language_policy(agent_class):
    if getattr(agent_class,'_owner_english_policy_installed',False):return
    old=agent_class.run_conversation
    @functools.wraps(old)
    def run(self,user_message,system_message=None,*args,**kwargs):
        from hermes_owner_context import retrieve
        owner_context,evidence=retrieve(user_message)
        self._owner_context_retrieval=evidence
        previous=getattr(self,'ephemeral_system_prompt',None)
        # Native API-time seam: continuing sessions restore frozen system prompts.
        # Do not persist private reference payloads into that frozen cache/history.
        self.ephemeral_system_prompt=(previous or '')+'\n'+LANGUAGE_POLICY+owner_context
        from hermes_response_language import chinese_requested, checked_result, checked_text, BufferedText
        allow=chinese_requested(user_message)
        saved={};buffers=[]
        # Reasoning is private model output, never an owner-facing progress report.
        for name in ('reasoning_callback','interim_assistant_callback','stream_delta_callback'):
            callback=getattr(self,name,None)
            saved[name]=callback
            if name=='reasoning_callback':setattr(self,name,None)
            elif callback and name=='interim_assistant_callback':
                def interim(text,*a,_callback=callback,**k):
                    return _callback(checked_text(text,allow),*a,**k)
                setattr(self,name,interim)
            elif callback:
                stream=BufferedText(callback,allow);buffers.append(stream);setattr(self,name,stream)
        # Native positional run_conversation args: history, task_id, stream_callback.
        args=list(args)
        if len(args)>2 and args[2]:
            stream=BufferedText(args[2],allow);buffers.append(stream);args[2]=stream
        elif kwargs.get('stream_callback'):
            stream=BufferedText(kwargs['stream_callback'],allow);buffers.append(stream);kwargs['stream_callback']=stream
        try:
            result=checked_result(old(self,user_message,system_message,*args,**kwargs),allow)
            for stream in buffers:stream.flush()
            return result
        finally:
            self.ephemeral_system_prompt=previous
            for name,callback in saved.items():setattr(self,name,callback)
    agent_class.run_conversation=run
    agent_class._owner_english_policy_installed=True
    import logging
    logging.getLogger(__name__).info('Owner language guard v2 active: final/interim/stream validation; raw reasoning disabled')

def command(script,verb):
    result=subprocess.run([sys.executable,str(HERE/script),verb],cwd=str(HERE.parent),capture_output=True,text=True,encoding='utf-8',timeout=240)
    try:data=json.loads(result.stdout)
    except ValueError:return json.dumps({'ok':False,'error':'local monitor returned no valid status','exit_code':result.returncode})
    return json.dumps(data)

def status_tool(args,**kwargs):return command('career_mail_monitor.py','status')
def scan_tool(args,**kwargs):return command('career_mail_monitor.py','scan')
def assessments_tool(args,**kwargs):
    try:return command('career_assessment_status.py','scan')
    except subprocess.TimeoutExpired:return json.dumps({'ok':False,'error':'assessment audit timed out; no status conclusions or writes made'})

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
    # Avoid importing run_agent recursively during plugin discovery.
    import threading,time
    def install_when_loaded():
        for _ in range(600):
            agent=getattr(sys.modules.get('run_agent'),'AIAgent',None)
            if agent is not None:
                install_language_policy(agent);return
            time.sleep(0.05)
    install_when_ready=getattr(sys.modules.get('run_agent'),'AIAgent',None)
    if install_when_ready is not None:install_language_policy(install_when_ready)
    else:threading.Thread(target=install_when_loaded,daemon=True).start()
    ctx.register_system_prompt_section('owner-response-language',LANGUAGE_POLICY,max_chars=1200)
    install_turn_guidance(GatewayTurnMixin)
    ctx.register_system_prompt_section('career-local-gmail',GUIDANCE,max_chars=2000)
    for name,description,handler,props in [
        ('career_gmail_status','Check existing local Gmail OAuth and approved monitoring status. No connector needed; no secrets printed.',status_tool,{}),
        ('career_gmail_scan','Read new recruitment Gmail using existing local OAuth. DRY RUN only: no tracker/Calendar/checkpoint/Gmail writes.',scan_tool,{}),
        ('career_gmail_assessments','Audit last 30 days for personal assessment/interview status: OPEN, EXPIRED, COMPLETED, UNKNOWN. Gmail read-only, no writes/checkpoint. Does not submit tests or infer validity from an invitation.',assessments_tool,{}),
        ('career_gmail_jobs','Read the private deduplicated newsletter job list. Unverified leads, not applications. No Gmail or tracker writes.',jobs_tool,{'limit':{'type':'integer','minimum':1,'maximum':50},'offset':{'type':'integer','minimum':0}})]:
        ctx.register_tool(name=name,toolset='career_gmail',schema={'name':name,'description':description,'parameters':{'type':'object','properties':props,'additionalProperties':False}},handler=handler)
