# Eval configs — A/B протокол (M3.D)

Два конфига для A/B сравнения вклада агентного контура:

- **`treatment.toml`** — полный контур (verifier on, self-check on). Текущее поведение ATLAS.
- **`baseline.toml`** — verifier off, self-check off (plain retrieval + Answer Node). Контрольная группа.

Запуск A/B (один и тот же golden set, оба прогона в один день):

```bash
# Treatment
python eval/runner.py --set eval/golden_set_v1/golden_set_v1.0.jsonl \
    --config eval/configs/treatment.toml \
    --output eval/results/run-treatment-$(date +%Y%m%d)/

# Baseline
python eval/runner.py --set eval/golden_set_v1/golden_set_v1.0.jsonl \
    --config eval/configs/baseline.toml \
    --output eval/results/run-baseline-$(date +%Y%m%d)/

# Score обоих
python eval/score.py --run eval/results/run-treatment-... --set eval/golden_set_v1/golden_set_v1.0.jsonl
python eval/score.py --run eval/results/run-baseline-... --set eval/golden_set_v1/golden_set_v1.0.jsonl
```

Сравнение метрик baseline vs treatment попадает в `eval/results/M3-report.md`.

## Что нужно от backend (TODO до полного запуска A/B)

Runner прокидывает в API header `X-ATLAS-Eval-Mode: <mode>`. Backend должен
**на этот header реагировать** в `/qa/message` и `/selfcheck/start`:

| `mode` | Поведение |
|---|---|
| `treatment` (default) | Текущее: Retrieval → Answer → Verifier (hard-gate) → ответ или отказ. |
| `baseline` | Retrieval → Answer → ответ как есть (no verifier, no refusal-by-evidence). |

**Минимальные правки backend (M3.D follow-up):**

1. В `src/atlas/api/routers/qa.py` — извлекать `X-ATLAS-Eval-Mode` из headers, прокидывать как параметр в orchestrator.
2. В `src/atlas/orchestrator/...` — при `mode == "baseline"` пропускать узел Verifier; ответ возвращается без проверки evidence (status всегда `answered`).
3. Аналогично для `/selfcheck/start` — при `baseline` self-check generator работает в упрощённом режиме (без grounded check) либо отключается полностью.

**Безопасность:** header принимается только от authenticated users с ролью `admin`/`super-admin` (после M4 RBAC). До тех пор — feature gate через ENV `ATLAS_EVAL_MODE_ENABLED=true`, иначе header игнорируется. Это защищает от обхода verifier'а в проде через произвольный header.

**Smoke-тест расширения** после имплементации:
```bash
curl -X POST http://127.0.0.1:8731/qa/message \
    -H "Authorization: Bearer $ATLAS_EVAL_TOKEN" \
    -H "X-ATLAS-Eval-Mode: baseline" \
    -H "Content-Type: application/json" \
    -d '{"message_text": "Что-то заведомо out-of-corpus"}'
# Ожидание: status="answered" (а не "refused"), потому что verifier отключён
```

## Когда A/B даст осмысленные числа

После того как:
1. Golden set v1.0 заморожен (60+20+20+20 = 120 элементов с заполненными `pages`).
2. Backend поддерживает `X-ATLAS-Eval-Mode`.
3. Оба прогона выполнены в один день, на одной модели LLM (минимизация дрейфа).

До этого момента — A/B запускается на текущих 10 entries, результаты используются только для smoke и отладки.
