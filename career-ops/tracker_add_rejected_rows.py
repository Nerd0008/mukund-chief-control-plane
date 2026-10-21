"""Append the rejections that were never tracked, from employer email evidence.

The 60-day Gmail sweep found nine employers whose rejections were real but had no
row in the tracker at all. Each row below carries the role the employer named in
its own email, the application date from the employer's own application
confirmation, and the employer's own application link (never an aggregator).

Safety: the same guarded writer the pipeline uses, so the write is atomic, backed
up, and verified. Nothing is written unless verification passes.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import tracker_prune as tp  # noqa: E402

TRACKER = pathlib.Path(r'C:\Users\mukun\Downloads\codex\uk-cyber-job-tracker.xlsx')

STATUS_COL = 6

NEW_ROWS = [
    {
        'date_found': '2026-09-01',
        'company': 'Dignity Funerals',
        'title': 'IT Service Support Analyst (Dignity Funerals)',
        'url': 'https://dignity.kallidusrecruit.com',
        'deadline': None,
        'status': 'Rejected',
        'evidence': 'Rejection 3 Sep 2026: experience and profile do not fully align',
    },
    {
        'date_found': '2026-09-21',
        'company': 'Margo Group',
        # The employer named no role in either the application confirmation or the
        # rejection. Recorded as unknown rather than guessed.
        'title': 'Role not named in employer emails',
        'url': 'https://jobs.lever.co/margo-group',
        'deadline': None,
        'status': 'Rejected',
        'evidence': 'Rejection 25 Sep 2026: unable to give a favorable response',
    },
    {
        'date_found': '2026-09-13',
        'company': 'Commify',
        'title': 'Cyber Governance Analyst',
        'url': ('https://jobs.workable.com/view/'
                '5HEgwWyiwRxPka7QGPaZ91/hybrid-cyber-governance-analyst-in-nottingham-at-commify'),
        'deadline': None,
        'status': 'Rejected',
        'evidence': 'Rejection 25 Sep 2026: not selected for further consideration',
    },
    {
        'date_found': '2026-09-21',
        'company': 'NTT DATA UK&I',
        'title': 'IT Support Engineer',
        'url': 'https://nttdata.jobs/vacancies',
        'deadline': None,
        'status': 'Rejected',
        'evidence': 'Rejection 9 Oct 2026: not proceeding with your application',
    },
    {
        'date_found': '2026-09-08',
        'company': 'The AA',
        'title': 'Cyber Security Engineer',
        'url': 'https://theaacareers.co.uk/apply/cyber-security-engineer',
        'deadline': None,
        'status': 'Rejected',
        'evidence': 'Rejection 10 Sep 2026: pursuing other candidates',
    },
    {
        'date_found': '2026-09-13',
        'company': 'Johnson Controls',
        'title': 'Remote Support Technician (WD30276030)',
        # Employer's own Workday URL pattern with the requisition id the employer
        # itself quoted in its application and rejection emails.
        'url': 'https://jobs.johnsoncontrols.com/job/WD30276030',
        'deadline': None,
        'status': 'Rejected',
        'evidence': 'Rejection 15 Sep 2026: not selected for the position',
    },
    {
        'date_found': '2026-08-24',
        'company': 'Bolt',
        'title': 'Junior Cybersecurity Engineer',
        'url': 'https://bolt.eu/en/careers/positions/6518856b-d8ef-4286-97df-ad58b04d0d09',
        'deadline': None,
        'status': 'Rejected',
        'evidence': 'Rejection 25 Aug 2026: position already filled',
    },
    {
        'date_found': '2026-09-13',
        'company': 'Vp plc',
        'title': 'IT Service Desk Analyst (1st Line)',
        'url': 'https://vacancies.vpplc.com/jobs/job/IT-Service-Desk-Analyst-1st-Line/1917',
        'deadline': None,
        'status': 'Rejected',
        'evidence': 'Rejection 16 Sep 2026: not shortlisted',
    },
    {
        'date_found': '2026-08-23',
        'company': 'Pencil',
        'title': 'Security Engineer - EMEA - Remote',
        'url': 'https://jobs.ashbyhq.com/pencil/872e9df1-4270-420c-ac69-e7de259a1d3b',
        'deadline': None,
        'status': 'Rejected',
        'evidence': 'Rejection 26 Aug 2026: decided not to move forward',
    },
]


def sort_key(r):
    s = str(r['values'][STATUS_COL - 1] or '').strip()
    bucket = 0 if s == 'Not Applied' else (1 if s == 'Applied' else 2)
    return (bucket, r['row'])


def build(rows):
    template = rows[0]['formats']
    out = list(rows)
    nxt = max(r['row'] for r in rows) + 1
    for spec in NEW_ROWS:
        out.append({
            'row': nxt,
            'values': [spec['date_found'], spec['company'], spec['title'],
                       spec['url'], spec['deadline'], spec['status']],
            'formats': list(template),
            'url': spec['url'],
            'link_target': spec['url'],
        })
        nxt += 1
    out.sort(key=sort_key)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tracker', default=str(TRACKER))
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    path = pathlib.Path(args.tracker)
    rows = tp.read_rows(path)
    kept = build(rows)
    profiles = tp.tw.load_profiles(None)

    print(f'rows in: {len(rows)}   rows out: {len(kept)}   (adding {len(NEW_ROWS)})')
    for spec in NEW_ROWS:
        print(f"  ADD: {spec['company']:<20} | {spec['title'][:44]:<44} | {spec['status']}")

    result = tp.apply_prune(path, rows, kept, profiles=profiles, dry_run=not args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:1600])
    return 0 if (result.get('applied') or result.get('dry_run')) else 1


if __name__ == '__main__':
    raise SystemExit(main())
