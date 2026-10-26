"""Native Hermes routing integration via execution middleware, not observer hooks."""
import functools
import inspect
from types import SimpleNamespace
from workflow_routing import select, RoutedClient, _request_task
from router_brain import RouterDecisionError


def llm_execution(request,next_call,provider='',model='',api_mode='',**context):
    # The native tool-loop requires its existing protocol-compatible transport.
    # CLI workers are not offered as emulated Hermes function-call transports.
    from workflow_control import operation,finish
    from workflow_routing import execute
    try:
        with operation(request.get('timeout') or 120) as state:
            _,receipt=select('hermes.native.'+str(api_mode or 'chat'),
                [{'id':'native','provider':provider,'model':model,
                  'capabilities':['preserve-native-tool-and-stream-protocol']}],
                task=_request_task(request),timeout=state.remaining(45))
            value=execute('hermes.native.'+str(api_mode or 'chat'),receipt,
                lambda:next_call(dict(request,timeout=state.remaining())))
            return finish(value,state,request.get('stream',False))
    except Exception as exc:
        from hermes_cli.middleware import _DownstreamExecutionError
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
        _,receipt=select(workflow,[native_offer(provider or 'native',str(kwargs.get('model') or 'configured'),
            ['preserve-native-'+str(api_mode or 'chat_completions')])],
            task=_request_task(kwargs),timeout=state.remaining(45))
        request=dict(kwargs,timeout=state.remaining())
        return request,receipt
    old_sync=module._relay_sync_completion;old_async=module._relay_async_completion
    @functools.wraps(old_sync)
    def sync(client,kwargs,**options):
        state=CURRENT.get()
        if state is None:
            with operation(kwargs.get('timeout') or 90):return sync(client,kwargs,**options)
        request,receipt=authorize(client,kwargs,options.get('provider'),options.get('api_mode'))
        result=execute(receipt.get('workflow','hermes.auxiliary'),receipt,lambda:old_sync(client,request,**options));return finish(result,state,kwargs.get('stream',False))
    @functools.wraps(old_async)
    async def asynchronous(client,kwargs,**options):
        state=CURRENT.get()
        if state is None:
            with operation(kwargs.get('timeout') or 90):return await asynchronous(client,kwargs,**options)
        request,receipt=await cancellable_thread(authorize,client,kwargs,options.get('provider'),options.get('api_mode'))
        result=await aexecute(receipt.get('workflow','hermes.auxiliary'),receipt,lambda:old_async(client,request,**options));return finish(result,state,kwargs.get('stream',False))
    module._relay_sync_completion=sync;module._relay_async_completion=asynchronous
    old_sync_stream=module._relay_sync_stream
    @functools.wraps(old_sync_stream)
    def sync_stream(client,kwargs,**options):
        state=CURRENT.get()
        if state is None:
            with operation(kwargs.get('timeout') or 90):return sync_stream(client,kwargs,**options)
        request,receipt=authorize(client,kwargs,options.get('provider'),options.get('api_mode'))
        return finish(old_sync_stream(client,request,**options),state,True)
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
    return {'reason':'unknown','retryable':False,'should_compress':False,
            'should_rotate_credential':False,'should_fallback':False,
            'error_context':{'component':'router_brain','router_failure':str(original)}}


def install_failure_copy(module):
    """Narrow host copy adapter; unrelated provider errors retain native behavior."""
    if getattr(module,'_router_failure_copy_installed',False):return
    old=module.nonretryable_copy
    @functools.wraps(old)
    def copy(classified,**kwargs):
        context=getattr(classified,'error_context',None) or {}
        if context.get('component')!='router_brain':return old(classified,**kwargs)
        code=context.get('router_failure')
        if code=='worker_preference_incompatible':
            return 'The requested worker does not support this tool or request protocol. No replacement worker was silently selected.'
        if code in ('workflow_deadline_exceeded','workflow_elapsed_budget_exhausted','workflow_cancelled'):
            return 'This workflow stopped at its elapsed-time limit or cancellation. It was not retried automatically. Check any completed actions before resending.'
        if str(code).startswith('bounded_text_worker_'):
            return 'The Codex content worker failed during generation ('+code+'). It was not retried automatically. No unverified document will be delivered.'
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
