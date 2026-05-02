"""Faithfulness через LLM-judge (M3.C).

Промпт: на каждый ответ + цитаты — LLM проверяет, поддерживается ли каждое
утверждение источником. Score = supported / total claims.

LLM-judge модель: для M3 берём GPT-4-class (один прогон ≈ единицы $).
Промпт: `eval/judge_prompts/faithfulness.md`, версионируется.

NOTE: requires OpenRouter (или другой OpenAI-compatible) API key. Реальный вызов
делается через httpx; для unit-test'ов есть `judge_with_stub()`.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

JUDGE_PROMPT_PATH = Path(__file__).resolve().parent.parent / "judge_prompts" / "faithfulness.md"

# Default — бесплатная free-модель на OpenRouter; отличается от Q&A LLM
# (qwen3.6-plus:free) чтобы снизить self-evaluation bias. Для production-grade
# evaluation (после пилота) — переключить на платную GPT-4-class через --judge-model.
DEFAULT_JUDGE_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"


@dataclass
class FaithfulnessResult:
    n_responses: int
    n_judged: int  # сколько прошли через judge (не отказы, не пустые)
    mean_score: float  # supported / total, усреднено по responses
    per_response: list[dict]  # детализация: entry_id, supported, total, score


JudgeFn = Callable[[str, list[dict], str], dict]
"""Сигнатура: (answer_text, citations, model) -> {claims: [{text, supported}]}."""


def _load_prompt() -> str:
    if not JUDGE_PROMPT_PATH.exists():
        return _DEFAULT_PROMPT
    return JUDGE_PROMPT_PATH.read_text(encoding="utf-8")


_DEFAULT_PROMPT = """\
Ты проверяешь, поддерживается ли каждое утверждение в ответе процитированным
источником. Верни JSON: {"claims": [{"text": "...", "supported": true|false,
"reason": "..."}]}.
"""


def judge_with_openrouter(answer_text: str, citations: list[dict], model: str) -> dict:
    """Реальный вызов LLM-judge через OpenRouter.

    Требует ENV `OPENROUTER_API_KEY`. Сетевой вызов; в тестах подменяй на стаб.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY не задан — judge не может работать")
    prompt = _load_prompt()
    user_msg = (
        f"ОТВЕТ:\n{answer_text}\n\n"
        f"ЦИТАТЫ (json):\n{json.dumps(citations, ensure_ascii=False, indent=2)}\n\n"
        "Верни ТОЛЬКО JSON по схеме."
    )
    resp = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _parse_judge_json(content)


def _parse_judge_json(content: str) -> dict:
    """Извлекает JSON из ответа judge'а (защита от code-fence и trailing text)."""
    # strip code fences if any
    content = content.strip()
    if content.startswith("```"):
        m = re.match(r"```(?:json)?\s*(.+?)\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)
    return json.loads(content)


def judge_with_stub(answer_text: str, citations: list[dict], model: str) -> dict:
    """Stub для тестов: считает все claims supported. Не использовать в продакшен."""
    return {"claims": [{"text": answer_text[:120], "supported": True, "reason": "stub"}]}


def faithfulness(
    responses: list[dict],
    entries_by_id: dict[str, dict],
    judge: JudgeFn = judge_with_openrouter,
    model: str = DEFAULT_JUDGE_MODEL,
) -> FaithfulnessResult:
    """Прогоняет judge по всем непустым ответам с цитатами.

    Args:
        responses: распарсенные строки responses.jsonl.
        entries_by_id: golden entries dict (для фильтрации по type).
        judge: функция вызова LLM-judge (по умолчанию OpenRouter; в тестах — stub).
    """
    per: list[dict] = []
    judged = 0
    total_score = 0.0

    for r in responses:
        entry = entries_by_id.get(r["entry_id"])
        if not entry or entry.get("type") not in ("qa", "formula"):
            continue
        if (r.get("api_status") or "").lower() != "answered":
            continue
        if not r.get("answer_text") or not r.get("citations"):
            continue
        try:
            out = judge(r["answer_text"], r["citations"], model)
            claims = out.get("claims") or []
            supported = sum(1 for c in claims if c.get("supported"))
            total = len(claims)
            score = supported / total if total else 0.0
            per.append(
                {
                    "entry_id": r["entry_id"],
                    "supported": supported,
                    "total": total,
                    "score": score,
                }
            )
            judged += 1
            total_score += score
        except Exception as e:
            per.append(
                {
                    "entry_id": r["entry_id"],
                    "error": f"{type(e).__name__}: {str(e)[:120]}",
                }
            )

    mean = total_score / judged if judged else 0.0
    return FaithfulnessResult(
        n_responses=len(responses),
        n_judged=judged,
        mean_score=mean,
        per_response=per,
    )
