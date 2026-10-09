"""Native CV tools using the owner-approved flow template, never span repair."""
import asyncio,functools,json,os,pathlib,sys,time,uuid,threading
from contextvars import ContextVar
HERE=pathlib.Path(__file__).resolve().parent
TEMPLATE=HERE/'cv-template-prototype'
if not TEMPLATE.exists():TEMPLATE=HERE/'career-ops/cv-template-prototype'
sys.path.insert(0,str(TEMPLATE))
import cv_template as cv
from cv_compile_prototype import compile_prototype,delivery_allowed
from cv_content_adapter import generate
OUTPUT_ROOT=pathlib.Path(os.environ.get('LOCALAPPDATA',str(pathlib.Path.home())))/'hermes/runtime/career-ops/cv-compiled'
JOB=ContextVar('career_cv_compiler_job',default=None)
AGENT_TURNS=4

def cv_request(message,history=()):
    import re
    return any(re.search(r'\bCV\b|\bJD\b|job description|curriculum vitae|tailor.{0,30}resume|https?://\S*(?:careers|jobs\.|/job/)',str(t),re.I) for t in
        [message]+[m.get('content','') for m in history[-4:] if isinstance(m,dict)])

def pre_tool(tool_name,args,**kwargs):
    state=JOB.get()
    if not state:return None
    if time.monotonic()>=state['deadline']:
        return {'action':'block','message':'CV generation failed: three-minute deadline reached. Stop; do not restart or substitute the master.'}
    allowed={'read_file','file_search','file_read','search_files','web_search','web_extract','skill_view','skills_list','think',
             'career_cv_master','career_cv_compile','career_cv_build','tool_search','tool_describe','tool_call'}
    if tool_name not in allowed:
        return {'action':'block','message':'CV jobs use career_cv_compile with JD text. Code edits, terminal execution, parallel builders and repair loops are forbidden.'}
    if state.get('attempted') and tool_name in {'career_cv_compile','career_cv_build'}:
        return {'action':'block','message':'One compiler invocation per CV request. Return its verified result or bounded failure; no retry.'}
    return None

def master_tool(args,**kwargs):
    layout=cv.load_layout()
    return json.dumps({'master_sha256':layout['master_sha256'],'layout_version':layout['version'],
        'instructions':'Read the JD and call career_cv_compile exactly once with JD text and a job ID. No character-count matching or code changes.',
        'target_seconds':120,'hard_seconds':180,'mandatory_summary':['MSc Information Security','CompTIA Security+','ISC2 CC'],
        'verified_facts':[{k:s[k] for k in ['id','section','text']} for s in layout['slots'] if s['section']!='Header']})

def compile_tool(args,**kwargs):
    state=JOB.get()
    if not state:return json.dumps({'status':'FAIL','reason':'native CV job context required'})
    if state.get('attempted'):return json.dumps({'status':'FAIL','reason':'compiler already invoked; no retries'})
    state['attempted']=True
    try:
        approval=json.loads((TEMPLATE/'approval.json').read_text(encoding='utf-8'))['final_visual_approval']
        if approval['layout_sha256']!=cv.digest(TEMPLATE/'layout.json') or approval['reproduction_sha256']!=cv.digest(TEMPLATE/'output/original-content-reproduction.pdf'):
            raise ValueError('owner-approved visual layout has drifted')
        remaining=state['deadline']-time.monotonic()
        if remaining<=0:raise ValueError('three-minute deadline reached')
        workspace=OUTPUT_ROOT/('application-'+uuid.uuid4().hex)
        result=compile_prototype(str(args.get('jd','')),str(args.get('job_id','application')),workspace,generate,hard_seconds=min(180,remaining))
        state['workspace']=workspace
        response={k:result.get(k) for k in ['status','stage','reason','elapsed_seconds','content_calls','renders','provider']}
        if time.monotonic()<state['deadline'] and result['delivery_allowed'] and delivery_allowed(result['pdf_path'],OUTPUT_ROOT):
            response.update(verified_pdf=result['pdf_path'],verification_report=str(workspace/'verification.json'))
        else:
            response.update(status='FAIL',instruction='CV generation failed. Report stage and reason. Do not attach any intermediate PDF, retry, or substitute the master.')
        return json.dumps(response)
    except Exception as e:return json.dumps({'status':'FAIL','reason':str(e),'instruction':'Stop this CV job; no engineering or PDF substitution.'})

def retired_build(args,**kwargs):
    return json.dumps({'status':'RETIRED','instruction':'Span edits and exact character counts are retired. Use career_cv_compile(jd, job_id) once.'})

def needs_gate(path):
    import re,pymupdf
    p=pathlib.Path(path)
    if p.suffix.lower()!='.pdf':return False
    if p.resolve().is_relative_to(OUTPUT_ROOT.resolve()) or re.search(r'\bCV\b|_CV\b|resume|curriculum',p.stem,re.I):return True
    try:
        with pymupdf.open(p) as doc:text=' '.join(page.get_text() for page in doc).lower()
        return 'professional summary' in text and 'education' in text and 'work experience' in text
    except Exception:return True

def install_delivery(media_class):
    if getattr(media_class,'_fast_cv_delivery_installed',False):return
    old_send=media_class.send_document
    @functools.wraps(old_send)
    async def send(self,chat_id,file_path,*args,**kwargs):
        if needs_gate(file_path) and not delivery_allowed(file_path,OUTPUT_ROOT):
            from gateway.platforms.base import SendResult
            message='CV generation failed — PDF verification absent, failed or stale. No unverified PDF was attached.'
            await self.send(chat_id=chat_id,content=message)
            return SendResult(success=False,error=message)
        return await old_send(self,chat_id,file_path,*args,**kwargs)
    media_class.send_document=send;media_class._fast_cv_delivery_installed=True

def install_runtime(runtime,turn_class,media_class):
    install_delivery(media_class)
    if getattr(turn_class,'_fast_cv_guard_installed',False):return
    old_limit=runtime._current_max_iterations
    runtime._current_max_iterations=lambda:min(old_limit(),AGENT_TURNS) if JOB.get() else old_limit()
    old_run=turn_class._run_agent
    # Use Hermes' own hard-interrupt/process-reaper seam for this CV turn only.
    # A thread deadline keeps firing even if the asyncio loop is busy.
    if hasattr(turn_class,'_run_agent_start_turn_worker'):
        old_start=turn_class._run_agent_start_turn_worker
        def start(self,turn_ctx,run_sync):
            worker=old_start(self,turn_ctx,run_sync);state=JOB.get()
            if state:
                worker.agent_timeout=min(worker.agent_timeout or 180,180)
                def watchdog():
                    if not worker.worker_done.wait(max(0,state['deadline']-time.monotonic())):
                        from gateway.run import _abandon_timed_out_gateway_turn
                        state['timed_out']=True
                        _abandon_timed_out_gateway_turn(agent_holder=turn_ctx.agent_holder,**self._reaper_kwargs(worker))
                threading.Thread(target=watchdog,name='cv-wall-clock-stop',daemon=True).start()
            return worker
        turn_class._run_agent_start_turn_worker=start
    @functools.wraps(old_run)
    async def run(self,message,context_prompt,history,*args,**kwargs):
        if not cv_request(message,history):return await old_run(self,message,context_prompt,history,*args,**kwargs)
        state={'deadline':time.monotonic()+180,'attempted':False}
        token=JOB.set(state)
        instruction=('\nCV production: call career_cv_compile once with the full JD and job_id. '
                     'No span edits, terminal, renderer repair, code changes or master substitution. '
                     'Attach only verified_pdf on PASS. Return bounded failure immediately otherwise.')
        try:return await old_run(self,message,context_prompt+instruction,history,*args,**kwargs)
        finally:JOB.reset(token)
    turn_class._run_agent=run;turn_class._fast_cv_guard_installed=True
    if hasattr(turn_class,'_run_agent_timeout_result'):
        old_timeout=turn_class._run_agent_timeout_result
        def timeout(self,worker,turn_ctx):
            if JOB.get() and JOB.get().get('timed_out'):
                return {'final_response':'CV generation failed — affected element: elapsed-time budget; reason: three-minute hard stop. Draft evidence preserved; no failed PDF attached.',
                        'failed':True,'messages':[]}
            return old_timeout(self,worker,turn_ctx)
        turn_class._run_agent_timeout_result=timeout

def register(ctx):
    import gateway.run as runtime
    from gateway.run_turn import GatewayTurnMixin
    from plugins.platforms.discord.adapter_media import DiscordMediaMixin
    install_runtime(runtime,GatewayTurnMixin,DiscordMediaMixin)
    ctx.register_hook('pre_tool_call',pre_tool)
    def tool(name,description,properties,required,handler):
        ctx.register_tool(name=name,toolset='career_cv',schema={'name':name,'description':description,
            'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False}},handler=handler)
    tool('career_cv_master','Read approved CV design/facts. No span editing or character-count constraint.',{},[],master_tool)
    tool('career_cv_compile','Tailor a CV from JD in one bounded compiler invocation; returns verified PDF or failure. Never repair formatting.',
         {'jd':{'type':'string','minLength':1},'job_id':{'type':'string'}},['jd','job_id'],compile_tool)
    tool('career_cv_build','Retired span builder; use career_cv_compile.',{},[],retired_build)
    def connected_v2(native,adapter):
        install_delivery(type(adapter))
        import logging
        logging.getLogger('gateway.platforms.base').info('Approved flow CV compiler active on %s; attachment guard=%s; source=%s',
            type(adapter).__module__,getattr(type(adapter),'_fast_cv_delivery_installed',False),cv.digest(pathlib.Path(__file__))[:12])
    ctx.register_platform_handler('discord',connected_v2)
