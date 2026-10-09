"""Strict independent golden-master CV audit; no layout exemptions."""
import argparse,json,sys
from pathlib import Path
import pymupdf
import cv_golden as g
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('pdf');p.add_argument('--edits',required=True);args=p.parse_args(argv)
 manifest=json.loads(g.MANIFEST.read_text())
 with pymupdf.open(g.MASTER) as doc:plan=g.prepare(doc,manifest,json.loads(Path(args.edits).read_text()))
 report=g.verify(g.MASTER,args.pdf,manifest,plan);print(json.dumps(report,indent=2));return 0 if report['status']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
