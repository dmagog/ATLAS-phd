# ATLAS Agent: Governance (Milestone 1)

## 1. Risk Register

| Риск | Вероятность / влияние | Детект | Защита | Остаточный риск |
|---|---|---|---|---|
| Галлюцинации в ответах | Medium / High | Gold-set review, factual error tracking, source coverage checks | Hard-gate verifier, answer only with sources, refusal on weak evidence | Medium |
| Промах retrieval | Medium / High | Failed benchmark queries, refusal-rate analysis, manual eval set | Retrieval tuning, quality checks on chunks, planned hybrid retrieval | Medium |
| Prompt injection в пользовательском вводе | Medium / High | Adversarial test set, blocked prompt review | Policy-first prompting, input filtering, refusal on override attempts | Medium |
| Prompt injection в документах KB | Medium / High | Ingestion review, red-team documents, anomaly review in answers | Treat retrieved text as data only, strip known patterns, verifier checks sources and policy | Medium |
| Утечка PII в логах или ответах | Low / High | Log audit, privacy review, manual spot checks | Data minimization, pseudonymized IDs, restricted log access, no secrets in prompts/logs | Low |
| Ошибка RBAC | Low / High | 403 integration tests, audit log review | Role checks in middleware and service layer, deny-by-default | Low |
| Невалидная self-check оценка | Medium / Medium | Schema validation, eval quality review | Strict payload validation, `invalid_evaluation` state, do not publish invalid results | Low |
| Сбой LLM provider | Medium / Medium | Error-rate monitoring, timeout tracking | Retries with backoff, timeouts, controlled error response | Medium |
| Потеря качества формул | Medium / Medium | Manual QA on formula documents, UI smoke tests | Web-first UI, LaTeX rendering, focused QA on formula-heavy sources | Medium |
| Превышение бюджета API | Medium / Medium | Cost dashboard, usage alerts | Limit context size, cap retries, monitor eval runs, cache where safe | Low |

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

## 3. Защиты от Injection и подтверждение действий

### 3.1 Prompt Injection Protection

- System and application policy always override user instructions and retrieved text.
- Retrieved chunks are treated as data, not as executable instructions.
- Unsafe override attempts are blocked or answered with refusal.
- Source-backed answering is mandatory in `Q&A`; weak evidence leads to refusal, not to free-form generation.
- Suspicious prompts and blocked attempts are logged for review.

### 3.2 Подтверждение действий

- Административные действия доступны только роли `администратор`.
- Любое рискованное действие с изменением данных требует явного пользовательского запроса.
- Операции загрузки, удаления и изменения ролей должны сопровождаться audit log.
- Система не выполняет внешние действия от имени пользователя без отдельного продуктового решения; такие действия вне scope PoC.

## 4. Human Oversight

- Product and grading quality are reviewed on a pilot eval set.
- Risky failures (`policy_blocked`, `invalid_evaluation`, suspected leakage) are reviewed manually.
- The governance document is expected to evolve after Milestone 1 based on implementation findings.
