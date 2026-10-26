"""Explicit bounded qualification of existing native models, using synthetic data only."""
from pathlib import Path
import argparse,json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'exec-brain'))
from native_controller_router import policy,qualify
from workflow_health import metadata


def probe(client,model,vision=False):
    checks={k:False for k in ('chat','tools','tool_continuation','stream','english')}
    from providers import get_provider_profile
    extras=get_provider_profile('nous').build_extra_body(session_id='synthetic-native-qualification')
    def completion(**kwargs):
        return client.chat.completions.create(**dict(kwargs,extra_body={**extras,**kwargs.get('extra_body',{})}))
    base=[{'role':'system','content':'Respond in English only. Follow the requested synthetic protocol exactly.'},
          {'role':'user','content':'Call qualification_probe with value CHECK. Do not perform any real action.'}]
    tool={'type':'function','function':{'name':'qualification_probe','description':'Synthetic protocol check. Never executed.',
          'parameters':{'type':'object','properties':{'value':{'type':'string'}},'required':['value'],'additionalProperties':False}}}
    first=completion(model=model,messages=base,tools=[tool],
             tool_choice={'type':'function','function':{'name':'qualification_probe'}},max_tokens=2048,timeout=25)
    checks['chat']=bool(first.choices)
    msg=first.choices[0].message
    calls=msg.tool_calls or []
    checks['tools']=len(calls)==1 and calls[0].function.name=='qualification_probe' and json.loads(calls[0].function.arguments)=={'value':'CHECK'}
    if checks['tools']:
        continuation=base+[msg.model_dump(exclude_none=True),{'role':'tool','tool_call_id':calls[0].id,'content':'CHECK'},
                            {'role':'user','content':'Return exactly QUALIFIED in English, with no other text.'}]
        final=completion(model=model,messages=continuation,max_tokens=1024,timeout=25)
        text=final.choices[0].message.content or ''
        checks['tool_continuation']=text.strip()=='QUALIFIED'
        checks['english']=checks['tool_continuation'] and not any('\u3400'<=c<='\u9fff' for c in text)
    with completion(model=model,messages=[{'role':'user','content':'Return exactly STREAM_OK in English.'}],
                                            max_tokens=1024,stream=True,timeout=25) as stream:
        pieces=[];finished=False
        for chunk in stream:
            for choice in chunk.choices:
                pieces.append(choice.delta.content or '')
                finished=finished or choice.finish_reason=='stop'
        checks['stream']=finished and ''.join(pieces).strip()=='STREAM_OK'
    if vision:
        import base64,io
        from PIL import Image
        image=io.BytesIO();Image.new('RGB',(16,16),(255,0,0)).save(image,format='PNG')
        url='data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()
        try:
            answer=completion(model=model,messages=[{'role':'user','content':[
            {'type':'text','text':'What single color fills this image? Reply RED, GREEN or BLUE only.'},
            {'type':'image_url','image_url':{'url':url}}]}],max_tokens=1024,timeout=25)
            checks['vision']=(answer.choices[0].message.content or '').strip().upper()=='RED'
        except Exception:checks['vision']=False
    return checks


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--live',action='store_true');p.add_argument('--output',type=Path,required=True);p.add_argument('--models',nargs='*')
    args=p.parse_args()
    if not args.live:p.error('Explicit --live required. No background qualification occurs.')
    from workflow_routing import native_client
    routed=native_client(workflow='qualification.native');client=routed._native
    config,_=policy();report=[]
    try:
        catalog={m.id:m.model_dump() for m in client.with_options(timeout=15,max_retries=0).models.list()}
        selected=set(args.models or [r['model'] for r in config['models'] if r['model'].endswith(':free')])
        if selected-set(r['model'] for r in config['models']):raise ValueError('Unapproved model')
        for row in config['models']:
            if row['model'] not in selected:continue
            start=time.monotonic();model=row['model'];checks={}
            result={'model':model,'qualified':False}
            actual=catalog.get(model,{})
            architecture=actual.get('architecture') or {}
            compatible=(actual.get('context_length',0)>=row['context_length'] and
                        set(row['parameters'])<=set(actual.get('supported_parameters') or []) and
                        set(row['input_modalities'])<=set(architecture.get('input_modalities') or []))
            try:
                if not compatible:raise ValueError('catalog capability mismatch')
                checks=probe(client,model,vision="image" in row["input_modalities"])
                result['qualified']=qualify(model,checks);result['checks']=checks
            except Exception as exc:
                qualify(model,{'withdrawn':metadata(exc)['error']=='provider_model_withdrawn'})
                result.update({k:v for k,v in metadata(exc).items() if v is not None})
                if not compatible:result['error']='catalog_capability_mismatch'
            result['elapsed_seconds']=round(time.monotonic()-start,3);report.append(result)
            args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    finally:client.close()
    print(json.dumps(report,indent=2))
    return 0 if any(r['qualified'] for r in report) else 1

if __name__=='__main__':raise SystemExit(main())
