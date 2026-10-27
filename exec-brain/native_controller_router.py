"""Compatible, locally qualified model offers over the existing native client.

Never swaps credentials/transports, drops parameters or trusts 429 alternates.
Qualification is explicit; no network request is made while assembling offers.
"""
from __future__ import annotations
from pathlib import Path
import hashlib,json,time
from router_brain import RouterDecisionError
from workflow_health import database,snapshot
POLICY_PATH=Path(__file__).with_name('native_controller_policy.json')


def policy():
    try:
        raw=POLICY_PATH.read_bytes(); value=json.loads(raw)
        assert value['version']==1 and value['provider']=='nous' and value['api_mode']=='chat_completions'
        assert 0<value['qualification_ttl_seconds']<=604800
        rows=value['models'];assert rows and len({r['model'] for r in rows})==len(rows)
        for row in rows:
            assert isinstance(row['model'],str) and type(row['context_length']) is int and row['context_length']>0
            assert isinstance(row['parameters'],list) and isinstance(row['input_modalities'],list)
        return value,hashlib.sha256(raw).hexdigest()
    except (OSError,ValueError,KeyError,AssertionError,TypeError):
        raise RouterDecisionError('controller_policy_invalid') from None


def qualify(model,metadata):
    config,sha=policy()
    assert model in {r['model'] for r in config['models']}
    # Store allowlisted booleans, never synthetic response content or errors.
    safe={k:metadata.get(k) is True for k in ('chat','tools','tool_continuation','stream','english','vision','withdrawn')}
    with database() as con:
        previous=con.execute('SELECT metadata FROM qualification WHERE provider=? AND model=?',(config['provider'],model)).fetchone()
        try:was_withdrawn=previous is not None and json.loads(previous['metadata']).get('withdrawn') is True
        except (ValueError,TypeError,AttributeError):was_withdrawn=True
        core_pass=all(safe[k] for k in ('chat','tools','tool_continuation','stream','english'))
        safe['withdrawn']=safe['withdrawn'] or (was_withdrawn and not core_pass)
        con.execute('INSERT OR REPLACE INTO qualification VALUES(?,?,?,?,?)',
                    (config['provider'],model,sha,time.time(),json.dumps(safe)))
    return not safe["withdrawn"] and all(safe[k] for k in ("chat","tools","tool_continuation","stream","english"))


def context_budget(request):
    """Use the host's multimodal/token accounting, never wire bytes as tokens.

    Keep a 50% tokenizer-uncertainty margin, explicit output reservation and
    framing reserve. The caller also leaves 15% of model capacity unused.
    No messages, tool schemas or attachments are removed or modified.
    """
    try:
        from agent.model_metadata import estimate_messages_tokens_rough,estimate_tokens_rough
        messages=estimate_messages_tokens_rough(request.get('messages') or [])
        schemas=estimate_tokens_rough(json.dumps(request.get('tools') or request.get('functions') or [],ensure_ascii=False,default=str))
    except (ImportError,TypeError,ValueError):
        raise RouterDecisionError('native_context_estimator_unavailable') from None
    output=request.get('max_completion_tokens')
    if output is None:output=request.get('max_tokens')
    if output is None:output=8192
    if type(output) is not int or output<1:raise RouterDecisionError('invalid_native_output_budget')
    estimated=messages+schemas
    return {'estimated_input_tokens':estimated,'reserved_input_tokens':((estimated*3+1)//2),
            'reserved_output_tokens':output,'framing_reserve_tokens':2048,
            'total_reserved_tokens':((estimated*3+1)//2)+output+2048}


def compatible(request,row,*,check_context=True):
    budget=context_budget(request)
    if check_context and budget['total_reserved_tokens']>int(row['context_length']*.85):return False
    for message in request.get('messages') or []:
        content=message.get('content')
        if isinstance(content,list):
            for part in content:
                if not isinstance(part,dict):return False
                kind=part.get('type')
                if kind not in ('text','input_text'):
                    if kind not in ('image_url','input_image') or 'image' not in row['input_modalities']:return False
    basic={'model','messages','timeout','stream','stream_options','extra_headers','extra_query'}
    aliases={'max_completion_tokens':'max_tokens','reasoning_effort':'reasoning'}
    for key,value in request.items():
        if value is None or key in basic:continue
        if key=='extra_body':
            if not isinstance(value,dict):return False
            # These are endpoint-level Hermes attribution/affinity fields, not
            # optional model capabilities. Preserve them exactly on every model.
            if 'tags' in value and (not isinstance(value['tags'],list) or any(not isinstance(t,str) for t in value['tags'])):return False
            if 'session_id' in value and not isinstance(value['session_id'],str):return False
            if any(k not in ('tags','session_id') and aliases.get(k,k) not in row['parameters'] for k in value):return False
        elif aliases.get(key,key) not in row['parameters']:return False
    return True


class ControllerOffers(list):
    """Empty offers retain the reason; protocol, qualification and capacity differ."""
    def __init__(self, values=(), *, reason='no_qualified_controller'):
        super().__init__(values)
        self.block_reason=reason


def offers(provider,model,api_mode,request):
    primary={'id':'native','provider':provider,'model':model,
             'capabilities':['preserve-native-tool-and-stream-protocol']}
    if provider!='nous' or api_mode not in ('','chat','chat_completions'):return [primary]
    config,sha=policy()
    if model not in {r['model'] for r in config['models']}:return [primary]
    now=time.time();result=ControllerOffers();eligibility=[];qualified_rows=[]
    budget=context_budget(request)
    with database() as con:
        proofs={r['model']:dict(r) for r in con.execute('SELECT * FROM qualification WHERE provider=?',(provider,))}
    for row in config['models']:
        name=row['model'];proof=proofs.get(name);reason=None
        if not proof or proof['policy_sha']!=sha:reason='unqualified'
        elif not 0<=now-proof['observed_at']<=config['qualification_ttl_seconds']:reason='qualification_expired'
        try:checks=json.loads((proof or {}).get('metadata') or '{}')
        except (ValueError,TypeError):checks={}
        if not isinstance(checks,dict):checks={}
        if checks.get('withdrawn') is True:reason='withdrawn'
        if not reason and not all(checks.get(k) is True for k in ('chat','tools','tool_continuation','stream','english')):reason='qualification_failed'
        if not reason:
            qualified_rows.append(row)
            if not compatible(request,row,check_context=False):reason='protocol_incompatible'
            elif budget['total_reserved_tokens']>int(row['context_length']*.85):reason='context_capacity'
            has_image=any(isinstance(m.get('content'),list) and any(isinstance(p,dict) and p.get('type') in ('image_url','input_image') for p in m['content']) for m in request.get('messages') or [])
            if has_image and checks.get('vision') is not True:reason='vision_unqualified'
        eligibility.append({'model':name,'reason':reason or 'eligible','context_length':row['context_length']})
        if reason:continue
        result.append({'id':'native' if name==model else 'native-'+hashlib.sha256(name.encode()).hexdigest()[:12],
                       'provider':provider,'model':name,'capabilities':['preserve-native-tool-and-stream-protocol'],
                       'evidence':{'qualification':'live chat, tool call, tool result continuation, streaming and English verified',
                                   'context_capacity':row['context_length']}})
    # Configured primary has priority among equal offers, but no qualification bypass.
    result.sort(key=lambda r:r['model']!=model)
    if not result:
        reasons={r['reason'] for r in eligibility}
        if 'context_capacity' in reasons:
            oversized_output=all(budget['reserved_output_tokens']+budget['framing_reserve_tokens']>int(row['context_length']*.85) for row in qualified_rows)
            result.block_reason='native_output_budget_exceeded' if oversized_output else 'native_context_capacity_exceeded'
        elif qualified_rows:result.block_reason='native_request_protocol_incompatible'
        from workflow_routing import persist
        import uuid
        persist({'workflow':'hermes.native.compatibility','stage':'eligibility','status':'BLOCKED',
                 'call_id':uuid.uuid4().hex,'error':result.block_reason,'request_context_budget':budget,
                 'qualified_model_eligibility':eligibility})
    return result
