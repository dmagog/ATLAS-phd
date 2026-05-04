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
    request_timeout_ms: int = 180000  # 3 min — reasoning models need time to think
    retriever_top_k: int = 8
    retriever_max_chunks_in_prompt: int = 4
    retriever_min_top1_score: float = 0.62
    retriever_min_score_threshold: float = 0.55
    retriever_min_chunks_above_threshold: int = 2
    retriever_hybrid_rrf_k: int = 60  # RRF constant (standard value)

    # M3 eval-harness A/B toggle (M3.D protocol).
    # treatment (default): full agentic loop with verifier hard-gate.
    # baseline (verifier_enabled=false): plain retrieval + LLM answer, no
    # hard-gate refusal, no post-answer citation check. Used by eval/runner.py
    # with config eval/configs/baseline.toml. The toggle is env-driven (set
    # ATLAS_VERIFIER_ENABLED=false in app environment + restart) — header-level
    # per-request switching deferred to a follow-up.
    verifier_enabled: bool = True

    # M4.5: which tenant a super-admin without X-Atlas-Tenant header acts in,
    # and which tenant `tenant_helpers.get_default_tenant_id` returns. Default
    # was 'default' through M4; renamed to 'optics-kafedra' as part of the
    # M4.5 handoff (migration 0007). Override via PILOT_TENANT_SLUG env var
    # for staging or future direction switches.
    pilot_tenant_slug: str = "optics-kafedra"


settings = Settings()
