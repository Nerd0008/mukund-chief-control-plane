"""Retired unsafe state writer. Preserved in the activation backup for history."""
import json

def main():
    print(json.dumps({'phase':'RETIRED','publish_performed':False,'reason':'Use career-ops/linkedin_state.py capture/reconcile/plan; do not hand-write approval or gate records.'}))
    return 2

if __name__=='__main__':raise SystemExit(main())
