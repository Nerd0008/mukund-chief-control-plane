#!/usr/bin/env python3
"""Canonical golden-master CV entrypoint. No force, geometry override or repair loop."""
import argparse,json,sys
from pathlib import Path
from cv_golden import MASTER,MANIFEST,generate
# Cover-letter compatibility only; CV rendering never reinserts/subsets fonts.
CMAP_FIXES = {"00a0": "0020", "00ad": "002d", "037e": "003b"}
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--master',default=str(MASTER));p.add_argument('--manifest',default=str(MANIFEST));p.add_argument('--edits',required=True);p.add_argument('--out',required=True);p.add_argument('--report');p.add_argument('--png-dir');args=p.parse_args(argv)
 if Path(args.master).resolve()!=MASTER.resolve() or Path(args.manifest).resolve()!=MANIFEST.resolve():
  print(json.dumps({'status':'FAIL','message':'CV generation failed','reason':'only the canonical golden master/manifest is permitted'}));return 1
 report=generate(MASTER,MANIFEST,json.loads(Path(args.edits).read_text()),args.out)
 report['ok']=report['status']=='PASS'
 if args.report:
  dest=Path(args.report).resolve()
  if not dest.is_relative_to(Path(args.out).resolve().parent):raise ValueError('report outside application workspace')
  dest.write_text(json.dumps(report,indent=2))
 if args.png_dir and report['ok']:
  preview=Path(args.png_dir).resolve()
  if not preview.is_relative_to(Path(args.out).resolve().parent):raise ValueError('preview outside application workspace')
  import pymupdf
  preview.mkdir(exist_ok=True,parents=True)
  with pymupdf.open(args.out) as doc:
   for page in doc:page.get_pixmap(dpi=144).save(str(preview/f'page-{page.number+1}.png'))
 print(json.dumps(report,indent=2));return 0 if report['ok'] else 1
if __name__=='__main__':sys.exit(main())
