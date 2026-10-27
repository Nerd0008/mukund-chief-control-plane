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


def install_windows_lifecycle(module,entry=None):
    """Preserve the mandatory wrapper when guarded CLI start/restart respawns."""
    if getattr(module,'_router_gateway_lifecycle',False):return
    from pathlib import Path
    wrapper=str(Path(entry) if entry else Path(__file__).with_name('hermes_cli.main_router.py'))
    original=module._gateway_run_argv
    @functools.wraps(original)
    def argv(python_exe,profile_arg):
        native=original(python_exe,profile_arg)
        if native[:3]!=[python_exe,'-m','hermes_cli.main']:
            raise RuntimeError('Gateway lifecycle contract changed; refusing unguarded launch')
        return [python_exe,wrapper,*native[3:]]
    module._gateway_run_argv=argv
    module._router_gateway_lifecycle=True


def main():
    import os
    if os.name=='nt':
        from hermes_cli import gateway_windows
        install_windows_lifecycle(gateway_windows)
    from hermes_cli import middleware,plugins
    install_guard(middleware,plugins)
    plugins.discover_plugins()
    require_registration(plugins)
    from agent import auxiliary_client
    if not getattr(auxiliary_client,'_mandatory_router_installed',False) or getattr(auxiliary_client,'_mandatory_router_contract',None)!='physical-relay-v1':
        raise RuntimeError('Mandatory auxiliary routing unavailable; gateway startup blocked')
    from hermes_cli.main import main as native_main
    return native_main()


if __name__=='__main__':main()
