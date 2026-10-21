"""Apply the owner's four decisions to the UK tracker, in one verified rewrite.

  1. Accenture  - add as Applied (applied 2026-10-12, requisition R00343504)
  2. FTI        - applied, scheme closed: collapse the duplicate pair and mark Rejected
  3. GHD        - same application: mark the existing row Applied
  4. Shell      - add as Applied (assessment 2026-10-18)

Order is preserved: open roles first, then applied history, then rejected.
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

# Row numbers are 1-based sheet rows, as read before any change.
GHD_ROW = 19          # GHD Advisory / Graduate Data Consultant -> Applied
FTI_KEEP_ROW = 21     # FTI Consulting / 2027 Graduate Scheme, Cyber Security -> Rejected
FTI_DROP_ROW = 83     # the same vacancy, a second row

NEW_ROWS = [
    {
        'date_found': '2026-10-12',
        'company': 'Accenture',
        'title': 'Security Analyst \u2013 Emerging Technology \u2013 Financial Services',
        'url': ('https://accenture.wd103.myworkdayjobs.com/en-US/AccentureCareers/job/'
                'Security-Analyst---Emerging-Technology---Financial-Services_R00343504'),
        'deadline': None,
        'status': 'Applied',
    },
    {
        'date_found': '2026-10-18',
        'company': 'Shell',
        'title': 'Shell Assessed Internship Programme 2027 \u2013 United Kingdom',
        'url': ('https://shell.wd3.myworkdayjobs.com/en-US/ShellCareers/job/'
                'Shell-Assessed-Internship-Programme-2027---United-Kingdom_R205154'),
        'deadline': None,
        'status': 'Applied',
    },
]

STATUS_COL = 6


def sort_key(r):
    s = str(r['values'][STATUS_COL - 1] or '').strip()
    bucket = 0 if s == 'Not Applied' else (1 if s == 'Applied' else 2)
    return (bucket, r['row'])


def build(rows):
    template = rows[0]['formats']
    by_row = {r['row']: r for r in rows}

    out = []
    for r in rows:
        if r['row'] == FTI_DROP_ROW:
            continue
        if r['row'] == GHD_ROW:
            r['values'][STATUS_COL - 1] = 'Applied'
        if r['row'] == FTI_KEEP_ROW:
            r['values'][STATUS_COL - 1] = 'Rejected'
        out.append(r)

    nxt = max(by_row) + 1
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
    # Capture the ORIGINAL statuses before build() rewrites them in place.
    before = {r['row']: (r['values'][1], r['values'][5]) for r in rows}
    kept = build(rows)
    profiles = tp.tw.load_profiles(None)

    changed = [k for k in before if k in (GHD_ROW, FTI_KEEP_ROW)]
    print(f'rows in: {len(rows)}   rows out: {len(kept)}   (dropped 1 duplicate, added 2)')
    for k in sorted(changed):
        print(f"  row {k}: {before[k][0]}  {before[k][1]} -> "
              f"{[r for r in kept if r['row'] == k][0]['values'][5]}")
    for spec in NEW_ROWS:
        print(f"  ADD: {spec['company']} | {spec['title']} | {spec['status']}")

    result = tp.apply_prune(path, rows, kept, profiles=profiles, dry_run=not args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:1200])
    return 0 if (result.get('applied') or result.get('dry_run')) else 1


if __name__ == '__main__':
    raise SystemExit(main())
