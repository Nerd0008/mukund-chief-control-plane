from pathlib import Path
import os,sys
runtime=Path(os.environ['LOCALAPPDATA'])/'hermes/exec-brain'
sys.path.insert(0,str(runtime))
from native_router_plugin import register
