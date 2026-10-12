"""Restrict direct native-agent mutation of canonical trackers to audited entrypoints."""
import json,pathlib,re
HERE=pathlib.Path(__file__).resolve().parent

def pre_tool(tool_name,args,**kwargs):
    if tool_name not in {'terminal','execute_code','write_file','patch','apply_patch'}:return None
    payload=json.dumps(args,ensure_ascii=False).lower()
    profiles=json.loads((HERE/'regional_profiles.json').read_text(encoding='utf-8'))
    names=[pathlib.PureWindowsPath(c['tracker']).name.lower() for c in profiles['regions'].values()]
    mutates=bool(re.search(r'\.save\s*\(|delete_rows|insert_rows|move_range|os\.replace|shutil\.copy|remove-item|copy-item|write_text|set-content|sort_values',payload)) or tool_name in {'write_file','patch','apply_patch'}
    if 'regional_profiles.json' in payload and mutates:
        return {'action':'block','reason':'Canonical tracker schema cannot be changed by an ad hoc agent tool; use a reviewed code repair.'}
    if any(name in payload for name in names) and mutates:
        return {'action':'block','reason':'Direct canonical workbook mutation/restoration is blocked. Use the audited Career Ops writer. Never restore owner-deleted rows without explicit owner approval.'}
    return None


def register(ctx):ctx.register_hook('pre_tool_call',pre_tool)
