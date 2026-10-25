"""Guarded normal gateway entrypoint: missing routing must stop execution."""
import functools


def require_registration(plugins):
    manager=plugins._delivery_manager()
    callbacks=getattr(manager,'_middleware',{}).get('llm_execution',[])
    if not any(getattr(cb,'__module__','')=='native_router_plugin' and
               getattr(cb,'__name__','')=='llm_execution' for cb in callbacks):
        raise RuntimeError('Mandatory router middleware unavailable; gateway execution blocked')


def install_guard(middleware,plugins):
    if getattr(middleware,'_mandatory_router_guard',False):return
    original=middleware.run_llm_execution_middleware
    @functools.wraps(original)
    def guarded(request,next_call,**context):
        require_registration(plugins)
        return original(request,next_call,**context)
    middleware.run_llm_execution_middleware=guarded
    middleware._mandatory_router_guard=True


def main():
    from hermes_cli import middleware,plugins
    install_guard(middleware,plugins)
    plugins.discover_plugins()
    require_registration(plugins)
    from agent import auxiliary_client
    if not getattr(auxiliary_client,'_mandatory_router_installed',False):
        raise RuntimeError('Mandatory auxiliary routing unavailable; gateway startup blocked')
    from hermes_cli.main import main as native_main
    return native_main()


if __name__=='__main__':main()
