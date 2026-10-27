import sys,json,io,base64,asyncio
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),r'C:/Users/mukun/AppData/Local/hermes/hermes-agent']
import router_media as media
import workflow_routing as wr
import native_router_plugin as plugin
from router_brain import RouterDecisionError
from workflow_control import CONTENT_WORKER

@pytest.fixture(autouse=True)
def offline(tmp_path,monkeypatch):
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path/'receipts');monkeypatch.setenv('HERMES_HOME',str(tmp_path))
    monkeypatch.setattr(media,'image_key',lambda:'PRIVATE-KEY')
    monkeypatch.setattr(media,'select',lambda *a,**kw:('native',{'request_id':'fixture'}))

def test_media_registrations_match_configured_e3_interfaces():
    ctx=NS(register_image_gen_provider=lambda p:images.append(p),register_transcription_provider=lambda p:audio.append(p))
    images=[];audio=[];media.register_media(ctx)
    assert images[0].name=='e3' and audio==[]
    assert images[0].default_model()==media.IMAGE_MODEL

def test_image_route_validates_and_saves_output(tmp_path):
    from PIL import Image
    import gemini_adapter
    data=io.BytesIO();Image.new('RGB',(8,8),'blue').save(data,format='PNG')
    body=json.dumps({'candidates':[{'content':{'parts':[{'inlineData':{'data':base64.b64encode(data.getvalue()).decode(),'mimeType':'image/png'}}]}}]})
    with patch.object(gemini_adapter,'_http_post_json',return_value=(200,body,{})) as request:
        result=media.RoutedImageProvider().generate('PRIVATE prompt')
    assert result['success'] and Path(result['image']).is_file() and request.call_count==1
    records=''.join(p.read_text() for p in (tmp_path/'receipts').glob('*.json'))
    assert 'PRIVATE' not in records

def test_media_denial_never_dispatches_image():
    import gemini_adapter
    with patch.object(media,'select',side_effect=RouterDecisionError('router_cli_timeout')),patch.object(gemini_adapter,'_http_post_json') as request:
        result=media.RoutedImageProvider().generate('synthetic')
    assert not result['success'] and result['error']=='router_cli_timeout';request.assert_not_called()



def test_unapproved_media_model_never_reads_or_sends(monkeypatch):
    monkeypatch.setattr(media,'image_key',lambda:(_ for _ in ()).throw(AssertionError('No auth read')))
    assert not media.RoutedImageProvider().generate('synthetic',model='unapproved')['success']

def test_owner_preference_is_request_scoped():
    class Turn:
        async def _run_agent(self,message,*args,**kwargs):return CONTENT_WORKER.get()
    plugin.install_turn_preference(Turn)
    assert asyncio.run(Turn()._run_agent('Use Codex to draft this'))=='codex'
    assert asyncio.run(Turn()._run_agent('Next unrelated request')) is None
    assert CONTENT_WORKER.get() is None

def test_plain_genai_codex_does_not_need_google_credentials():
    with patch.object(wr,'select',return_value=('codex',{})),patch.object(wr,'text_via_codex',return_value='synthetic'):
        response=wr.RoutedGenAIClient(None,worker='codex').models.generate_content(model='ignored',contents='synthetic')
    assert response.text=='synthetic'

def test_explicit_worker_incompatible_with_grounding_fails_closed():
    calls=[];client=NS(models=NS(generate_content=lambda **kw:calls.append(kw)))
    with pytest.raises(RouterDecisionError,match='incompatible'):
        wr.RoutedGenAIClient(client,worker='codex').models.generate_content(model='google',contents='synthetic',config={'tools':['google_search']})
    assert calls==[]


def test_linkedin_image_uses_four_by_five_and_explicit_failure(tmp_path,monkeypatch):
    import linkedin_content_gen as gen
    target=tmp_path/'image.png';target.write_bytes(b'validated-provider-image')
    calls=[]
    monkeypatch.setattr(media.RoutedImageProvider,'generate',lambda self,prompt,**kw:calls.append(kw) or {'success':True,'image':str(target)})
    assert gen.generate_image_bytes('Synthetic')==target.read_bytes()
    assert calls==[{'aspect_ratio':'4:5'}]
    monkeypatch.setattr(media.RoutedImageProvider,'generate',lambda *a,**kw:{'success':False,'error_type':'media_provider_rate_limit'})
    with pytest.raises(RouterDecisionError,match='media_provider_rate_limit'):gen.generate_image_bytes('Synthetic')


def test_image_four_by_five_reaches_native_payload(monkeypatch,tmp_path):
    from PIL import Image
    import gemini_adapter
    data=io.BytesIO();Image.new('RGB',(8,10),'blue').save(data,format='PNG')
    body=json.dumps({'candidates':[{'content':{'parts':[{'inlineData':{'data':base64.b64encode(data.getvalue()).decode()}}]}}]})
    with patch.object(gemini_adapter,'_http_post_json',return_value=(200,body,{})) as request:
        result=media.RoutedImageProvider().generate('Synthetic',aspect_ratio='4:5')
    assert result['success']
    assert request.call_args.args[1]['generationConfig']['imageConfig']['aspectRatio']=='4:5'


def test_invalid_image_aspect_never_dispatches(monkeypatch):
    monkeypatch.setattr(media,'image_key',lambda:pytest.fail('credential read before validation'))
    result=media.RoutedImageProvider().generate('Synthetic',aspect_ratio='wrong')
    assert not result['success'] and result['error_type']=='unsupported_aspect_ratio'


def test_image_billing_failure_is_explicit_without_retries():
    import gemini_adapter
    with patch.object(gemini_adapter,'_http_post_json',return_value=(402,'{}',{})) as request:
        result=media.RoutedImageProvider().generate('Synthetic',aspect_ratio='4:5')
    assert result['error_type']=='media_provider_billing' and result['aspect_ratio']=='4:5'
    assert request.call_count==1 and not result['success']
