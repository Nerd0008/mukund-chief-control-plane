---
name: linkedin-weekly-posts
description: Use when managing Mukund's LinkedIn posts workflow.
version: 1.1.0
metadata:
  hermes:
    tags: [mukund, linkedin, content-generation, gemini, publishing, social-media]
    category: operations
    author: chief-of-staff
    license: MIT
---

# LinkedIn Weekly Posts Workflow

## When to Use

- Mukund asks to generate, review, or publish LinkedIn posts
- The weekly cron job fires and needs to produce fresh content
- Mukund wants to resume or debug the LinkedIn posting workflow
- Mukund asks about LinkedIn content style, dedupe, or publishing status

## Owner Approval Is Mandatory (hard rule)

**Never publish before Mukund has explicitly approved the exact text.**

A request that mentions publishing is NOT approval. "Write a post about X", "upload a post about this", "let's do a post on Y" and similar are all requests for a DRAFT. The required sequence is always:

1. Draft the post text.
2. Show Mukund the full text in chat.
3. Wait for his explicit approval of that text.
4. Only then generate the image and publish.

Publishing an unapproved draft is a failure regardless of how clearly the request implied publication. When in doubt, draft and ask. There is no downside to asking and a real cost to publishing something the owner has not read.

Do not treat a previously granted approval as covering a different or edited body: approval attaches to the exact bytes, which is why the publish path requires `--confirm-token` to equal the SHA-256 of the body.

**Once the owner approves, act in the same turn.** Approval of the exact bytes is the authorisation; building the artefact, running the gates, arming and scheduling are yours to execute. Do not ask for a second confirmation, do not re-run gates in order to put a choice back to him, and do not end the turn on another question. Being asked twice for something already granted is what the owner experiences as stalling.

A new owner message arriving while a reply is still building cuts that reply off and Discord shows "Response interrupted". That is reply latency, not a platform fault, and it is what makes a long multi-tool turn look like a freeze. Keep the path from approval to publish as short as you can.

## Bounded preparation and enabled publishing

The Sunday job runs `linkedin_weekly.py` as an existing Hermes script with `no_agent=true`.
It prepares one AI + cyber post, one AI + non-cyber post and one personal reflection,
using current complete professional references, observed source research, actual article
text and both real factual reviews. It checkpoints under `runtime/linkedin/review/` and
resumes completed verified slots. It never approves text, generates an unapproved image,
arms publication or calls LinkedIn. A blocked stage is reported as blocked, never as ready.
If live LinkedIn profile reading is unavailable, its report explicitly declares the complete
local professional-reference fallback. Do not claim a full live profile was read.

For manual preparation, use the Hermes interpreter:

```
python career-ops/linkedin_weekly.py --week-of <Monday-YYYY-MM-DD>
```

The owner enabled publishing on 27 October 2026. This is capability permission, never approval
of unseen future text. Check the persisted policy using:

```
python career-ops/linkedin_state.py publishing status
```

After authenticated exact-body approval and both passing reviews, use the existing
`capture`/`reconcile` and `plan --drafts <artifact> --date <YYYY-MM-DD>` flow. With publishing
enabled, planning automatically arms the earliest verified, approved future dated post for
that weekday through the locked scheduler API. No second enablement permission is needed.
Missing, blocked, already-published or stale slots are never armed. Successful scheduled
publication refreshes the jobs, pausing empty weekdays. Preserve exact-body approval and
duplicate protections. Use `publishing disable` only when the owner requests it.

Images use the existing routed Nano Banana 2 backend through
`linkedin_content_gen.generate_image_bytes()` at 4:5. It no longer depends on the old bot
interpreter or a Lite image model. Billing, permission and rate-limit failures are explicit;
never disguise them as missing context or silently substitute a different provider.

## Canonical approval and status contract

Use `career-ops/linkedin_state.py` as the authoritative state surface. Do not infer approval,
publishing readiness or scheduling from conversation summaries, folder names, `approved`,
`confirm_token`, old plans or `next_run_at` on a disabled cron job.

Run these using the Hermes Python interpreter before answering status questions:

```
python career-ops/linkedin_state.py week
python career-ops/linkedin_state.py status --drafts <exact-artifact.json>
python career-ops/linkedin_state.py check-jobs
```

Report the exact `phase`, `owner_approved`, `reviews_ready`, `content_ready`, `slot_matches`
and `job.enabled` separately. `APPROVED_BUT_BLOCKED` means the owner DID approve but review
or artifact integrity is incomplete. `APPROVED_READY_PAUSED` means verified content exists
but automatic publishing is disabled. Check policy and actual job state: planning arms a future ready slot only when publishing is enabled.
Never tell an owner to approve the same unchanged text again merely because a gate failed.

An owner may use `APPROVE LINKEDIN <sha256>` or reply naturally to the exact post just
presented. Show the full post and its `APPROVE LINKEDIN <sha256>` version marker in the
presentation; the owner does not have to type the marker. Natural consent is accepted only
when the canonical verifier authenticates the owner/platform message and binds the reply to
the latest exact presented post in that session. Negation, background/tool output, another
user, an unrelated historical "yes", or a different body is refused. Never hand-write a
receipt or guess a Hermes message id. Discord IDs and Hermes message IDs are different.

Persist and review an existing approval through:

```
python career-ops/linkedin_state.py reconcile --drafts <artifact> --approve-message-id <real-Hermes-ID>
```

This preserves verified consent even when later review fails. It recovers a complete audited
news pass only when exact body/source provenance still matches, reuses valid receipts and
runs the existing local personal review when needed. It does not rerun model judges unless
`--refresh-news` is explicitly requested for missing/stale evidence. `--dry-run` changes no
artifact/receipt/schedule/ledger and invokes no review provider. It never enables cron jobs.

### Owner override is for a gate REFUSAL, not a stale hash

An `owner_override` record authorises publishing a post a gate **refused** (verdict `block` or
`ungated`). It does not repair a gate record that was produced for different text: that record
simply does not cover these bytes, and the only fix is to re-run the gate over the current text.

```python
draft['owner_override'] = {
    'approved_by': 'Mukund',
    'approved_at': '<timestamp>',
    'reason': 'Owner explicitly approved this exact text in Discord',
    'body_sha256': raw_sha
}
```

The override binds to the **raw** body hash, so it cannot leak to an edited draft. It never rewrites
the gate verdict: both records are preserved and the override is reported as an override rather than
as a gate pass. Never use an override to paper over a hash mismatch â€” that hides the fact that the
text was never checked.

## Frozen text integrity is not owner approval

`runtime/linkedin/verify_draft.py` reports text/hash integrity only. A matching frozen file
and confirm token do not prove consent, fact-check completion or scheduling. Use the canonical
status command for those checks. Never overwrite a differing frozen body to make a test pass;
verify the correct owner-approved version and preserve its audit history.

## Overview

Generates and publishes LinkedIn posts for Mukund in the style of his previous bot. Uses Gemini for content and image generation, LinkedIn REST API for publishing, and maintains a dedupe index against all previously posted content.

## Architecture

- **Content generation:** `career-ops/linkedin_content_gen.py` â€” Gemini-based, old bot's style
- **Publishing:** `career-ops/linkedin_publish.py` â€” LinkedIn REST API, owner-gated
- **OAuth:** `career-ops/linkedin_auth.py` â€” Windows Credential Manager storage
- **Dedupe:** `runtime/linkedin/old_bot_posts_index.json` â€” imports old bot's 18 posts
- **Cron:** Tuesday, Wednesday, Thursday at 8:00 AM UK (`0 8 * * 2,3,4`), generates 3 posts (2 news + 1 personal)

## Content Style Rules

- **Lead with the actual event, not the surrounding controversy.** When a source article is supplied, the post must be about what happened, not about the debate around it. Read the whole article before drafting and identify the concrete event. (Lesson: given an article about AI companies destroying physical books, a post was written about data provenance and copyright debate instead â€” the destruction of the books was the point and was missed entirely.)
- **Vivid, concrete lede.** Open with a physical, sensory detail â€” a place, an object, an action. "There is a version of AI training that does not happen in a data centre. It happens in a warehouse, with a knife." Not: "AI training data raises important questions."
- **First-person reflection.** Use "I" naturally â€” "I keep coming back to...", "I think this is also...", "Should there be..." â€” not third-person analysis.
- **Preserve the source's uncertainty.** Where the article says a claim is unestablished, the post must say so too. "That part is not actually established." Do not repeat claims as fact.
- **Short, punchy paragraphs.** One to three sentences each. Blank line between paragraphs. No run-on analysis.
- **End with a genuine engagement question.** Not a rhetorical flourish â€” a real question the reader could answer.
- First-person narrative ("I", "my", "I've")
- Hook openings (concrete observation, honest question, practical contradiction)
- Short paragraphs with blank lines between them
- 3-6 hashtags grouped at the end
- No company names (user preference)
- No em dashes, en dashes, or semicolons
- End with engagement question
- Keep posts SHORT â€” roughly 1000 characters, counted across short one-to-two-sentence beats. A post of eight to ten beats is fine when the whole thing stays near that budget. A paragraph-count cap is the wrong rule: it rejects a post the owner would accept
- No images until user approves the text

## News Post Topic Selection

News posts must be about **concrete, physical, surprising events** â€” not generic cybersecurity breach news, not abstract policy debates, not "AI raises important questions" think pieces.

The profile to match (from the used-books post):
- A specific place, object, or action
- A measurable, physical consequence
- A surprising fact that makes the reader stop scrolling
- The intersection of AI/digital systems and the physical world

Good examples of the right shape (all now used or ruled out, so do not reuse â€” see the exclusion
list above):
- A data center in one county consuming 10% of that county's water
- US data centers out-consuming all heavy industry combined
- Physical books being destroyed to train AI models

Bad examples:
- "X company breached via zero-day" (generic breach news)
- "AI raises important questions about privacy" (abstract)
- "The future of AI regulation" (policy debate)

When planning a post, ask: "Is there a physical, concrete, surprising fact here?" If not, find a different topic.

## Write About The Thing The Source Reports

When the owner supplies a source article, the post must be about the specific thing that article
reports, led by its concrete event. Do not abstract it into the surrounding theme.

Mukund's correction when this went wrong: an article about AI firms buying used books, slicing the
spines off and discarding the physical copies, became a generic post about data provenance and
training-data ethics. The concrete event â€” physical books being destroyed â€” was the point, and it
was absent.

Procedure:

1. Read the full article, not the headline or the category page.
2. Write down the concrete event in one sentence: what physically happened, to what, by whom.
3. Open the post with that event. Keep the theme as the closing reflection, never the lede.
4. Keep the article's own uncertainty intact. Where it reports a claim as unestablished, the post
   must say so too rather than repeating the claim as fact.

If a supplied URL carries a search or filter parameter, confirm it actually filtered. A category
page returned regardless of the query means the filter matched nothing â€” say so and ask which
article was meant, rather than writing from whatever the page happened to show.

## Post Mix

- 1 news post about AI + cyber security (concrete, physical, surprising event)
- 1 news post about AI + something other than cyber security (not all posts about data centers â€” vary
  the topic; data centres and water are both on the exclusion list)
- 1 personal post from user's own experiences/projects
- All topics must be fresh â€” zero duplication against old bot's posts
- No countries, towns, or geographic references in posts (user preference)

## User Preferences

- No company names in posts
- No countries, towns, or geographic references
- Shorter posts for engagement
- 1 AI + cyber security, 1 AI + other, 1 personal mix
- No images until text is approved
- Topics must be fresh (not previously posted)
- User wants to review before publishing
- Always show all 3 posts when drafting â€” never ask for one at a time

## Two Fact Gates, Both Required

Publishing requires **two** independent gates. Neither can be skipped and neither can be satisfied by a hand-written record.

1. **Personal-claims gate** â€” `verify-cv-facts.mjs` in the Career Ops install (`C:\Users\mukun\Documents\ChatGPT\CV customizer\career-ops-career-ops-v1.29.0`). Checks the draft makes no claim about Mukund that his CV does not support (`allow_facts` / `allow_metrics` / `forbidden_phrases`). Run by `linkedin_workflow.py draft`; lands in `fact_gate`.
2. **News-claims gate** â€” `career-ops/linkedin_factcheck.py`. Checks the factual claims the post makes **about the world** against its cited sources. Lands in `news_fact_gate`.

`linkedin_content_gen.py:factcheck_post()` runs gate 2 automatically for every generated post. If the gate does not pass, the failure is reported to the incident log via `report_problem()`.

### The personal-claims gate cannot fact-check news

`verify-cv-facts.mjs` is a personal-claims gate, not a news checker. A deliberately fabricated news claim passes it untouched (verified: a false claim about "500 million books destroyed by Meta" returns `verdict: pass`). Never treat it as evidence that a post's news claims are true.

### Never hand-write a gate verdict

Writing `"fact_gate": {"verdict": "pass"}` into a draft artefact fabricates evidence in an audit trail, and the publish path reads that field as a gate. Do not create draft artefacts by hand; generate them through the module so the gate record is real.

### Verify what the publish path actually reads before trusting a gate

A gate only protects you if the publish path consults it. Do not assume that because a gate exists,
or because a provenance check exists in the gate module, the publisher calls it. Check the key the
publisher reads:

```bash
grep -n 'news_fact_gate\|fact_gate\|provenance\|blocked' career-ops/linkedin_publish.py
```

As last verified, `_preflight()` reads `news_fact_gate` (via `linkedin_factcheck.provenance_ok`, so
the record must name its gate and cover the exact bytes) and `personal_fact_gate`, and refuses a post
carrying no usable gate record at all. The personal gate is accepted at `pass` or `warn`; `block`
refuses. Re-run the grep rather than trusting this note â€” the check is cheap and the code moves.

### Never hand-write the source text either

A gate is only as good as the source it grounds against. Do not paste a paraphrase, a summary, or a
few sentences you wrote from the article into `cache_source_text()` or into a draft-building script.
A paraphrased source makes the gate judge the post against your own words: it either blocks a correct
post (the paraphrase is thinner than the post, so grounded claims read as unsupported) or passes a
post against claims you asserted yourself, which is self-confirmation dressed as verification.

Cache the real article text. If the publisher serves a stub to a plain fetch, capture the readable
article through a browser and cache that. A cache entry that is a few hundred words of paraphrase is
a fabricated source, not a cached one.

### The gate hash is over the prose-normalised text, not the raw body

`linkedin_factcheck.provenance_ok()` compares the gate record's `body_sha256` against
`sha256(post_prose(body))`. `post_prose` normalises whitespace, so a record can cover the same post
and still not equal `sha256(raw_body.strip())`. Compute both and keep them apart:

```python
import hashlib
import linkedin_factcheck as fc

raw_sha = hashlib.sha256(body.strip().encode("utf-8")).hexdigest()   # approval binding
--confirm-token takes this

fc.sha256_text(fc.post_prose(body))                                 # gate comparison
the gate record's body_sha256 is checked against this
```

Mixing the two makes a valid record read as stale (so you re-run the gate and burn judge calls)
and a re-run read as unnecessary. The publish path's `owner_approval_matches_bytes` check uses the
**raw** hash; the gate provenance check uses the **prose** hash.

A gate record that does not cover the current text is **re-run**, never patched. Editing
`body_sha256` to make a stale record match fabricates provenance, which is the same failure as
hand-writing a verdict. `career-ops/linkedin_arm_drafts.py` does this correctly: it reuses a record
that already covers the text and re-runs the gate when it does not.

### A non-passing gate must stop the pipeline, not just log

`linkedin_content_gen.py:factcheck_post()` reports a non-passing verdict via `report_problem()` and
then returns the post anyway. Reporting while continuing means the same blocked draft is re-emitted
on every run and the same incident re-alerts indefinitely, with nothing quarantined. The news-claims
The news-claims gate passes only at `pass`; the personal gate at `pass` or `warn`. When a gate returns anything worse
than that, mark the draft blocked and exclude it from the batch that goes to the owner. Never hand on
a post that a gate refused.

### A `block` is not automatically a gate defect

A gate that returns `block` with `unsupported_claims` reads as a broken gate and is usually a correct
one. Empty `evidence` is expected â€” the judge prompt asks for it. Check `source_chars_fed` against
`source_chars_total`, then search the cached article text for the claim's substance, *before*
concluding the gate never saw its source or reaching for an override. A rejection that survives every
run is almost always a real rejection: fix the claim and get fresh approval for the edited bytes. An
override is for a gate that is wrong, not for a post that is. See `references/fact-gate.md`.

### Publisher blocking (why the source cache exists)

The Atlantic and similar publishers serve a stub to a plain HTTP fetch, so claims cannot be grounded and the gate correctly returns `ungated` (never `pass`). Capture the article through a browser and store it with `linkedin_factcheck.cache_source_text(url, text)`; the gate reads that cache first. Without readable source text the gate refuses to pass â€” that is intended, not a bug.

## Capture approved content as data, not ad-hoc scripts

Use the shared state tool to capture the exact text already shown to the owner:

```
python career-ops/linkedin_state.py capture --text-file <exact-shown-text.txt> --date YYYY-MM-DD --approve-message-id <real-ID> --source-url <article-URL>
```

Capture validates owner consent before writing any artifact. It does not run providers, invent
verdicts, enable jobs or publish. For an explicitly approved revision, `--replace` requires fresh
consent matching the new bytes, preserves the old version, and invalidates old review receipts.
Use `--image <asset-in-this-artifact-directory>` to bind an authorized local image.

The old build/create-approved and hand-written override helper scripts are retired. They must
not overwrite the canonical artifact or manifest. Do not resurrect them to make a failed gate
look like a pass. Normal content work changes only bounded data through the state commands.

## Reconciling, planning and cancellation

`career-ops/linkedin_arm_drafts.py` is a compatibility entrypoint into `linkedin_state.py`.
It preserves the same state and review rules. Approval and gate failure are recorded
independently, with hash-checked writes and a shared mutation lock. Do not hand-edit the JSON.

After content is verified, bind an exact target date:

```
python career-ops/linkedin_state.py plan --drafts <artifact> --date YYYY-MM-DD
```

The canonical `schedule.json` is a versioned exact-date manifest pinning artifact path,
body hash, image hash and Europe/London publish time. Planning automatically arms the exact future slot when the owner-enabled publishing policy is on; otherwise jobs remain paused. Check the returned job state, not a narrative assumption.
Automatic publishing stays paused until separately authorized and deliberately enabled.

Cancellation uses `linkedin_state.py cancel --drafts <artifact> --reason <reason>` (or the
compatibility `--cancel`). It preserves historical owner consent, marks the artifact cancelled,
and removes only schedule entries for that exact artifact. It cannot unpublish a live post.
Never erase the published ledger to make a duplicate guard pass.

## Publishing Gates

1. OAuth credentials present (client_id + client_secret + valid access_token)
2. Explicit owner approval (--approve-publish + --confirm-token matching sha256 of body)
3. Not a duplicate (checked against published ledger)
4. Both fact gates passed **with provenance**
5. Not cancelled (a cancelled artefact is refused on its own record)

Dry-run by default; spend no network calls while validating.

### Supported scheduled dates

Scheduled automation supports Tuesday, Wednesday and Thursday at 08:00 Europe/London.
Each date must have an explicit canonical manifest entry. No newest-folder or hardcoded
week fallback exists. A different-day request requires an explicit owner-approved scheduling
change, not editing wrapper code. Never promise a time that has already passed.

### Confirm token must match the exact draft body

The `--confirm-token` must be the SHA-256 of the **exact draft body** that the publish path will read from the draft JSON â€” not the source text, not the factgate input, not a paraphrase. Compute it from the same bytes the publish path will hash. If the token does not match, the publish is refused with `owner_approval_matches_bytes: failed`.

To get the correct token, read the draft JSON, extract the post text, and compute `hashlib.sha256(text.encode('utf-8')).hexdigest()`.

Gate 4 is a truthfulness gate, not a formality: see `references/fact-gate.md`. Never hand-write a
`fact_gate` field into a draft artefact â€” the publish path reads that field as a gate, so a
fabricated `pass` is self-granted approval. The gate also only validates claims about Mukund; it
does **not** verify news content, so for a news post a passing gate discharges nothing and every
factual sentence still has to be checked against the source article.

### Dry-run every draft before arming a schedule

A batch that has never been dry-run is not ready to be armed. The publisher resolves the artefact
shape, the gate records, the credentials and the duplicate check in one pass, and any of them can
refuse the whole batch at the first gate â€” which then fails at 08:00 with nobody watching. See
"Draft artefact shape" below for the shape it accepts.

```bash
python career-ops/linkedin_publish.py publish \
  --drafts <draft.json> --kind post --index 0 \
  --approve-publish --confirm-token <sha256-of-body> --dry-run
```

A dry run spends no network calls and surfaces artefact-shape errors, missing credentials, duplicate
bodies and gate verdicts in one pass. Read the JSON: `ok`, `refused`, `fact_gate_verdict` and the
`blockers` list are the real answer, not the exit code. A batch that has not been dry-run is not
ready to be armed.

### The published ledger blocks republishing a post that was deleted

Gate 3 compares the draft body's SHA-256 against the published ledger
(`runtime/linkedin/published/posts.jsonl`). **Deleting a post on LinkedIn does not remove it from the
ledger.** So when the owner deletes a post and asks for it to go out again, the republish is refused
with `not_a_duplicate: failed` and "already published at ... pass --allow-duplicate to publish
again".

`--allow-duplicate` is the wrong fix â€” it defeats the duplicate guard for every future post. Remove
the stale ledger entry instead, then republish:

```python
import json
from pathlib import Path
ledger = Path("runtime/linkedin/published/posts.jsonl")
target = "<body_sha256 of the post being republished>"
kept = [l for l in ledger.read_text(encoding="utf-8").splitlines(True)
        if json.loads(l).get("body_sha256") != target]
ledger.write_text("".join(kept), encoding="utf-8")
```

Clear the entry whenever a post was deleted or removed after publishing and is being re-sent. Check
this **before** telling the owner a republish is scheduled â€” a job armed against an
already-published body fails silently at 08:00.

### Never leave a job armed without checking what it will actually publish

An auto-publish job points at one date-stamped draft directory. If that draft's body is already in
the published ledger, the job fails the duplicate check at 08:00 and the post never goes out with
nobody watching. After any schedule change, and before each week starts, run:

```bash
python runtime/linkedin/verify_armed_jobs.py
```

See `scripts/verify_armed_jobs.py`. It reads every armed `publish_scheduled_*` job, resolves the draft
that job will really publish, hashes it and compares against the ledger. Exit 1 means at least one
armed job would fail.

## Image Publishing

Publishing with an image is a three-step API sequence, all inside `linkedin_publish.py publish --image <path>`:

1. `POST /rest/images?action=initializeUpload` with `{"initializeUploadRequest": {"owner": <person_urn>}}` returns `value.uploadUrl` and `value.image` (the image URN).
2. `PUT` the raw image bytes to `uploadUrl` with the Bearer token **and a `Content-Type` header** (`image/jpeg` / `image/png`). Omitting Content-Type returns **HTTP 400 with an HTML error page** â€” this is the single easiest step to get wrong.
3. `POST /rest/posts` with `"content": {"media": {"id": <image_urn>}}` added to the normal payload.

Image style must match the post topic. `linkedin_content_gen.py:_classify_post_topic()` buckets the draft (ai_data / automation / ai_security / data_breach / phishing / general_cyber / personal) and `build_image_prompt()` emits the matching style and concept.

### Rotate distinct visual mediums, not fixed templates

Fixed style buckets with hardcoded prompts produce near-identical images across posts. If two posts land in the same bucket (e.g., two ai_security posts in consecutive weeks), they look like the same AI-generated image. The owner rejected this: "why are all the image types same from last weeks post I dont want same boring image types which look clearly ai generate."

**Solution:** rotate through a list of genuinely distinct visual mediums (documentary photograph, macro still life, paper collage, risograph print, architectural photograph, overhead flat lay, night street photograph, analogue film portrait). Each post takes the next one in rotation, skipping anything used in the last three posts. The rotation state is persisted to `runtime/linkedin/image_style_state.json`.

**AI-look bans in the prompt:** refuse glowing 3D renders, isometric tech scenes, neon/cyan-purple gradients, flat vector art, holographic interfaces, circuit patterns, shield icons, and rendered text. Rendered text is the single most obvious AI tell â€” ban it entirely and avoid screens as a subject.

**Health-AI concept fix:** the original health concept ("a glowing screen showing a calm conversational interface") produced gibberish rendered text on a tablet. Replace with physical objects (stethoscope, blank prescription slip, empty couch) and explicitly state "no screens and no text anywhere in the frame."

Always verify generated images visually (via `vision_analyze`) before presenting to the owner. Check: does it look like a real photograph or print, not a glossy AI render? Is there any rendered text? If it fails, regenerate with a different medium.

Image-generation depth: which interpreter to run it under, the rotation's side effect, the classifier buckets that hand the model a banned subject, and how to override them. See `references/image-generation.md`.

LinkedIn image rules: 1080x1350 (4:5 portrait) for feed reach, no text overlay, no logos or watermarks, generous negative space.

## Safe scheduled-path preview and exact-date execution

The installed weekday wrappers and the repository compatibility script delegate to the same
`linkedin_scheduled.py`. All flags and nonzero return codes propagate. Preview explicitly:

```
python runtime/linkedin/publish_scheduled.py tuesday --date YYYY-MM-DD --dry-run
```

Preview makes no subprocess/provider/publishing/ledger writes. Real scheduled execution
requires an exact current date, a matching pinned manifest, enabled owner-approved cron job,
verified consent, current reviews, unchanged image/text and no published duplicate. It never
selects the newest folder, falls back to a different week or publishes a future artifact early.
A disabled job remains disabled even when a planned artifact is ready. The direct scheduled
CLI defaults to preview; installed cron wrappers explicitly request execution and still enforce
all of these checks. Never use `--execute` merely to test readiness.

`verify_armed_jobs.py` delegates to canonical `check-jobs`. Zero enabled jobs means zero armed
posts, not "all posts will publish". All status reports must use this same interpretation.

## Draft artefact shape: let the flat reader find the gate records

The publisher reads a flat single-post artefact via `flat_post_draft()`, which lifts a fixed key
list â€” `post_text`, `news_fact_gate`, `personal_fact_gate`, `owner_override`, `owner_approval`
and `cancelled` â€” from the top level. If the same file ALSO contains a top-level
`drafts: [{kind, body}]` list, `drafts_of_kind()` selects that list instead and the entries carry
no gate records, so every gate reads as missing and the publish is refused. Write the flat shape
only: do not include a `drafts` list alongside `post_text`.

**Every key the publisher reads with `draft.get(KEY)` must be in that lifted list.** A preflight
check on a key the reader does not lift can never fire: no exception, no blocker, just a guard
that silently always passes while the file on disk looks correct. Add the writer field and its
lifted-list entry in the same commit, and confirm the key on the *loaded* draft, not on the file.

## Auto-stash hazard (read before editing career-ops files)

A poller runs `git stash` on uncommitted tracked changes every few minutes (stash messages `poller-autostash-<timestamp>`). Any edit to a tracked `career-ops/*.py` file that is not committed is silently reverted, which looks exactly like "my patch did not apply". The poller can also delete uncommitted new files entirely.

Therefore: apply the edit and `git commit` it in the **same terminal call**, or verify with `grep` and commit immediately. Never apply a multi-step patch sequence and expect it to survive to the next tool call. Confirm the change landed with `grep` before testing behaviour.

If a file is missing and you did not delete it, check `git log --all --oneline -- <path>` to find the last commit that had it, then restore with `git show <commit>:<path> > <path>` and commit immediately.

### The inverse hazard: a "restore" commit can revert a committed fix

The poller's counterpart commit â€” the one that puts stashed files back â€” has deleted a committed
implementation outright. A commit whose message reads like restoring auto-stashed files can remove
hundreds of lines that were already committed, so HEAD no longer contains a fix that git history
clearly shows was written.

When a bug you previously fixed reappears, check for a revert/restore commit **before** re-diagnosing
from scratch:

```bash
git log --oneline -- <path>          # find a suspicious restore/revert commit
git show --stat <commit> -- <path>   # confirm the line-count drop
git show <commit>:<path> | wc -l     # confirm the implementation is recoverable
git show <commit>:<path> > <path>    # restore it, then commit immediately
```

Treat a committed-and-tested fix as recoverable, not lost: the implementation usually survives in
the commit that introduced it.

## API Version Pitfall

LinkedIn API versions activate with a delay. Using the current month's version (e.g., `202610` in October) may return HTTP 426 `NONEXISTENT_VERSION`. Use a known-active version like `202607` instead.

## Python Environment

Use the existing Hermes Python interpreter for state commands and installed scheduled wrappers:
`%LOCALAPPDATA%/hermes/hermes-agent/venv/Scripts/python.exe`.
Do not hardcode the old Desktop bot interpreter into scheduler wrappers. Existing content/judge
modules own their backend/interpreter resolution; an unavailable backend is a blocked review,
not a reason to rewrite a wrapper or install packages into the runtime during a post job.

## Credential Storage

All secrets stored in Windows Credential Manager via `linkedin_auth.py`:
- `chief-linkedin-client-id`
- `chief-linkedin-client-secret`
- `chief-linkedin-access-token`
- `chief-linkedin-access-token-expiry-utc`
- `chief-gemini-api-key`

## Deduplication

Topic repetition is blocked by a **code-level guard reading a data file**, not by advice to a model.

`runtime/linkedin/topic_registry.json` is the single source of truth for topics already used. Each
entry carries a `status` (`used` = blocks, `pending` = warns but does not block its own week),
`used_on`, `evidence` and a `signals` list. `scripts/topic_reuse_check.py` reads it and exits 1 on a
match, and it is wired into `runtime/linkedin/build_approved_drafts.py` so a reused topic cannot
produce an artefact at all â€” the check runs *before* the fact gate, so a duplicate costs nothing.

The Sunday draft job (`7db108b00189`) must also read the registry and refuse any draft whose core
topic matches a `used` entry. Before proposing a mid-week replacement topic, read the registry and
confirm the new topic is not on it.

The old bot's 18 posts (July 2026) are imported into `runtime/linkedin/old_bot_posts_index.json`.
The narrative plan (SafePaste, InboxDefender, curiosity) is EXHAUSTED â€” use trending topics instead.

See `references/topic-reuse-guard.md` for the registry schema, the guard's matching rules, and how to
rebuild the registry from the published ledger.

The publish path records each post's `topic` in the ledger
(`runtime/linkedin/published/posts.jsonl`), so the registry can be rebuilt from evidence instead of
memory.

### Advisory dedupe is not enough

Asking a job to "check the published ledger" or "avoid previously posted topics" does not stop a
repeat, because none of those inputs can see a topic the owner himself posted: the old-bot index
covers only that bot's posts; the ledger is hash-based, so it catches only a byte-identical repost,
not a topic reused with new wording; and "the previous week's approved directories" misses a topic
from two weeks prior. Encode the block as data a job must read and match against, rather than as an
instruction â€” and when the owner says "I have already talked about X", add X to the registry the same
turn, not just to the job prompt.

Keep the registry current: whenever the owner rules a topic out, or a post goes live on a topic,
append an entry with the reason. A stale registry silently permits the exact repeat it exists to
prevent.

### The guard must be wired in, not merely written

A block list only works if something reads it at the moment the draft is produced. Creating the file
without pointing the drafting job at it leaves the gap exactly as wide. After adding or changing a
block list, confirm the consumer references it â€” grep the drafting prompt for the filename â€” and
commit the guard and its wiring in the same step.

### Register a topic as soon as it is approved, not after it publishes

Mark the entry `used` once the owner approves the exact text and the job is armed, so the next week's
drafting job cannot re-land on it. If that week's publish fails, revert the entry to `pending` â€” a
premature `used` silently blocks a legitimate fresh post.

## Source Caching (automatic)

`cache_topic_sources(topic)` runs **before** post generation, so the news-claim gate has real article text to ground claims against. Without readable source text the gate returns `ungated` (never `pass`) â€” that is intended. If source caching fails, the failure is reported to the incident log.

## Incident Reporting

When something breaks, report it to the Discord #incidents channel (`1551586416260161699`). See `references/incident-reporting.md` for the full procedure.

Key points:
- `career-ops/incident_report.py` logs incidents locally and attempts delivery
- `career-ops/incident_flush.py` flushes undelivered incidents via a cron job (every 30m)
- The cron job (`ebd5d0bcd189`) delivers to #incidents
- Never falsify outputs or errors: if something is not running, say so

## Workflow

1. Research trending topics via Gemini Google Search â€” look for concrete, physical, surprising events at the intersection of AI and the real world
2. Cache topic sources (automatic, before generation)
3. Generate 1 AI + cyber security post, 1 AI + other post, 1 personal post (text only)
4. News-claim gate runs automatically on each post
5. Present ALL 3 posts to user for review in a single message
6. After approval, generate images for all 3
7. Set up auto-publish cron jobs for each post on its respective day
8. Record in published ledger

### Start the week's content before the week starts

Each posting week needs its own drafts. Finishing one week's posts does not arm the next week: the
armed jobs point at the previous week's date-stamped directories and will fail the duplicate check.
When the owner asks for a plan, do not answer from memory â€” read the ledger, the draft directories
and the armed jobs, then state plainly whether this week's content exists. If it does not, say so and
produce it rather than describing last week's posts as if they were the plan.

Run `scripts/verify_armed_jobs.py` to see at a glance which armed job would publish and which would
fail. Write the resulting plan to `runtime/linkedin/plans/<week>_plan.md` (for example
`2026-W44_plan.md`) and commit it, so the week's state is on disk rather than in a chat scroll.

### The Sunday-to-Tuesday readiness check

Sunday creates text drafts only. After owner approval, capture the exact body, reconcile real
receipts and plan the exact date using the canonical state commands. A missing artifact/manifest
must report NOT_SCHEDULED and never select a previous week's post. `check-jobs` is the readiness
source; keep disabled jobs visibly paused rather than describing them as upcoming publications.

## HARD RULE: ground every draft in Mukund's own profile (owner instruction, 2026-10-12)

Before drafting ANY LinkedIn post, always consult Mukund's LinkedIn profile. The profile is
what sets what the posts may claim and also decides which topics are worth posting at all:

- **Grounding:** what Mukund has genuinely done, built, studied or is currently doing comes
  from the profile. A post may not claim a skill, a project, a credential or an experience that
  the profile does not support. If the profile does not support it, cut it.
- **Topic choice:** use the profile to pick angles and topics, not just to fact-check them. A
  post reads as belonging to a specific person when it connects to work they have actually
  done.
- **Personal posts especially:** the third weekly post is a reflection on Mukund's own work.
  It must come from the profile, not from a generic builder observation.
- **This applies in every session**, whether or not it is reminded.

Concrete procedure (owner decision 2026-10-12): every LinkedIn draft must consult Mukund's LIVE
LinkedIn profile from the web at https://www.linkedin.com/in/mukund-didwania-612771166 before
drafting. Read the profile sections relevant to the draft: headline, about, experience,
projects, education, certifications, skills. The profile on LinkedIn is the source of truth
for what Mukund has genuinely done, built, studied or is currently doing; the local
`career_context.md` and `public_voice.md` files are a secondary reference for style, voice
and boundaries, not a substitute for the live profile.

Fallback: if the live profile cannot be read (blocked, login wall, fetch failure), say so
plainly, fall back to the local profile files, and flag which claims could not be
grounded against the live profile. Never proceed silently on stale information.

## The weekly rhythm

Mukund wants fresh drafts every Sunday so he can review them before the week starts:

| Day | Job | What it does |
|-----|-----|--------------|
| Sunday 08:00 | `LinkedIn weekly drafts - Sunday 8am` (`7db108b00189`) | Researches and presents 3 fresh drafts for approval. Publishes nothing, generates no images. |
| Tuesday 08:00 | `LinkedIn Post 1 - Tuesday 8am` (`beb0251ed70c`) | Publishes the approved Tuesday post. |
| Wednesday 08:00 | `LinkedIn Post 2 - Wednesday 8am` (`f1b1452f18b1`) | Publishes the approved Wednesday post. |
| Thursday 08:00 | `LinkedIn Post 3 - Thursday 8am` (`8e6048e2dfa7`) | Publishes the approved Thursday post. |

The Sunday job drafts only. Approval, gating, images and arming remain a manual step triggered by Mukund's explicit approval of the exact text. The draft job must not arm the publish jobs on its own: an armed publish job pointed at a draft that was never approved is the failure this whole workflow exists to prevent.

## Cron Job

- **Name:** LinkedIn Post 1/2/3 - Tuesday/Wednesday/Thursday 8am
- **Schedule:** `0 8 * * 2`, `0 8 * * 3`, `0 8 * * 4` (one cron job per post)
- **Delivers to:** origin chat
- **Behavior:** publishes the pre-approved draft for that day automatically
- **Script:** `publish_scheduled.py <day>` (wrapper in `~/AppData/Local/hermes/scripts/`)

### Auto-publish workflow

Never create or patch publisher/wrapper code for a particular week. Code is installed once by
`scripts/install_linkedin_state.py`; each post changes data only.

1. Present exact text with its version marker, then obtain owner approval.
2. Capture/reconcile the exact body and verified approval through the canonical state tool.
3. Generate an authorized image using the existing content workflow and retain the intended file.
4. Verify both real fact-review receipts, frozen text and image through `status`.
5. `plan --drafts <artifact> --date YYYY-MM-DD` binds the exact artifact/body/image in the manifest.
6. Preview the exact date with `linkedin_scheduled.py <day> --date YYYY-MM-DD --dry-run`.
7. Only explicit authorization for automatic publishing permits enabling the corresponding existing
   cron job. This repair leaves all three publish jobs disabled. Do not recreate jobs each week. When
   explicitly enabling later, set next_run_at from the canonical slot publish_at via the scheduler
   API; never reuse a stale disabled-job timestamp across the London clock change.
8. Run `check-jobs` and report the exact phase. An approved, verified but disabled post is
   APPROVED_READY_PAUSED, never “will publish”. Cancellation removes only the exact target artifact.

Do not edit the published ledger to bypass duplicates. A one-week schedule change must remain an
explicit date-bound plan and must not silently change a recurring weekday's behavior forever.

## OAuth Note

LinkedIn did not return a refresh token for this app. `linkedin_auth.oauth_ready()` therefore accepts **either** a refresh token **or** a non-expired access token, so an access-token-only credential set still counts as ready. Check `linkedin_auth.py status` for the reason string and expiry.
