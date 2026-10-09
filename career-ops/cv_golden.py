"""Golden-master CV pipeline: native glyph-stream edits, one render, fail-closed delivery."""
from __future__ import annotations
import argparse,contextlib,copy,hashlib,json,os,re,tempfile
from pathlib import Path
import pymupdf
from PIL import Image,ImageChops
HERE=Path(__file__).resolve().parent
MASTER=HERE/'master/CV_FORMAT_MASTER.pdf'
MANIFEST=HERE/'master/cv_master_manifest.json'
OUTPUT_ROOT=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'hermes/runtime/career-ops/cv-output'
MAX_FIT_ATTEMPTS=3
BT=re.compile(rb'BT\s.*?\sET',re.S)
STR=re.compile(rb'(\((?:\\.|[^\\)])*\)|<[0-9a-fA-F\s]+>)\s*Tj',re.S)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pdfbytes(token):
 if token.startswith(b'<'):return bytes.fromhex(token[1:-1].decode())
 value=token[1:-1];out=bytearray();i=0
 while i<len(value):
  c=value[i];i+=1
  if c!=92:out.append(c);continue
  c=value[i];i+=1
  if 48<=c<=55:
   digits=bytes([c])
   while i<len(value) and len(digits)<3 and 48<=value[i]<=55:digits+=bytes([value[i]]);i+=1
   out.append(int(digits,8));continue
  if c in (10,13):
   if c==13 and i<len(value) and value[i]==10:i+=1
   continue
  out.append({110:10,114:13,116:9,98:8,102:12}.get(c,c))
 return bytes(out)
def numbers(text):
 tokens=re.findall(r'\[|\]|-?\d+(?:\.\d+)?',text);i=0
 def arr():
  nonlocal i
  result=[];i+=1
  while tokens[i]!=']':
   if tokens[i]=='[':result.append(arr())
   else:result.append(float(tokens[i]));i+=1
  i+=1;return result
 return arr()
def fonts(doc):
 result={}
 for page in doc:
  for xref,_,_,name,ref,*_ in page.get_fonts(full=True):
   if ref in result:continue
   kind,key=doc.xref_get_key(xref,'ToUnicode');cmap=doc.xref_stream(int(key.split()[0])).decode('ascii');decode={}
   for block in re.findall(r'beginbfchar(.*?)endbfchar',cmap,re.S):
    for a,b in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>',block):decode[int(a,16)]=bytes.fromhex(b).decode('utf-16-be')
   for block in re.findall(r'beginbfrange(.*?)endbfrange',cmap,re.S):
    for a,b,c in re.findall(r'<(\w+)>\s*<(\w+)>\s*<(\w+)>',block):
     for n in range(int(a,16),int(b,16)+1):decode[n]=chr(int(c,16)+n-int(a,16))
   descendant=int(re.search(r'\d+',doc.xref_get_key(xref,'DescendantFonts')[1]).group());w=numbers(doc.xref_get_key(descendant,'W')[1]);widths={};i=0
   while i<len(w):
    start=int(w[i]);i+=1
    if isinstance(w[i],list):
     for offset,v in enumerate(w[i]):widths[start+offset]=v
     i+=1
    else:
     end=int(w[i]);width=w[i+1];i+=2
     for n in range(start,end+1):widths[n]=width
   result[ref]={'font':name.split('+')[-1],'decode':decode,'encode':{v:k for k,v in decode.items()},'widths':widths,'default_width':float(doc.xref_get_key(descendant,'DW')[1]) if doc.xref_get_key(descendant,'DW')[0]!='null' else 1000}
 return result

def blocks(doc,fontmap):
 out=[]
 for xref in range(1,doc.xref_length()):
  if not doc.xref_is_stream(xref):continue
  stream=doc.xref_stream(xref)
  for match in BT.finditer(stream):
   body=match.group();refs=re.findall(rb'/([\w]+)\s+[\d.]+\s+Tf',body)
   if len(refs)!=1 or refs[0].decode() not in fontmap:continue
   ref=refs[0].decode();fm=fontmap[ref];raw=b''.join(pdfbytes(m.group(1)) for m in STR.finditer(body))
   try:text=''.join(fm['decode'][int.from_bytes(raw[i:i+2],'big')] for i in range(0,len(raw),2))
   except KeyError:continue
   out.append({'xref':xref,'start':match.start(),'end':match.end(),'body':body,'text':text,'font_ref':ref})
 return out

def spans(doc):
 out=[]
 for page in doc:
  for block in page.get_text('dict')['blocks']:
   if block.get('type')==0:
    for line in block['lines']:
     for s in line['spans']:out.append({'page':page.number,'text':s['text'],'bbox':list(s['bbox']),'origin':list(s['origin']),'font':s['font'],'size':s['size']})
 return out

def build_manifest(master):
 with pymupdf.open(master) as d:
  ss=spans(d);fm=fonts(d);bb=blocks(d,fm);sections=[s for s in ss if s['size']>10.5 and s['text'].strip()];items=[]
  for i,s in enumerate(ss):
   candidates=[b for b in bb if b['text'].strip()==s['text'].strip() and fm[b['font_ref']]['font']==s['font']]
   right=[t for t in ss if t['page']==s['page'] and abs(t['origin'][1]-s['origin'][1])<1 and t['origin'][0]>s['bbox'][2]+.1]
   boundary=min([t['bbox'][0] for t in right]+[d[s['page']].rect.width-21.75])
   section=max([t for t in sections if t['page']==s['page'] and t['origin'][1]<=s['origin'][1]],key=lambda t:t['origin'][1],default={'text':'Identity'})['text'].strip()
   label=section=='Technical Skills' and s['size']<10.5 and s['text'].strip().endswith(':')
   editable=len(candidates)==1 and ((s['font'].endswith('PSMT') and len(s['text'].strip())>35) or label) and section not in ('Identity','Education','Certifications')
   chars=[c for block in d[s['page']].get_text('rawdict')['blocks'] if block.get('type')==0 for line in block['lines'] for raw in line['spans'] if abs(raw['origin'][0]-s['origin'][0])<.001 and abs(raw['origin'][1]-s['origin'][1])<.001 for c in raw['chars'] if c['c'].strip()]
   glyph_origin=chars[0]['origin'] if chars else s['origin']
   item={**s,'id':f'p{s["page"]}-s{i}','section':section,'editable':editable,'glyph_origin':list(glyph_origin),'label':label,'available_width':max(0,boundary-glyph_origin[0]),'neighbours':[t['bbox'] for t in ss if t is not s and t['page']==s['page'] and abs(t['origin'][1]-s['origin'][1])<15]}
   if editable:item.update(stream_xref=candidates[0]['xref'],stream_start=candidates[0]['start'],stream_end=candidates[0]['end'],font_ref=candidates[0]['font_ref'])
   items.append(item)
  return {'schema':1,'master_sha256':sha(master),'pages':[{'rect':list(p.rect),'mediabox':list(p.mediabox),'cropbox':list(p.cropbox),'rotation':p.rotation} for p in d],'page_count':len(d),'spans':items,'policy':{'max_fit_attempts':3,'char_delta':.15,'raster_dpi':144,'pixel_channel_tolerance':0,'region_edge_tolerance_pixels':1,'render_attempts':1}}

def fit(span,text,fm,policy):
 if '\n' in text or '\r' in text or not text.strip():return 'replacement must be one nonempty line'
 if ((len(text.strip())>len(span['text'].strip())*(1+policy['char_delta'])) if span.get('label') else (abs(len(text.strip())-len(span['text'].strip()))/max(1,len(span['text'].strip()))>policy['char_delta'])):return 'character budget exceeded'
 if any(c not in fm['encode'] for c in text):return 'glyph absent from immutable master font'
 width=sum(fm['widths'].get(fm['encode'][c],fm['default_width']) for c in text)/1000*span['size']
 if width>span['available_width']:return 'rendered width overflow'
 return None

def prepare(doc,manifest,spec,rewrite=None,budget=None,save_budget=None):
 fm=fonts(doc);plan=[];seen=set()
 for e in spec.get('edits',[]):
  if set(e)-{'find','replace','span_id','alternatives'}:raise ValueError('geometry/font overrides and force exemptions forbidden')
  matches=[s for s in manifest['spans'] if s['id']==e.get('span_id') or ('span_id' not in e and s['text'].strip()==e.get('find','').strip())]
  if len(matches)!=1 or not matches[0]['editable']:raise ValueError('affected span absent, ambiguous or immutable: '+e.get('find',e.get('span_id','')))
  s=matches[0]
  if s['id'] in seen:raise ValueError('duplicate span edit')
  seen.add(s['id']);candidate=e['replace'].strip();reason=None
  used=(budget or {}).get(s["id"],0)
  if used>=MAX_FIT_ATTEMPTS:raise ValueError(s["id"]+": three content-fit attempts exhausted")
  for attempt in range(used+1,MAX_FIT_ATTEMPTS+1):
   if budget is not None:
    budget[s["id"]]=attempt
    if save_budget:save_budget()
   reason=fit(s,candidate,fm[s['font_ref']],manifest['policy'])
   if reason is None:break
   if attempt==MAX_FIT_ATTEMPTS:break
   if rewrite is not None:candidate=rewrite(s,candidate,reason,attempt).strip()
   elif len(e.get('alternatives',[]))>=attempt:candidate=e['alternatives'][attempt-1].strip()
   else:raise ValueError(s['id']+': content rewrite required: '+reason)
  if reason:raise ValueError(s['id']+': three content-fit attempts exhausted: '+reason)
  plan.append({'span':s,'replace':candidate,'attempts':attempt,'encoded':b''.join(fm[s['font_ref']]['encode'][c].to_bytes(2,'big') for c in candidate)})
 return plan

def render_once(doc,plan,out):
 grouped={}
 for p in plan:grouped.setdefault(p['span']['stream_xref'],[]).append(p)
 for xref,edits in grouped.items():
  data=doc.xref_stream(xref)
  for p in sorted(edits,key=lambda e:e['span']['stream_start'],reverse=True):
   s=p['span'];body=data[s['stream_start']:s['stream_end']]
   matrices=list(re.finditer(rb'[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+Tm',body))
   if len(matrices)!=1:raise ValueError(s['id']+': unsupported text matrix; no repair permitted')
   new=body[:matrices[0].end()]+b'\n<'+p['encoded'].hex().encode()+b'> Tj\nET'
   data=data[:s['stream_start']]+new+data[s['stream_end']:]
  doc.update_stream(xref,data,compress=False)
 doc.save(out,no_new_id=True,garbage=0,deflate=False)

def verify(master,out,manifest,plan):
 problems=[]
 with pymupdf.open(master) as a,pymupdf.open(out) as b:
  if len(a)!=len(b):return {'status':'FAIL','problems':['page count changed']}
  original=spans(a);actual=spans(b);edited={p['span']['id']:p for p in plan}
  expected=[]
  for s in manifest['spans']:
   p=edited.get(s['id']);expected.append({k:(p['replace'] if k=='text' and p else s[k]) for k in ('page','text','origin','font','size')})
  remaining=actual.copy()
  for idx,s in enumerate(expected):
   is_edit=manifest['spans'][idx]['id'] in edited
   match=next((v for v in remaining if v['page']==s['page'] and (v['text'].strip()==s['text'].strip() if is_edit else v['text']==s['text']) and v['font']==s['font'] and abs(v['size']-s['size'])<.001 and all(abs(x-y)<.001 for x,y in zip(v['origin'],s['origin']))),None)
   if match is None:problems.append('text/font/baseline mismatch: '+s['text'][:55])
   else:remaining.remove(match)
  if any(v['text'].strip() for v in remaining):problems.append('unexpected text spans')
  # Whitespace extraction may regroup after an edit, but its native PDF objects
  # must remain byte-identical. Every non-edited stream/object is immutable.
  grouped={}
  for p in plan:grouped.setdefault(p['span']['stream_xref'],[]).append(p)
  for x in range(1,a.xref_length()):
   if not a.xref_is_stream(x):continue
   expected_stream=a.xref_stream(x)
   for p in sorted(grouped.get(x,[]),key=lambda e:e['span']['stream_start'],reverse=True):
    z=p['span'];body=expected_stream[z['stream_start']:z['stream_end']]
    tm=list(re.finditer(rb'[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+Tm',body))[0]
    new=body[:tm.end()]+b'\n<'+p['encoded'].hex().encode()+b'> Tj\nET'
    expected_stream=expected_stream[:z['stream_start']]+new+expected_stream[z['stream_end']:]
   if b.xref_stream(x)!=expected_stream:problems.append('unauthorised native PDF stream change: '+str(x))
  for p in plan:
   s=p['span'];err=fit(s,p['replace'],fonts(a)[s['font_ref']],manifest['policy'])
   if err:problems.append(s['id']+': '+err)
  pixel_count=0
  for i,(pa,pb) in enumerate(zip(a,b)):
   if list(pa.rect)!=list(pb.rect) or list(pa.mediabox)!=list(pb.mediabox) or list(pa.cropbox)!=list(pb.cropbox) or pa.rotation!=pb.rotation:problems.append('page geometry changed')
   aa=pa.get_pixmap(dpi=144,alpha=False);bb=pb.get_pixmap(dpi=144,alpha=False)
   if (aa.width,aa.height)!=(bb.width,bb.height):continue
   im1=Image.frombytes('RGB',(aa.width,aa.height),aa.samples);im2=Image.frombytes('RGB',(bb.width,bb.height),bb.samples);diff=ImageChops.difference(im1,im2)
   from PIL import ImageDraw
   draw=ImageDraw.Draw(diff)
   for p in plan:
    s=p['span']
    if s['page']!=i:continue
    fm=fonts(a)[s['font_ref']];width=sum(fm['widths'].get(fm['encode'][c],fm['default_width']) for c in p['replace'])/1000*s['size'];x0,y0,x1,y1=s['bbox']
    # One pixel edge tolerance is documented. Never mask a section or whole page.
    import math
    draw.rectangle((math.floor(x0*2)-1,math.floor(y0*2)-1,math.ceil(max(x1,s.get('glyph_origin',s['origin'])[0]+width)*2)+1,math.ceil(y1*2)+1),fill=0)
   pixel_count+=sum(any(rgb) for rgb in diff.getdata())
  if pixel_count:problems.append(f'unexpected pixels outside approved regions: {pixel_count}')
  if '\ufffd' in ''.join(p.get_text() for p in b):problems.append('invalid ATS text')
 return {'status':'FAIL' if problems else 'PASS','problems':problems,'outside_region_changed_pixels':pixel_count,'verified_spans':len(expected),'raster_dpi':144,'pixel_channel_tolerance':0,'edge_tolerance_pixels':1}

@contextlib.contextmanager
def immutable_files(paths):
 before={str(p):sha(p) for p in paths};handles=[]
 try:
  if os.name=='nt':
   import ctypes,msvcrt
   from ctypes import wintypes
   lib=ctypes.WinDLL('kernel32',use_last_error=True);create=lib.CreateFileW;create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE];create.restype=wintypes.HANDLE
   for p in paths:
    h=create(str(Path(p).resolve()),0x80000000,1,None,3,0x80,None)
    if h==ctypes.c_void_p(-1).value:raise ValueError('immutable dependency busy: '+str(p))
    handles.append(os.fdopen(msvcrt.open_osfhandle(h,os.O_RDONLY|os.O_BINARY),'rb'))
  yield before
 finally:
  for h in handles:h.close()
  if {str(p):sha(p) for p in paths}!=before:raise ValueError('immutable dependency hash changed; generation aborted')

def delivery_allowed(pdf):
 pdf=Path(pdf).resolve();report=pdf.with_suffix('.verification.json')
 try:
  if not pdf.is_relative_to(OUTPUT_ROOT.resolve()):return False
  r=json.loads(report.read_text())
  if not (r['status']=='PASS' and r['output_sha256']==sha(pdf) and r['master_sha256']==sha(MASTER) and r['manifest_sha256']==sha(MANIFEST) and all(sha(Path(p))==v for p,v in r['immutable_after'].items())):return False
  manifest=json.loads(MANIFEST.read_text())
  with pymupdf.open(MASTER) as doc:plan=prepare(doc,manifest,{'edits':r['approved_edits']})
  return verify(MASTER,pdf,manifest,plan)['status']=='PASS'
 except (OSError,KeyError,ValueError):return False

def generate(master,manifest_path,spec,out,rewrite=None):
 out=Path(out).resolve();manifest_path=Path(manifest_path);master=Path(master)
 if out==master.resolve() or not out.is_relative_to(OUTPUT_ROOT.resolve()):raise ValueError('output outside bounded CV application workspace')
 if out.exists():raise ValueError('output already exists; use a fresh application workspace')
 out.parent.mkdir(parents=True,exist_ok=True);manifest=json.loads(manifest_path.read_text());report_path=out.with_suffix('.verification.json');temp=out.with_suffix('.candidate.pdf');report={'status':'FAIL','problems':[]}
 protected=[master,manifest_path,HERE/'cv_tailor.py',Path(__file__),HERE/'hermes_cv_guard.py',HERE/'master/format_spec.json']
 try:
  ledger_path=out.parent/'content_fit_verification.json'
  ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else {'attempts':{},'render_attempts':0}
  def save_ledger():ledger_path.write_text(json.dumps(ledger,indent=2))
  if ledger['render_attempts']:raise ValueError('one-render job budget exhausted; no visual repair loop permitted')
  with immutable_files(protected) as before:
   if sha(master)!=manifest['master_sha256']:raise ValueError('master differs from versioned manifest')
   with pymupdf.open(master) as doc:
    plan=prepare(doc,manifest,spec,rewrite,ledger['attempts'],save_ledger);ledger['render_attempts']=1;save_ledger();render_once(doc,plan,str(temp))
   report=verify(master,temp,manifest,plan);report.update(immutable_before=before,immutable_after={str(p):sha(p) for p in protected},master_sha256=sha(master),manifest_sha256=sha(manifest_path),content_fit_attempts={p['span']['id']:p['attempts'] for p in plan},render_attempts=1,approved_edits=[{'span_id':p['span']['id'],'replace':p['replace']} for p in plan])
   if report['status']!='PASS':raise ValueError('; '.join(report['problems']))
  os.replace(temp,out);report['output_sha256']=sha(out)
 except Exception as e:
  report.update(status='FAIL',problems=[str(e)],message='CV generation failed');temp.unlink(missing_ok=True)
 report_path.write_text(json.dumps(report,indent=2))
 return report
