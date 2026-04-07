# ATLAS phd: Governance

## 1. Risk Register

| Риск | Вероятность / влияние | Детект | Защита | Остаточный риск |
|---|---|---|---|---|
| Галлюцинации в ответах | Средняя / Высокое | Проверка на gold-set, трекинг factual errors, проверка покрытия источниками | Hard-gate verifier, ответы только с источниками, отказ при слабом evidence | Средний |
| Промах retrieval | Средняя / Высокое | Анализ промахов на benchmark queries, refusal-rate, ручной eval set | Настройка retrieval, QA чанков, roadmap к hybrid retrieval | Средний |
| Prompt injection в пользовательском вводе | Средняя / Высокое | Adversarial test set, review заблокированных попыток | Policy-first prompting, фильтрация входа, отказ при попытках override | Средний |
| Prompt injection в документах KB | Средняя / Высокое | Review ingestion, red-team документы, анализ аномалий в ответах | Retrieved text трактуется как данные, удаление известных паттернов, verifier checks sources and policy | Средний |
| Утечка PII в логах или ответах | Низкая / Высокое | Аудит логов, privacy review, выборочные проверки | Минимизация данных, псевдонимизированные ID, ограниченный доступ к логам, запрет секретов в prompts/logs | Низкий |
| Компрометация аутентификации | Низкая / Высокое | Аудит логинов, review неуспешных входов, auth integration tests | Password hashing, role checks, short-lived sessions, admin allowlist in Telegram | Низкий |
| PII в загружаемых документах | Средняя / Высокое | Review загружаемых документов, spot checks, corpus audit | Ограничение корпуса approved materials, редактирование obvious personal data, удаление документа по запросу | Средний |
| Ошибка RBAC | Низкая / Высокое | 403 integration tests, audit log review | Role checks в middleware и service layer, deny-by-default | Низкий |
| Невалидная self-check оценка | Средняя / Среднее | Schema validation, review качества оценивания | Strict payload validation, `invalid_evaluation` state, публикация только валидных результатов | Низкий |
| Сбой LLM provider | Средняя / Среднее | Мониторинг error-rate и timeout | Retries with backoff, таймауты, controlled error response | Средний |
| Потеря качества формул | Средняя / Среднее | Manual QA на formula-heavy документах, UI smoke tests | Web-first UI, LaTeX rendering, focused QA на formula-heavy sources | Средний |
| Превышение бюджета API | Средняя / Среднее | Cost dashboard, usage alerts | Ограничение контекста, cap retries, мониторинг eval runs, безопасный кеш | Низкий |

## 2. Политика логов и персональных данных

### 2.1 Что логируем

- `request_id`, `timestamp`, `node_name`, `decision`, `duration_ms`
- `reason_code` для отказов и технических сбоев
- псевдонимизированный `user_id`
- административные действия и события отказа в доступе

### 2.2 Что не логируем

- API keys, secrets, tokens, passwords
- полные персональные идентификаторы в открытом виде без операционной необходимости
- сырой чувствительный пользовательский контент, не нужный для отладки или review

### 2.3 Политика PII

- Хранить только данные, необходимые для аутентификации, учебной истории и аудита.
- Использовать внутренние идентификаторы вместо прямых персональных полей в большинстве логов.
- Доступ к логам и административным данным ограничен участниками проекта.
- Системные логи хранятся 90 дней по умолчанию.
- История `self-check` хранится до ручной очистки или запроса удаления.

### 2.4 PII в загружаемых документах

- В knowledge base допускаются только материалы, одобренные для учебного использования в рамках пилота.
- При загрузке документов администратор обязан исключать файлы с лишними персональными данными, если они не нужны для учебной задачи.
- Если документ содержит incidental PII, он подлежит редактированию, замене или удалению из корпуса.
- Документы, загруженные в KB, не должны использоваться как источник для раскрытия персональных данных в ответах модели.

## 3. Защиты от Injection и подтверждение действий

### 3.1 Prompt Injection Protection

- System and application policy always override user instructions and retrieved text.
- Retrieved chunks are treated as data, not as executable instructions.
- Попытки override поведения системы блокируются или переводятся в отказ.
- Source-backed answering is mandatory in `Q&A`; weak evidence leads to refusal, not to free-form generation.
- Suspicious prompts and blocked attempts are logged for review.

### 3.2 Подтверждение действий

- Административные действия доступны только роли `администратор`.
- Любое рискованное действие с изменением данных требует явного пользовательского запроса.
- Операции загрузки, удаления и изменения ролей должны сопровождаться audit log.
- Система не выполняет внешние действия от имени пользователя без отдельного продуктового решения; такие действия вне scope PoC.

### 3.3 Защита аутентификации

- Web MVP использует password hashing и ограниченный доступ к административным маршрутам.
- Telegram admin access ограничен allowlist по `telegram_user_id`.
- Аутентификационные ошибки и события отказа в доступе логируются для review.

## 4. Human Oversight

- Product and grading quality are reviewed on a pilot eval set.
- Risky failures (`policy_blocked`, `invalid_evaluation`, suspected leakage) are reviewed manually.
- The governance document is expected to evolve as the system is implemented and used in practice.
