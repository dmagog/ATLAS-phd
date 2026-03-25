# C4 Component

Диаграмма показывает внутреннее устройство backend-ядра как набор компонентов и их зависимостей.
Она не отражает порядок выполнения шагов запроса; за это отвечает `Workflow Graph`.

![C4 Component](./c4-component.svg)

```mermaid
flowchart LR
    subgraph interface["Интерфейсный слой"]
        api["FastAPI App / Web handlers"]
        auth["Аутентификация / RBAC"]
        session["Менеджер сессий"]
    end

    subgraph orchestration["Оркестрация"]
        orchestrator["Оркестратор"]
        policy["Policy Engine"]
    end

    subgraph qa_domain["Q&A компоненты"]
        planner["Planner Node"]
        retriever["Retriever"]
        answer["Answer Node"]
        verifier["Verifier Node"]
    end

    subgraph sc_domain["Self-check компоненты"]
        scgen["Self-check Generator"]
        sceval["Self-check Evaluator"]
    end

    subgraph ingestion_domain["Ingestion компонент"]
        ingest["Ingestion Pipeline"]
    end

    subgraph infra["Инфраструктурный слой"]
        llm["LLM / Embeddings Client"]
        store["Storage Gateway"]
        obs["Observability Adapter"]
        pg["PostgreSQL + pgvector"]
        files["Файловое хранилище"]
    end

    api --> auth
    api --> session
    api --> orchestrator
    api --> ingest
    api --> obs

    orchestrator --> planner
    orchestrator --> retriever
    orchestrator --> answer
    orchestrator --> verifier
    orchestrator --> scgen
    orchestrator --> sceval
    orchestrator --> policy
    orchestrator --> obs

    planner --> llm

    retriever --> llm
    retriever --> store

    answer --> llm
    answer --> store

    verifier --> policy
    verifier --> store

    scgen --> llm
    scgen --> store

    sceval --> llm
    sceval --> store
    sceval --> policy

    ingest --> llm
    ingest --> store
    ingest --> files
    ingest --> obs

    store --> pg
```
