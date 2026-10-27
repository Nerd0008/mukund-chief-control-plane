"""Exact-date scheduled LinkedIn publisher. Dry-run has no account/ledger writes."""
from __future__ import annotations
import argparse,json,os,subprocess,sys
from datetime import date,datetime,time
from pathlib import Path
import linkedin_state as state


def run_day(day,*,target_date=None,dry_run=True,root=state.ROOT,db_path=None,jobs_path=state.JOBS,now=None,runner=None):
    now=now or datetime.now(state.LONDON)
    if now.tzinfo is None:raise ValueError('timezone-aware execution time required')
    now=now.astimezone(state.LONDON);target=date.fromisoformat(str(target_date)) if target_date else now.date()
    if day not in state.JOB_IDS or target.strftime('%A').lower()!=day:
        return 1,{'phase':'NOT_DUE','reason':'requested weekday is not the exact execution/preview date','publish_performed':False}
    root=Path(root);slots=state.load_slots(root/'drafts/schedule.json');slot=slots.get(target.isoformat())
    if not slot:return 1,{'phase':'NOT_SCHEDULED','target_date':target.isoformat(),'reason':'no exact dated manifest entry','publish_performed':False}
    path=state.absolute(slot['draft_path'])
    if not path.is_relative_to((root/'drafts').resolve()):raise ValueError('scheduled artifact is outside the canonical drafts directory')
    snapshot=state.inspect_artifact(path,root=root,db_path=db_path,jobs_path=jobs_path)
    result={**snapshot,'dry_run':dry_run,'publish_performed':False,'network_calls':0}
    if dry_run:
        result['would_publish_if_enabled_and_due']=bool(snapshot['content_ready'] and snapshot['slot_matches'] and not snapshot['published'])
        result['writes']=0
        return (0 if result['would_publish_if_enabled_and_due'] else 1),result
    if target!=now.date() or now<datetime.combine(target,time(8),state.LONDON):
        return 1,{**result,'phase':'NOT_DUE','reason':'future or stale date cannot publish'}
    if not snapshot['automatic_publish_armed']:
        return 1,{**result,'reason':'publishing job disabled, content blocked, or manifest invalid'}
    # Recheck after taking the shared mutation lock, then keep the exact identity
    # stable through the bounded child call. The child independently checks consent/gates.
    with state.locked(root):
        current=state.inspect_artifact(path,root=root,db_path=db_path,jobs_path=jobs_path)
        if not current['automatic_publish_armed'] or current['body_sha256']!=snapshot['body_sha256']:
            raise state.StateConflict('scheduled state changed before execution')
        command=[sys.executable,str(state.REPO/'career-ops/linkedin_publish.py'),'publish','--drafts',str(path),
            '--approve-publish','--confirm-token',current['body_sha256']]
        doc=state.read(path)
        if doc.get('image_path'):command+=['--image',str(state.absolute(doc['image_path']))]
        proc=(runner or subprocess.run)(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180,cwd=str(state.REPO))
        # Never print raw subprocess output or claim a post succeeded solely from exit 0.
        payload=None
        try:payload=json.loads(proc.stdout)
        except (ValueError,TypeError):pass
        success=bool(proc.returncode==0 and isinstance(payload,dict) and payload.get('performed') and payload.get('post_urn') and state.published(current['body_sha256'],root))
        scheduling=None
        if success and state.publishing_enabled(root):
            try:scheduling=state.refresh_publishing_jobs(root=root,db_path=db_path,jobs_path=jobs_path,now=now)
            except (OSError,ValueError) as exc:scheduling={'error_type':type(exc).__name__,'reason':str(exc)}
        return (0 if success else (proc.returncode or 1)),{**result,'publish_performed':success,'next_schedule':scheduling,
            'network_calls':None,'reported_publish_attempts':payload.get('network_calls_spent') if isinstance(payload,dict) else None,
            'child_exit_code':proc.returncode,'post_urn':payload.get('post_urn') if success else None,
            'phase':'PUBLISHED' if success else 'PUBLISH_FAILED'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('day',choices=tuple(state.JOB_IDS))
    p.add_argument('--date',help='exact preview date; real execution must be today')
    mode=p.add_mutually_exclusive_group();mode.add_argument('--dry-run',action='store_true');mode.add_argument('--execute',action='store_true')
    args=p.parse_args(argv)
    try:
        code,result=run_day(args.day,target_date=args.date,dry_run=not args.execute)
    except (OSError,ValueError,state.StateConflict,subprocess.SubprocessError) as exc:
        code,result=1,{'phase':'BLOCKED','error_type':type(exc).__name__,'reason':str(exc),'publish_performed':False}
    print(json.dumps(result,indent=2,ensure_ascii=False));return code


def weekday_main(day,argv=None):
    # Installed cron wrappers use this same parser. They preserve every argument
    # and every nonzero exit; --dry-run can never be dropped or overridden.
    argv=list(sys.argv[1:] if argv is None else argv)
    if '--dry-run' not in argv and '--execute' not in argv:argv.append('--execute')
    return main([day,*argv])


if __name__=='__main__':raise SystemExit(main())
