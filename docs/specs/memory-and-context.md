# Спецификация памяти и контекста

## Состояние сессии

В рамках активной сессии сохраняются:
- `session_id`
- последние сообщения диалога;
- режим (`qa` / `self_check`);
- профиль ответа;
- служебные признаки последнего route/decision.

## Политика памяти

### `Q&A`

- Используется только текущая сессия.
- В генерацию попадает ограниченное окно сообщений.
- Межсессионная персонализация `Q&A` в PoC не поддерживается.

### `Self-check`

- Результаты попыток сохраняются между сессиями.
- История нужна для просмотра результатов и будущей аналитики, но не для динамической адаптации PoC-логики.
- Незавершенная попытка хранит `attempt_id`, `topic`, `question_set`, `status`.
- Завершенная попытка дополняется `submitted_answers`, `overall_score`, `criterion_scores`, `feedback_summary`.

## Политика сборки контекста

Контекст генерации собирается из:
- system prompt;
- policy prompt;
- user message;
- session window;
- retrieved chunks;
- service metadata.

Правила:
- приоритет отдается свежему сообщению и retrieved evidence;
- лишние и дублирующие chunk удаляются;
- при превышении budget сначала уменьшается session window, а не удаляются top evidence chunks.

## Хранение

- session records: PostgreSQL, с ограниченным retention для активной сессии;
- self-check history: PostgreSQL, сохраняется до удаления;
- секреты, токены и raw credentials в memory/state не сохраняются.
