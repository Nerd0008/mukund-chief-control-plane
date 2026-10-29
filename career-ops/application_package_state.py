"""Private per-session application receipts; no provider or messaging calls."""
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
import ast

ROOT = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'hermes/runtime/career-ops/application-packages'


def retry(text):
    text = re.sub(r'^\[Triggering message id:.*?\]\s*', '', str(text), flags=re.S)
    return bool(re.fullmatch(r'\s*(?:please\s+)?(?:try again|retry|continue|resume|finish it|finish the package|send again)[.!\s]*', text, re.I))


def prior_production(history, detector):
    for message in reversed(history or []):
        if message.get('role') != 'user': continue
        text = str(message.get('content') or '')
        if text.startswith(("You've reached the maximum", '[CONTEXT COMPACTION')): continue
        if retry(text): continue
        return detector(text, [])
    return False


def load(session_id):
    if not session_id: return {}
    path = ROOT / (hashlib.sha256(str(session_id).encode()).hexdigest()+'.json')
    try:
        result = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(result,dict) or not isinstance(result.get('results',{}),dict):return {}
        return result if result.get('session_id') == str(session_id) and result.get('active') is True else {}
    except (OSError, ValueError): return {}


def save(state):
    if not state.get('session_id'): return
    record = {key: state[key] for key in ('session_id','request_id','cv_args','cover_args','results','content_worker','cv_only','cover_only') if key in state}
    record['active'] = bool(state.get('cv_active'))
    ROOT.mkdir(parents=True, exist_ok=True)
    target = ROOT / (hashlib.sha256(str(state['session_id']).encode()).hexdigest()+'.json')
    temporary = target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(record, ensure_ascii=True), encoding='utf-8')
        os.replace(temporary, target)
    finally: temporary.unlink(missing_ok=True)


def record(state, kind, args, result):
    previous=state.get('results',{}).get(kind,{})
    if previous.get('status')=='PASS' and result.get('reason')=='verified cover already produced':
        return result
    state[kind+'_args'] = dict(args)
    stored=dict(result)
    if result.get('status')=='PASS' and result.get('compiler_pdf'):
        stored['artifact_sha256']=hashlib.sha256(Path(result['compiler_pdf']).read_bytes()).hexdigest()
    state.setdefault('results', {})[kind] = stored
    try: save(state)
    except OSError: state['receipt_error'] = 'Application resume receipt could not be saved'
    return result


def accepted(state):
    import hermes_cv_compiler_guard as guard
    from hermes_cover_tool import verified
    files = {}
    for kind, result in state.get('results', {}).items():
        path = result.get('verified_pdf')
        if result.get('status') == 'PASS' and path and source_matches(result) and (guard.verified_attachment(path) if kind == 'cv' else verified(path)):
            files[kind] = path
    return files


def source_matches(result):
    try:
        source=Path(result['compiler_pdf'])
        expected=result['artifact_sha256']
        metadata=Path(result['verified_pdf']).with_suffix('.verification.json')
        if metadata.exists() and Path(json.loads(metadata.read_text(encoding='utf-8'))['source']).resolve()!=source.resolve():return False
        return hashlib.sha256(source.read_bytes()).hexdigest()==expected==hashlib.sha256(Path(result['verified_pdf']).read_bytes()).hexdigest()
    except (OSError,KeyError,ValueError,TypeError):return False


def delivery_path(path):
    return ROOT / 'delivery' / (hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()+'.json')


def record_delivery(path, result):
    """Only an actual successful media-adapter return acknowledges delivery."""
    success=result is True or getattr(result,'success',False) is True
    if not success:return
    target=delivery_path(path);target.parent.mkdir(parents=True,exist_ok=True)
    receipt={'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'confirmed':True}
    temp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(receipt),encoding='utf-8');os.replace(temp,target)
    finally:temp.unlink(missing_ok=True)


def delivered(path):
    try:
        receipt=json.loads(delivery_path(path).read_text(encoding='utf-8'))
        return receipt.get('confirmed') is True and receipt['sha256']==hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except (OSError,ValueError,KeyError):return False


def render(state):
    files = accepted(state)
    needed = required(state)
    lines = []
    for kind in needed:
        label = 'CV' if kind == 'cv' else 'Cover letter'
        if kind in files: lines.append(label + (': delivery previously confirmed.' if state.get('resuming') and not state.get('resend') and delivered(files[kind]) else ': verified and ready.'))
        else:
            result = state.get('results', {}).get(kind, {})
            reason = result.get('reason') or state.get('blocked_reason') or 'not completed within this attempt'
            lines.append(label + ': incomplete — ' + str(reason)[:300] + '.')
    for kind, path in files.items():
        if not (state.get('resuming') and not state.get('resend') and delivered(path)): lines.append('MEDIA:' + path)
    if state.get('receipt_error'): lines.append(state['receipt_error']+'. Existing verified files are preserved.')
    return '\n'.join(lines)


def required(state):
    return ['cover'] if state.get('cover_only') else ['cv'] if state.get('cv_only') else ['cv','cover']


def outcome(state):
    files=accepted(state)
    return 'VERIFIED_READY' if all(k in files for k in required(state)) else 'PARTIAL' if files else 'INCOMPLETE'


def trim_history(history):
    """Drop repeatable preparation payloads, preserving user data and receipts."""
    removed = set()
    result = []
    seen_reads=set()
    duplicate_reads=set()
    for message in reversed(history or []):
        calls=message.get('tool_calls') or []
        if isinstance(calls,str):
            try:calls=json.loads(calls)
            except ValueError:continue
        if message.get('role')=='assistant' and len(calls)==1:
            call=calls[0]; key=readonly_cell(call)
            if key:
                if key in seen_reads: duplicate_reads.add(call.get('id'))
                seen_reads.add(key)
    for message in history or []:
        if message.get('role') == 'assistant' and message.get('tool_calls'):
            calls = message['tool_calls']
            if isinstance(calls, str):
                try: calls=json.loads(calls)
                except ValueError: calls=[]
            if calls and all(c.get('function',{}).get('name')=='skill_view' for c in calls):
                removed.update(c.get('id') for c in calls); continue
            if len(calls)==1 and calls[0].get('id') in duplicate_reads:
                removed.add(calls[0].get('id'));continue
        if message.get('role') == 'tool' and message.get('tool_call_id') in removed: continue
        result.append(message)
    return result


def readonly_cell(call):
    """Recognize only inert open/read/print cells; never discard write outcomes."""
    function=call.get('function',{})
    if function.get('name')!='execute_code':return None
    try:
        args=function.get('arguments',{})
        if isinstance(args,str):args=json.loads(args)
        code=args.get('code','')
        if '\\n' in code and '\n' not in code:code=code.replace('\\n','\n').replace('\\"','"')
        tree=ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node,(ast.For,ast.While,ast.If,ast.Try,ast.FunctionDef,ast.ClassDef,ast.Import,ast.Raise,ast.Delete,ast.Await,ast.Global,ast.Nonlocal,ast.Lambda)):
                return None
            if isinstance(node,ast.ImportFrom) and (node.module!='hermes_tools' or any(a.name!='read_file' for a in node.names)):return None
            if isinstance(node,ast.Call):
                f=node.func
                if isinstance(f,ast.Name) and f.id in ('open','print'):
                    if f.id=='open' and (len(node.args)>1 and not (isinstance(node.args[1],ast.Constant) and node.args[1].value in ('r','rb'))):return None
                    if f.id=='open' and any(k.arg=='mode' and not (isinstance(k.value,ast.Constant) and k.value.value in ('r','rb')) for k in node.keywords):return None
                elif not (isinstance(f,ast.Attribute) and isinstance(f.value,ast.Name) and f.attr=='read' and not node.args and not node.keywords):return None
        if not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='open' for n in ast.walk(tree)):return None
        return ast.dump(tree)
    except (ValueError,TypeError,SyntaxError):return None
