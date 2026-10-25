"""Native Hermes routing integration via execution middleware, not observer hooks."""
import functools
import inspect
from types import SimpleNamespace
from workflow_routing import select, RoutedClient, _request_task
from router_brain import RouterDecisionError


def llm_execution(request,next_call,provider='',model='',api_mode='',**context):
    # The native tool-loop requires its existing protocol-compatible transport.
    # CLI workers are not offered as emulated Hermes function-call transports.
    try:
        select('hermes.native.'+str(api_mode or 'chat'),
            [{'id':'native','provider':provider,'model':model,
              'capabilities':['preserve-native-tool-and-stream-protocol']}],
            task=_request_task(request))
    except Exception as exc:
        # This host version fails open on middleware callback exceptions. Use
        # its downstream-error envelope to propagate a policy denial instead.
        from hermes_cli.middleware import _DownstreamExecutionError
        raise _DownstreamExecutionError(exc) from None
    return next_call(request)


def install_auxiliary(module):
    if getattr(module,'_mandatory_router_installed',False):return
    old=module._resolve_call_client
    @functools.wraps(old)
    def resolve(*args,**kwargs):
        route=old(*args,**kwargs)
        if isinstance(route.client,RoutedClient):return route
        task=args[0] if args else kwargs.get('task')
        wrapped=RoutedClient(route.client,route.effective_provider,route.final_model,
            workflow='hermes.auxiliary.'+str(task or 'text'),
            async_mode=kwargs.get('async_mode',False),allow_cli=False)
        return route._replace(client=wrapped)
    module._resolve_call_client=resolve
    module._mandatory_router_installed=True


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
