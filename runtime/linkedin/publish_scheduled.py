"""Compatibility entrypoint: canonical exact-date LinkedIn scheduled publisher."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'career-ops'))
from linkedin_scheduled import main

if __name__=='__main__':raise SystemExit(main())
