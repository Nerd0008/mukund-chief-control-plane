"""Unattended activation guards, no Google/network calls."""
import sys,json,copy
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import career_mail_monitor as m
from test_career_mail_monitor import mail,assess
class Tracker:
 def __init__(self,records=(),drift=False):self.records=list(records);self.writes=[];self.reads=0;self.drift=drift
 def read(self):
  self.reads+=1
  return copy.deepcopy(self.records),{'uk':'changed' if self.drift and self.reads>1 else 'original'}
 def upsert(self,r):self.writes.append(r);return {'ok':True}
class Reader:
 def __init__(self,messages):self.messages=messages;self.cursor=None
 def read_window(self,cursor,**kwargs):self.cursor=cursor;return {'messages':self.messages,'mode':'incremental','checkpoint':'200'}
def setup(root):m.atomic_json(root/'write-approval.json',{'approved_report_id':'fixture'})
def test_uncertain_and_unconfirmed_new_application_never_written(tmp_path):
 setup(tmp_path);t=Tracker();r=m.run_scan({'backfill_days':30,'max_messages':10},tmp_path,apply=True,reader=Reader([mail()]),tracker=t)
 assert not t.writes and r['tracker_writes']==0
 assert json.loads((tmp_path/'pending-review.json').read_text())['m1']['needs_review']
 assert json.loads((tmp_path/'checkpoint.json').read_text())['history_id']=='200'
def test_confident_existing_application_can_update(tmp_path):
 setup(tmp_path);records=m.reconcile([mail()],[])['proposed_records'];records[0]['row']=3
 t=Tracker(records);r=m.run_scan({'backfill_days':30,'max_messages':10},tmp_path,apply=True,reader=Reader([mail('new',body='Your application is under review.')]),tracker=t)
 assert len(t.writes)==1 and r['tracker_writes']==1

def test_drift_aborts_without_checkpoint(tmp_path):
 setup(tmp_path);t=Tracker(drift=True)
 with pytest.raises(ValueError,match='drift'):m.run_scan({'backfill_days':30,'max_messages':10},tmp_path,apply=True,reader=Reader([]),tracker=t)
 assert not (tmp_path/'checkpoint.json').exists() and not t.writes

def test_approved_apply_uses_verified_baseline_without_acknowledging_review(tmp_path):
 setup(tmp_path);baseline={'checkpoint_proposed':'100'};baseline['report_id']=m.report_hash(baseline);bp=tmp_path/'baseline.json';m.atomic_json(bp,baseline)
 reader=Reader([]);m.run_scan({'backfill_days':30,'max_messages':10,'initial_baseline_report':str(bp)},tmp_path,apply=True,reader=reader,tracker=Tracker())
 assert reader.cursor=='100'
 assert json.loads((tmp_path/'checkpoint.json').read_text())['processed_ids']==[]

def test_write_failure_does_not_advance_checkpoint(tmp_path):
 setup(tmp_path);records=m.reconcile([mail()],[])['proposed_records'];records[0]['row']=3
 class Failing(Tracker):
  def upsert(self,r):raise OSError('fixture failure')
 with pytest.raises(OSError):m.run_scan({'backfill_days':30,'max_messages':10},tmp_path,apply=True,reader=Reader([mail('new',body='Your application is under review.')]),tracker=Failing(records))
 assert not (tmp_path/'checkpoint.json').exists()


def test_previously_review_only_message_cannot_be_automatically_promoted(tmp_path):
 setup(tmp_path);records=m.reconcile([mail()],[])['proposed_records'];records[0]['row']=3
 m.atomic_json(tmp_path/'pending-review.json',{'new':{'gmail_message_id':'new','needs_review':True}})
 t=Tracker(records);r=m.run_scan({'backfill_days':30,'max_messages':10},tmp_path,apply=True,reader=Reader([mail('new',body='Your application is under review.')]),tracker=t)
 assert not t.writes and r['tracker_writes']==0
 assert json.loads((tmp_path/'pending-review.json').read_text())['new']['needs_review']
