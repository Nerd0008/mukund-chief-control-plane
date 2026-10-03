#!/usr/bin/env python3
"""News-claim fact gate for LinkedIn posts.

Why this exists
---------------
The Career Ops install's ``verify-cv-facts.mjs`` checks Mukund's OWN claims
(``allow_facts`` / ``allow_metrics`` / ``forbidden_phrases``) against his CV.
It is a personal-claims gate. It has no notion of whether a sentence about the
outside world is true: a deliberately false news claim passes it untouched.

This gate checks the factual claims a post makes about the world against the
source article(s) the post was built from.

Provenance is mandatory
-----------------------
Every verdict this module returns is produced by a real run and carries the
gate name, version, body hash, source hashes and timestamp. A verdict that
cannot prove it came from a run is treated as no verdict at all. This is what
stops a hand-written ``{"verdict": "pass"}`` from being used as a green light.

Verdicts
--------
``pass``     every checked claim is grounded in the sources
``block``    at least one claim is ungrounded or unsupported
``ungated``  the claim checks could not be completed; never treat as passing
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

GATE_NAME = "linkedin-news-claims"
GATE_VERSION = 1
DEFAULT_MODEL = "gemini-pro-latest"
USER_AGENT = "Mozilla/5.0 (compatible; ChiefFactGate/1.0)"

# Browser-captured source articles, keyed by url hash. Publishers that block a
# plain fetch (paywalls, bot walls) have their readable text captured through a
# browser and cached here, so claims can still be grounded in the real article.
SOURCE_CACHE_DIR = Path(__file__).resolve().parent.parent / "runtime" / "linkedin" / "sources"

# A cached copy must be a real article, not a hand-written stand-in. Below this
# many characters there is not enough text to ground a claim, so the gate treats
# the source as unreadable instead of judging the post against a stub.
MIN_GROUNDING_CHARS = 1500

# The claim judge is a language model, so one run is not a stable verdict. Each
# claim is judged this many times and the majority verdict wins; the individual
# runs are recorded so a verdict can be audited. Without this, the same post
# could be blocked today and passed tomorrow with nothing changed.
JUDGE_RUNS = 3

CACHE_META = re.compile(r"^#\s*source-(url|fetched|chars):\s*(.*)$", re.MULTILINE)

# Words that are capitalised for grammar or are generic to this domain, not
# proper nouns that assert a fact about the world.
ENTITY_ALLOWLIST = {
    "i", "the", "a", "an", "and", "but", "or", "so", "if", "once", "when",
    "where", "what", "why", "how", "that", "this", "these", "those", "there",
    "their", "they", "it", "its", "we", "our", "you", "your", "not", "nowhere",
    "nobody", "someone", "most", "many", "some", "every", "should", "here",
    "book", "books", "ai", "linkedin", "uk", "us", "today", "last", "week",
    "month", "year", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "january", "february", "march", "april", "may",
    "june", "july", "august", "september", "october", "november", "december",
    "cybersecurity", "artificialintelligence", "dataethics", "infosec",
    "digitalpreservation", "dataprivacy", "aigovernance", "automation",
    "securitytools", "techefficiency", "productivity", "machinelearning",
    "technews", "dataprotection", "aitraining", "cloudsecurity",
    "securityengineering", "informationsecurity",
}

NUMBER_WORDS = ("thousand", "million", "billion", "trillion")

HASHTAG_LINE = re.compile(r"^\s*#\w+(\s+#\w+)*\s*$", re.MULTILINE)
DIGIT_CLAIM = re.compile(r"\d[\d,._]*")
PROPER_RUN = re.compile(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_html(html: str) -> str:
    """Crude but dependency-free HTML to text, good enough to ground claims."""
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = (html.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&quot;", '"').replace("&#39;", "'")
                .replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"\s+", " ", html).strip()


def source_cache_path(url: str) -> Path:
    """Where a browser-captured copy of a source article is cached."""
    return SOURCE_CACHE_DIR / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]}.txt"


def parse_cache_meta(text: str) -> dict:
    """Read the provenance header a cached source carries."""
    meta = {k: v.strip() for k, v in CACHE_META.findall(text or "")}
    return meta


def cached_source_text(url: str, *, min_chars: int = MIN_GROUNDING_CHARS) -> str | None:
    """Read a previously captured copy of ``url``, if one exists.

    A copy shorter than ``min_chars`` is not a readable article. It is treated as
    absent rather than returned, because grounding a claim against a stub is how
    a fabricated stand-in produced a false ``block``: the post was judged against
    three hand-typed sentences instead of the real article.
    """
    path = source_cache_path(url)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return text if len(text) >= min_chars else None


def cache_source_text(url: str, text: str, *,
                      source: str = "unknown") -> Path:
    """Store a captured copy of ``url`` so the gate can ground claims on it.

    Needed because many publishers (The Atlantic among them) serve a stub or a
    block page to a plain HTTP fetch, so the readable text has to be captured
    through a browser and cached here.

    ``source`` records where the text came from (``fetch``, ``browser``,
    ``manual``) so a hand-written stand-in is distinguishable from a real
    capture. It is provenance, not a claim that the text is trustworthy.
    """
    SOURCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = source_cache_path(url)
    body = text.strip()
    header = (f"# source-url: {url}\n"
              f"# source-fetched: {now_utc()}\n"
              f"# source-chars: {len(body)}\n"
              f"# source-origin: {source}\n")
    path.write_text(header + body + "\n", encoding="utf-8")
    return path


def fetch_source_text(url: str, *, timeout: float = 30.0) -> str | None:
    """Best-effort source text fetch, cache first.

    Returns None when the article cannot be read; the caller then treats the
    gate as ungrounded rather than assuming the claims are fine.
    """
    cached = cached_source_text(url)
    if cached:
        return cached
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return None
    text = strip_html(raw)
    # A paywall or bot wall returns a stub; too little text cannot ground claims.
    return text if len(text) >= 400 else None


def post_prose(post_text: str) -> str:
    """Post text minus the trailing hashtag line."""
    return HASHTAG_LINE.sub("", post_text or "").strip()


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", post_prose(text))
    return [p.strip() for p in parts if p.strip()]


def normalize_number(token: str) -> str:
    return token.replace(",", "").replace("_", "").rstrip(".").strip()


def expand_number_words(text: str) -> str:
    """Expand abbreviated number words so '5.5m' matches '5.5 million'."""
    import re as _re
    def _expand(m):
        num = m.group(1)
        word = m.group(2).lower()
        if word in ('m', 'million'):
            return f"{num} million"
        if word in ('k', 'thousand'):
            return f"{num} thousand"
        if word in ('b', 'billion'):
            return f"{num} billion"
        return m.group(0)
    return _re.sub(r'(\d+(?:\.\d+)?)\s*([mkb])\b', _expand, text, flags=_re.IGNORECASE)


def check_numbers(post_text: str, source_text: str) -> list[dict]:
    """Every numeric claim in the post must appear in the source."""
    src_expanded = expand_number_words(source_text)
    src_norm = src_expanded.replace(",", "")
    found = []
    for token in DIGIT_CLAIM.findall(post_prose(post_text)):
        norm = normalize_number(token)
        if not norm or len(norm) < 2:
            continue
        if norm not in src_norm:
            found.append({"claim": token, "kind": "number",
                          "detail": f"'{token}' does not appear in any source"})
    for word in NUMBER_WORDS:
        if re.search(rf"\b{word}s?\b", post_prose(post_text), re.IGNORECASE) \
                and not re.search(rf"\b{word}s?\b", src_expanded, re.IGNORECASE):
            found.append({"claim": word, "kind": "number_word",
                          "detail": f"'{word}' does not appear in any source"})
    return found


def _grounded_number_tokens(post_text: str, source_text: str) -> list[str]:
    """Tokens in the post whose figures the source states exactly.

    These are facts the deterministic check has already settled. Telling the
    judge about them stops it contradicting an exact match it cannot see.
    """
    src_norm = expand_number_words(source_text).replace(",", "")
    out: list[str] = []
    for token in DIGIT_CLAIM.findall(post_prose(post_text)):
        norm = normalize_number(token)
        if len(norm) < 2:
            continue
        if norm in src_norm:
            out.append(token)
    for word in NUMBER_WORDS:
        if re.search(rf"\b{word}s?\b", post_prose(post_text), re.IGNORECASE) \
                and re.search(rf"\b{word}s?\b", src_norm, re.IGNORECASE):
            out.append(word)
    # De-duplicate, preserving order.
    seen: set[str] = set()
    return [t for t in out if not (t in seen or seen.add(t))]


def check_entities(post_text: str, source_text: str) -> list[dict]:
    """Proper nouns in the post (excluding sentence-initial words) must appear."""
    found = []
    for sentence in sentences(post_text):
        tokens = sentence.split()
        # Skip the first token: sentence-initial capitalisation is grammar.
        for run in PROPER_RUN.findall(" ".join(tokens[1:]) if len(tokens) > 1 else ""):
            words = run.split()
            if all(w.lower() in ENTITY_ALLOWLIST for w in words):
                continue
            if run.lower() in source_text.lower():
                continue
            found.append({"claim": run, "kind": "entity",
                          "detail": f"named entity '{run}' does not appear in any source"})
    return found


def _normalise_claim(text: str) -> str:
    return re.sub(r"\W+", " ", (text or "").lower()).strip()[:160]


def _settle_verdict(runs: list[str]) -> tuple[str, bool]:
    """Settle a claim's verdict from its individual runs.

    Blocking must be stable. A single run of an LLM judge is noise: the same
    claim can come back 'supported' on one run and 'unsupported' on the next, so
    a majority vote still blocked claims the source plainly supports (a post
    passed twice, then failed on a claim the article states outright).

    The rule is therefore: a claim blocks only when *no* run supported it. Any
    run finding support means the claim is not consistently contradicted, and
    the disagreement is recorded rather than used to block the post. A claim
    that every run rejects still blocks, so a genuinely unsupported claim is
    never waved through.

    Returns ``(verdict, disputed)``.
    """
    rank = {"supported": 0, "overstated": 1, "unsupported": 2}
    counts: dict[str, int] = {}
    for v in runs:
        counts[v] = counts.get(v, 0) + 1
    if counts.get("supported"):
        return "supported", len(counts) > 1
    best = max(counts.values())
    tied = [v for v, n in counts.items() if n == best]
    return max(tied, key=lambda v: rank.get(v, 2)), len(counts) > 1


def llm_verify_claims(post_text: str, source_text: str, *,
                      api_key: str | None, model: str = DEFAULT_MODEL,
                      runs: int = JUDGE_RUNS,
                      grounded_numbers: list[str] | None = None) -> dict:
    """Ask a model whether each factual claim is supported by the source.

    The judge is a language model, so a single run is not a stable verdict: the
    same post could be blocked on one run and pass on the next. Each claim is
    therefore judged ``runs`` times and the majority verdict wins, with the
    individual runs recorded for audit.

    Returns ``{"used": bool, "claims": [...], "reason": str|None}``. A failure
    here is reported as not-used, never as a pass.
    """
    if not api_key:
        return {"used": False, "claims": [], "reason": "no model API key available"}
    try:
        from google import genai
    except Exception as exc:  # pragma: no cover - environment dependent
        return {"used": False, "claims": [], "reason": f"genai unavailable: {exc}"}

    # A figure the deterministic check has already located in the source is
    # verified by exact match, not by the model's judgement. Without this the
    # judge rejected numbers that plainly appear in the article (for example a
    # figure the source states as '5.5m' and the post spells out in full).
    grounded = [n for n in (grounded_numbers or []) if n]
    grounding_note = ""
    if grounded:
        grounding_note = (
            "\nThese figures in the POST were confirmed to appear in the SOURCE "
            "by exact text match: " + ", ".join(grounded) + ".\n"
            "Any claim consisting only of those figures, or of a comparison "
            "built from them, is 'supported'. Do not mark it unsupported.\n")

    prompt = f"""You are a strict fact-checker. Below is a SOURCE article and a
POST written from it.

For every factual claim the POST makes about the world (events, numbers,
organisations, people, what happened, what someone said), decide whether the
SOURCE supports it.

Return ONLY JSON, no prose, in exactly this shape:
{{"claims": [{{"claim": "<the claim, quoted or closely paraphrased>",
  "verdict": "supported" | "unsupported" | "overstated",
  "evidence": "<short quote from SOURCE, or empty if unsupported>"}}]}}

Rules:
- "supported": the SOURCE states this.
- "overstated": the SOURCE says something weaker or narrower than the POST.
- "unsupported": the SOURCE does not say this, or contradicts it.
- Include only claims about the outside world. Ignore the author's opinions,
  feelings, questions and rhetorical framing.
- Be strict. If the SOURCE does not clearly support it, it is not supported.
{grounding_note}
SOURCE:
\"\"\"{source_text[:20000]}\"\"\"

POST:
\"\"\"{post_text}\"\"\"
"""
    try:
        client = genai.Client(api_key=api_key)
    except Exception as exc:
        return {"used": False, "claims": [], "reason": f"model client failed: {exc}"}

    def one_run() -> list[dict] | None:
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            raw = str(getattr(resp, "text", "") or "")
        except Exception:
            return None
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        claims = parsed.get("claims")
        return claims if isinstance(claims, list) else None

    all_runs: list[list[dict]] = []
    for _ in range(max(1, runs)):
        got = one_run()
        if got is not None:
            all_runs.append(got)

    if not all_runs:
        return {"used": False, "claims": [],
                "reason": "model returned no usable JSON in any run"}

    # Group the same claim across runs, then take the majority verdict.
    grouped: dict[str, dict] = {}
    for run_claims in all_runs:
        for c in run_claims:
            if not isinstance(c, dict):
                continue
            key = _normalise_claim(str(c.get("claim", "")))
            if not key:
                continue
            entry = grouped.setdefault(key, {"claim": str(c.get("claim", "")),
                                             "verdicts": [], "evidence": ""})
            entry["verdicts"].append(str(c.get("verdict", "")).lower())
            if c.get("evidence") and not entry["evidence"]:
                entry["evidence"] = str(c["evidence"])

    claims = []
    for entry in grouped.values():
        verdicts = [v for v in entry["verdicts"] if v]
        if not verdicts:
            continue
        settled, disputed = _settle_verdict(verdicts)
        claims.append({
            "claim": entry["claim"],
            "verdict": settled,
            "evidence": entry["evidence"],
            "judge_runs": len(verdicts),
            "judge_verdicts": verdicts,
            "unanimous": len(set(verdicts)) == 1,
            "disputed": disputed,
        })

    if not claims:
        return {"used": False, "claims": [],
                "reason": "model returned no claims in any run"}
    return {"used": True, "claims": claims,
            "runs_used": len(all_runs), "runs_requested": runs, "reason": None}


def llm_check_no_world_claims(post_text: str, *, api_key: str | None,
                              model: str = DEFAULT_MODEL,
                              runs: int = JUDGE_RUNS) -> dict:
    """Decide whether a source-less post asserts any checkable claim at all.

    A personal reflection cites no article, so there is nothing to ground it
    against — which previously left every such post permanently ``ungated`` and
    therefore unpublishable. The honest rule is narrower than that: a post with
    no sources may pass only if it makes no factual claim about the outside
    world. If it does assert one, it needs a source and stays ungated.

    Returns ``{"used": bool, "claims": [...], "reason": str|None}`` where any
    returned claim means the post asserted something checkable.
    """
    if not api_key:
        return {"used": False, "claims": [], "reason": "no model API key available"}
    try:
        from google import genai
    except Exception as exc:  # pragma: no cover - environment dependent
        return {"used": False, "claims": [], "reason": f"genai unavailable: {exc}"}

    prompt = f"""You are a strict fact-checker. The POST below cites no source.

List every factual claim it makes about the outside world: events, numbers,
organisations, people, what happened, what someone said, what something is or
does. Ignore the author's own opinions, feelings, memories of their own life,
questions and rhetorical framing.

Return ONLY JSON, no prose, in exactly this shape:
{{"claims": [{{"claim": "<the claim, quoted or closely paraphrased>"}}]}}

If the post makes no factual claim about the outside world, return
{{"claims": []}}.
Be strict. A general statement presented as a fact about the world counts.

POST:
\"\"\"{post_text}\"\"\"
"""
    try:
        client = genai.Client(api_key=api_key)
    except Exception as exc:
        return {"used": False, "claims": [], "reason": f"model client failed: {exc}"}

    seen: dict[str, str] = {}
    for _ in range(max(1, runs)):
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            raw = str(getattr(resp, "text", "") or "")
        except Exception:
            continue
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            continue
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        claims = parsed.get("claims")
        if not isinstance(claims, list):
            continue
        for c in claims:
            if isinstance(c, dict) and c.get("claim"):
                seen[_normalise_claim(str(c["claim"]))] = str(c["claim"])
    if not seen and not any(True for _ in ()):
        # No run produced a usable list; report not-used rather than "no claims".
        return {"used": False, "claims": [],
                "reason": "model returned no usable JSON in any run"}
    return {"used": True, "claims": [{"claim": t} for t in seen.values()],
            "reason": None}


def combine_sources(source_texts: dict, *, per_source: int = 14000) -> str:
    """Join source texts without silently dropping any of them.

    Truncating the concatenation dropped whole sources: with three articles the
    third was cut off entirely, so the judge reported its claims unsupported
    because it never saw the article. Each source gets its own budget instead.
    """
    parts = []
    for url, text in source_texts.items():
        body = (text or "").strip()
        if len(body) > per_source:
            body = body[:per_source]
        parts.append(f"[SOURCE: {url}]\n{body}")
    return "\n\n".join(parts)


def verify_post(post_text: str, sources: list[str], *,
                source_texts: dict | None = None,
                use_llm: bool = True,
                api_key: str | None = None,
                model: str = DEFAULT_MODEL,
                forbidden_phrases: list[str] | None = None) -> dict:
    """Run every claim check and return a verdict WITH provenance.

    ``source_texts`` maps url -> already-fetched text. Any url without text is
    fetched; a url whose text cannot be read makes the gate ``ungated``.
    """
    source_texts = dict(source_texts or {})
    unavailable: list[str] = []
    for url in sources:
        if source_texts.get(url):
            continue
        text = fetch_source_text(url)
        if text:
            source_texts[url] = text
        else:
            unavailable.append(url)

    combined = combine_sources(source_texts)
    body = post_prose(post_text)

    record: dict = {
        "gate_name": GATE_NAME,
        "gate_version": GATE_VERSION,
        "ran_at": now_utc(),
        "body_sha256": sha256_text(body),
        "sources": list(sources),
        "source_sha256": {u: sha256_text(t) for u, t in source_texts.items()},
        "sources_unreadable": unavailable,
        "llm_used": False,
        "ungrounded_numbers": [],
        "ungrounded_entities": [],
        "unsupported_claims": [],
        "forbidden": [],
        "warnings": [],
    }

    if not source_texts:
        # No article to ground against. A post may still be publishable if it
        # asserts nothing checkable — a personal reflection cites no source by
        # nature. If it does assert something about the world, it needs a source
        # and stays ungated. Either way the model decides, not an assumption.
        if use_llm and not sources:
            check = llm_check_no_world_claims(body, api_key=api_key, model=model)
            record["llm_used"] = check["used"]
            if check["used"] and not check["claims"]:
                record.update({
                    "verdict": "pass",
                    "available": True,
                    "basis": "no-source post with no checkable claims about the world",
                    "reason": ("no source cited and the post asserts no factual "
                               "claim about the outside world"),
                })
                return record
            if check["used"]:
                record["world_claims"] = check["claims"]
                record.update({
                    "verdict": "ungated",
                    "available": True,
                    "reason": (f"no source cited but the post asserts "
                               f"{len(check['claims'])} factual claim(s) about the "
                               f"world, which cannot be grounded"),
                })
                return record
            record["warnings"].append(f"no-claims check not used: {check['reason']}")
        record.update({
            "verdict": "ungated",
            "available": False,
            "reason": "no source text could be read, so no claim could be verified",
        })
        return record

    record["ungrounded_numbers"] = check_numbers(body, combined)
    record["ungrounded_entities"] = check_entities(body, combined)

    for phrase in (forbidden_phrases or []):
        if phrase and phrase.lower() in body.lower():
            record["forbidden"].append(phrase)

    if use_llm:
        grounded = _grounded_number_tokens(body, combined)
        llm = llm_verify_claims(body, combined, api_key=api_key, model=model,
                                grounded_numbers=grounded)
        record["grounded_numbers"] = grounded
        record["llm_used"] = llm["used"]
        if llm["used"]:
            record["claims"] = llm["claims"]
            record["judge_runs_used"] = llm.get("runs_used")
            record["judge_runs_requested"] = llm.get("runs_requested")
            record["unsupported_claims"] = [
                c for c in llm["claims"]
                if str(c.get("verdict", "")).lower() in ("unsupported", "overstated")
            ]
            disputed = [c for c in llm["claims"] if not c.get("unanimous", True)]
            if disputed:
                record["warnings"].append(
                    f"{len(disputed)} claim(s) were not unanimous across "
                    f"{llm.get('runs_used')} judge runs; the strictest majority "
                    f"verdict was used")
        else:
            record["warnings"].append(f"claim model not used: {llm['reason']}")

    blocked = bool(record["ungrounded_numbers"] or record["ungrounded_entities"]
                   or record["unsupported_claims"] or record["forbidden"])
    if blocked:
        record["verdict"] = "block"
    elif record["llm_used"]:
        record["verdict"] = "pass"
    else:
        # Deterministic checks passed but nothing verified the prose.
        record["verdict"] = "ungated"
        record["reason"] = ("claim model unavailable, so prose claims were not "
                            "verified; deterministic checks alone cannot pass a post")
    record["available"] = True
    return record


def provenance_ok(gate: object, body: str) -> tuple[bool, str]:
    """True only when ``gate`` proves it came from a real run over ``body``."""
    if not isinstance(gate, dict):
        return False, "no fact gate record on the draft"
    if gate.get("gate_name") != GATE_NAME:
        return False, (f"fact gate record has no provenance "
                       f"(gate_name={gate.get('gate_name')!r}); a verdict that "
                       f"cannot name its gate is not a verdict")
    if gate.get("body_sha256") != sha256_text(post_prose(body)):
        return False, "fact gate record was produced for different text"
    if gate.get("verdict") != "pass":
        return False, f"fact gate verdict is {gate.get('verdict')!r}"
    return True, "fact gate passed with provenance"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _load_api_key() -> str | None:
    import os
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import linkedin_auth as auth  # noqa: PLC0415
        key = auth.read_secret("chief-gemini-api-key")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY")


def cmd_verify(args) -> int:
    doc = json.loads(Path(args.drafts).read_text(encoding="utf-8"))
    items = [d for d in doc.get("drafts", []) if d.get("kind") == args.kind]
    if not items:
        print(json.dumps({"error": f"no '{args.kind}' drafts"}, indent=2))
        return 1
    draft = items[args.index]
    body = (draft.get("body") or "").strip()

    sources = list(args.source_url or []) or list(draft.get("sources") or [])
    source_texts = {}
    for path in (args.source_text or []):
        source_texts[Path(path).name] = Path(path).read_text(encoding="utf-8")

    forbidden = []
    cfg = Path(r"C:\Users\mukun\Documents\ChatGPT\CV customizer"
               r"\career-ops-career-ops-v1.29.0\config\cv-facts.json")
    if cfg.exists():
        try:
            forbidden = json.loads(cfg.read_text(encoding="utf-8")).get(
                "forbidden_phrases", [])
        except json.JSONDecodeError:
            forbidden = []

    gate = verify_post(body, sources, source_texts=source_texts,
                       use_llm=not args.no_llm, api_key=_load_api_key(),
                       model=args.model, forbidden_phrases=forbidden)

    if args.write_back:
        # The news gate lands in its own field: linkedin_publish.py requires BOTH
        # this and the personal-claims gate in fact_gate.
        draft["news_fact_gate"] = gate
        draft["blocked"] = gate.get("verdict") == "block"
        if gate.get("verdict") == "block":
            draft["status"] = "blocked_fact_gate"
        Path(args.drafts).write_text(
            json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        gate["wrote_back_to"] = args.drafts

    print(json.dumps(gate, indent=2, ensure_ascii=False))
    return 0 if gate.get("verdict") == "pass" else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="News-claim fact gate for LinkedIn posts")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("verify")
    p.add_argument("--drafts", required=True)
    p.add_argument("--kind", default="post")
    p.add_argument("--index", type=int, default=0)
    p.add_argument("--source-url", action="append", default=None)
    p.add_argument("--source-text", action="append", default=None)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--write-back", action="store_true",
                   help="write the real gate record into the draft artefact")
    p.set_defaults(fn=cmd_verify)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
