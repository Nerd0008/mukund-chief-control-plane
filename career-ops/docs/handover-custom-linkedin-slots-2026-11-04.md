# Handover — custom LinkedIn publishing slots

**Written:** 2026-11-04 (London)
**From:** Chief of Staff
**To:** Codex
**Owner authority:** Mukund Didwania, 2026-11-04, #linkedin

> "Create a handover codex will configure the LinkedIn workflow to accomadate customer slots from now"
> "It's a custom slot only for this week"
> "No need to cut it from Wednesday"

## 1. What is being asked

The LinkedIn publishing workflow currently supports **only Tuesday, Wednesday and Thursday**.
The owner wants it to support **custom slots** — additional weekdays on demand, not a fixed weekly
pattern. The immediate case is **Friday 6 November 2026**.

"From now" means this should be a **standing capability**, not a one-off patch for Friday.

## 2. Current state (verified 2026-11-04 03:18 UTC)

- **Publishing policy:** enabled (`publishing_enabled: true`).
- **Publish jobs:** three, all **disabled**, all `last_status: error` from the 27 Oct run.
  - `beb0251ed70c` — Tuesday
  - `f1b1452f18b1` — Wednesday
  - `8e6048e2dfa7` — Thursday
- **Last real publication:** Tuesday 27 Oct, body `e896bb7d…`, `urn:li:share:7518816860826476545`.
  The Wednesday 28 Oct post went out late on Friday 30 Oct (`7521734825171439617`, body `de49b0cf…`).
- **Schedule manifest:** `runtime/linkedin/drafts/schedule.json` — schema_version 2, `Europe/London`,
  currently holds only the 21 Oct (legacy) and 27 Oct slots.
- **This week's drafts:** `runtime/linkedin/review/2026-11-02/weekly.json` — Tuesday and Wednesday
  have no draft; Thursday has a personal draft (`3a3916d1…`) that is not approved and whose reviews
  are incomplete.

## 3. The exact code constraints

All in `career-ops/linkedin_state.py`. Every one of these must be addressed for a custom slot to work.

| Line | Code | Problem |
|------|------|---------|
| 16 | `JOB_IDS={'tuesday':'beb0251ed70c','wednesday':'f1b1452f18b1','thursday':'8e6048e2dfa7'}` | Hardcoded three-day map. No Friday entry, no way to add one. |
| 119 | `re.fullmatch(r'approved_(\d{8})_(tuesday\|wednesday\|thursday)', ...)` | `artifact_date()` refuses any other weekday in a directory name. |
| 139 | `if day not in JOB_IDS ... raise ValueError('unknown legacy schedule entry')` | Legacy schedule loader rejects unknown days. |
| 182 | `job=job_state(day,...) if day in JOB_IDS else {'known':False,...,'reason':'no publishing weekday'}` | Non-standard days report as "no publishing weekday". |
| 303-304 | `selected=set(JOB_IDS) if days is None else set(days)` / `if not selected<=set(JOB_IDS): raise ValueError('unknown publishing weekday')` | `refresh_publishing_jobs()` cannot arm a day outside the map. |
| 363 | `if day not in JOB_IDS: raise ValueError('scheduled capture supports Tuesday/Wednesday/Thursday only')` | `capture()` refuses to write a Friday artifact at all. |

### Related files to check

- `runtime/linkedin/publish_scheduled.py` — the scheduled wrapper. Takes a weekday argument.
- `career-ops/linkedin_publish.py` — the publisher. Confirm it has no weekday assumption.
- `scripts/install_linkedin_state.py` — installs the cron wrappers. A new weekday needs a wrapper
  and a job, or the scheduled path will not exist for it.
- `career-ops/linkedin_approval.py` — the approval verifier. Check for weekday assumptions.

## 4. Design requirement

Do **not** hardcode Friday. The owner asked for *custom slots*, so the design should be
**data-driven**: a slot is any date the owner names, and the weekday is derived from the date.

Recommended shape:

1. Replace the fixed `JOB_IDS` map with a **slot registry** (a JSON file, e.g.
   `runtime/linkedin/publish_slots.json`) mapping weekday name -> job ID, seeded with the three
   existing entries. New weekdays are added by adding an entry, not by editing code.
2. `artifact_date()` should accept **any** weekday name, not a fixed alternation.
3. `capture()` and `refresh_publishing_jobs()` should read the registry instead of `JOB_IDS`.
4. A new weekday needs a **cron job** and an installed **wrapper**. Confirm with the owner before
   creating a standing Friday job; the immediate ask is one custom slot for this week.

**Preserve these invariants — they are the safety rails, not obstacles:**

- Exact-date manifest entry per slot (`schedule.json`), pinning artifact path, body hash, image hash
  and `Europe/London` publish time.
- `plan_slot()` must still refuse to arm anything that is not verified, owner-approved and unpublished.
- `refresh_publishing_jobs()` must still arm **only** the earliest verified, approved, exact future
  slot per weekday, and must still pause empty weekdays.
- Artifact identity must still bind directory name to date (`approved_YYYYMMDD_<weekday>`), and the
  weekday in the name must still match the date.
- Never arm a slot whose body is already in the published ledger.

## 5. Immediate case — Friday 6 November 2026

A draft exists and is **not approved**:

```
A startup just came out of stealth with $62.5 million to build a world model that predicts how a person will behave.

Not what they will buy. How they will decide.

It reads sentiment, voice, how often someone calls support, the timing of transfers. It converts those into a mathematical picture of a person, then estimates the probability of their next choice.

The company says it is running this at a handful of brokerages, to anticipate how traders act when markets turn volatile.

I keep thinking about the phrase "every individual is the world." A world model is supposed to simulate a place. This one simulates a person.

The company is candid that the claim is probabilistic, not certain. That is honest. But a probability about a person is still a claim about who they are.

What would you want to know before a model made that kind of claim about you?

#AI #WorldModel #Privacy #DataEthics #ArtificialIntelligence
```

- 923 chars
- body sha256 `b99c2d7cb9b67fd402e9a95c9c9217a93cb5fd6db41f8158ee56d60e8dfe5045`
- Source: TechCrunch, 2 Nov 2026 — `https://techcrunch.com/2026/11/02/42ai-comes-out-of-stealth-with-62-5m-and-a-world-model-that-can-predict-human-behavior`
- No company names, no countries, no towns in the body.

**Do not publish this without a fresh authenticated exact-body owner approval.** The owner has not
approved this text.

## 6. Also drafted this week (not approved)

**Wednesday 4 Nov — AI + cyber (876 chars)**, body `b8b0bd7aa0f5e37eb17ab7c106da07e96297e956f9383c8a0e5f2de725ee737a`.
Fridge/OT misconfiguration attack. Sources: BBC 3 Nov, Censys 14 Oct, OWASP Top 10 2025.
The owner explicitly said **keep the OWASP name** in this one ("No need to cut it from Wednesday").

**Thursday 5 Nov — personal (505 chars)**, body `1f598ac40f129d9ffcd011dcb45b9e26e9a19c6072dbf16456e0c9013dbeb51e`.
AttackSurfaceIQ / event-log reflection.

## 7. Standing rules the owner has set

- No company names, no country names, no town names in post bodies. (OWASP is an approved exception
  for the Wednesday post only.)
- No em dashes, no semicolons.
- Short paragraphs, 3-6 hashtags, end on a genuine engagement question, under 1,000 characters.
- Every draft must be grounded in Mukund's live LinkedIn profile before drafting.
- Topics must be fresh against `runtime/linkedin/topic_registry.json` (17 entries) and
  `runtime/linkedin/topic_exclusions.json`.
- Publication requires an authenticated exact-body owner approval. A request to publish is not approval.
- The published ledger blocks republishing a deleted post; remove the stale ledger entry rather than
  using `--allow-duplicate`.

## 8. Definition of done

1. A custom slot can be captured, verified, planned and armed for a weekday outside
   Tuesday/Wednesday/Thursday, with no code edit per slot.
2. The existing three weekdays still behave exactly as before.
3. All safety rails in section 4 still hold, with tests.
4. Friday 6 Nov can be planned and armed once the owner approves the exact text.
5. Changes committed and pushed to `fix/e3-whole-repo-architecture` — the repo is the warm-site
   backup and must stay deployable within hours.
6. Tests run and the result reported with real output.

## 9. Cautions

- **Auto-stash hazard.** A poller runs `git stash` on uncommitted tracked changes every few minutes.
  Apply an edit and commit it in the **same** terminal call, or the change will be silently reverted.
- **Never reset, stash or discard uncommitted work in this repo.**
- Stage only your own files, never `git add -A`.
- The owner's standing rule: fix the root cause, verify it will not recur, and report real test output.
