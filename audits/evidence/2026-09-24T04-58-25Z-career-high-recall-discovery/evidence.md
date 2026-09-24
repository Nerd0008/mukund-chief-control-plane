# Career high-recall semantic discovery — bounded live/dry-run evidence

Task: `agent-career-high-recall-semantic-discovery-2026-09-24`
Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`
Run id: `discovery-uk-20260924T050143Z` (funnel run) · compare-modes generated `2026-09-24T05:02:38+00:00`
Region: `uk` · Title-policy mode: `high_recall`

No canonical tracker was written by any step below. No `--apply` was passed anywhere;
`compare-modes` performs no dedupe probe and writes no manifest. The four canonical workbooks
(UK / Dubai / Japan / Singapore) are byte-identical before and after (SHA-256 table in
`summary.json`).

Raw per-posting artifacts (posting titles, companies, application URLs and per-candidate
classifications) are **not committed**: they stay in the git-ignored local path
`runtime/career-ops/discovery/evidence-2026-09-24T045825Z/` (`run.json`, `compare-modes.json`,
run-health). This file and `summary.json` are aggregate only.

## 1. Source coverage (what was actually collected)

| Source | Coverage |
|---|---|
| Career Ops lane scan (`regional-run-uk-20260924T034745Z.json`) | scan ok; counters `jobs_found=2861`, `filtered_title=2726`, `filtered_location=130`, `filtered_age=3`, `duplicates=1`, `new_offers_added=1`; 1 offer line parsed |
| Company Watch (`findings-uk-latest.json`) | 594 findings; 505 `new` findings entered the funnel; the rest are excluded **with their own reason** before the funnel: `duplicate-in-run=85`, `routed_other_region=dubai 1 / japan 1 / singapore 2` |
| Run limit | candidate limit 60 of 506 discovered; the pre-limit count is recorded in the run evidence, so a run limit is never presented as a market fact |

Scan offers carry company/title/location only — no posting URL and no description text. That is
recorded on every affected classification: `jd_available=false`,
`classification_basis=title_company_location_only`, plus an explicit uncertainty line stating the
result is **NOT semantic JD analysis**. No claim of JD analysis is made where the source text does
not support it.

## 2. Funnel (real counts, this run)

```
discovered_raw                    60   (506 before the 60-candidate run limit)
after_hard_negative_prefilter      6
semantically_reviewed              6
deepseek_accept                    1
codex_escalated                    3
codex_accept                       0
deterministic_eligibility_pass     0
duplicates_removed                 0
tracker_candidates                 0
```

Zero attribution (recorded, not inferred): *"no candidate was left accepted by the semantic stage
(DeepSeek bulk pass, plus any Codex second pass) — so no candidate reached the deterministic gates;
see the classification labels and rejections_by_reason for the per-candidate reason."*

Rejections by reason: Tier B hard negatives 21 (manager 10, executive 5, senior 5, director 2,
chief 1, principal 1, lead 1); Tier A no-recall-signal 25 (no discipline signal 18, no early-career
level signal 7); non-cyber signals 3 (sales 2, business development 1); semantic labels 6
(`codex_second_pass ambiguous_review` 3, `deepseek_bulk too_senior` 2, `deepseek_bulk
wrong_discipline` 1).

## 3. Provider evidence

**DeepSeek bulk semantic triage** — model **observed** at the provider (`deepseek-flash`; the
provider also listed `deepseek-v4-pro`), auth source `credential_manager`, 2 requests / 2 batches,
6 candidates classified, 0 unclassified, 0 split retries, 0 errors, provider-reported usage
`prompt_tokens=1222, completion_tokens=6356, total_tokens=7578`. No credential value was read,
printed or committed.

> Defect found and fixed during this pass: the first attempt used `max_tokens=4096`; the model spent
> the entire completion budget on reasoning and returned empty content (`completion_tokens=4096`).
> The classifier now uses an 8192-token budget and retries a failed batch once in halves, and an
> empty response is recorded as a provider failure — never as "no candidates".

**Codex bounded second pass** — CLI `codex-cli 0.155.0-alpha.16.3`, budget 4, **1 request**,
3 candidates escalated, 0 dropped for budget. Escalation reasons: `deepseek_label_ambiguous_review`
(2) and `high_value_plausible_without_jd_text` (1). Codex was not called for the other 503
discovered postings: escalation is deterministic and capped by `--codex-budget`.

## 4. Compare modes — the recall delta on one captured candidate set

Same 506-candidate set, identical deterministic gates, only the title policy differs.
Nothing written: `canonical_workbook_written=false`, `manifest_written=false`,
`tracker_probe_run=false`.

| Mode | title pass | title reject | would reach the tracker |
|---|---|---|---|
| `intern_only` (the owner's current rule) | 3 | 503 | **0** |
| `high_recall` (new default) | 15 | 491 | **4** |

Delta: **+12 titles, +4 tracker-eligible candidates**, no title lost. The 12 regained titles are
entry-level/graduate security-engineering, SOC/incident-response, GRC, IAM, vulnerability,
network/product security and threat-intelligence postings — the same role families the owner asked
for in the task scope. Regained titles that still fail a deterministic gate are listed separately in
`recall_delta.recall_regained_titles` (with their gate reasons) so a title-policy delta is never
presented as a tracker delta.

## 5. Truth boundaries

* Zero tracker candidates in this run is **not** a statement that no UK vacancies exist. The
  discovered pool was 506 real postings; 60 were processed under an explicit limit; 6 survived the
  Tier A prefilter; the semantic stage finally accepted fewer than the deterministic gates required.
  Every step is counted and each rejection carries a reason.
* No application was submitted, no employer or recruiter was contacted, no browser or GUI was used,
  no account was touched, no canonical workbook was modified.
* Classifications are model outputs over the fields a record actually carries. They are policy
  inputs for owner review, not factual claims about a vacancy.
