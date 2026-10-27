from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from router_gateway_entry import install_windows_lifecycle

def test_guarded_windows_restart_preserves_wrapper_and_profile():
    module=NS(_gateway_run_argv=lambda exe,profile:[exe,'-m','hermes_cli.main',*profile.split(),'gateway','run'])
    install_windows_lifecycle(module,'C:/runtime/hermes_cli.main_router.py')
    assert module._gateway_run_argv('python.exe','--profile personal')==['python.exe',str(Path('C:/runtime/hermes_cli.main_router.py')),'--profile','personal','gateway','run']
    install_windows_lifecycle(module,'ignored')
    assert module._gateway_run_argv('python.exe','')[1]==str(Path('C:/runtime/hermes_cli.main_router.py'))

def test_changed_native_launcher_cannot_silently_drop_router_guard():
    module=NS(_gateway_run_argv=lambda exe,profile:[exe,'different-new-launcher'])
    install_windows_lifecycle(module,'C:/runtime/hermes_cli.main_router.py')
    with pytest.raises(RuntimeError,match='refusing unguarded'):module._gateway_run_argv('python.exe','')
