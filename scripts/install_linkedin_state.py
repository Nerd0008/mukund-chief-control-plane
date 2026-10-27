"""Install thin LinkedIn state wrappers; never enable a publish job or publish."""
from __future__ import annotations
import argparse,datetime,hashlib,json,os,shutil,sys
from pathlib import Path
REPO=Path(__file__).resolve().parent.parent
HOME=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'hermes'
sys.path.insert(0,str(REPO/'career-ops'))
import linkedin_state as state

PREFIX='''Canonical LinkedIn state (required before any narrative status):
Run the Hermes Python interpreter on career-ops/linkedin_state.py week in the canonical repository.
Use its phase, owner_approved, reviews_ready, content_ready, slot_matches and job.enabled exactly.
Owner approval, verification and scheduled publication are separate states. Preserve an already
approved unchanged post and present it as APPROVED_BUT_BLOCKED or APPROVED_READY_PAUSED when applicable.
Do not ask the owner to approve those unchanged bytes again. A directory name, plan, confirm token,
old chat summary or last_status=ok is not proof that a post is approved or scheduled.
The exact-date manifest and canonical state resolver are authoritative. Do not guess the newest folder.
Do not enable publishing jobs, publish, create receipts, or alter an approved post in this drafting run.
New unapproved Wednesday/Thursday texts remain chat drafts only. If a state command fails, report that
failure instead of inventing readiness. After state inspection, apply the existing topic/content rules.

'''


def payloads():
    boot=f"import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path({str(REPO)!r})/'career-ops'))\n"
    result={}
    for day in state.JOB_IDS:
        result[HOME/'scripts'/f'publish_scheduled_{day}.py']=(boot+f"from linkedin_scheduled import weekday_main\nif __name__=='__main__':raise SystemExit(weekday_main({day!r}))\n").encode()
    result[HOME/'scripts/publish_scheduled.py']=(boot+"from linkedin_scheduled import main\nif __name__=='__main__':raise SystemExit(main())\n").encode()
    result[HOME/'scripts/linkedin_weekly.py']=(boot+"from linkedin_weekly import main\nif __name__=='__main__':raise SystemExit(main())\n").encode()
    result[REPO/'runtime/linkedin/verify_draft.py']=(boot+'''from linkedin_state import verify_integrity

def verify_draft(draft_dir):return verify_integrity(Path(draft_dir)/'linkedin_drafts.json')

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: verify_draft.py <draft_dir>')
    ok,message=verify_draft(sys.argv[1]);print(message);raise SystemExit(0 if ok else 1)
''').encode()
    result[HOME/'skills/operations/linkedin-weekly-posts/scripts/verify_armed_jobs.py']=(boot+"from linkedin_state import main\nif __name__=='__main__':raise SystemExit(main(['check-jobs',*sys.argv[1:]]))\n").encode()
    result[HOME/'skills/operations/linkedin-weekly-posts/SKILL.md']=(REPO/'career-ops/hermes-skills/linkedin-weekly-posts/SKILL.md').read_bytes()
    result[HOME/'skills/operations/linkedin-weekly-posts/references/image-generation.md']=(REPO/'career-ops/hermes-skills/linkedin-weekly-posts/references/image-generation.md').read_bytes()
    retired='"""Retired unsafe state writer. Preserved in the activation backup for history."""\nimport json\n\ndef main():\n    print(json.dumps({\'phase\':\'RETIRED\',\'publish_performed\':False,\'reason\':\'Use career-ops/linkedin_state.py capture/reconcile/plan; do not hand-write approval or gate records.\'}))\n    return 2\n\nif __name__==\'__main__\':raise SystemExit(main())\n'
    for name in ('create_approved_drafts.py','write_approved_with_override.py','apply_override.py'):
        result[REPO/'runtime/linkedin'/name]=retired.encode()
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');p.add_argument('--update-weekly-prompt',action='store_true');p.add_argument('--update-weekly-script',action='store_true');a=p.parse_args(argv)
    jobs=state.read(HOME/'cron/jobs.json');jobs=jobs if isinstance(jobs,list) else jobs['jobs']
    for day in state.JOB_IDS:
        if state.job_state(day)['enabled']:raise SystemExit('Publish jobs must remain paused during installation')
    data=payloads();changes=[(path,content,state.file_hash(path)) for path,content in data.items() if not path.exists() or path.read_bytes()!=content]
    if not a.apply:
        print(json.dumps({'dry_run':True,'files_to_update':[str(x[0]) for x in changes],'publish_jobs_enabled':0,'publish_performed':False},indent=2));return 0
    backup=HOME/'backups'/('linkedin-state-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir(parents=True)
    manifest=[]
    for index,(path,content,before) in enumerate(changes):
        if path.exists():shutil.copy2(path,backup/(str(index)+'-'+path.name))
        if state.replace_bytes(path,content,before):manifest.append({'path':str(path),'before_sha256':before,'after_sha256':state.file_hash(path)})
    if a.update_weekly_prompt:
        sys.path.insert(0,str(HOME/'hermes-agent'))
        from cron.jobs import update_job
        found=[j for j in jobs if j.get('id')=='7db108b00189']
        if len(found)!=1:raise SystemExit('Weekly draft job missing/duplicated; wrapper installation succeeded but prompt not changed')
        old=found[0].get('prompt') or ''
        if not old.startswith(PREFIX):
            new=PREFIX+old.replace('- **First action:** read','- **After state inspection:** read',1)
            # Use the scheduler's own locked update API. No enabled/schedule field is changed.
            result=update_job('7db108b00189',{'prompt':new})
            if not result:raise SystemExit('Weekly prompt update failed')
            manifest.append({'job_id':'7db108b00189','field_changed':'prompt','before_sha256':hashlib.sha256(old.encode()).hexdigest(),'after_sha256':hashlib.sha256(new.encode()).hexdigest()})
    if a.update_weekly_script:
        sys.path.insert(0,str(HOME/'hermes-agent'))
        from cron.jobs import update_job
        found=[j for j in jobs if j.get('id')=='7db108b00189']
        if len(found)!=1:raise SystemExit('Weekly draft job missing/duplicated')
        (backup/'weekly-job.before.json').write_text(json.dumps(found[0],indent=2),encoding='utf-8')
        updates={'script':'linkedin_weekly.py','no_agent':True,
            'prompt':'Bounded weekly preparation: research, authoritative profile, writing and both factual gates. Exact output only. No approval, images or publication in this drafting job.'}
        result=update_job('7db108b00189',updates)
        if not result:raise SystemExit('Weekly script wiring failed')
        manifest.append({'job_id':'7db108b00189','fields_changed':list(updates),'enabled_and_schedule_unchanged':True})
    for day in state.JOB_IDS:
        if state.job_state(day)['enabled']:raise SystemExit('Concurrent publish enablement detected; stop and review')
    (backup/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'installed':True,'backup':str(backup),'updates':len(manifest),'publish_jobs_enabled':0,'publish_performed':False},indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
