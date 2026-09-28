"""Bounded, source-provenanced persistent context assembled by Chief.

This is deliberately provider-neutral.  Chief owns memory selection; E3 only
receives the compiled package and remains responsible for worker selection.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, Iterable, Optional


_SECRET = re.compile(
    r"(?i)(api[_ -]?key|token|password|secret|credential)\s*[:=]\s*[^\s,;]+"
)


@dataclass(frozen=True)
class ContextSource:
    source_id: str
    path: str
    text: str
    kind: str = "canonical"


class ChiefContextCompiler:
    """Select relevant persistent sources under a strict character budget."""

    DEFAULT_BUDGET = 16000
    # Keep owner, company, project and history lanes simultaneously visible;
    # one large canonical file must not crowd out the other source classes.
    DEFAULT_SOURCE_LIMIT = 4000

    def __init__(self, *, root: Optional[Path] = None, max_chars: int = DEFAULT_BUDGET,
                 source_limit: int = DEFAULT_SOURCE_LIMIT,
                 sources: Optional[Iterable[ContextSource]] = None,
                 local_context_root: Optional[Path] = None,
                 history_root: Optional[Path] = None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[1]
        self.max_chars = max_chars
        self.source_limit = source_limit
        self._sources = tuple(sources) if sources is not None else None
        self.local_context_root = Path(local_context_root) if local_context_root else None
        self.history_root = Path(history_root) if history_root else None

    def _default_sources(self) -> tuple[ContextSource, ...]:
        hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / "AppData" / "Local" / "hermes"))
        local_root = self.local_context_root or hermes_home
        paths = [
            ("owner-context-local", local_root / "skills" / "personal" / "mukund-owner-context" / "SKILL.md", "owner"),
            ("company-registry-local", local_root / "skills" / "personal" / "mukund-company-registry" / "SKILL.md", "company"),
            ("owner-memory", local_root / "memories" / "MEMORY.md", "owner"),
            ("owner-profile", local_root / "memories" / "USER.md", "owner"),
            ("owner-context", self.root / "state" / "current_company_state.md", "owner/project"),
            ("company-registry", self.root / "state" / "v1-agent-roster.md", "company/project"),
            ("project-state", self.root / "state" / "full_build_tracker.md", "project"),
        ]
        out = []
        for source_id, path, kind in paths:
            try:
                if path.is_file():
                    out.append(ContextSource(source_id, str(path), path.read_text(encoding="utf-8"), kind))
            except OSError:
                continue
        history_root = self.history_root
        if history_root is None:
            archive_env = os.environ.get("HERMES_DISCORD_ARCHIVE_DIR")
            history_root = Path(archive_env) if archive_env else Path.home() / "DiscordArchive" / "chief"
            if not history_root.is_dir():
                history_root = hermes_home / "hooks" / "discord-chief-archive"
        # The archive hook is code plus local state; only ingest textual/jsonl
        # records when present, never copy private archives into the repository.
        if history_root.is_dir():
            for path in sorted(history_root.rglob("*.jsonl"))[-4:]:
                try:
                    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
                    selected = []
                    for line in lines:
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(row, dict) and row.get("content"):
                            selected.append(f"{row.get('role', 'message')}: {row['content']}")
                    if selected:
                        out.append(ContextSource("discord-chief-history", path.name, "\n".join(selected), "history"))
                except OSError:
                    continue
        return tuple(out)

    @staticmethod
    def _relevant(source: ContextSource, objective: str) -> bool:
        text = (objective or "").casefold()
        if source.kind in {"owner/project", "owner", "company", "history"}:
            return True
        if source.kind == "canonical" and source.source_id in {"owner-context", "company-registry"}:
            return True
        if any(word in text for word in ("job", "career", "resume", "cv", "application", "recruit")):
            return source.kind in {"company/project", "project"}
        if any(word in text for word in ("company", "project", "repository", "hermes", "chief", "previous")):
            return True
        return source.kind == "project"

    def compile(self, objective: str, *, recent_transcript: Optional[list] = None,
                department_state: Optional[Dict[str, Any]] = None,
                task_records: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        candidates = self._sources if self._sources is not None else self._default_sources()
        selected = [s for s in candidates if self._relevant(s, objective)]
        priority = {"owner": 0, "company": 1, "history": 2, "project": 2,
                    "owner/project": 3, "company/project": 4, "canonical": 5}
        selected.sort(key=lambda s: priority.get(s.kind, 5))
        sections = []
        manifest = []
        remaining = self.max_chars
        for source in selected:
            clean = _SECRET.sub(r"\1: [REDACTED]", source.text)
            clean = clean[: min(self.source_limit, remaining)]
            if not clean:
                continue
            sections.append({"source_id": source.source_id, "kind": source.kind, "text": clean})
            manifest.append({
                "source_id": source.source_id,
                "kind": source.kind,
                "path": source.path,
                "sha256": hashlib.sha256(source.text.encode("utf-8")).hexdigest(),
                "chars_included": len(clean),
            })
            remaining -= len(clean)
            if remaining <= 0:
                break
        package = {
            "objective": objective,
            "facts": sections,
            "recent_transcript": (recent_transcript or [])[-12:],
            "department_state": department_state or {},
            "task_records": task_records or {},
            "inferences": [],
            "source_manifest": manifest,
            "char_budget": self.max_chars,
            "chars_included": sum(len(s["text"]) for s in sections),
        }
        return package

    def validate(self, package: Dict[str, Any]) -> list[str]:
        warnings = []
        if package.get("chars_included", 0) > self.max_chars:
            warnings.append("context exceeds declared character budget")
        rendered = repr(package)
        if re.search(r"(?i)(api[_ -]?key|password|secret|token)\s*[:=]\s*(?!\[REDACTED\])", rendered):
            warnings.append("context contains an unredacted sensitive field")
        return warnings
