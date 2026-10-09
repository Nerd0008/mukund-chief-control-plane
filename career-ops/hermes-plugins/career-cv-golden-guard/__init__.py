import sys
import importlib
from pathlib import Path
root=Path(r'C:/Users/mukun/Documents/mukund-chief-control-plane/career-ops')
if str(root) not in sys.path:sys.path.insert(0,str(root))
if 'hermes_cv_compiler_guard' in sys.modules:
    importlib.reload(sys.modules['hermes_cv_compiler_guard'])
from hermes_cv_compiler_guard import register
