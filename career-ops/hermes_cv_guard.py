"""CV-only native Hermes budget/write restrictions and independent Discord delivery guard."""
from contextvars import ContextVar
from pathlib import Path
import functools,json,re,sys
REPO=Path(r'C:/Users/mukun/Documents/mukund-chief-control-plane')
if str(REPO/'career-ops') not in sys.path:sys.path.insert(0,str(REPO/'career-ops'))
import cv_golden as golden
CV_ACTIVE=ContextVar('career_cv_active',default=False)
CV_WORKSPACE=ContextVar('career_cv_workspace',default=None)
CV_AGENT_TURNS=8
PROTECTED=[golden.MASTER,golden.MANIFEST,REPO/'career-ops/cv_tailor.py',REPO/'career-ops/cv_golden.py',REPO/'career-ops/master/format_spec.json',REPO/'career-ops/hermes_cv_guard.py']
def cv_request(message,history=()):
 texts=[message]+[m.get('content','') for m in history[-4:] if isinstance(m,dict)]
 return any(re.search(r'\bCV\b|curriculum vitae|cv_tailor|tailor.{0,30}resume',str(t),re.I) for t in texts)
def pre_tool(tool_name,args,**kwargs):
 text=json.dumps(args).replace('\\\\','/').lower()
 mutates=tool_name in {'write_file','patch','apply_patch','terminal','execute_code','python','delegate_task'}
 if mutates and any(str(p).replace('\\','/').lower() in text or p.name.lower() in text for p in PROTECTED):
  if tool_name!='terminal' or not safe_renderer(args.get('command','')):
   return {'action':'block','message':'CV generation failed: immutable master/renderer/layout cannot be changed by an application job.'}
 if not CV_ACTIVE.get():return None
 if tool_name=='terminal':
  if not safe_renderer(args.get('command','')):return {'action':'block','message':'CV generation is bounded: only the canonical renderer command is permitted. Rewrite edits JSON, never code.'}
 elif tool_name in {'write_file','patch','apply_patch'}:
  path=args.get('path') or args.get('file_path') or args.get('file') or ''
  if not path or Path(path).name!='cv_edits.json' or not Path(path).resolve().is_relative_to(golden.OUTPUT_ROOT.resolve()):return {'action':'block','message':'Application writes restricted to the bounded CV output workspace.'}
  state=CV_WORKSPACE.get()
  if isinstance(state,dict):
   parent=Path(path).resolve().parent
   if state['path'] is not None and state['path']!=parent:return {'action':'block','message':'One bounded CV application workspace per job.'}
   state['path']=parent
 elif tool_name in {'execute_code','python','delegate_task'}:return {'action':'block','message':'CV jobs cannot launch a parallel builder or an unbounded repair subagent.'}
 elif tool_name not in {'read_file','file_search','file_read','search_files','web_search','web_extract','skill_view','skills_list','think'}:return {'action':'block','message':'CV jobs allow only read-only research and bounded edits/renderer execution; unknown tools fail closed.'}
 return None

def safe_renderer(command):
 command=command.strip()
 if command.startswith('& '):command=command[2:].strip()
 if any(c in command for c in ';|><`\n\r') or '&' in command or '--force' in command or ' -c ' in command:return False
 import shlex,os
 try:tokens=shlex.split(command,posix=False)
 except ValueError:return False
 if len(tokens)<3:return False
 expected_python=Path(os.environ.get('LOCALAPPDATA',''))/'hermes/hermes-agent/venv/Scripts/python.exe'
 if Path(tokens[0].strip('"')).resolve()!=expected_python.resolve() or Path(tokens[1].strip('"')).resolve()!=(REPO/'career-ops/cv_tailor.py').resolve():return False
 if '--out' not in tokens:return False
 if tokens.index('--out')+1>=len(tokens):return False
 output=Path(tokens[tokens.index('--out')+1].strip('"')).resolve()
 if not output.is_relative_to(golden.OUTPUT_ROOT.resolve()):return False
 state=CV_WORKSPACE.get()
 workspace=state.get('path') if isinstance(state,dict) else state
 if workspace is not None and output.parent!=workspace:return False
 if isinstance(state,dict):state['path']=output.parent
 else:CV_WORKSPACE.set(output.parent)
 return True

def needs_gate(path):
 p=Path(path)
 if p.suffix.lower()!='.pdf':return False
 if bool(re.search(r'\bCV\b|_CV\b|curriculum|resume',p.stem,re.I)) or p.resolve().is_relative_to(golden.OUTPUT_ROOT.resolve()):return True
 # Renaming an old/broken CV must not evade the attachment guard.
 try:
  with golden.pymupdf.open(p) as doc:text=' '.join(page.get_text() for page in doc).lower()
  return 'professional summary' in text and 'education' in text and ('technical skills' in text or 'work experience' in text)
 except Exception:return True

def install_runtime(gateway_module,turn_class,media_class):
 if getattr(turn_class,'_golden_cv_guard_installed',False):
  install_delivery(media_class);return
 old_limit=gateway_module._current_max_iterations
 def bounded():return min(old_limit(),CV_AGENT_TURNS) if CV_ACTIVE.get() else old_limit()
 gateway_module._current_max_iterations=bounded
 old_run=turn_class._run_agent
 @functools.wraps(old_run)
 async def run(self,message,context_prompt,history,*args,**kwargs):
  token=CV_ACTIVE.set(cv_request(message,history));workspace_token=CV_WORKSPACE.set({'path':None})
  try:return await old_run(self,message,context_prompt,history,*args,**kwargs)
  finally:CV_ACTIVE.reset(token);CV_WORKSPACE.reset(workspace_token)
 turn_class._run_agent=run
 turn_class._golden_cv_guard_installed=True
 install_delivery(media_class)

def install_delivery(media_class):
 if getattr(media_class,'_golden_cv_delivery_installed',False):return
 old_send=media_class.send_document
 @functools.wraps(old_send)
 async def send(self,chat_id,file_path,*args,**kwargs):
  if needs_gate(file_path) and not golden.delivery_allowed(file_path):
   from gateway.platforms.base import SendResult
   message='CV generation failed — affected element: PDF verification/delivery; reason: golden-master PASS verification absent or invalid.'
   await self.send(chat_id=chat_id,content=message)
   return SendResult(success=False,error=message)
  return await old_send(self,chat_id,file_path,*args,**kwargs)
 media_class.send_document=send
 media_class._golden_cv_delivery_installed=True

def register(ctx):
 import gateway.run as runtime
 from gateway.run_turn import GatewayTurnMixin
 from plugins.platforms.discord.adapter_media import DiscordMediaMixin
 install_runtime(runtime,GatewayTurnMixin,DiscordMediaMixin)
 ctx.register_hook('pre_tool_call',pre_tool)
 # Hermes lazily loads Discord under hermes_plugins.*, a different module identity.
 # Connect/reload callback must guard the actual live adapter, not only a static import.
 def connected(native,adapter):
  install_delivery(type(adapter))
  import logging
  logging.getLogger(__name__).info('CV golden delivery guard active on actual Discord adapter %s',type(adapter).__module__)
 ctx.register_platform_handler('discord',connected)
