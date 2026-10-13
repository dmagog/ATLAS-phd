#!/usr/bin/env python3
"""calibrate_gate.py — подбор порогов hard-gate (evidence gate) для кафедры.

Прогоняет размеченный набор (eval/gate_sets/*.jsonl: expected = answer|refuse)
через тот же retrieval, что и чат, БЕЗ вызова LLM, и считает для сетки порогов:
  * TPR — доля вопросов «answer», которые проходят gate (будут отвечены);
  * TNR — доля вопросов «refuse», которые gate отклоняет.

Retrieval берётся с top_k = 2 × retriever_top_k: при провале первого прохода
qa_flow повторяет поиск с удвоенным top_k, т.е. фактически gate решается на
16 кандидатах (top1 тот же, кандидатов над порогом — не меньше).

Gate = векторный путь (top1 + число чанков над порогом) ИЛИ лексический
(все значимые слова вопроса встречаются хотя бы в L чанках; L = None — выключен).

Наборов может быть несколько (--set повторяется, например основной +
контрольный): конфигурация годится, только если TNR = 1.0 на ВСЕХ «refuse».

Рекомендация — минимальное изменение: векторные пороги глобальные, подбирается
только lexical_min_chunks (максимум TPR, при равенстве — более строгий L).
Полный перебор всех порогов печатается справочно: на сотне вопросов он
подгоняет три параметра под набор (переобучение), применять его не стоит.

Запуск (нужны БД и embeddings — внутри контейнера app):
    docker compose exec -T app python /app/scripts/calibrate_gate.py --tenant ipma-pm \\
        --set /app/eval/gate_sets/ipma_gate_v1.jsonl \\
        --set /app/eval/gate_sets/ipma_gate_holdout_v1.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from collections import defaultdict

import structlog
from sqlalchemy import select, text

# Логи retrieval (по строке на вопрос) топили отчёт — оставляем только WARNING+.
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

from atlas.core.config import settings
from atlas.db.models import Tenant
from atlas.db.session import AsyncSessionLocal
from atlas.llm.embeddings import get_embedding
from atlas.retriever.retriever import content_terms, gate_thresholds, retrieve

TOP1_GRID = [round(0.45 + i * 0.01, 2) for i in range(31)]   # 0.45 … 0.75
SCORE_GRID = [0.50, 0.52, 0.55]
CHUNKS_GRID = [1, 2]
LEXICAL_GRID = [None, 1, 2, 3]

_LEX_COUNT_SQL = text(
    "SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id "
    "WHERE c.tenant_id = :t AND d.status = 'active' "
    "AND to_tsvector('russian', c.text) @@ plainto_tsquery('russian', :q)"
)


def passes(row, min_top1, min_score, min_chunks, lexical=None) -> bool:
    above = sum(1 for v in row["vscores"] if v >= min_score)
    vector = row["top1"] >= min_top1 and above >= min_chunks
    return vector or (lexical is not None and row["lexical"] >= lexical)


def evaluate(rows, min_top1, min_score, min_chunks, lexical=None):
    ans = [r for r in rows if r["expected"] == "answer"]
    ref = [r for r in rows if r["expected"] == "refuse"]
    tp = sum(passes(r, min_top1, min_score, min_chunks, lexical) for r in ans)
    tn = sum(not passes(r, min_top1, min_score, min_chunks, lexical) for r in ref)
    # запас: насколько порог top1 выше лучшего «refuse», прошедшего по чанкам
    risky = [r["top1"] for r in ref
             if sum(1 for v in r["vscores"] if v >= min_score) >= min_chunks]
    margin = min_top1 - max(risky) if risky else 1.0
    return tp / len(ans), tn / len(ref), margin


def breakdown(rows, key, cfg):
    groups = defaultdict(list)
    for r in rows:
        groups[r.get(key) or "—"].append(r)
    out = {}
    for g, items in sorted(groups.items()):
        ok = sum(passes(r, *cfg) == (r["expected"] == "answer") for r in items)
        out[g] = f"{ok}/{len(items)}"
    return out


async def collect(tenant_slug: str, paths: list[str]):
    items = []
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        items += [{**json.loads(line), "set": name}
                  for line in open(path, encoding="utf-8") if line.strip()]
    rows = []
    async with AsyncSessionLocal() as db:
        tenant_id = (await db.execute(
            select(Tenant.id).where(Tenant.slug == tenant_slug)
        )).scalar_one()
        current = await gate_thresholds(db, tenant_id)
        for it in items:
            r = await retrieve(
                query_embedding=await get_embedding(it["query"]),
                db=db, tenant_id=tenant_id,
                top_k=settings.retriever_top_k * 2, query_text=it["query"],
            )
            # vscore — только векторных кандидатов (у BM25-only в RRF vscore = 0)
            vs = sorted((c.vscore for c in r.candidates if c.vscore > 0), reverse=True)
            terms = content_terms(it["query"])
            lexical = (await db.execute(_LEX_COUNT_SQL, {
                "t": tenant_id, "q": " ".join(terms),
            })).scalar() if terms else 0
            rows.append({**it, "top1": vs[0] if vs else 0.0, "vscores": vs, "lexical": lexical})
    return rows, (current.min_top1_score, current.min_score_threshold,
                  current.min_chunks_above_threshold, current.lexical_min_chunks)


def report(rows, tenant_slug: str, current) -> str:
    base = (settings.retriever_min_top1_score, settings.retriever_min_score_threshold,
            settings.retriever_min_chunks_above_threshold, None)
    lines = [f"# Калибровка hard-gate: {tenant_slug}", ""]
    for name in sorted({r["set"] for r in rows}):
        part = [r for r in rows if r["set"] == name]
        n_a = sum(r["expected"] == "answer" for r in part)
        lines.append(f"- `{name}`: {n_a} answer + {len(part) - n_a} refuse")
    lines += ["", f"top_k={settings.retriever_top_k * 2}. TPR — доля отвеченных «answer», "
              "TNR — доля отклонённых «refuse».", ""]

    candidates = []
    for s in SCORE_GRID:
        for c in CHUNKS_GRID:
            for t in TOP1_GRID:
                for lx in LEXICAL_GRID:
                    tpr, tnr, margin = evaluate(rows, t, s, c, lx)
                    candidates.append(((t, s, c, lx), tpr, tnr, margin))
    safe = [x for x in candidates if x[2] == 1.0]
    best = max(safe, key=lambda x: (round(x[1], 4), round(x[3], 4), x[0][3] or 0)) if safe else None
    # Минимальное изменение: глобальные векторные пороги + только lexical.
    minimal = [(base[:3] + (lx,),) + evaluate(rows, *base[:3], lx) for lx in LEXICAL_GRID]
    minimal_safe = [x for x in minimal if x[2] == 1.0]
    recommended = max(minimal_safe, key=lambda x: (round(x[1], 4), x[0][3] or 0)) if minimal_safe else None

    def row_line(name, cfg):
        tpr, tnr, margin = evaluate(rows, *cfg)
        return (f"| {name} | {cfg[0]:.2f} / {cfg[1]:.2f} / {cfg[2]} / {cfg[3] or '—'} | {tpr:.3f} | {tnr:.3f} | "
                f"{margin:+.3f} | {breakdown([r for r in rows if r['expected']=='answer'], 'set', cfg)} | "
                f"{breakdown([r for r in rows if r['expected']=='answer'], 'length', cfg)} | "
                f"{breakdown([r for r in rows if r['expected']=='refuse'], 'kind', cfg)} |")

    lines += ["| Конфигурация | top1 / score / chunks / lexical | TPR | TNR | запас | answer по наборам | "
              "answer по длине | refuse по типу |",
              "|---|---|---|---|---|---|---|---|",
              row_line("Глобальная", base),
              row_line("**Текущая у кафедры**", current)]
    for lx in LEXICAL_GRID[1:]:
        lines.append(row_line(f"Глобальная + lexical≥{lx}", base[:3] + (lx,)))
    if recommended:
        lines.append(row_line("**Рекомендуемая**", recommended[0]))
    if best:
        lines.append(row_line("Максимум перебора (справочно)", best[0]))
    lines.append("")

    lines += ["## Только min_top1 (score и chunks — глобальные)", "",
              "| min_top1 | TPR | TNR | запас |", "|---|---|---|---|"]
    for t in TOP1_GRID:
        tpr, tnr, margin = evaluate(rows, t, base[1], base[2], None)
        lines.append(f"| {t:.2f} | {tpr:.3f} | {tnr:.3f} | {margin:+.3f} |")
    lines.append("")

    lines += ["## top1 и лексические совпадения по вопросам", "",
              "| id | ожидание | top1 | 2-й | 3-й | lexical | вопрос |", "|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["expected"], -r["top1"])):
        v = r["vscores"] + [0, 0, 0]
        lines.append(f"| {r['id']} | {r['expected']} | {v[0]:.3f} | {v[1]:.3f} | {v[2]:.3f} | {r['lexical']} | {r['query']} |")
    lines += ["", "## Рекомендация", ""]
    if recommended:
        lx = recommended[0][3]
        status = "совпадает с текущей" if recommended[0] == current else "отличается от текущей"
        lines.append(
            f"`lexical_min_chunks={lx}` при глобальных векторных порогах → TPR {recommended[1]:.3f}, "
            f"TNR {recommended[2]:.3f} ({status}). Применить:")
        lines += ["", "```", f'PUT /tenants/{tenant_slug}/config/retrieval  {{"lexical_min_chunks": {json.dumps(lx)}}}', "```"]
    else:
        lines.append("Ни одна конфигурация с глобальными векторными порогами не даёт TNR = 1.0 — "
                     "разберите «refuse», прошедшие gate, прежде чем менять пороги.")
    if best:
        t, s, c, lx = best[0]
        lines += ["", f"Справочно, максимум полного перебора: `{t:.2f} / {s:.2f} / {c} / {lx}` → "
                  f"TPR {best[1]:.3f} — подогнан под набор, не применять без нового контрольного набора."]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--set", required=True, action="append",
                    help="jsonl-набор; можно указать несколько раз")
    args = ap.parse_args()
    rows, current = asyncio.run(collect(args.tenant, args.set))
    print(report(rows, args.tenant, current))


if __name__ == "__main__":
    main()
