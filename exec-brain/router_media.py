"""Protocol-specific image bridge using existing approved credential stores.

The configured e3 media name is a router boundary, never a text-CLI backend.
No new account/key, silent cross-provider fallback or global config rewrite.
"""
from __future__ import annotations
import base64,io,os,uuid
from pathlib import Path
from agent.image_gen_provider import ImageGenProvider,error_response,success_response
from workflow_control import operation
from workflow_routing import select,native_offer,execute,failure_code

IMAGE_MODEL='gemini-3.1-flash-image'


def image_key():
    from gemini_keyaccess import get_gemini_key
    return get_gemini_key()


def image_parts(references,state):
    from PIL import Image
    parts=[]
    for ref in references:
        if str(ref).startswith('https://'):
            import urllib.request
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*args):return None
            with urllib.request.build_opener(NoRedirect).open(ref,timeout=state.remaining(15)) as response:
                data=response.read(25*1024*1024+1)
            if len(data)>25*1024*1024:raise ValueError('reference_image_too_large')
        else:
            path=Path(ref)
            if path.stat().st_size>25*1024*1024:raise ValueError('reference_image_too_large')
            data=path.read_bytes()
        with Image.open(io.BytesIO(data)) as image:
            kind=image.format;image.verify()
        mime={'PNG':'image/png','JPEG':'image/jpeg','WEBP':'image/webp'}.get(kind)
        if not mime:raise ValueError('unsupported_reference_image')
        parts.append({'inlineData':{'data':base64.b64encode(data).decode('ascii'),'mimeType':mime}})
    return parts


class RoutedImageProvider(ImageGenProvider):
    name='e3'
    def is_available(self):
        try:return bool(image_key())
        except Exception:return False
    def list_models(self):return [{'id':IMAGE_MODEL,'display':'Existing Google image backend via router'}]
    def capabilities(self):return {'modalities':['text','image'],'max_reference_images':4}
    def generate(self,prompt,aspect_ratio='landscape',*,image_url=None,reference_image_urls=None,**kwargs):
        model=kwargs.get('model') or IMAGE_MODEL
        if model!=IMAGE_MODEL:return error_response(error='media_model_not_authorized',error_type='media_model_not_authorized',provider='e3')
        aspects={'landscape':'16:9','portrait':'9:16','square':'1:1','4:5':'4:5'}
        if aspect_ratio not in aspects:return error_response(error='unsupported_aspect_ratio',error_type='unsupported_aspect_ratio',provider='e3')
        try:
            with operation(120) as state:
                key=image_key()
                if not key:return error_response(error='Existing Google image credential unavailable',error_type='credential_unavailable',provider='e3')
                _,receipt=select('hermes.media.image',[native_offer('google',model,['image-generation','image-editing'])],
                    task=prompt, family='image',timeout=state.remaining(45))
                refs=([image_url] if image_url else [])+list(reference_image_urls or [])
                if len(refs)>4:raise ValueError('too_many_reference_images')
                contents=[{'text':prompt},*image_parts(refs,state)]
                aspect=aspects[aspect_ratio]
                import json
                from gemini_adapter import _http_post_json,GENERATE_ENDPOINT
                payload={'contents':[{'parts':contents}],'generationConfig':{'responseModalities':['IMAGE'],'imageConfig':{'aspectRatio':aspect}}}
                status,body,_=execute('hermes.media.image',receipt,lambda:_http_post_json(GENERATE_ENDPOINT.format(model=model),payload,
                    {'x-goog-api-key':key,'Content-Type':'application/json'},state.remaining()))
                if status!=200:
                    from router_brain import RouterDecisionError
                    raise RouterDecisionError('media_provider_billing' if status==402 else 'media_provider_rate_limit' if status==429 else 'media_provider_auth' if status==401 else 'media_provider_permission' if status==403 else 'media_provider_unavailable')
                response=json.loads(body);data=None
                for candidate in response.get('candidates') or []:
                    for part in (candidate.get('content') or {}).get('parts') or []:
                        inline=part.get('inlineData') or part.get('inline_data')
                        if inline:data=inline.get('data');break
                    if data:break
                if not data:raise ValueError('media_response_missing_image')
                if isinstance(data,str):data=base64.b64decode(data,validate=True)
                from PIL import Image
                with Image.open(io.BytesIO(data)) as img:img.verify()
                state.remaining();root=Path(os.environ.get('HERMES_HOME',str(Path.home()/'.hermes')))/'cache/images'
                root.mkdir(parents=True,exist_ok=True);target=root/('router-'+uuid.uuid4().hex+'.png')
                with Image.open(io.BytesIO(data)) as img:img.save(target,format='PNG')
                return success_response(image=str(target),model=model,prompt=prompt,aspect_ratio=aspect_ratio,provider='e3',
                    modality='image' if refs else 'text',extra={'router_request_id':receipt.get('request_id')})
        except Exception as exc:
            return error_response(error=failure_code(exc),error_type=failure_code(exc),provider='e3',model=model,aspect_ratio=aspect_ratio)


def register_media(ctx):
    ctx.register_image_gen_provider(RoutedImageProvider())
