"""program.md parser (M4.5.A).

Format conventions (per roadmap §M4.5.A):
  * YAML frontmatter with program_version, tenant_slug, ratified_at.
  * H1 (`#`) is the human title — ignored.
  * H2 (`## Раздел N. <title>`) starts a section.
  * H3 (`### N.M <title>`) starts a topic (билет).
    The `N.M` prefix becomes external_id (stable across re-uploads).
  * `**key_concepts:**` line under each H3 is a comma-separated list.

The parser is strict: any malformed structure raises `ProgramParseError`
with line/section context. The caller (load endpoint) wraps the error
in 422 Unprocessable Entity.

This is intentionally a hand-rolled parser; no markdown-AST dependency.
The format is small and tight enough that regexes are clearer than a
full mdast tree, and we want exact error messages tied to source lines.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


class ProgramParseError(ValueError):
    """Structural error in a program.md document."""


# ─── Frontmatter ─────────────────────────────────────────────────────────────
_FRONTMATTER_FIELDS = {"program_version", "tenant_slug", "ratified_at"}

# ─── H3 topic header: "### 1.3 Тонкие линзы и зеркала"
# The N.M prefix is required; "1.3" → external_id="1.3"
_H3_RE = re.compile(r"^###\s+(?P<eid>\d+(?:\.\d+)?(?:\.\d+)?)\s+(?P<title>.+?)\s*$")
# "## Раздел 1. Геометрическая и волновая оптика"
_H2_RE = re.compile(r"^##\s+(?:Раздел\s+\d+\.\s+)?(?P<title>.+?)\s*$")
# "**key_concepts:** принцип Ферма, принцип Гюйгенса"
_KC_RE = re.compile(r"^\*\*key_concepts:\*\*\s+(?P<list>.+?)\s*$")


@dataclass
class ParsedTopic:
    external_id: str
    section: str
    title: str
    ordinal: int  # 1-based, across the whole program
    key_concepts: list[str] = field(default_factory=list)


@dataclass
class ParsedProgram:
    program_version: str
    tenant_slug: str
    ratified_at: date | None
    topics: list[ParsedTopic]


def _parse_frontmatter(lines: list[str]) -> tuple[dict, int]:
    """Return (frontmatter_dict, lines_consumed). Frontmatter is a YAML-like
    block delimited by '---'. We don't pull yaml as a dep — it's k=v lines.
    """
    if not lines or lines[0].strip() != "---":
        raise ProgramParseError("expected frontmatter (`---` on first line)")
    fm: dict[str, str] = {}
    for i, raw in enumerate(lines[1:], start=2):
        line = raw.strip()
        if line == "---":
            return fm, i  # 1-indexed line just after the closing ---
        if not line:
            continue
        if ":" not in line:
            raise ProgramParseError(f"line {i}: malformed frontmatter line")
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    raise ProgramParseError("frontmatter never closed (missing trailing `---`)")


def parse_program(text: str) -> ParsedProgram:
    """Parse a program.md document. Raises ProgramParseError on any
    structural violation."""
    lines = text.splitlines()
    fm, consumed = _parse_frontmatter(lines)
    missing = _FRONTMATTER_FIELDS - set(fm)
    if missing:
        raise ProgramParseError(
            f"frontmatter missing required fields: {sorted(missing)}"
        )

    program_version = fm["program_version"]
    tenant_slug = fm["tenant_slug"]
    raw_ratified = fm.get("ratified_at", "").strip()
    try:
        ratified_at = date.fromisoformat(raw_ratified) if raw_ratified else None
    except ValueError:
        raise ProgramParseError(
            f"ratified_at: '{raw_ratified}' is not ISO date YYYY-MM-DD"
        )

    topics: list[ParsedTopic] = []
    current_section: str | None = None
    current_topic: ParsedTopic | None = None
    seen_external_ids: set[str] = set()

    def _commit_topic() -> None:
        nonlocal current_topic
        if current_topic is None:
            return
        if current_topic.external_id in seen_external_ids:
            raise ProgramParseError(
                f"duplicate external_id '{current_topic.external_id}'"
            )
        seen_external_ids.add(current_topic.external_id)
        topics.append(current_topic)
        current_topic = None

    for i, raw in enumerate(lines[consumed:], start=consumed + 1):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        # H1 = human title — silently ignored.
        if stripped.startswith("# ") and not stripped.startswith("## "):
            continue

        # H2 = section
        if stripped.startswith("## "):
            _commit_topic()
            m = _H2_RE.match(stripped)
            if not m:
                raise ProgramParseError(f"line {i}: malformed H2 section header")
            current_section = m.group("title")
            continue

        # H3 = topic
        if stripped.startswith("### "):
            _commit_topic()
            m = _H3_RE.match(stripped)
            if not m:
                raise ProgramParseError(
                    f"line {i}: malformed H3 topic header — expected '### <N.M> <title>'"
                )
            if current_section is None:
                raise ProgramParseError(
                    f"line {i}: topic '{m.group('eid')}' before any section"
                )
            current_topic = ParsedTopic(
                external_id=m.group("eid"),
                section=current_section,
                title=m.group("title"),
                ordinal=len(topics) + 1,
            )
            continue

        # key_concepts inline
        if stripped.startswith("**key_concepts:"):
            m = _KC_RE.match(stripped)
            if not m:
                raise ProgramParseError(
                    f"line {i}: malformed **key_concepts:** line"
                )
            if current_topic is None:
                raise ProgramParseError(
                    f"line {i}: key_concepts line before any topic"
                )
            current_topic.key_concepts = [
                kc.strip() for kc in m.group("list").split(",") if kc.strip()
            ]
            continue

        # Anything else — quote line or a blockquote — silently allowed
        # (e.g. the leading "> Это демо-версия..." note).
        if stripped.startswith(">"):
            continue

        # Plain prose under a topic — also tolerated; the format isn't
        # rigid about the gap between key_concepts and the next H3.
        # We just don't capture it.

    _commit_topic()

    if not topics:
        raise ProgramParseError("program contains no H3 topics")

    return ParsedProgram(
        program_version=program_version,
        tenant_slug=tenant_slug,
        ratified_at=ratified_at,
        topics=topics,
    )


def parse_program_file(path: Path | str) -> ParsedProgram:
    return parse_program(Path(path).read_text(encoding="utf-8"))
