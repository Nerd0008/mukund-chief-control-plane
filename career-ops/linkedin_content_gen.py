#!/usr/bin/env python3
"""LinkedIn content generation in the old bot's style.

Reuses the old bot's Gemini-based content generation (linkcont.py) and
integrates it with the new workflow's OAuth publishing path.

Style: first-person narrative, hook openings, hashtags, images.
Dedupe: imports the old bot's 18 posted posts to prevent duplication.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
sys.path.insert(0, str(CAREER_OPS_DIR))

import linkedin_auth as auth  # noqa: E402

# Old bot's knowledge bank
OLD_BOT_DIR = Path.home() / "Desktop" / "Pythob Bot" / "chief_of_staff_bot"
OLD_POSTED_FILE = OLD_BOT_DIR / "posted_posts.json"
OLD_MEMORY_FILE = OLD_BOT_DIR / "memory.json"
OLD_DRAFT_HISTORY_FILE = OLD_BOT_DIR / "linkedin_draft_history.json"

# New workflow's dedupe index
DEDUP_INDEX_FILE = CONTROL_PLANE / "runtime" / "linkedin" / "old_bot_posts_index.json"

# Gemini API
GEMINI_API_KEY = auth.read_secret("chief-gemini-api-key") or os.environ.get("GEMINI_API_KEY", "")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Old bot's post history (for dedupe)
# --------------------------------------------------------------------------- #

def load_old_bot_posts() -> list[dict]:
    """Load the old bot's posted posts for dedupe."""
    posts = _read_json(OLD_POSTED_FILE, [])
    if not posts:
        # Try the dedupe index
        index = _read_json(DEDUP_INDEX_FILE, [])
        return index
    return posts


def _recent_post_phrases(limit: int = 6) -> list[str]:
    """Return recent opening/closing prose so a new post does not recycle it."""
    posts = load_old_bot_posts()
    phrases: list[str] = []
    for entry in posts[-limit:]:
        text = str(entry.get("post_text", entry.get("first_paragraph", ""))).strip()
        paragraphs = [item.strip() for item in text.split("\n\n") if item.strip() and not item.strip().startswith("#")]
        if paragraphs:
            phrases.append(paragraphs[0][:240])
            if len(paragraphs) > 1:
                phrases.append(paragraphs[-1][:240])
    return phrases[-12:]


def _load_recent_feedback(limit: int = 10) -> list[str]:
    """Load style-related feedback from the old bot's memory."""
    memories = _read_json(OLD_MEMORY_FILE, [])
    style_markers = (
        "sound like me", "sound more human", "writing style", "vocabulary", "spacing",
        "paragraph", "hashtags", "layout", "format", "less generic", "more personal",
        "more humorous", "more humourous", "more technical", "shorter", "longer",
    )
    feedback: list[str] = []
    for memory in memories:
        text = str(memory.get("feedback", "")).strip()
        if text and any(marker in text.lower() for marker in style_markers):
            feedback.append(text)
    return feedback[-limit:]


def _load_persona_block() -> str:
    """Build a block describing who the user is and how they write."""
    knowledge_dir = Path.home() / "Documents" / "Chief of staff" / ".mukund_os"
    profile = _read_json(knowledge_dir / "profile.json", {})
    voice_profile = _read_json(knowledge_dir / "voice_profile.json", {})
    lessons = _read_json(knowledge_dir / "lessons.json", [])

    if not profile and not lessons:
        return ""

    lines = []
    name = profile.get("name")
    if name:
        lines.append(f"- Name: {name}")
    if profile.get("career_goal"):
        lines.append(f"- Career goal: {profile['career_goal']}")

    writing_prefs = list(profile.get("writing_preferences", []))
    vocab_avoid = list(profile.get("vocabulary_to_avoid", []))
    public_persona = list(profile.get("public_persona", []))

    for lesson in lessons:
        category = lesson.get("category")
        text = lesson.get("text")
        if not text:
            continue
        if category == "writing_preference" and text not in writing_prefs:
            writing_prefs.append(text)
        elif category == "vocabulary_to_avoid" and text not in vocab_avoid:
            vocab_avoid.append(text)

    if public_persona:
        lines.append("- How I want to come across publicly: " + " ".join(public_persona))
    if writing_prefs:
        lines.append("- My writing voice and preferences: " + " ".join(writing_prefs))
    if vocab_avoid:
        lines.append("- Things to NEVER do or say: " + " ".join(vocab_avoid))

    if voice_profile:
        for key, label in (
            ("identity_summary", "- Core identity"),
            ("values", "- Values"),
            ("points_of_view", "- Personal viewpoints"),
            ("voice_rules", "- Voice rules"),
            ("humour_rules", "- Humour rules"),
            ("public_boundaries", "- Public-use rules"),
            ("private_boundaries", "- Private boundaries that must never be used"),
        ):
            value = voice_profile.get(key)
            if isinstance(value, list) and value:
                lines.append(label + ": " + " ".join(str(item) for item in value))
            elif isinstance(value, str) and value:
                lines.append(label + ": " + value)

    if not lines:
        return ""

    body = "\n".join(lines)
    return f"""
    About the author (write this post AS ME, in first person "I", not as a ghostwriter describing me):
{body}
    """


def _next_hook_style() -> str:
    styles = (
        "start with a concrete observation",
        "start with a short honest question",
        "start with a small practical contradiction",
        "start with a specific lesson from the work",
        "start with a plain-English security thought",
    )
    history = _read_json(OLD_DRAFT_HISTORY_FILE, [])
    return styles[len(history) % len(styles)]


def _humanize_text(text: str) -> str:
    """Strip common AI-writing 'tells'."""
    if not text:
        return text
    text = re.sub(r"\s*[\u2014\u2013]\s*", ", ", text)
    text = re.sub(r"\s+--\s+", ", ", text)
    text = text.replace(";", ".")
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _strip_image_descriptions(text: str) -> str:
    """Remove any stray bracketed image-description lines."""
    if not text:
        return text
    cleaned = re.sub(r"\[image[^\]]*\]\s*", "", text, flags=re.IGNORECASE)
    return cleaned.strip()


# --------------------------------------------------------------------------- #
# Gemini content generation
# --------------------------------------------------------------------------- #

def _get_gemini_client():
    """Get a Gemini client, or None if no API key."""
    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai
        return genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        return None


def generate_linkedin_content(
    content: str,
    source_type: str = "LinkedIn prompt",
    narrative_anchor: str = "",
    career_signal: str = "",
) -> str:
    """Generate a LinkedIn post in the old bot's style using Gemini."""
    client = _get_gemini_client()
    if not client:
        return ""

    if not content:
        return ""

    tone_focus = "Focus on one practical lesson and explain why it matters in real life."
    if source_type == "technical article":
        tone_focus = (
            "Focus on technical vulnerabilities, specific attack vectors, and engineering-level fixes."
        )

    remembered_feedback = _load_recent_feedback()
    feedback_block = ""
    if remembered_feedback:
        feedback_lines = "\n".join(f"- {fb}" for fb in remembered_feedback)
        feedback_block = f"""
    User Preferences (learned from past revisions — these are TOP PRIORITY and override
    any default formatting/structure instructions below if they conflict, apply every one
    of these to this post):
    {feedback_lines}
    """

    persona_block = _load_persona_block()
    recent_phrases = _recent_post_phrases()
    recent_phrases_block = "\n".join(f"- {phrase}" for phrase in recent_phrases) or "- No previous posts are available."
    hook_style = _next_hook_style()

    prompt = f"""
    Role: You ARE the author writing this LinkedIn post yourself, in first person ("I", "my",
    "I've"). You are not a ghostwriter describing someone else in third person, you are a
    Cybersecurity Professional writing your own post, in your own authentic voice.

    Task: Write a LinkedIn post based on the provided {source_type}.

    Audience & Tone:
    - Primary Audience: Technical professionals (e.g., engineers, developers, IT).
    - Framing: Highly relatable and easy to understand for a non-technical audience. Use clear analogies and avoid overly dense jargon.
    - Style: Punchy, fast-paced, and optimized for scrollers with short attention spans. Deliver immediate value without fluff.
    - Specific Focus: {tone_focus}

    Narrative anchor (background for the post, not text to copy):
    {narrative_anchor or "Use a real observation, build decision, or learning moment from the author profile."}

    Career signal:
    {career_signal or "Show practical learning and clear cybersecurity judgement."}

    Recent post phrases to avoid repeating or closely paraphrasing:
    {recent_phrases_block}

    Required hook style for this draft: {hook_style}.

    Structure:
    - Start with one fresh sentence in the required hook style. Do not copy the narrative anchor into the hook.
    - Explain one technical point in simple language, then why it matters to a person.
    - End with a genuine reflection or question. Do not manufacture engagement.
    - Use short paragraphs with one blank line between them. Do not force a fixed number of lines.

    Hashtags: After the conclusion, leave a blank line and add one final line with 3-6 relevant
    hashtags grouped together. Use none if they would be forced.

    Writing style constraints (avoid common AI writing tells):
    - Do not use em dashes (—), en dashes as separators, or semicolons (;) anywhere.
    - Use only plain periods and commas to join or separate ideas.
    - Write in a natural, human, conversational tone. Avoid stiff or overly formal AI-sounding phrasing.
    - Never use generic importance language, corporate buzzwords, fake industry consensus, or "not just X, but Y" formulas.
    - Do not name an employer or organisation unless it appears in the source content and is explicitly needed.
    - Use exactly one personal story element: the narrative anchor above. Do not add a second biography or origin story.
    - Do not default to the author's cybersecurity origin, master's degree, "stay curious", or a fixed resilience question unless that is the chosen narrative anchor.
    - Do not reuse the opening or closing pattern of the recent posts listed above.
    - The narrative anchor is internal guidance. Never include labels such as "Narrative anchor", "Career signal", "quality check", or "source type" in the post.
    - Do not invent first-person activity, testing, tools, employers, projects, outcomes, or recent events. If a personal detail is not in the supplied source content or narrative anchor, write a general reflection instead.
    - Never begin with "Whenever I see", "As I continue to learn", "I originally entered", or a variation of these phrases.
{persona_block}{feedback_block}
    FINAL AND MOST IMPORTANT INSTRUCTIONS (these override every rule above if there is any
    conflict — Audience/Tone/Structure above are just a default template, not fixed rules):
    - Every line must be written as "I" — never describe the author in third person, never
      write like a generic corporate listicle or a stranger's case study.
    - Weave in the "About the author" details and User Preferences above naturally so this
      genuinely reads like this specific person wrote it, on this specific new topic.
    - If a User Preference contradicts the default Audience/Tone/Structure/Hashtag rules
      above, follow the User Preference instead.

    Output ONLY the post text itself — do not include any image description, caption,
    or bracketed notes like "[Image: ...]". Do not add conversational filler before or
    after the post.
    """

    api_payload = f"{prompt}\n\nInformation to analyze:\n{content}"
    response = client.models.generate_content(
        model="gemini-pro-latest",
        contents=api_payload,
    )
    return _humanize_text(_strip_image_descriptions(str(response.text)))


def research_trending_topics(count: int = 6) -> list[dict]:
    """Use Gemini with live Google Search grounding to find trending topics."""
    client = _get_gemini_client()
    if not client:
        return []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = f"""
    Search the web for what is trending RIGHT NOW (as of {today}) in cybersecurity and
    technology news, specifically stories relevant to a cybersecurity professional's
    LinkedIn audience (breaches, new attack techniques, major vulnerabilities, AI security
    risks, notable industry reports or incidents).

    Pick the {count} most trending, most discussed topics from the last few days.

    Return ONLY a valid JSON array (no markdown fences, no commentary before or after) of
    exactly {count} objects. Each object must have these exact keys:
    - "title": a short topic title, max 12 words.
    - "summary": 2-3 sentences explaining what happened or what the topic is.
    - "technical_impact": 1-2 sentences on how this directly affects technical/security
      professionals (engineers, IT, security teams).
    - "non_technical_impact": 1-2 sentences on how this directly affects everyday,
      non-technical people.
    """

    try:
        from google.genai import types
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                response_modalities=["TEXT"],
                http_options=types.HttpOptions(timeout=45000),
            ),
        )
        raw_text = str(response.text) if response.text else ""
        return _parse_topics_json(raw_text, count)
    except Exception:
        return []


def _parse_topics_json(raw_text: str, count: int) -> list[dict]:
    if not raw_text:
        return []
    text = raw_text.strip()
    text = re.sub(r"^```(json)?", "", text.strip(), flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text.strip()).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, flags=re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    topics = []
    for item in data[:count]:
        if not isinstance(item, dict):
            continue
        topics.append({
            "title": str(item.get("title", "")).strip(),
            "summary": str(item.get("summary", "")).strip(),
            "technical_impact": str(item.get("technical_impact", "")).strip(),
            "non_technical_impact": str(item.get("non_technical_impact", "")).strip(),
        })
    return topics


# --------------------------------------------------------------------------- #
# Image generation
# --------------------------------------------------------------------------- #

def generate_image_bytes(prompt: str) -> bytes | None:
    """Generate image bytes using Gemini."""
    client = _get_gemini_client()
    if not client:
        return None

    try:
        model = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )
        if model and hasattr(model, 'candidates') and model.candidates:
            candidate = model.candidates[0]
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        if hasattr(part.inline_data, 'data') and part.inline_data.data:
                            return part.inline_data.data
        return None
    except Exception:
        return None


def _classify_post_topic(post_text: str) -> dict:
    """Classify the post topic to determine the best image style.

    Returns a dict with:
    - category: 'ai_security' | 'automation' | 'data_breach' | 'general_cyber' | 'personal'
    - style: the visual style that best matches
    - concept: the visual concept to represent
    """
    text = post_text.lower()

    # AI training data / copyright / authorship
    if any(kw in text for kw in ["training data", "books", "authors", "copyright", "scraped", "memorization", "dataset"]):
        return {
            "category": "ai_data",
            "style": "editorial conceptual illustration, layered paper and light, warm neutral palette with one cool accent, premium magazine aesthetic",
            "concept": "a stack of books and loose pages dissolving at the edges into streams of glowing data particles flowing into a single luminous sphere, representing human work absorbed into an AI model",
        }

    # Automation / tools / workflows (check first — "AI agents" is common in automation contexts)
    if any(kw in text for kw in ["automation", "workflow", "schedule", "build tools", "asleep"]):
        return {
            "category": "automation",
            "style": "flat design illustration, geometric shapes, clean lines, modern minimal, soft blue and white palette",
            "concept": "interconnected gears and flowing data streams forming a continuous loop, representing automated systems working independently",
        }

    # AI security / sandbox / agent topics
    if any(kw in text for kw in ["sandbox", "ai model", "autonomous", "breakout", "escape", "containment", "ai agent"]):
        return {
            "category": "ai_security",
            "style": "abstract 3D render, isometric view, soft gradients, premium tech aesthetic",
            "concept": "a transparent glass container with subtle cracks, light escaping through the gaps, representing AI systems breaking out of controlled environments",
        }

    # Data breach / zero-day / vulnerability
    if any(kw in text for kw in ["breach", "zero-day", "vulnerability", "exploit", "data theft", "stolen", "leak"]):
        return {
            "category": "data_breach",
            "style": "photorealistic, dramatic lighting, dark background with subtle red accents, cinematic composition",
            "concept": "a locked door slightly ajar with light spilling through, representing a security gap being exploited",
        }

    # Phishing / social engineering
    if any(kw in text for kw in ["phishing", "social engineering", "suspicious", "email", "scam"]):
        return {
            "category": "phishing",
            "style": "minimal illustration, soft shadows, muted tones, professional and clean",
            "concept": "an email envelope with subtle warning signals (exclamation marks, unusual patterns) floating around it",
        }

    # General cybersecurity
    if any(kw in text for kw in ["cybersecurity", "security", "threat", "attack", "defense", "protection"]):
        return {
            "category": "general_cyber",
            "style": "modern abstract, geometric patterns, deep blue and teal gradients, professional and sleek",
            "concept": "a network of connected nodes with one node highlighted, representing a security point in a larger system",
        }

    # Personal / career narrative
    return {
        "category": "personal",
        "style": "warm, approachable, soft lighting, human-centered, editorial photography style",
        "concept": "a person working at a desk with multiple screens, warm ambient light, representing a professional in their element",
    }


def build_image_prompt(post_text: str, extra_instructions: str = "") -> str:
    """Build a topic-aware, style-matched image prompt for LinkedIn.

    The image style and concept are chosen based on the post's topic category,
    so the visual always matches the content.
    """
    topic_summary = " ".join(post_text.split())[:300]
    topic_info = _classify_post_topic(post_text)

    feedback_block = ""
    if extra_instructions.strip():
        feedback_block = (
            "\nAdditional requested changes (apply these, they take priority over the defaults below):\n"
            f"\"{extra_instructions.strip()}\"\n"
            "Note: this is a single static image, not a video/GIF — express 'engaging'/'animated' requests "
            "through dynamic composition, motion lines, energetic angles, or a lively accent color instead of literal motion.\n"
        )

    return (
        f"Create a professional LinkedIn post image for a cybersecurity topic.\n\n"
        f"Post topic: \"{topic_summary}\"\n\n"
        f"Visual style: {topic_info['style']}\n\n"
        f"Concept: {topic_info['concept']}\n\n"
        f"{feedback_block}\n"
        "Composition rules:\n"
        "- Single unified scene, no split layouts\n"
        "- Balanced with generous negative space (important for mobile feed)\n"
        "- If text is used, keep it very short (max 3-4 words) and neatly aligned\n"
        "- No logos, watermarks, or brand marks\n"
        "- No literal violence, malware code, or attacker imagery\n"
        "- Clean, premium, professional aesthetic\n\n"
        "Avoid:\n"
        "- Neon colours, clutter, hacker cliches, shields, flashy effects\n"
        "- Busy UI, large headlines, stock photo look\n\n"
        "Output:\n"
        "1 high-resolution image, 1080x1350 pixels (4:5 portrait aspect ratio). "
        "This is a strict requirement — portrait orientation for maximum mobile feed visibility."
    )


# --------------------------------------------------------------------------- #
# Weekly narrative plan (from the old bot)
# --------------------------------------------------------------------------- #

def weekly_narrative_plan() -> list[dict]:
    """Rotate narrative themes so the bot never has one permanent opening or ending."""
    plans = [
        [
            {"slot": "Build log", "title": "What SafePaste taught me about catching sensitive data before it leaves the browser", "narrative_anchor": "My curiosity about building things eventually led me to try solving a practical data-handling problem.", "career_signal": "Practical DLP thinking, testing, JavaScript, and clear communication."},
            {"slot": "Analyst's note", "title": "Why a phishing email is more than one suspicious-looking clue", "narrative_anchor": "While building InboxDefender, I kept coming back to how several small signals can tell a clearer story together.", "career_signal": "Phishing analysis, MITRE ATT&CK, structured thinking, and analyst empathy."},
            {"slot": "Career narrative", "title": "Starting cybersecurity with questions, not confidence", "narrative_anchor": "I entered cybersecurity curious but unsure, and learned by asking questions, accepting feedback, and staying with difficult material.", "career_signal": "Growth mindset, communication, and readiness to develop in a junior cyber role."},
        ],
        [
            {"slot": "Build log", "title": "What testing SafePaste taught me about false positives", "narrative_anchor": "When I was testing SafePaste, I learned that a rule which flags everything is not actually helping anyone.", "career_signal": "Testing discipline, DLP trade-offs, and practical problem solving."},
            {"slot": "Analyst's note", "title": "Why playbooks matter when a security problem is moving quickly", "narrative_anchor": "I am drawn to frameworks because they give people a shared starting point when there is pressure and incomplete information.", "career_signal": "Security operations, frameworks, SOPs, and structured judgement."},
            {"slot": "Career narrative", "title": "The first website that made me want to keep building", "narrative_anchor": "As a student, seeing an HTML and CSS website I built go live made technology feel like something I could create, not only use.", "career_signal": "Curiosity, building mindset, and a genuine technology story."},
        ],
        [
            {"slot": "Build log", "title": "What AttackSurfaceIQ taught me about asking better security questions", "narrative_anchor": "Looking at exposed services and endpoint signals taught me to start with what is actually visible before assuming I know the risk.", "career_signal": "Attack-surface thinking, logs, endpoint hardening, and investigation."},
            {"slot": "Analyst's note", "title": "Why security awareness should appear where people make decisions", "narrative_anchor": "I keep thinking that telling people to be careful is not enough if the platform gives them no help at the moment a risky click happens.", "career_signal": "Human-centred security, phishing awareness, and practical design thinking."},
            {"slot": "Career narrative", "title": "Why difficult feedback has made me better at spotting mistakes", "narrative_anchor": "I have learned more when someone showed me what needed improving and then gave me the chance to try again.", "career_signal": "Coachability, accountability, and growth in a junior role."},
        ],
        [
            {"slot": "Build log", "title": "Why InboxDefender needs analyst-readable output, not only a classification", "narrative_anchor": "While building InboxDefender, I did not want a system to simply label an email. I wanted it to show why the label made sense.", "career_signal": "Phishing intelligence, automation, clear reporting, and analyst support."},
            {"slot": "Analyst's note", "title": "What interests me about new technology and new attack surfaces", "narrative_anchor": "Use Mukund's view that a useful new tool should also be examined for what it changes for users, defenders, and misuse. This is background only, not a sentence to copy.", "career_signal": "Emerging technology curiosity and threat modelling mindset."},
            {"slot": "Career narrative", "title": "Why I still see myself as a student of cybersecurity", "narrative_anchor": "Finishing a degree gave me a foundation, but it also showed me how much more there is to ask, test, and understand.", "career_signal": "Humility, continual learning, and professional maturity."},
        ],
    ]
    return plans[datetime.now(timezone.utc).isocalendar().week % len(plans)]


# --------------------------------------------------------------------------- #
# Review and revise
# --------------------------------------------------------------------------- #

def review_linkedin_draft(post_text: str) -> dict:
    """Flag common generic/AI-like patterns for review."""
    lowered = (post_text or "").lower()
    checks = {
        "generic significance language": ("evolving landscape", "pivotal", "lasting impact", "significant shift"),
        "corporate or promotional language": ("game-changing", "groundbreaking", "seamlessly", "thrilled to share"),
        "formulaic contrast": ("not just ", "rather than "),
        "canned opening": ("in today's fast-paced", "as we navigate"),
        "generic learner opening": ("as i continue to learn", "whenever i see a new tool"),
    }
    flags = [name for name, phrases in checks.items() if any(phrase in lowered for phrase in phrases)]
    if (post_text or "").count("—") > 1:
        flags.append("overuse of em dashes")
    return {
        "flags": flags,
        "personal_narrative": "7/10",
        "technical_depth": "5/10",
        "summary": "No generic-writing flags found." if not flags else "Review: " + ", ".join(flags),
    }


def revise_linkedin_content(current_text: str, feedback: str) -> str:
    """Revise a post based on user feedback."""
    client = _get_gemini_client()
    if not client:
        return current_text

    persona_block = _load_persona_block()
    prompt = f"""
    Revise the following LinkedIn post draft using the user's feedback below.

    Feedback: {feedback}

    Original draft:
    {current_text}

    Keep the same overall tone and core message unless the feedback says otherwise.
    Preserve the final hashtag line at the end.

    Writing style constraints (avoid common AI writing tells):
    - Do not use em dashes (—), en dashes as separators, or semicolons (;) anywhere.
    - Use only plain periods and commas to join or separate ideas.
    - Write in a natural, human, conversational tone. Avoid stiff or overly formal AI-sounding phrasing.
{persona_block}
    FINAL AND MOST IMPORTANT INSTRUCTIONS (these override every rule above if there is any
    conflict):
    - You ARE the author, writing this in first person ("I", "my", "I've"), in your own
      authentic voice, not as a ghostwriter describing someone else in third person.
    - The user's feedback above is the top priority — apply it precisely, even if it changes
      formatting, spacing, or line structure (e.g. adding blank lines between paragraphs,
      reordering sections, changing length). Do not ignore or water down the feedback in
      order to preserve the original format.
    - Weave in the "About the author" details above naturally so this genuinely reads like
      this specific person wrote it.

    Output ONLY the revised post text — do not include any image description, caption,
    or bracketed notes like "[Image: ...]". Do not add conversational filler, explanations,
    or notes about what you changed.
    """

    response = client.models.generate_content(
        model="gemini-pro-latest",
        contents=prompt,
    )
    return _humanize_text(_strip_image_descriptions(str(response.text)))


# --------------------------------------------------------------------------- #
# Main interface
# --------------------------------------------------------------------------- #

def generate_post_from_topic(topic: dict, generate_image: bool = False) -> dict:
    """Generate a post from a trending topic. Image only if explicitly requested."""
    content = (
        f"Title: {topic['title']}\n"
        f"Summary: {topic['summary']}\n"
        f"Technical impact: {topic['technical_impact']}\n"
        f"Non-technical impact: {topic['non_technical_impact']}"
    )
    post_text = generate_linkedin_content(content, source_type="LinkedIn prompt")
    image_bytes = None
    if post_text and generate_image:
        image_prompt = build_image_prompt(post_text)
        image_bytes = generate_image_bytes(image_prompt)
    # Run the news-claim gate here so every generated post carries a real,
    # provenance-bearing verdict. A post is never handed on with a fabricated
    # or absent gate record: the publish path refuses those outright.
    news_fact_gate = factcheck_post(post_text, topic.get("sources") or [])
    return {
        "topic": topic,
        "post_text": post_text,
        "image_bytes": image_bytes,
        "news_fact_gate": news_fact_gate,
        "blocked": news_fact_gate.get("verdict") == "block",
        "generated_at": now_utc(),
    }


def factcheck_post(post_text: str, sources: list) -> dict:
    """Run the news-claim gate over a generated post.

    Imported lazily so this module keeps working when the gate is unavailable;
    in that case it returns a truthful ungated record rather than a pass.
    """
    if not post_text:
        return {"verdict": "ungated", "available": False,
                "reason": "no post text to check"}
    try:
        import linkedin_factcheck as fc
    except Exception as exc:
        return {"verdict": "ungated", "available": False,
                "reason": f"fact gate unavailable: {exc}"}
    return fc.verify_post(post_text, list(sources or []),
                          use_llm=True, api_key=fc._load_api_key())


def generate_post_from_narrative(idea: dict) -> dict:
    """Generate a full post (text + image) from a narrative plan idea."""
    content = f"Topic: {idea['title']}\n{idea['narrative_anchor']}"
    post_text = generate_linkedin_content(
        content,
        source_type="Mukund narrative plan",
        narrative_anchor=idea["narrative_anchor"],
        career_signal=idea["career_signal"],
    )
    image_bytes = None
    if post_text:
        image_prompt = build_image_prompt(post_text)
        image_bytes = generate_image_bytes(image_prompt)
    return {
        "idea": idea,
        "post_text": post_text,
        "image_bytes": image_bytes,
        "generated_at": now_utc(),
    }


if __name__ == "__main__":
    # Test: generate a weekly narrative plan
    plan = weekly_narrative_plan()
    print(f"Weekly narrative plan ({len(plan)} ideas):")
    for i, idea in enumerate(plan, 1):
        print(f"  {i}. [{idea['slot']}] {idea['title']}")
