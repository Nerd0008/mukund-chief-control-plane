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


def cached_source_text(url: str) -> str | None:
    """Read a previously captured copy of ``url``, if one exists."""
    path = source_cache_path(url)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return text if len(text) >= 400 else None


def cache_source_text(url: str, text: str) -> Path:
    """Store a captured copy of ``url`` so the gate can ground claims on it.

    Needed because many publishers (The Atlantic among them) serve a stub or a
    block page to a plain HTTP fetch, so the readable text has to be captured
    through a browser and cached here.
    """
    SOURCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = source_cache_path(url)
    header = f"# source-url: {url}\n"
    path.write_text(header + text.strip() + "\n", encoding="utf-8")
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


def llm_verify_claims(post_text: str, source_text: str, *,
                      api_key: str | None, model: str = DEFAULT_MODEL) -> dict:
    """Ask a model whether each factual claim is supported by the source.

    Returns ``{"used": bool, "claims": [...], "reason": str|None}``. A failure
    here is reported as not-used, never as a pass.
    """
    if not api_key:
        return {"used": False, "claims": [], "reason": "no model API key available"}
    try:
        from google import genai
    except Exception as exc:  # pragma: no cover - environment dependent
        return {"used": False, "claims": [], "reason": f"genai unavailable: {exc}"}

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

SOURCE:
\"\"\"{source_text[:20000]}\"\"\"

POST:
\"\"\"{post_text}\"\"\"
"""
    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(model=model, contents=prompt)
        raw = str(getattr(resp, "text", "") or "")
    except Exception as exc:
        return {"used": False, "claims": [], "reason": f"model call failed: {exc}"}

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {"used": False, "claims": [], "reason": "model returned no JSON"}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return {"used": False, "claims": [], "reason": f"model JSON unparsable: {exc}"}

    claims = parsed.get("claims")
    if not isinstance(claims, list):
        return {"used": False, "claims": [], "reason": "model JSON had no claims list"}
    return {"used": True, "claims": claims, "reason": None}


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

    combined = "\n\n".join(source_texts.values())
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
        llm = llm_verify_claims(body, combined, api_key=api_key, model=model)
        record["llm_used"] = llm["used"]
        if llm["used"]:
            record["claims"] = llm["claims"]
            record["unsupported_claims"] = [
                c for c in llm["claims"]
                if str(c.get("verdict", "")).lower() in ("unsupported", "overstated")
            ]
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
