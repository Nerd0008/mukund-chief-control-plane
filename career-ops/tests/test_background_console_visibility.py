import ast,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[2]

def test_watchdog_children_have_no_window_flags():
    tree=ast.parse((ROOT/'career-ops/gateway_watchdog.py').read_text())
    launches=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='run']
    assert len(launches)==2
    assert all(any(k.arg=='creationflags' for k in call.keywords) for call in launches)

def test_sync_hides_only_its_own_console_and_children():
    source=(ROOT/'scripts/scheduled_sync_chief.py').read_text()
    assert 'GetConsoleProcessList(users,2)==1 and users[0]==os.getpid()' in source
    assert 'creationflags=subprocess.CREATE_NO_WINDOW' in source
    tree=ast.parse(source)
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    assert main.body[0].value.func.id=='hide_owned_console'
