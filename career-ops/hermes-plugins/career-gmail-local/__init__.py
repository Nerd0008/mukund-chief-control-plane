import sys
from pathlib import Path
root=Path(r'C:/Users/mukun/Documents/mukund-chief-control-plane/career-ops')
if str(root) not in sys.path:sys.path.insert(0,str(root))
from hermes_gmail_tools import register
