from pathlib import Path
import copy
import openpyxl,pytest
import tracker_writer as tw

URL='https://employer.com/jobs/12345678'

def workbook(path,url):
    wb=openpyxl.Workbook();ws=wb.active;ws.title='Jobs'
    ws.append(['UK jobs']);ws.append(['Date Found','Company','Role Title','Apply Link','Application Deadline','Status'])
    if url:ws.append(['2026-10-26','Example','Cyber Intern',url,'UNKNOWN','Not Applied'])
    wb.save(path);wb.close()

@pytest.mark.parametrize('suffix',['.write-tmp.xlsx','.rollback-tmp.xlsx'])
def test_uncommitted_stages_are_not_archive_evidence(tmp_path,suffix):
    profile={'canonical_dir':str(tmp_path),'career_ops_root':str(tmp_path)}
    cfg={'region':'uk','sheet':'Jobs','dedupe':{'url_column':'D'},'first_data_row':3}
    stage=tmp_path/('uk-cyber-job-tracker'+suffix);workbook(stage,URL)
    committed=tmp_path/'uk-cyber-job-tracker-2026-09.xlsx';archived='https://employer.com/jobs/87654321';workbook(committed,archived)
    report=tw.build_cross_month_index(profile,cfg)
    assert tw.normalize_url(URL) not in report['url_keys']
    assert tw.normalize_url(archived) in report['url_keys']

def test_failed_replace_preserves_canonical_and_removes_own_stage(tmp_path,monkeypatch):
    profile=copy.deepcopy(tw.load_profiles());path=tmp_path/'uk-cyber-job-tracker.xlsx';workbook(path,None);before=path.read_bytes()
    profile['canonical_dir']=str(tmp_path);profile['career_ops_root']=str(tmp_path);profile['backup_dir']=str(tmp_path/'backups');profile['regions']['uk']['tracker']=str(path)
    original=Path.replace
    def replace(self,target):
        if self==path.with_suffix('.write-tmp.xlsx'):raise PermissionError('fixture workbook held by Excel')
        return original(self,target)
    monkeypatch.setattr(Path,'replace',replace)
    with pytest.raises(PermissionError):
        tw.write_records(profile,'uk',[{'company':'Example','title':'Cyber Intern','url':URL,'location':'London, United Kingdom','deadline':'UNKNOWN'}],apply=True,cleanup_existing=False)
    assert path.read_bytes()==before
    assert not path.with_suffix('.write-tmp.xlsx').exists()
