"""Schema for ATLAS eval golden set (M3.A).

Format: JSONL, one entry per line. Each entry is one of QAEntry / RefusalEntry /
FormulaEntry / SelfCheckEntry, discriminated by `type`.

Versioning: golden_set_v{MAJOR}.{MINOR}.jsonl is immutable once frozen. Schema
changes — bump MAJOR; content additions — bump MINOR.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

# Refusal reasons — mirrors `atlas.orchestrator.states.RefusalReasonCode` (M2 enum).
# Источник истины: `src/atlas/orchestrator/states.py`. Если ATLAS добавит новые
# причины — добавить здесь и пересобрать eval-set.
RefusalReason = Literal[
    "LOW_EVIDENCE",
    "NO_CITATIONS",
    "POLICY_BLOCKED",
    "OFF_TOPIC",
]

# Self-check rubric criteria (from product-proposal §6.1)
RubricCriterion = Literal["correctness", "completeness", "logic", "terminology"]


class CitationSpec(BaseModel):
    """Acceptable citation: doc shortname + acceptable page list.

    A QA entry may have multiple CitationSpec — answer is fine if it cites any
    of these combinations.
    """

    doc: str  # short doc id, e.g. "born-wolf", "matveev", "yariv"
    pages: list[int]


class _BaseEntry(BaseModel):
    id: str
    tenant: str = "default"
    tags: list[str] = []
    version: str = "v1.0"


class QAEntry(_BaseEntry):
    """Standard Q&A — system should answer with citations."""

    type: Literal["qa"] = "qa"
    query: str
    expected_behavior: Literal["answer"] = "answer"
    acceptable_citations: list[CitationSpec]
    reference_answer: str
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class RefusalEntry(_BaseEntry):
    """Off-topic / out-of-corpus — system should refuse with a reason."""

    type: Literal["refusal"] = "refusal"
    query: str
    expected_behavior: Literal["refuse"] = "refuse"
    expected_refusal_reasons: list[RefusalReason]


class FormulaEntry(_BaseEntry):
    """Formula-heavy / terminology-dense Q&A — vector-only retrieval may struggle."""

    type: Literal["formula"] = "formula"
    query: str
    expected_behavior: Literal["answer"] = "answer"
    acceptable_citations: list[CitationSpec]
    reference_answer: str
    formula_required: bool = True
    difficulty: Literal["easy", "medium", "hard"] = "hard"


class SelfCheckEntry(_BaseEntry):
    """Self-check evaluator test case.

    Provides a canned (question, user_answer) pair with expected rubric scores.
    Tests Evaluator agreement, not Generator.
    """

    type: Literal["self_check"] = "self_check"
    topic: str
    canned_question: str
    canned_question_type: Literal["mc", "open"]
    user_answer: str
    expected_scores: dict[RubricCriterion, float]
    expected_overall: float = Field(ge=0, le=5)
    reference_answer: str


GoldenSetEntry = Annotated[
    Union[QAEntry, RefusalEntry, FormulaEntry, SelfCheckEntry],
    Field(discriminator="type"),
]

_entry_adapter: TypeAdapter[GoldenSetEntry] = TypeAdapter(GoldenSetEntry)


def parse_entry(raw: dict) -> GoldenSetEntry:
    """Validate one raw dict against the GoldenSetEntry discriminated union."""
    return _entry_adapter.validate_python(raw)


def load_jsonl(path: Path) -> list[GoldenSetEntry]:
    """Load and validate every line of a JSONL golden set."""
    entries: list[GoldenSetEntry] = []
    errors: list[str] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                raw = json.loads(line)
                entries.append(parse_entry(raw))
            except (json.JSONDecodeError, ValidationError) as e:
                errors.append(f"line {lineno}: {e}")
    if errors:
        raise ValueError(
            f"Golden set validation failed ({len(errors)} errors):\n  "
            + "\n  ".join(errors)
        )
    return entries


def dump_jsonl(entries: list[GoldenSetEntry], path: Path) -> None:
    """Serialize entries back to JSONL (one entry per line, deterministic order)."""
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.model_dump_json(exclude_none=True) + "\n")


def summary(entries: list[GoldenSetEntry]) -> dict[str, int]:
    """Quick distribution-by-type for sanity checks."""
    counts = {"qa": 0, "refusal": 0, "formula": 0, "self_check": 0}
    for e in entries:
        counts[e.type] += 1
    return counts
