# ATLAS Agent: System Design (Milestone 2)

## 1. Назначение документа

Документ фиксирует архитектуру PoC-системы перед разработкой. Его цель: снять архитектурную неопределенность по основным модулям, процессу выполнения, контрактам, защитным механизмам и эксплуатационным ограничениям.

Документ описывает именно PoC-реализацию для ближайшей итерации. Целевая расширенная архитектура из `docs/product-proposal.md` сохраняется как зона развития, но не считается обязательной для первой реализации.

## 2. Контекст и границы PoC

ATLAS phd решает задачу подготовки к кандидатскому минимуму по технической специальности. Система должна:
- отвечать на вопросы по учебному корпусу с опорой на источники;
- честно отказывать при недостатке evidence;
- проводить self-check по теме и возвращать структурированную обратную связь;
- работать через web-интерфейс как основной канал MVP.

В PoC входят:
- `Q&A` по загруженной базе знаний;
- `Self-check` с двухшаговым жизненным циклом: старт попытки и отдельная отправка ответов на оценку;
- ручной ingestion материалов администратором;
- локальное развертывание;
- базовая наблюдаемость и пилотные проверки качества.

Вне основных границ PoC:
- production-grade multi-service deployment;
- hybrid retrieval как режим по умолчанию;
- продвинутая персонализация обучения;
- Telegram как основной канал;
- любые внешние действия от имени пользователя.

## 3. Ключевые архитектурные решения

1. Система строится как `agentic RAG` с явным графом оркестрации, а не как один свободный tool-calling агент.
2. Агентность PoC выражена как маршрутизируемый агентный конвейер: `Planner` выбирает ветку сценария, после чего внутри выбранной ветки исполняется фиксированная последовательность специализированных узлов.
3. Основной пользовательский канал PoC: `web-first`; Telegram остается дополнительным направлением развития и не влияет на основной путь выполнения.
4. PoC реализуется как один backend-сервис с внутренними модулями, а не как набор отдельных микросервисов.
5. Генерация выполняется через один внешний LLM-провайдер с одной основной моделью; отдельные локальные модели для планирования и генерации в PoC не закладываются.
6. Retrieval в PoC: `vector-only` поверх `PostgreSQL + pgvector`, но контракт retriever совместим с будущим hybrid-контуром.
7. В `Q&A` действует `hard-gate verifier`: при слабом evidence система отказывает, а не отвечает "по памяти".
8. Память `Q&A` ограничена активной сессией; между сессиями хранится только история `self-check`.
9. Наблюдаемость закладывается вендор-нейтрально: структурированные логи, прикладные метрики, трассировка совместимого формата.

## 4. Логическая архитектура

### 4.1 Основные модули

| Модуль | Роль |
|---|---|
| `Web UI` | Основной пользовательский интерфейс MVP; чат, self-check, просмотр результатов |
| `FastAPI App` | HTTP API, auth, web handlers, admin endpoints |
| `Orchestrator` | Исполнение графа, переходы состояний, retry/fallback, reason codes |
| `Planner Node` | Классификация запроса: `qa`, `self_check`, `clarify` |
| `Retriever` | Поиск релевантных chunk по индексу `pgvector` |
| `Answer Node` | Генерация черновика ответа по источникам |
| `Verifier Node` | Проверка evidence coverage, citations, policy gates |
| `Self-check Generator` | Генерация набора вопросов по теме |
| `Self-check Evaluator` | Оценка ответов по рубрике и формирование структурированного payload |
| `Ingestion Pipeline` | Обработка загруженных документов: parse -> normalize -> chunk -> embed -> index |
| `Storage` | PostgreSQL для бизнес-данных, pgvector для индекса, локальный volume для исходных файлов |
| `Observability Layer` | Структурированные логи, метрики, следы выполнения |

### 4.2 Диаграммы

- C4 Context: [docs/diagrams/c4-context.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/diagrams/c4-context.md)
- C4 Container: [docs/diagrams/c4-container.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/diagrams/c4-container.md)
- C4 Component: [docs/diagrams/c4-component.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/diagrams/c4-component.md)
- Workflow Graph: [docs/diagrams/workflow-graph.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/diagrams/workflow-graph.md)
- Data Flow: [docs/diagrams/data-flow.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/diagrams/data-flow.md)

Разделение ролей диаграмм:
- `C4 Context`, `C4 Container`, `C4 Component` описывают границы системы, контейнеры и внутреннюю структуру.
- `Workflow Graph` описывает порядок выполнения запроса.
- `Data Flow` описывает движение данных, хранение и логирование.

## 5. Основной процесс выполнения

### 5.1 Поток `Q&A`

После того как `Planner Node` выбрал маршрут `qa`, дальше выполняется детерминированный конвейер `Retriever -> Answer Node -> Verifier Node`. Следующий шаг определяется оркестратором, а не свободным решением LLM.

1. Пользователь отправляет запрос через `Web UI`.
2. `FastAPI App` создает `request_id`, определяет пользователя и активную сессию.
3. `Orchestrator` переводит запрос в `REQUEST_RECEIVED`.
4. `Planner Node` определяет маршрут:
   - `qa`
   - `self_check`
   - `clarify`
5. Для маршрута `qa`:
   - `Retriever` получает top-k chunk;
   - `Answer Node` строит черновик ответа только по retrieved context;
   - `Verifier Node` проверяет релевантность, citations и policy conditions.
6. Если verifier пропускает ответ:
   - ответ отдается пользователю с источниками;
   - в логи пишутся state transitions и decision metadata.
7. Если verifier блокирует ответ:
   - пользователю возвращается отказ с reason code и вариантом переформулировки.

### 5.2 Поток `Self-check`

PoC-ветка намеренно упрощена относительно целевой архитектуры:

После того как `Planner Node` выбрал маршрут `self_check`, дальше выполняется фиксированный конвейер `Self-check Generator -> сохранение попытки -> Self-check Evaluator -> выдача результата`. В PoC здесь нет свободного выбора следующего шага агентом.

1. Пользователь инициирует `self-check` по теме.
2. `Planner Node` маршрутизирует запрос в `self_check`.
3. `Self-check Generator` генерирует набор вопросов по теме.
4. Backend создает `attempt_id`, сохраняет попытку в статусе `created` и возвращает `QuestionSet` в UI.
5. Пользователь отвечает на вопросы и отправляет ответы отдельным запросом.
6. Backend валидирует `attempt_id`, статус попытки и payload ответов.
7. `Self-check Evaluator` оценивает ответы по рубрике и возвращает структурированный payload.
8. Результат оценки сохраняется в попытку; из payload формируется финальная обратная связь для пользователя.

Примечание:
- Отдельный `Feedback Agent` зарезервирован в целевой архитектуре, но в PoC не обязателен как отдельный исполняемый модуль.
- Контракт оценки уже проектируется так, чтобы позднее можно было выделить отдельный шаг обратной связи без ломающего рефакторинга.
- Таким образом, пользовательский сценарий один, но выполнение состоит из двух API-взаимодействий: `start attempt` и `submit answers`.

### 5.3 Поток администратора и ingestion

1. Администратор аутентифицируется в web-интерфейсе.
2. Загружает пакет поддерживаемых файлов.
3. `Ingestion Pipeline` выполняет:
   - MIME/type validation;
   - text extraction;
   - normalization;
   - chunking;
   - embeddings generation;
   - запись metadata и chunk в PostgreSQL / pgvector.
4. Для каждого файла и job сохраняется статус обработки.

## 6. Состояния, память и управление контекстом

### 6.1 Оркестрационные состояния

PoC использует конечный автомат со следующими ключевыми состояниями:

- `REQUEST_RECEIVED`
- `PLANNER_DECIDED`
- `QA_RETRIEVAL_DONE`
- `QA_ANSWER_DRAFTED`
- `QA_VERIFIED_PASS`
- `QA_VERIFIED_FAIL`
- `SC_ATTEMPT_CREATED`
- `SC_ANSWERS_SUBMITTED`
- `SC_QUESTIONS_READY`
- `SC_EVALUATED`
- `INVALID_EVALUATION`
- терминалы: `RESPONSE_SENT`, `REFUSAL_SENT`, `CLARIFICATION_REQUESTED`, `TECHNICAL_ERROR`

Каждый переход логируется с `request_id`, `state_from`, `state_to`, `decision`, `reason_code`, `duration_ms`.

Для `self-check` жизненный цикл PoC фиксируется так:
- `POST /self-check/start` создает попытку и переводит ее в `SC_ATTEMPT_CREATED`;
- генерация вопросов фиксируется как `SC_QUESTIONS_READY`;
- `POST /self-check/{attempt_id}/submit` переводит попытку в `SC_ANSWERS_SUBMITTED`;
- после успешной оценки попытка переходит в `SC_EVALUATED`;
- при невалидном payload используется `INVALID_EVALUATION`.

### 6.2 Модель памяти

`Q&A`:
- используется только контекст активной пользовательской сессии;
- в prompt попадают последние сообщения диалога в пределах context budget;
- долгосрочная персонализация по истории `Q&A` в PoC не делается.

`Self-check`:
- результаты попыток сохраняются между сессиями;
- хранятся `attempt_id`, `topic`, `status`, `question_set`, `submitted_answers`, `overall_score`, `criterion_scores`, `feedback_summary`, `timestamp`;
- незавершенная попытка может находиться в статусах `created` или `submitted`, завершенная в статусе `evaluated`.

### 6.3 Политика бюджета контекста

Для контура генерации вводится фиксированный бюджет контекста:

- системный и policy-промпт;
- текущий пользовательский запрос;
- ограниченный контекст сессии;
- retrieved chunks;
- служебные поля оркестрации.

Практические правила PoC:
- в генерацию не передаются все найденные chunk без отбора;
- дубликаты и почти идентичные фрагменты удаляются;
- при конфликтующих источниках verifier переводит ответ в отказ или требует осторожную формулировку;
- Telegram-специфичный формат контекста в PoC не оптимизируется, так как канал не является основным.

## 6.4 Внешний API PoC

Минимальная внешняя поверхность PoC фиксируется так:

| Endpoint | Назначение | Основной ответ |
|---|---|---|
| `POST /qa/message` | Один `Q&A` запрос | `answer` или `refusal` |
| `POST /self-check/start` | Создание новой попытки self-check | `attempt_id` + `QuestionSet` |
| `POST /self-check/{attempt_id}/submit` | Отправка ответов на оценку | `EvaluationResult` |
| `POST /admin/ingestion-jobs` | Запуск пакетной загрузки документов | `job_id` + статусы файлов |

Детальные payload-контракты перечислены в [docs/specs/tools-and-apis.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/specs/tools-and-apis.md).

## 7. Контур retrieval

### 7.1 Индекс и источники

Источники retrieval:
- учебные материалы, загруженные администратором;
- поддерживаемые форматы: `pdf`, `docx`, `txt`, `md`.

Индекс:
- raw file metadata в PostgreSQL;
- chunk metadata и embeddings в PostgreSQL с `pgvector`.

### 7.2 Query-time retrieval

Поисковый pipeline PoC:

1. Нормализация пользовательского запроса.
2. Генерация embedding для запроса.
3. Vector search по `pgvector`.
4. Детерминированная постобработка:
   - dedup соседних chunk;
   - ограничение числа context candidates;
   - нормализация score;
   - отбор top candidates для шага ответа.

### 7.3 Решение answer / refuse

Для ответа должны выполняться guardrails из ТЗ:
- `top1_score >= 0.70`
- минимум 2 фрагмента с `score >= 0.60`

Если условия не выполнены:
- `Answer Node` не считается достаточным основанием для публикации;
- `Verifier Node` возвращает `REFUSAL_SENT` с reason code.

### 7.4 Ограничения retrieval в PoC

- `vector-only` может хуже работать на редких терминах и запросах с высокой плотностью формул;
- OCR и качество исходных документов ограничивают качество chunk;
- hybrid search и отдельный reranker оставлены в зоне развития.

## 8. Интеграции и инструменты

### 8.1 Внешние интеграции

| Интеграция | Назначение | Примечание |
|---|---|---|
| `LLM Generation API` | Planner, answer generation, self-check generation/evaluation | Один провайдер, одна основная модель |
| `Embeddings API` | Построение embeddings для chunk и query | Может быть тем же provider, но отдельным endpoint/model |
| `PostgreSQL + pgvector` | Хранение бизнес-данных и retrieval index | Основная stateful зависимость PoC |

### 8.2 Внутренние контракты инструментов

Минимальные внутренние tools:
- `retrieve(query, filters, top_k) -> RetrievalResult`
- `generate_answer(input) -> AnswerDraft`
- `verify_answer(input) -> VerificationDecision`
- `generate_self_check(topic, settings) -> QuestionSet`
- `evaluate_self_check(input) -> EvaluationPayload`

Общие требования:
- явные timeout;
- типизированный error payload;
- отсутствие скрытых побочных эффектов;
- обязательная запись метаданных выполнения в слой наблюдаемости.

## 9. Отказы, деградация и защитные механизмы

| Сценарий отказа | Детект | Поведение |
|---|---|---|
| Недостаточный retrieval evidence | `top1/top_k` ниже порога | Осознанный отказ с reason code |
| Ambiguous intent | Planner confidence ниже порога или конфликт категорий | Запрос уточнения |
| LLM timeout / `429` / `5xx` | Ошибка внешнего API | До 2 retry с backoff, затем controlled error |
| Invalid self-check evaluation | Схема payload невалидна | Не публиковать результат, вернуть controlled refusal/error |
| Prompt injection | Policy violation или suspicious pattern | Игнорировать инструкцию, логировать, при необходимости отказать |
| Unsupported document format | MIME/extension validation | Отклонить файл до ingestion |
| Auth / RBAC failure | `401/403` на API | Не выполнять действие, писать security log |

Защитные механизмы PoC:
- ответы без источников запрещены;
- retrieved text трактуется как данные, а не инструкции;
- административные действия проходят RBAC-проверку;
- финальный ответ публикуется только после verifier-pass или валидного evaluation payload.

## 10. Технические и операционные ограничения

### 10.1 Задержка и надежность

- Целевой `p95 latency` для `Q&A`: `<= 15 sec`
- Целевой `error rate`: `<= 3%`
- Таймаут retrieval: `<= 2 sec`
- Таймаут одного LLM-вызова: `<= 25 sec`
- Retry policy для generation/evaluation: до 2 повторов при `429/5xx`

### 10.2 Стоимость

- Плановый бюджет внешнего API на пилот: до `150 USD / month`
- Основные драйверы стоимости:
  - число `Q&A` и `self-check` запросов;
  - размер retrieved context;
  - число повторных generation/evaluation вызовов;
  - объем batch embeddings при ingestion.

### 10.3 Операционные ограничения

- Локальное развертывание, без production cluster и без HA.
- Одна команда разработки и короткий цикл итерации.
- Ручная загрузка материалов, без web crawling и без автоматического обновления корпуса.

### 10.4 Предпосылки масштаба пилота

Для обоснования выбранной PoC-архитектуры принимаются следующие рабочие предпосылки:

- корпус знаний порядка `50-150` документов;
- итоговый размер индекса порядка `5,000-20,000` chunk;
- типичный ingestion batch: `5-20` файлов за один job;
- активная одновременная нагрузка: до `5` пользователей;
- типичный пользовательский сценарий: короткие сессии `Q&A` и эпизодические `self-check` попытки.

Эти значения объясняют, почему для PoC достаточно одного backend-сервиса и `PostgreSQL + pgvector`; выход за эти допущения будет поводом для пересмотра формы развертывания и retrieval-стека.

## 11. Реализационная готовность

Для старта разработки после этого документа считаются зафиксированными:

1. Основная форма развертывания: один backend-сервис + PostgreSQL/pgvector + Web UI.
2. Основной execution graph для `Q&A` и упрощенный graph для `self-check`.
3. State model и reason codes.
4. Retrieval policy и hard refusal rules.
5. Tool contracts и наблюдаемость.
6. Ограничения по latency, cost и reliability.

Детали модулей вынесены в отдельные спеки:
- [docs/specs/agent-orchestrator.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/specs/agent-orchestrator.md)
- [docs/specs/web-and-api.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/specs/web-and-api.md)
- [docs/specs/ingestion.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/specs/ingestion.md)
- [docs/specs/retriever.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/specs/retriever.md)
- [docs/specs/tools-and-apis.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/specs/tools-and-apis.md)
- [docs/specs/memory-and-context.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/specs/memory-and-context.md)
- [docs/specs/serving-and-config.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/specs/serving-and-config.md)
- [docs/specs/observability-and-evals.md](/Users/georgijmamarin/Desktop/ATLAS-phd/docs/specs/observability-and-evals.md)
