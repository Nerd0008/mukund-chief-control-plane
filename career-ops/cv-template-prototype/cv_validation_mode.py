"""Local development switch; factual validation is enabled by default.

No JD, model response or compiler tool argument can select this mode.
"""
import argparse,json,os,pathlib,uuid

DISABLED='DISABLED_FOR_TESTING'

def config_path():
    default=pathlib.Path(os.environ.get('LOCALAPPDATA',str(pathlib.Path.home()/'AppData/Local')))/'hermes/runtime/career-ops/cv-validation-mode.json'
    return pathlib.Path(os.environ.get('CV_VALIDATION_CONFIG_PATH',str(default)))

def canonical_gate_enabled():
    try:
        value=json.loads(config_path().read_text(encoding='utf-8'))
        return not (isinstance(value,dict) and value.get('mode')=='development' and value.get('canonical_fact_gate_enabled') is False)
    except (OSError,ValueError,TypeError):return True

def authorize_receipt(value):
    return value=='PASS' or (value==DISABLED and not canonical_gate_enabled())

def configure(development=False):
    target=config_path();target.parent.mkdir(parents=True,exist_ok=True)
    value={'mode':'development' if development else 'production','canonical_fact_gate_enabled':not development,'independent_fact_review_enabled':not development,
           'reason':'Explicit owner instruction: temporarily disable both canonical and independent factual checks for builder testing; preserve production PDF appearance.' if development else 'Production canonical validation enabled.'}
    temporary=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value,indent=2),encoding='utf-8');temporary.replace(target)
    return value

if __name__=='__main__':
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group()
    group.add_argument('--production',action='store_true');group.add_argument('--development-no-canonical-gate','--development-no-fact-checks',action='store_true')
    args=parser.parse_args()
    if args.production or args.development_no_canonical_gate:configure(args.development_no_canonical_gate)
    print(json.dumps({'config':str(config_path()),'canonical_fact_gate_enabled':canonical_gate_enabled()}))
