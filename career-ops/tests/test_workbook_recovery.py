"""Recovery safety invariants; temporary workbook copies only."""
import sys,zipfile
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from career_workbook_recovery import patch_package,sha

def package(path):
 with zipfile.ZipFile(path,'w') as z:z.writestr('owned.xml',b'old');z.writestr('owner.xml',b'untouched')

def test_patch_preserves_unrelated_parts_and_verified_backup(tmp_path):
 p=tmp_path/'book.xlsx';package(p);before=sha(p)
 result=patch_package(p,{'owned.xml':b'new'},tmp_path/'audit',before)
 assert sha(result['backup'])==before and sha(p)==result['after_hash']
 with zipfile.ZipFile(p) as z:assert z.read('owner.xml')==b'untouched' and z.read('owned.xml')==b'new'

def test_patch_refuses_stale_source_hash(tmp_path):
 p=tmp_path/'book.xlsx';package(p);before=p.read_bytes()
 with pytest.raises(ValueError,match='drift'):patch_package(p,{'owned.xml':b'new'},tmp_path/'audit','incorrect')
 assert p.read_bytes()==before and not p.with_suffix('.xlsx.career-mail.lock').exists()

def test_patch_refuses_overlapping_mail_writer(tmp_path):
 p=tmp_path/'book.xlsx';package(p);lock=p.with_suffix('.xlsx.career-mail.lock');lock.write_text('active')
 with pytest.raises(FileExistsError):patch_package(p,{},tmp_path/'audit',sha(p))
 assert lock.read_text()=='active'

def test_patch_refuses_drift_immediately_before_commit(tmp_path,monkeypatch):
 import career_workbook_recovery as recovery
 p=tmp_path/'book.xlsx';package(p);before=sha(p);real=recovery.sha;calls=0
 def drift(path):
  nonlocal calls
  if Path(path)==p:
   calls+=1
   if calls==2:return 'drift'
  return real(path)
 monkeypatch.setattr(recovery,'sha',drift)
 with pytest.raises(ValueError,match='before commit'):patch_package(p,{'owned.xml':b'new'},tmp_path/'audit',before)
 assert real(p)==before

@pytest.mark.parametrize('change',['company','owner_status','marker'])
def test_duplicate_discovery_ack_fails_closed_on_conflict(tmp_path,change):
 import tracker_writer as tw
 from openpyxl import load_workbook
 profiles=tw.load_profiles();cfg=tw.region_config(profiles,'singapore');p=tmp_path/'sg.xlsx'
 w=load_workbook(cfg['tracker']);s=w[cfg['sheet']]
 assert tw.verify_workbook(Path(cfg['tracker']),cfg)['ok']
 if change=='company':s['B33']='Distinct Employer'
 elif change=='owner_status':s['R33']='Applied'
 else:s['Z33']='arbitrary override'
 w.save(p);w.close()
 assert not tw.verify_workbook(p,cfg)['ok']
