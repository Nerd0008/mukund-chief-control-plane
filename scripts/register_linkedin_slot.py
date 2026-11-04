"""Register a dormant weekday dispatcher. Exact dated approved slots alone arm it."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'career-ops'))
import linkedin_state as state


def register(day,*,root=state.ROOT,home=state.HOME,creator=None,jobs_path=state.JOBS):
    if day not in state.WEEKDAYS:raise ValueError('invalid publishing weekday')
    root=Path(root);home=Path(home)
    with state.locked(root):
        registry=state.job_ids(root)
        path=root/'publish_slots.json'
        before=state.file_hash(path)
        wrapper=home/'scripts'/f'publish_scheduled_{day}.py'
        payload=("import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path("+repr(str(state.REPO))+")/'career-ops'))\nfrom linkedin_scheduled import weekday_main\nif __name__=='__main__':raise SystemExit(weekday_main("+repr(day)+"))\n").encode()
        if day in registry:
            if not state.job_state(day,root=root,jobs_path=jobs_path)['known']:
                raise ValueError('registered scheduler job missing or duplicated; repair existing identity')
        else:
            if creator is None:
                if Path(jobs_path).resolve()!=state.JOBS.resolve():raise ValueError('private scheduler requires injected creator')
                sys.path.insert(0,str(home/'hermes-agent'))
                from cron.jobs import create_job
                creator=create_job
            # Install wrapper before creating any scheduler record. Job starts paused.
            state.replace_bytes(wrapper,payload,state.file_hash(wrapper))
            job=creator(prompt='Publish only a verified, approved exact-date LinkedIn slot.',
                schedule=f'0 8 * * {(state.WEEKDAYS.index(day)+1)%7}',
                name=f'LinkedIn dated-slot dispatcher - {day}',script=wrapper.name,no_agent=True,
                paused=True,paused_reason='No future approved, verified exact LinkedIn slot',deliver='local')
            registry[day]=job['id']
        state.replace_bytes(wrapper,payload,state.file_hash(wrapper))
        state.audited_json(path,{'schema_version':1,'weekdays':registry},before,
            root=root,operation='weekday_dispatcher_registered',body_sha=None)
        return {'registered':day,'job_id':registry[day],'publish_performed':False,'approval_granted':False,
                'note':'Dispatcher has no standing content slot; exact-date manifest and readiness checks govern arming.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('day',choices=state.WEEKDAYS);p.add_argument('--apply',action='store_true');args=p.parse_args(argv)
    if not args.apply:
        print(json.dumps({'would_register':args.day,'publish_performed':False}));return 0
    print(json.dumps(register(args.day),indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
