# Спецификация агента-оркестратора

## Назначение

`Orchestrator` управляет графом выполнения запроса, фиксирует переходы состояний и гарантирует, что итоговый ответ выходит только через разрешенный путь.

Для PoC оркестратор реализует не свободный multi-agent graph, а маршрутизируемый агентный конвейер:
- `Planner` определяет сценарий (реализован на уровне API-маршрутизации, см. ниже);
- после выбора сценария исполняется фиксированная цепочка узлов;
- следующий шаг задается правилами оркестрации, а не автономным решением LLM.

---

## Реализация Planner

Planner реализован в двух режимах в зависимости от точки входа.

### Режим 1: явная маршрутизация (Q&A и Самопроверка страницы)

Пользователь явно выбирает режим через отдельные страницы интерфейса:

| Эндпоинт | Сценарий |
|---|---|
| `POST /qa/message` | `qa` |
| `POST /self-check/start` | `self_check` |
| `POST /self-check/{id}/submit` | `sc_evaluate` |

Это устраняет класс ошибок классификации и снижает latency.

### Режим 2: LLM-Planner (Unified Chat, `/chat/message`)

На странице `/` (чат) работает LLM-Planner (`src/atlas/orchestrator/planner.py`), классифицирующий свободный запрос пользователя.

**System prompt:**

```
You are a router for an academic study assistant.
Classify the user message into exactly one of these routes:
- "qa": the user is asking a factual or conceptual question that should be answered from study materials
- "self_check": the user wants to test their knowledge on a topic (e.g. "test me on X", "quiz me", "give me questions about")
- "clarification": the message is too vague, off-topic, or cannot be classified

Respond with a single JSON object: {"route": "<route>", "confidence": <0.0-1.0>}
No explanation, no markdown, just JSON.
```

**User message:** сырой текст запроса пользователя.

**Параметры:** `temperature=0.0`, `max_tokens=64`.

**Парсинг решения:**

```python
start = raw.find("{")
end   = raw.rfind("}") + 1
data  = json.loads(raw[start:end])
route_str = data.get("route", "clarification")
route = PlannerRoute(route_str) if route_str in PlannerRoute._value2member_map_ \
        else PlannerRoute.CLARIFICATION
```

1. Извлекается первый JSON-объект из ответа (устойчиво к leading/trailing текstu от reasoning-моделей).
2. Поле `route` сопоставляется с `PlannerRoute` enum (`qa` / `self_check` / `clarification`).
3. При любом исключении (сетевой сбой, невалидный JSON, неизвестный route) — fallback на `clarification`. Принцип: Planner **предпочитает уточнение** агрессивному автозапуску ветки.

---

## Шаги PoC

### `Q&A`

1. Принять запрос, создать `request_id` → `REQUEST_RECEIVED`
2. Вычислить embedding запроса
3. Вызвать `Retriever` (top_k чанков) → `QA_RETRIEVAL_DONE`
4. Вызвать `Answer Node` → `QA_ANSWER_DRAFTED`
5. Вызвать `Verifier Node`
   - **Passed** → `RESPONSE_SENT`
   - **Failed** → попытка re-generation с расширенным top_k (×2)
     - Re-generation passed → `RESPONSE_SENT` (флаг `via_regen=True` в логах)
     - Re-generation также failed → `REFUSAL_SENT`

### `Self-check`

1. Принять запрос, создать `request_id` → `REQUEST_RECEIVED`
2. Вычислить embedding темы; вызвать `Retriever` для контекста из корпуса
3. Вызвать `Self-check Generator` с контекстными чанками → `SC_ATTEMPT_CREATED`
4. Зафиксировать `attempt_id`, сохранить вопросы в БД → `SC_QUESTIONS_READY`
5. После отдельной отправки ответов пользователем: валидировать `attempt_id` и payload
6. Перевести попытку в `SC_ANSWERS_SUBMITTED`
7. Вызвать `Self-check Evaluator`
8. Опубликовать валидный результат → `SC_EVALUATED` или → `INVALID_EVALUATION`

---

## Промпты агентных узлов

### Answer Node

**System prompt** (`src/atlas/qa/prompts.py`):

```
You are ATLAS, an academic study assistant for PhD exam preparation.
Answer the user's question using ONLY the provided context excerpts.
Rules:
1. Base every claim on the provided excerpts. Do not add external knowledge.
2. Cite each source inline using [Doc: <title>, p.<page>] or [Doc: <title>, §<section>].
3. If the context is insufficient to answer, say so clearly — do not fabricate.
4. Use markdown formatting. For mathematical formulas, use LaTeX ($$...$$).
5. Be precise and academically rigorous.
6. Respond in the same language as the user's question (Russian or English).

Response style: <brief|detailed|study — подставляется динамически>
```

**User message** (строится в `build_answer_prompt`):

```
Context excerpts:

[1] Born & Wolf: Principles of Optics — p.343
<текст чанка>

---

[2] Irodov: Problems in General Physics — p.112
<текст чанка>

---

Question: Объясните принцип Гюйгенса–Френеля и его связь с дифракцией.
```

**Параметры:** `temperature=0.2`, `max_tokens=2048`.

---

### Verifier Node

Verifier является **детерминированным** (без LLM-вызова). Проверяет два условия последовательно:

1. `retrieval.enough_evidence` — флаг из Retriever:
   - `top1_score >= 0.62` (настраивается через `retriever_min_top1_score`)
   - не менее 2 чанков с `score >= 0.55` (`retriever_min_score_threshold`)
2. Наличие маркера `[Doc:` в тексте сгенерированного ответа.

При провале — `reason_code` (`LOW_EVIDENCE` / `NO_CITATIONS`) и запуск re-generation с `top_k × 2`. Если и re-generation не прошла — `REFUSAL_SENT`.

Реализация: `src/atlas/qa/verifier.py`.

---

### Self-check Generator

**System prompt** (при наличии контекста из корпуса):

```
You are an academic exam question generator for PhD-level study.
You will be given excerpts from textbooks and study materials, followed by a topic.
Generate a mixed question set that tests understanding of the topic STRICTLY
based on the provided excerpts.

Rules:
- Generate exactly 3 multiple_choice and 2 open_ended questions
- Every question must be answerable using information present in the provided excerpts
- Do NOT invent facts, definitions or formulas not mentioned in the excerpts
- Questions must be academically rigorous and test deep understanding
- Multiple choice options must be plausible (no obviously wrong answers)
- Respond in the same language as the topic (Russian or English)

Return a JSON object with this exact structure (ONLY JSON, no markdown, no explanation):
{
  "questions": [
    {
      "question_id": "q1",
      "type": "multiple_choice",
      "prompt": "Question text",
      "options": ["A. option1", "B. option2", "C. option3", "D. option4"],
      "correct_option": "A"
    },
    {
      "question_id": "q2",
      "type": "open_ended",
      "prompt": "Question text",
      "options": [],
      "correct_option": null
    }
  ]
}
```

**User message:**

```
EXCERPTS FROM STUDY MATERIALS:

<чанк 1>

---

<чанк 2>

---

TOPIC: Принцип Гюйгенса–Френеля
```

**Fallback** (тема не найдена в корпусе): аналогичный промпт без выдержек; LLM генерирует вопросы из параметрических знаний. В логах: `grounded=false`.

**Параметры:** `temperature=0.4`, `max_tokens=1500`, контекст до 6000 символов.

---

### Self-check Evaluator

**System prompt** (`src/atlas/selfcheck/evaluator.py`):

```
You are an academic exam evaluator for PhD-level study.
Evaluate the student's answers against the questions provided.

SCORING RUBRIC — four weighted criteria, each scored 0-5:
- correctness  (weight 40%): factual accuracy
- completeness (weight 30%): how fully the question is answered
- logic        (weight 20%): quality of reasoning and argumentation
- terminology  (weight 10%): correct use of domain-specific terms

overall_score = correctness*0.40 + completeness*0.30 + logic*0.20 + terminology*0.10

QUESTION TYPE RULES:

multiple_choice questions:
  - per-question score: 1.0 if correct, 0.0 otherwise
  - status: "correct" or "incorrect" (never "partial")
  - MC answers count only toward CORRECTNESS criterion

open_ended questions:
  - per-question score: weighted average of four criteria (0-5)
  - status: "correct" (>=4), "partial" (>=2), "incorrect" (<2)
  - evaluate all four criteria

Return ONLY a JSON object (no markdown, no explanation):
{
  "overall_score": <0-5>,
  "criterion_scores": { "correctness": <0-5>, "completeness": <0-5>,
                        "logic": <0-5>, "terminology": <0-5> },
  "question_results": [
    {"question_id": "q1", "type": "multiple_choice", "score": 1.0, "status": "correct"},
    {"question_id": "q2", "type": "open_ended",      "score": 3.5, "status": "partial"}
  ],
  "error_tags": ["terminology", "incomplete"],
  "confidence": 0.9,
  "evaluator_summary": "2-4 sentences of constructive feedback in student's language",
  "policy_flags": { "low_confidence": false, "inconsistent_eval": false, "needs_review": false }
}
```

**User message** (строится в `_build_eval_prompt`):

```
Q (multiple_choice) [q1]: Какое условие описывает принцип Гюйгенса–Френеля?
Options: A. Каждая точка фронта волны — источник вторичных волн | B. ... | C. ... | D. ...
Correct answer: A
Student answer: B

Q (open_ended) [q2]: Объясните связь между дифракцией и интерференцией вторичных волн.
Student answer: Дифракция возникает когда...
```

**Параметры:** `temperature=0.1`, `max_tokens=1500`.

---

### Обеспечение соответствия схеме (Evaluator schema validation)

После получения LLM-ответа применяется `_validate_payload` (`src/atlas/selfcheck/evaluator.py`):

```python
def _validate_payload(data: dict) -> bool:
    required = {"overall_score", "criterion_scores", "question_results",
                 "error_tags", "confidence", "evaluator_summary", "policy_flags"}
    if not required.issubset(data.keys()):
        return False
    cs = data.get("criterion_scores", {})
    if not {"correctness", "completeness", "logic", "terminology"}.issubset(cs.keys()):
        return False
    if not (0 <= data.get("overall_score", -1) <= 5):
        return False
    return True
```

При провале валидации: попытка маркируется `INVALID_EVALUATION`, не публикуется пользователю (FR-16), событие `evaluator_invalid_payload` пишется в лог.

---

## Правила переходов

- Planner реализован на уровне API-маршрутизации (отдельные эндпоинты по сценариям).
- `Retriever` не делает fallback в generation без evidence.
- `Verifier` является обязательным шагом для `Q&A`; при провале допускается одна re-generation попытка с расширенным контекстом.
- `Evaluator` должен пройти schema validation до публикации результата.
- Оценивание `self-check` разрешено только для существующей незавершенной попытки.
- Повторная отправка уже оцененной попытки отклоняется по идемпотентности.

## Условия остановки

- успешный ответ с источниками;
- осознанный отказ с объяснением и вариантами переформулировки;
- контролируемая техническая ошибка.

## Повторные попытки и деградация

- LLM-вызовы: до 5 retry при `429/5xx` с экспоненциальным backoff (5→10→20→40→60 сек).
- Re-generation при провале Verifier: 1 попытка с `top_k × 2`.
- Если re-generation также провалилась — `REFUSAL_SENT` без дополнительных попыток.

## Основные входы / выходы

Вход orchestrator:
- `request_id`
- `user_id`
- `session_id`
- `channel`
- `message_text`

Выход orchestrator:
- `final_status`
- `response_payload`
- `reason_code`
- `state_trace`
- `attempt_id` (только для `self-check/start`)
