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

## 5. DPIA-lite (M6 pilot)

Облегчённая оценка влияния на персональные данные перед запуском пилота. Этот раздел подписывается ответственным с кафедры (методист или научрук) **до** приглашения первого аспиранта. Подпись = факт того, что осознали риски и согласны с защитами.

### 5.1 Категории обрабатываемых данных

| Категория | Что | Где хранится | Срок |
|---|---|---|---|
| Email | для login, инвайты | `users.email` | до удаления аккаунта |
| Хешированный пароль | для аутентификации | `users.hashed_password` (Argon2) | до удаления аккаунта |
| Дата согласия | юридическое доказательство | `users.consent_recorded_at` | до удаления аккаунта |
| История self-check | оценки, ответы, error_tags | `selfcheck_attempts` (JSON) | до явного запроса удаления |
| История Q&A | вопросы, ответы, цитаты | `qa_sessions`, `qa_feedback` | до явного запроса удаления |
| Audit log | действия, доступ к данным | `audit_log` | append-only, не удаляется |
| Telegram (если используется) | оперативная связь | вне ATLAS DB | по политике мессенджера |

**Не собираем:** ФИО, дату рождения, биометрию, данные о здоровье, финансовые данные.

### 5.2 Юридическое основание (lawful basis)

Согласие (consent) — единственное основание. Каждый аспирант явно даёт согласие при регистрации (BDD 4.10): чекбокс «согласие на обработку учебных данных», без которого регистрация невозможна. Согласие отзывается по запросу — данные удаляются (BDD 7.3).

### 5.3 Privacy posture

- **По умолчанию anonymous** — научрук видит только agg-статистику, не персональные профили.
- **Opt-in для персонального профиля** (`supervisor_visibility='show-to-supervisor'`) — flip back any time.
- **Анти-leak в API** — попытка прочитать профиль без opt-in возвращает 404, чтобы не утекало даже существование (BDD 5.5).
- **Audit на каждый персональный доступ** — `personal_data.access` event с actor + target + timestamp.
- **N-threshold** на heatmap — agg-статистика недоступна, пока в группе < 5 студентов и < 30 attempts (BDD 5.3, 5.6) — иначе слишком легко деанонимизировать.

### 5.4 Access control

| Роль | Что видит |
|---|---|
| super-admin | все тенанты, все данные. Используется только владельцем платформы. |
| tenant-admin | свой тенант: программа, материалы, audit_log, agg по студентам |
| supervisor | свой тенант: heatmap, drilldown, list студентов, профили opted-in |
| student | свои данные + agg по своему тенанту (без персональных деталей других) |

Cross-tenant запрос → 403/404. Attempt to bypass → audit + tenant-admin alert.

### 5.5 Data retention

- **Активные аккаунты** — без срока (пока пилот идёт).
- **Soft-deleted users** — `deleted_at` стоит, attempts анонимизируются (`user_id=NULL`), но agg остаётся.
- **Audit log** — append-only, не удаляется (для расследования incident'ов в будущем).
- **Backups** — 7 дней rolling (см. `scripts/pg_backup.sh`).
- **После пилота** — БД либо архивируется (для post-mortem), либо удаляется по решению пилотной группы. Решение фиксируется в `docs/pilot/notes/end-of-pilot-report.md`.

### 5.6 Права субъекта данных

| Право | Как реализуется |
|---|---|
| Доступ к своим данным | `GET /me` + ручной dump через tenant-admin (incident-runbook §3.3) |
| Исправление | через UI (когда появится) или ручной `psql` UPDATE |
| Удаление | tenant-admin делает soft-delete + анонимизацию (BDD 7.3, incident-runbook §3.3) |
| Portability | manual dump в JSON по запросу (audit как `data.export`) |
| Отзыв согласия | = удаление данных |
| Жалоба | контакт ответственного (раздел 5.8) |

### 5.7 Incident response

См. `docs/pilot/incident-runbook.md`. Ключевые действия:
1. Stop the bleed в течение 1 часа (jwt_version bump, read-only flag).
2. Notify затронутого пользователя в течение 24 часов.
3. Post-mortem в `docs/pilot/incidents/{date}-privacy.md`.

### 5.8 Подписанты

- **Ответственный за обработку (data controller):** ___________________ (методист/научрук, ФИО)
- **Дата подписи:** _____________________
- **Срок действия:** до конца пилота (8 недель), затем обязательно review.

> Эта DPIA-lite не заменяет полную DPIA по GDPR/152-ФЗ, если объём пилота вырастет за пределы 5–10 студентов одной кафедры. При расширении на multi-кафедра mode → нужен полноценный пересмотр (включая возможный DPO + регистрацию в Роскомнадзоре, если применимо).
