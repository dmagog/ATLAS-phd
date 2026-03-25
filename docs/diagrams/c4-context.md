# C4 Context

Диаграмма показывает систему ATLAS Agent как PoC и ее внешнее окружение.

![C4 Context](./c4-context.svg)

```mermaid
flowchart LR
    user["Пользователь / аспирант"] --> web["Web-интерфейс"]
    admin["Администратор"] --> web
    web --> atlas["ATLAS Agent PoC"]
    atlas --> llm["Внешний LLM API / API эмбеддингов"]
    atlas --> db["PostgreSQL + pgvector"]
    admin --> corpus["Одобренные учебные материалы"]
    corpus --> atlas
    telegram["Telegram-бот (дополнительный / отложенный канал)"] -. optional .-> atlas
```

Ключевой акцент PoC:
- основной пользовательский контур идет через `Web UI`;
- Telegram показан как дополнительный и отложенный канал, но не как критическая зависимость основного PoC.
