"""Offline flow-template prototype. Not registered with Hermes.

Only schema-bound, source-evidenced plain text can vary. ReportLab Paragraph
performs real word/line flow inside versioned slots. No PDF glyph surgery.
"""
import hashlib, html, json, pathlib, re, time
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
import pymupdf as fitz
from PIL import Image, ImageChops, ImageDraw

HERE=pathlib.Path(__file__).parent
FONT_NAMES={}
def load_layout():
    layout=json.loads((HERE/'layout.json').read_text(encoding='utf-8'))
    layout['master_source']=str(HERE/layout['master_source'])
    return layout
def digest(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def norm(t): return re.sub(r'\s+([,.;:])',r'\1',re.sub(r'\s+',' ',t)).strip()
def register(layout):
    global FONT_NAMES
    FONT_NAMES={name:'CV_'+pathlib.Path(file).stem for name,file in layout['fonts'].items()}
    for name,file in layout['fonts'].items():
        pdfmetrics.registerFont(TTFont(FONT_NAMES[name],str(pathlib.Path('C:/Windows/Fonts')/file)))
    pdfmetrics.registerFontFamily(FONT_NAMES['normal'],normal=FONT_NAMES['normal'],bold=FONT_NAMES['bold'],italic=FONT_NAMES['italic'],boldItalic=FONT_NAMES['bold_italic'])
def paragraph(slot, replacement=None):
    tags={'normal':('',''),'bold':('<b>','</b>'),'italic':('<i>','</i>'),'bold_italic':('<b><i>','</i></b>')}
    runs=slot['runs'] if replacement is None else [{'text':replacement,'style':'normal'}]
    if replacement is not None and slot['section']=='Technical Skills':
        label=replacement.split(':',1)[0]+': ' if ':' in replacement else slot['runs'][0]['text']
        if replacement.startswith(label):
            runs=[{'text':label,'style':'bold'},{'text':replacement[len(label):],'style':'normal'}]
    markup=''.join(tags[r['style']][0]+html.escape(r['text'])+tags[r['style']][1] for r in runs)
    if slot['id']=='s15' and replacement is None:
        markup=markup.replace(' Secure Business Architectures','<br/>Secure Business Architectures')
    style=ParagraphStyle(slot['id'],fontName=FONT_NAMES['normal'],fontSize=slot['font_size'],leading=slot['leading'],
                         leftIndent=6.75 if slot['bullet'] else 0,firstLineIndent=0,
                         bulletIndent=0,bulletFontName=FONT_NAMES['normal'],bulletFontSize=slot['font_size'],
                         splitLongWords=False,alignment=4 if slot['section']=='Professional Summary' else 0)
    return Paragraph(markup,style,bulletText='\u2022' if slot['bullet'] else None)
def expected_text(slot, replacement=None):
    if replacement is not None: return ('\u2022 ' if slot['bullet'] else '')+replacement
    return slot['text']
def content_check(layout, content):
    failures=[]; slots={s['id']:s for s in layout['slots']}
    if content:
        summary=next(s for s in layout['slots'] if s['section']=='Professional Summary' and s['variable'])
        text=norm(content.get(summary['id'],{}).get('text',summary['text'])).lower()
        checks={'MSc Information Security':'msc information security' in text,
                'CompTIA Security+':'comptia security+' in text,
                'ISC2 CC':('isc2 cc' in text or 'isc2 certified in cybersecurity (cc)' in text)}
        for credential,present in checks.items():
            if not present:failures.append({'slot':summary['id'],'reason':'mandatory summary credential missing','credential':credential})
    for key,item in content.items():
        s=slots.get(key)
        if not s or not s['variable']: failures.append({'slot':key,'reason':'immutable/unknown slot'}); continue
        if not isinstance(item,dict) or not isinstance(item.get('text'),str):
            failures.append({'slot':key,'reason':'invalid structured content'}); continue
        text=item['text']
        if not text.strip() or '\n\n' in text or any(c in text for c in '<>\ufffd'):
            failures.append({'slot':key,'reason':'blank line, markup, or invalid text'}); continue
        if s['section']=='Technical Skills' and (':' not in text or not text.split(':',1)[1].strip()):
            failures.append({'slot':key,'reason':'missing skill label/value'}); continue
        # A selected source must be explicit and the content must be verbatim from it.
        # Paraphrase claims require a future independently reviewed fact validator.
        sources=item.get('sources',[])
        if not sources or any(k not in slots for k in sources):
            failures.append({'slot':key,'reason':'missing fact provenance'}); continue
        hay=' '.join(expected_text(slots[k]).removeprefix('\u2022 ') for k in sources)
        verified=False
        if 'variant' in item:
            bank_path=HERE/'fact_bank.json'
            bank=json.loads(bank_path.read_text(encoding='utf-8')) if bank_path.exists() else {}
            variant=bank.get('slots',{}).get(key,{}).get(item['variant'])
            verified=(bank.get('master_sha256')==layout['master_sha256'] and variant is not None and
                      text==variant['text'] and sources==variant['sources'])
        else: verified=norm(text) in norm(hay)
        if not verified: failures.append({'slot':key,'reason':'unverified/invented content'})
        if (s['bullet'] or s['section']=='Professional Summary') and not text.rstrip().endswith(('.', '!', '?')):
            failures.append({'slot':key,'reason':'incomplete sentence'})
    return failures
def fit(layout, content):
    register(layout); failures=content_check(layout,content)
    for s in layout['slots']:
        p=paragraph(s,content.get(s['id'],{}).get('text'))
        width,height=p.wrap(s['width'],1000)
        if len(p.blPara.lines)>s['max_lines'] or any(getattr(l,'extraSpace',l[0] if isinstance(l,tuple) else 0)<-.3 for l in p.blPara.lines):
            failures.append({'slot':s['id'],'reason':'content capacity exceeded','max_lines':s['max_lines']})
        if s['id'] in content and len(p.blPara.lines)<s['max_lines']:
            failures.append({'slot':s['id'],'reason':'content underfills slot, leaving unexpected blank line','required_lines':s['max_lines']})
    return failures
def render(layout, content, output):
    register(layout); output=pathlib.Path(output); output.parent.mkdir(parents=True,exist_ok=True)
    c=canvas.Canvas(str(output),pagesize=layout['page'],invariant=1,pageCompression=1)
    c.setTitle('Mukund Didwania CV - flow-template prototype')
    for rule in layout['rules']:
        c.setLineWidth(rule['width']); c.line(rule['x1'],layout['page'][1]-rule['y'],rule['x2'],layout['page'][1]-rule['y'])
    for s in layout['slots']:
        p=paragraph(s,content.get(s['id'],{}).get('text')); _,h=p.wrap(s['width'],1000)
        # Paragraph first baseline is height minus its font size.
        p.drawOn(c,s['x'],layout['page'][1]-s['baseline']-h+s['font_size'])
    c.showPage(); c.save()
def validate(layout, content, pdf):
    failures=fit(layout,content); d=fitz.open(pdf)
    if len(d)!=1 or any(abs(a-b)>.01 for a,b in zip(d[0].rect[2:],layout['page'])):
        failures.append({'slot':'page','reason':'page dimensions/count'})
    spans=[s for b in d[0].get_text('dict')['blocks'] for l in b.get('lines',[]) for s in l['spans']]
    for s in layout['slots']:
        region=fitz.Rect(s['region']); found=[]
        for t in spans:
            # Baseline-based slot association avoids shared font ascender bbox edges.
            if s['baseline']-.2<=t['origin'][1]<=region.y1 and region.x0-.1<=t['origin'][0]<=region.x1:
                found.append(t)
        actual=norm(' '.join(t['text'] for t in found))
        if actual!=norm(expected_text(s,content.get(s['id'],{}).get('text'))):
            failures.append({'slot':s['id'],'reason':'missing/corrupted/overflow ATS text','expected':expected_text(s,content.get(s['id'],{}).get('text')),'actual':actual})
        allowed={'TimesNewRomanPSMT','TimesNewRomanPS-BoldMT','TimesNewRomanPS-BoldItalicMT','TimesNewRomanPS-BoldItal'}
        if s['section']=='Technical Skills' and not s['heading']:
            label=content.get(s['id'],{}).get('text',s['text']).split(':',1)[0]+':'
            if not any('Bold' in t['font'] and norm(t['text'])==norm(label) for t in found):
                failures.append({'slot':s['id'],'reason':'missing bold skill label'})
        for t in found:
            if t['font'] not in allowed or abs(t['size']-s['font_size'])>.02:
                failures.append({'slot':s['id'],'reason':'wrong font/size'})
            if not s['heading'] and (s['bullet'] or s['section']=='Professional Summary') and ('Bold' in t['font'] or 'Ital' in t['font']):
                failures.append({'slot':s['id'],'reason':'unexpected emphasis'})
            if t['bbox'][2]>region.x1+.2: failures.append({'slot':s['id'],'reason':'clipped/overflow text'})
            offset=(t['origin'][1]-s['baseline'])/s['leading']
            if abs(offset-round(offset))*s['leading']>.2:
                failures.append({'slot':s['id'],'reason':'baseline/line spacing moved'})
            style='bold_italic' if 'BoldItal' in t['font'] else 'bold' if 'Bold' in t['font'] else 'normal'
            # Ordinary content cannot acquire emphasis; fixed heading/title/label runs
            # are the only source of emphasis. Also reject missing required emphasis.
            if s['heading'] and style!='bold': failures.append({'slot':s['id'],'reason':'heading emphasis changed'})
            label=content.get(s['id'],{}).get('text',s['text']).split(':',1)[0]+':'
            if s['section']=='Technical Skills' and not s['heading'] and style=='bold' and norm(t['text'])!=norm(label):
                failures.append({'slot':s['id'],'reason':'unexpected bold skills'})
            if s['id'] not in content:
                allowed_text=' '.join(r['text'] for r in s['runs'] if r['style']==style)
                if norm(t['text']) not in norm(allowed_text) and t['text'].strip()!='\u2022':
                    failures.append({'slot':s['id'],'reason':'template emphasis/font weight changed'})
    reference=HERE/'output'/'original-content-reproduction.pdf'
    if reference.exists():
        def raster(doc):
            pix=doc[0].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
            return Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
        base=raster(fitz.open(reference)); actual=raster(d)
        if base.size==actual.size:
            mask=Image.new('L',base.size,255); draw=ImageDraw.Draw(mask)
            for s in layout['slots']:
                if s['id'] in content:
                    x0,y0,x1,y1=s['region']
                    draw.rectangle([int(2*x0)-1,int(2*y0)-1,int(2*x1)+1,int(2*y1)+1],fill=0)
            diff=ImageChops.difference(base,actual)
            bands=diff.split(); high=ImageChops.lighter(ImageChops.lighter(bands[0],bands[1]),bands[2]).point(lambda v:255 if v>16 else 0)
            changed=ImageChops.multiply(high,mask)
            if changed.getbbox(): failures.append({'slot':'visual','reason':'unexpected pixels outside approved content regions'})
    return {'status':'PASS' if not failures else 'FAIL','failures':failures,'page_count':len(d),'pdf_sha256':digest(pdf)}
def reproduce(output):
    started=time.monotonic(); layout=load_layout()
    if digest(layout['master_source'])!=layout['master_sha256']: raise ValueError('master hash mismatch')
    t=time.monotonic(); render(layout,{},output); rendered=time.monotonic()-t
    t=time.monotonic(); result=validate(layout,{},output); validated=time.monotonic()-t
    result.update(total_seconds=time.monotonic()-started,render_seconds=rendered,validation_seconds=validated,
                  content_generation_seconds=0,model_calls=0,owner_visual_acceptance=False,not_deployed=True)
    pathlib.Path(str(output)+'.verification.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    return result
if __name__=='__main__':
    print(json.dumps(reproduce(HERE/'output'/'original-content-reproduction.pdf'),indent=2,ensure_ascii=True))
