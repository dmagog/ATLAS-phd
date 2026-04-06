from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str
    embeddings_url: str = "http://localhost:8001"
    llm_api_key: str
    llm_model_id: str = "qwen/qwen3-8b:free"
    jwt_secret: str
    admin_email: str
    admin_password: str
    log_level: str = "INFO"
    request_timeout_ms: int = 25000
    retriever_top_k: int = 8
    retriever_max_chunks_in_prompt: int = 4
    retriever_min_top1_score: float = 0.62
    retriever_min_score_threshold: float = 0.55
    retriever_min_chunks_above_threshold: int = 2
    retriever_hybrid_rrf_k: int = 60  # RRF constant (standard value)


settings = Settings()
