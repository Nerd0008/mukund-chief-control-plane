"""One-time template authoring, never part of application execution."""
import json, re, pathlib, hashlib
import pymupdf as fitz
ROOT = pathlib.Path(__file__).parent
SOURCE = pathlib.Path(r'C:/Users/mukun/Downloads/Mukund_Didwania_Tencent_Cyber_Security_Intern_CV.pdf.pdf')
d = fitz.open(SOURCE)
lines = []
for b in d[0].get_text('dict')['blocks']:
    for l in b.get('lines', []):
        spans = [s for s in l['spans'] if s['text'].strip()]
        if spans:
            lines.append(spans)
lines.sort(key=lambda ss: ss[0]['origin'][1])
headings = ['Professional Summary','Technical Skills','Education','Work Experience','Projects','Certifications']
slots = []; section = 'Header'
for ss in lines:
    text = ''.join(s['text'] for s in ss).strip().replace('\xa0',' ')
    bullet = text.startswith(('\ufffd ', '\u2022 '))
    if bullet: text = '\u2022 ' + text[2:]
    text = text.replace('\ufffd','\u2013')
    heading = text in headings
    if heading: section = text
    previous = slots[-1] if slots else None
    # Join natural paragraphs, not glyphs. Typography belongs to the template.
    continuation = (previous and not heading and not bullet and
        ((previous['bullet'] and ss[0]['origin'][0] > 25) or
         (section == 'Professional Summary' and not previous['heading']) or
         (section == 'Education' and text.startswith('Secure Business Architectures'))))
    if continuation:
        sep = '' if previous['text'].endswith('time-') else ' '
        previous['text'] += sep + text
        previous['source_baselines'].append(ss[0]['origin'][1]); continue
    runs = []
    for s in ss:
        t = s['text'].replace('\xa0',' ').replace('\ufffd','\u2013')
        if bullet and not runs: t = '\u2022 ' + t[2:]
        runs.append({'text':t.strip() if len(ss)==1 else t,
                     'style':'bold_italic' if 'BoldItal' in s['font'] else 'bold' if 'Bold' in s['font'] else 'normal'})
    slots.append({'id':f's{len(slots):02d}', 'section':section,'text':text,
                  'runs':runs,'heading':heading,'bullet':bullet,
                  'font_size':11.0 if heading else round(ss[0]['size'],2), 'baseline':ss[0]['origin'][1],
                  'x':ss[0]['origin'][0], 'source_baselines':[ss[0]['origin'][1]],
                  'variable': section in ['Professional Summary','Technical Skills','Work Experience','Projects'] and not heading and (bullet or section in ['Professional Summary','Technical Skills'])})
for i,s in enumerate(slots):
    s['max_lines'] = len(s['source_baselines'])
    s['leading'] = round((s['source_baselines'][-1]-s['baseline'])/(s['max_lines']-1),3) if s['max_lines']>1 else 11.5
    s['width'] = (545.25 if s['section']=='Header' else 545.25)-s['x']
    s['region'] = [s['x'],s['baseline']-s['font_size'],545.25,s['source_baselines'][-1]+3]
    if s['bullet']: s['runs'] = [{'text':s['text'][2:], 'style':'normal'}]
    elif s['max_lines']>1: # joined body / modules
        if s['text'].startswith('Modules: '):
            s['runs']=[{'text':'Modules: ','style':'bold'},{'text':s['text'][9:],'style':'normal'}]
        else: s['runs']=[{'text':s['text'],'style':'normal'}]
layout={'version':2,'status':'PROTOTYPE_NOT_DEPLOYED','master_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'heading_policy':'All six section headings: exactly 11 pt Times New Roman Bold, owner requested 2026-10-09',
        'master_source':'source-master.pdf','page':[595.5,850.5], 'fonts':{'normal':'times.ttf','bold':'timesbd.ttf','italic':'timesi.ttf','bold_italic':'timesbi.ttf'},
        'section_order':headings,'slots':slots,'target_seconds':120,'hard_seconds':180,
        'max_generation_calls':2,'max_renders':2,
        'rules':[{'x1':21.75,'x2':515.25 if s['section']=='Projects' else 545.25,'y':s['baseline']+5,'width':1.0} for s in slots if s['heading']]}
from layout_typography import standardize
standardize(layout)
(ROOT/'layout.json').write_text(json.dumps(layout,indent=2,ensure_ascii=False),encoding='utf-8')
print('slots',len(slots),'variable',sum(s['variable'] for s in slots))
