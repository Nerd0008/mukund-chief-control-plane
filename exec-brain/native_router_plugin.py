"""Native Hermes routing integration via execution middleware, not observer hooks."""
import functools
import inspect
import threading,time

_request_budgets={}
_budget_lock=threading.Lock()

def request_budget(context,timeout):
    from workflow_control import seconds,WorkflowTimeoutError
    key=context.get("api_request_id")
    if not isinstance(key,str) or not key:return seconds(timeout,120)
    now=time.monotonic()
    with _budget_lock:
        for old,(deadline,created) in list(_request_budgets.items()):
            if now-created>86400:_request_budgets.pop(old,None)
        if key not in _request_budgets:
            if len(_request_budgets)>=8192:raise RouterDecisionError("controller_request_capacity_exceeded")
            _request_budgets[key]=(now+seconds(timeout,120),now)
        remaining=_request_budgets[key][0]-now
    if remaining<=0:raise WorkflowTimeoutError("workflow_deadline_exceeded")
    return min(remaining,seconds(timeout,120))

from types import SimpleNamespace
from workflow_routing import select, RoutedClient, _request_task
from router_brain import RouterDecisionError


def llm_execution(request,next_call,provider='',model='',api_mode='',**context):
    # The native tool-loop requires its existing protocol-compatible transport.
    # CLI workers are not offered as emulated Hermes function-call transports.
    from workflow_control import operation,finish
    from workflow_routing import execute
    try:
        with operation(request_budget(context,request.get('timeout') or 120)) as state:
            from native_controller_router import offers
            owner_module=__import__('sys').modules.get('hermes_owner_context')
            if owner_module is not None:
                try:coverage=owner_module.verify_dispatch(request)
                except RuntimeError:raise RouterDecisionError('owner_context_coverage_failed') from None
                if coverage:
                    from workflow_routing import persist
                    import uuid
                    persist({'workflow':'hermes.owner-context','call_id':uuid.uuid4().hex,
                             'operation_id':state.id,'stage':'context','status':'CONTEXT_VERIFIED','context_coverage':coverage})
            from hermes_diagnostics import enrich_request,router_task,receipt_evidence
            request,diagnostic=enrich_request(request)
            if diagnostic:
                from workflow_routing import persist
                import uuid
                persist({'workflow':'hermes.operational-evidence','call_id':uuid.uuid4().hex,
                         'operation_id':state.id,'stage':'current_state','status':'EVIDENCE_READY' if diagnostic.get('evidence_sha256') else 'EVIDENCE_UNAVAILABLE',
                         'input_sha256':diagnostic.get('evidence_sha256'),'operational_evidence':receipt_evidence(diagnostic)})
            _,receipt=select('hermes.native.'+str(api_mode or 'chat'),
                offers(provider,model,api_mode,request),
                task=router_task(request,_request_task(request)),
                # High-reasoning selection can exceed 45s. Reserve at least a
                # quarter of the existing request budget for the chosen worker;
                # never extend the parent deadline or replay actions on timeout.
                timeout=min(90,state.remaining()*.75))
            value=execute('hermes.native.'+str(api_mode or 'chat'),receipt,
                lambda:next_call(dict(request,model=receipt.get('selected_model') or model,timeout=state.remaining())),
                stream=request.get('stream',False))
            return finish(value,state,request.get('stream',False))
    except Exception as exc:
        from hermes_cli.middleware import _DownstreamExecutionError
        if isinstance(exc, _DownstreamExecutionError):
            raise
        raise _DownstreamExecutionError(exc) from None


def install_auxiliary(module):
    """Gate physical attempts, including native fallback/rebuilt clients."""
    if getattr(module,'_mandatory_router_installed',False):
        if getattr(module,'_mandatory_router_contract',None)!='physical-relay-v1':
            raise RuntimeError('Gateway restart required: stale auxiliary routing contract')
        return
    from workflow_control import CURRENT,operation,cancellable_thread,finish
    from workflow_routing import native_offer,execute,aexecute
    required=('_relay_sync_completion','_relay_async_completion','_relay_sync_stream','_call_llm_impl','_async_call_llm_impl','_start_recovery_ladder')
    if any(not hasattr(module,name) for name in required):
        raise RuntimeError('Auxiliary physical-attempt contract unavailable; abort deployment')
    def authorize(client,kwargs,provider,api_mode):
        state=CURRENT.get()
        if state is None:raise RouterDecisionError('auxiliary_operation_context_missing')
        workflow='hermes.auxiliary.'+str((module._RELAY_AUX_CALL_CONTEXT.get() or {}).get('task') or 'text')
        from native_controller_router import offers
        _,receipt=select(workflow,offers(provider or 'native',str(kwargs.get('model') or 'configured'),
            api_mode or 'chat_completions',kwargs),
            task=_request_task(kwargs),timeout=state.remaining(45))
        request=dict(kwargs,model=receipt.get('selected_model') or kwargs.get('model'),timeout=state.remaining())
        return request,receipt
    old_sync=module._relay_sync_completion;old_async=module._relay_async_completion
    @functools.wraps(old_sync)
    def sync(client,kwargs,**options):
        state=CURRENT.get()
        if state is None:
            with operation(kwargs.get('timeout') or 90):return sync(client,kwargs,**options)
        request,receipt=authorize(client,kwargs,options.get('provider'),options.get('api_mode'))
        result=execute(receipt.get('workflow','hermes.auxiliary'),receipt,lambda:old_sync(client,request,**options),stream=kwargs.get('stream',False));return finish(result,state,kwargs.get('stream',False))
    @functools.wraps(old_async)
    async def asynchronous(client,kwargs,**options):
        state=CURRENT.get()
        if state is None:
            with operation(kwargs.get('timeout') or 90):return await asynchronous(client,kwargs,**options)
        request,receipt=await cancellable_thread(authorize,client,kwargs,options.get('provider'),options.get('api_mode'))
        result=await aexecute(receipt.get('workflow','hermes.auxiliary'),receipt,lambda:old_async(client,request,**options),stream=kwargs.get('stream',False));return finish(result,state,kwargs.get('stream',False))
    module._relay_sync_completion=sync;module._relay_async_completion=asynchronous
    old_sync_stream=module._relay_sync_stream
    @functools.wraps(old_sync_stream)
    def sync_stream(client,kwargs,**options):
        state=CURRENT.get()
        if state is None:
            with operation(kwargs.get('timeout') or 90):return sync_stream(client,kwargs,**options)
        request,receipt=authorize(client,kwargs,options.get('provider'),options.get('api_mode'))
        return finish(execute(receipt.get('workflow','hermes.auxiliary'),receipt,
            lambda:old_sync_stream(client,request,**options),stream=True),state,True)
    module._relay_sync_stream=sync_stream
    for name in ('_call_llm_impl','_async_call_llm_impl'):
        original=getattr(module,name)
        def prepare(original):
            if inspect.iscoroutinefunction(original):
                @functools.wraps(original)
                async def run(*args,**kwargs):
                    timeout=module._effective_aux_timeout(args[0] if args else kwargs.get('task'),kwargs.get('timeout'))
                    with operation(timeout):return await original(*args,**kwargs)
            else:
                @functools.wraps(original)
                def run(*args,**kwargs):
                    timeout=module._effective_aux_timeout(args[0] if args else kwargs.get('task'),kwargs.get('timeout'))
                    with operation(timeout):return original(*args,**kwargs)
            return run
        setattr(module,name,prepare(original))
    old_ladder=module._start_recovery_ladder
    @functools.wraps(old_ladder)
    def ladder(error,*args,**kwargs):
        if isinstance(error,RouterDecisionError):raise error
        if CURRENT.get():CURRENT.get().remaining()
        return old_ladder(error,*args,**kwargs)
    module._start_recovery_ladder=ladder
    # Streaming helper deadlines may be shorter than the provider's idle limit.
    old_plan=module._stream_request_plan
    @functools.wraps(old_plan)
    def stream_plan(kwargs):
        request,model,ceiling=old_plan(kwargs);state=CURRENT.get()
        return request,model,min(ceiling,state.remaining()) if state else ceiling
    module._stream_request_plan=stream_plan
    module._mandatory_router_installed=True
    module._mandatory_router_contract='physical-relay-v1'


def router_error_classification(*,error=None,**kwargs):
    # Match typed failures only, never keywords in user/model/provider text.
    original=getattr(error,'original',error)
    if not isinstance(original,RouterDecisionError):return None
    compress=str(original)=='native_context_capacity_exceeded'
    return {'reason':'context_overflow' if compress else 'unknown','retryable':False,'should_compress':compress,
            'should_rotate_credential':False,'should_fallback':False,
            'error_context':{'component':'router_brain','router_failure':str(original),'retry_after_seconds':(original.receipt or {}).get('retry_after_seconds')}}


def install_failure_copy(module):
    """Narrow host copy adapter; unrelated provider errors retain native behavior."""
    if getattr(module,'_router_failure_copy_installed',False):return
    old=module.nonretryable_copy
    @functools.wraps(old)
    def copy(classified,**kwargs):
        context=getattr(classified,'error_context',None) or {}
        if context.get('component')!='router_brain':return old(classified,**kwargs)
        code=context.get('router_failure')
        if code=='native_output_budget_exceeded':
            return 'The requested output budget exceeds qualified model capacity. It must be reduced; compressing history cannot repair this request.'
        if code=='native_context_capacity_exceeded':
            return 'The request exceeds every qualified controller context budget. Context compression is required; no model or tool action was executed by this attempt.'
        if code=='no_qualified_controller':
            return 'No controller has current successful qualification. Model availability must be verified before this request can run.'
        if code=='native_request_protocol_incompatible':
            return 'Qualified controllers cannot handle this request protocol. No model request was sent.'
        if code=='owner_context_coverage_failed':
            return 'Required owner context did not reach the model request completely. The request stopped before model execution.'
        if code=='worker_preference_incompatible':
            return 'The requested worker does not support this tool or request protocol. No replacement worker was silently selected.'
        if code in ('workflow_deadline_exceeded','workflow_elapsed_budget_exhausted','workflow_cancelled'):
            return 'This workflow stopped at its elapsed-time limit or cancellation. It was not retried automatically. Check any completed actions before resending.'
        if str(code).startswith('bounded_text_worker_'):
            return 'The Codex content worker failed during generation ('+code+'). It was not retried automatically. No unverified document will be delivered.'
        if code in ('no_healthy_compatible_worker','worker_health_changed'):
            return ('Compatible workers are temporarily unavailable'+(' for up to '+str(context['retry_after_seconds'])+' seconds' if context.get('retry_after_seconds') else '')+'. No actions were replayed. Earlier steps may have completed; preserve their state before continuing.')
        if code=='router_cli_rate_limited':
            delay=context.get('retry_after_seconds')
            return ('The Codex routing model returned HTTP 429 (rate limited).'+
                    (' Its cooldown has '+str(delay)+' seconds remaining.' if delay is not None else '')+
                    ' No downstream worker ran for this attempt. Completed workflow actions are preserved; no actions were replayed.')
        if code=='router_cli_busy':
            return 'The shared Codex model slot was busy until this request deadline. No additional model call or workflow action was started.'
        messages={
            'router_cli_timeout':'The Codex router reached its bounded time limit.',
            'router_cli_usage_limit':'The Codex router reported a usage or rate limit.',
            'router_cli_auth':'The Codex router requires authentication.',
            'router_cli_configuration':'The Codex router CLI configuration failed.',
        }
        return (messages.get(code,'The Codex router could not authorize this request.')+
                ' No downstream model call was made for this attempt. '
                'The request stopped without automatic retries. No failed document was attached.')
    module.nonretryable_copy=copy
    terminal=getattr(module,'nonretryable_client_error_result',None)
    if terminal:
        @functools.wraps(terminal)
        def report(*args,**kwargs):
            bound=inspect.signature(terminal).bind_partial(*args,**kwargs)
            classified=bound.arguments.get('classified');detail=getattr(classified,'error_context',None) or {}
            agent=bound.arguments.get('agent')
            if agent is not None and detail.get('component')=='router_brain' and detail.get('router_failure') in ('no_healthy_compatible_worker','worker_health_changed'):
                class DiagnosticAgent:
                    def __getattr__(self,name):return getattr(agent,name)
                    def __setattr__(self,name,value):setattr(agent,name,value)
                    def _emit_diagnostic_status(self,message):
                        wait=detail.get('retry_after_seconds')
                        return agent._emit_diagnostic_status('Router workers are temporarily unavailable'+(' (cooldown up to '+str(wait)+' seconds)' if wait else '')+'. No automatic action replay was attempted.')
                bound.arguments['agent']=DiagnosticAgent()
            return terminal(*bound.args,**bound.kwargs)
        module.nonretryable_client_error_result=report
    module._router_failure_copy_installed=True


def install_turn_preference(turn_class):
    if getattr(turn_class,'_router_worker_preference_installed',False):return
    from workflow_control import CONTENT_WORKER,requested_worker
    method='run_conversation' if hasattr(turn_class,'run_conversation') else '_run_agent'
    old=getattr(turn_class,method)
    if inspect.iscoroutinefunction(old):
        @functools.wraps(old)
        async def run(self,message,*args,**kwargs):
            token=CONTENT_WORKER.set(requested_worker(message) or CONTENT_WORKER.get())
            try:return await old(self,message,*args,**kwargs)
            finally:CONTENT_WORKER.reset(token)
    else:
        @functools.wraps(old)
        def run(self,message,*args,**kwargs):
            token=CONTENT_WORKER.set(requested_worker(message) or CONTENT_WORKER.get())
            try:return old(self,message,*args,**kwargs)
            finally:CONTENT_WORKER.reset(token)
    setattr(turn_class,method,run);turn_class._router_worker_preference_installed=True


def register(ctx):
    from hermes_cli import middleware
    if not hasattr(middleware,'_DownstreamExecutionError'):
        raise RuntimeError('Native middleware denial contract unavailable; abort deployment')
    ctx.register_middleware('llm_execution',llm_execution)
    from pathlib import Path
    import sys
    career=Path.home()/'Documents/mukund-chief-control-plane/career-ops'
    if str(career) not in sys.path:sys.path.insert(0,str(career))
    from hermes_linkedin_control import install as install_linkedin_control
    install_linkedin_control()
    from hermes_diagnostics import transform_output
    ctx.register_hook('transform_llm_output',transform_output)
    from career_workflow_bridge import guard
    ctx.register_hook('pre_tool_call',guard)
    __import__('logging').getLogger(__name__).info('Operational evidence v1 active: fresh LinkedIn state, exact execution logs, protected cron and before-persistence status transform')
    ctx.register_hook('transform_api_error_classification',router_error_classification)
    from agent import turn_recovery
    install_failure_copy(turn_recovery)
    from agent import auxiliary_client
    install_auxiliary(auxiliary_client)
    from router_media import register_media
    register_media(ctx)
    from gateway.run_turn import GatewayTurnMixin
    install_turn_preference(GatewayTurnMixin)
    from agent.turn_facade import TurnFacadeMixin
    install_turn_preference(TurnFacadeMixin)
