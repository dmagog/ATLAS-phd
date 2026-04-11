# Спецификация инструментов и API

## Внешние API

### Внешний HTTP API PoC

#### `POST /qa/message`

Назначение:
- выполнить один `Q&A` запрос.

Минимальный запрос:
```json
{
  "session_id": "sess_123",
  "message_text": "Объясни принцип метода наименьших квадратов",
  "response_profile": "study"
}
```

Минимальный ответ:
```json
{
  "request_id": "req_123",
  "status": "answered",
  "answer_markdown": "Метод наименьших квадратов ...",
  "citations": [
    {
      "document_title": "lecture_03.pdf",
      "section_or_page": "p. 12",
      "snippet": "..."
    }
  ],
  "followup_suggestions": []
}
```

#### `POST /self-check/start`

Назначение:
- создать новую попытку self-check и вернуть вопросы.

Минимальный ответ:
```json
{
  "request_id": "req_124",
  "attempt_id": "sc_001",
  "status": "created",
  "question_set": {
    "topic": "Градиентный спуск",
    "questions": [
      {
        "question_id": "q1",
        "type": "open",
        "prompt": "Объясните роль learning rate"
      }
    ]
  }
}
```

#### `POST /self-check/{attempt_id}/submit`

Назначение:
- отправить ответы на уже созданную попытку self-check.

Минимальный запрос:
```json
{
  "answers": [
    {
      "question_id": "q1",
      "answer_text": "Learning rate задает шаг обновления ..."
    }
  ]
}
```

Минимальный ответ:
```json
{
  "request_id": "req_125",
  "attempt_id": "sc_001",
  "status": "evaluated",
  "overall_score": 4,
  "criterion_scores": {
    "correctness": 4,
    "completeness": 4,
    "logic": 4,
    "terminology": 3
  },
  "feedback_summary": "Ответ в целом корректный, но терминология местами неточна."
}
```

#### `POST /admin/ingestion-jobs`

Назначение:
- запустить ingestion пакета документов и получить `job_id`.

Минимальный ответ:
```json
{
  "job_id": "ing_001",
  "status": "created",
  "accepted_files": [
    "lecture_01.pdf",
    "lecture_02.pdf"
  ],
  "rejected_files": [
    {
      "filename": "notes.djvu",
      "reason_code": "unsupported_format"
    }
  ]
}
```

## Стандартные формы ответов

### `RefusalResponse`

Используется для осознанных отказов в `Q&A`.

```json
{
  "request_id": "req_126",
  "status": "refused",
  "reason_code": "insufficient_evidence",
  "user_safe_message": "Недостаточно подтверждающего контекста для надежного ответа.",
  "followup_suggestions": [
    "Уточните раздел или формулу",
    "Сузьте вопрос до одного метода"
  ]
}
```

### `ErrorResponse`

Используется для контролируемых технических ошибок.

```json
{
  "request_id": "req_127",
  "status": "error",
  "reason_code": "llm_timeout",
  "user_safe_message": "Сервис временно недоступен. Повторите запрос позже."
}
```

### `ValidationErrorResponse`

Используется для ошибок клиента и некорректного жизненного цикла.

```json
{
  "request_id": "req_128",
  "status": "validation_error",
  "reason_code": "attempt_already_evaluated",
  "user_safe_message": "Эта попытка уже оценена и не может быть отправлена повторно."
}
```

### LLM Generation API

Используется для:
- `Planner`
- `Answer Node`
- `Self-check Generator`
- `Self-check Evaluator`

Требования:
- один основной generation-model id в конфиге;
- timeout;
- retry при `429/5xx`;
- логирование model id, latency и token usage.

### Embeddings API

Используется для:
- embeddings chunk при ingestion;
- query embedding при retrieval.

Требования:
- стабильный output dimension;
- batch mode для ingestion;
- timeout и retry policy.

## Внутренние инструменты

### `retrieve`

`retrieve(query: str, filters: dict | None, top_k: int) -> RetrievalResult`

Пример:
```json
{
  "top1_score": 0.82,
  "enough_evidence_hint": true,
  "candidates": [
    {
      "chunk_id": "ch_101",
      "document_id": "doc_17",
      "document_title": "lecture_03.pdf",
      "section_or_page": "p. 12",
      "text": "Метод наименьших квадратов минимизирует ...",
      "score": 0.82
    }
  ]
}
```

Ошибки:
- `retrieval_timeout`
- `empty_index`
- `storage_error`

Побочные эффекты:
- нет пользовательских побочных эффектов;
- метаданные выполнения логируются.

### `generate_answer`

`generate_answer(input: AnswerInput) -> AnswerDraft`

Требования:
- генерация только по retrieved context;
- обязательные ссылки на источники в черновике.

Пример:
```json
{
  "answer_markdown": "Метод наименьших квадратов минимизирует сумму квадратов ошибок ...",
  "citations": [
    {
      "chunk_id": "ch_101",
      "document_title": "lecture_03.pdf",
      "section_or_page": "p. 12"
    }
  ],
  "formula_mode": "latex"
}
```

### `verify_answer`

`verify_answer(input: VerificationInput) -> VerificationDecision`

Выход:
- `pass | fail`
- `reason_code`
- `user_safe_message`

Пример:
```json
{
  "decision": "fail",
  "reason_code": "insufficient_evidence",
  "user_safe_message": "Недостаточно подтверждающего контекста для надежного ответа.",
  "followup_suggestions": [
    "Уточните раздел или формулу",
    "Сузьте вопрос до одного метода"
  ]
}
```

### `generate_self_check`

`generate_self_check(topic: str, settings: dict) -> QuestionSet`

Пример:
```json
{
  "topic": "Градиентный спуск",
  "questions": [
    {
      "question_id": "q1",
      "type": "open",
      "prompt": "Объясните роль learning rate"
    },
    {
      "question_id": "q2",
      "type": "multiple_choice",
      "prompt": "Что происходит при слишком большом шаге?",
      "options": ["Медленная сходимость", "Расходимость", "Ничего"]
    }
  ]
}
```

### `evaluate_self_check`

`evaluate_self_check(input: EvaluationInput) -> EvaluationPayload`

Требования:
- payload проходит schema validation;
- сохраняются `overall_score`, `criterion_scores`, `error_tags`, `confidence`.

Пример:
```json
{
  "attempt_id": "sc_001",
  "overall_score": 4,
  "criterion_scores": {
    "correctness": 4,
    "completeness": 4,
    "logic": 4,
    "terminology": 3
  },
  "error_tags": ["terminology"],
  "confidence": 0.84,
  "feedback_summary": "Ответ корректен по сути, но терминология нуждается в уточнении."
}
```

## Контракт ответа для web-интерфейса

Для web-first PoC backend должен уметь отдавать:
- `answer_markdown` как основной формат вывода;
- `citations[]` как отдельную структурированную часть ответа;
- `formula_mode` (`latex`, `plain_text`);
- `refusal_reason` и `followup_suggestions[]` для отказов;
- `self_check_result` с оценками и кратким feedback.

Единые поля для отказов и ошибок:
- `request_id`
- `status`
- `reason_code`
- `user_safe_message`
- `followup_suggestions[]` (если применимо)

## Защита

- retrieved text рассматривается как данные, не как инструкции;
- все admin endpoints защищены auth/RBAC;
- секреты поступают только через конфигурацию окружения.
