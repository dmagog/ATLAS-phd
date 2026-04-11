# Data Flow

Диаграмма показывает, какие данные проходят через систему, что хранится и что логируется.

![Data Flow](./data-flow.svg)

```mermaid
flowchart LR
    user["Пользовательский запрос / ввод self-check"] --> api["FastAPI App"]
    api --> orch["Состояние оркестратора"]
    orch --> prompt["Сборка промпта"]
    prompt --> llm["LLM API"]
    orch --> retr["Retriever"]
    retr --> chunks["Метаданные документов / chunks / embeddings"]
    llm --> orch
    orch --> response["Ответ / отказ / результат оценки"]
    response --> user_out["Web-интерфейс"]

    admin["Загрузка администратором"] --> ingest["Ingestion Pipeline"]
    ingest --> files["Файловое хранилище документов"]
    ingest --> chunks

    orch --> session["Состояние сессии"]
    orch --> attempts["Попытки self-check"]
    session --> pg["PostgreSQL"]
    attempts --> pg

    orch --> logs["Структурированные логи"]
    api --> audit["Аудит-логи"]
    ingest --> audit

    api --> privacy["Минимизация PII / псевдонимизация"]
    privacy --> logs
    privacy --> audit
```
