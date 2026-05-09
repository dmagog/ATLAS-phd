import logging
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_log = logging.getLogger(__name__)

# Заведомо слабые placeholder-значения из .env.example. Никогда не должны
# пройти в боевой запуск — даже в dev-окружении это знак, что .env не
# заполнен. Список исчерпывающий: если добавляются новые placeholders в
# .env.example, их нужно перечислить здесь.
_FORBIDDEN_SECRETS = {
    "change_me_in_production",
    "changeme",
    "atlas_dev",
    "your_openrouter_key_here",
    "secret",
    "password",
    "admin",
}

_MIN_SECRET_LEN = 32  # JWT-секрет: 32+ байта рекомендация для HS256
_MIN_PASSWORD_LEN = 12


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

    # ── Security middleware (Итерация 5) ─────────────────────────────────
    # Белый список Host header'ов (TrustedHostMiddleware). В production
    # обязательно задать явный список: 'atlas.example.com,www.atlas.example.com'.
    # '*' допустим только в dev — иначе атакующий может подменять Host для
    # cache-poisoning или смены ссылок в email-уведомлениях.
    trusted_hosts: str = "*"

    # Белый список origin'ов для CORS. Пустая строка = CORSMiddleware не
    # подключается (same-origin only, безопасно по умолчанию для Jinja2 UI).
    # В production задать: 'https://atlas.example.com'.
    cors_allowed_origins: str = ""

    # HSTS: max-age и subdomain-флаг отдаются заголовком
    # Strict-Transport-Security. Включаем только в production, потому что
    # за HTTP в dev браузер всё равно проигнорирует, а на проде он pin'ит
    # домен на HTTPS. Если хостимся за HTTPS-proxy (Caddy/nginx) — это
    # обязательно. 31536000 = 1 год (рекомендация OWASP).
    hsts_max_age: int = 31536000

    # Лимиты на загрузку файлов через /admin/ingestion-jobs. UploadFile.read()
    # читает весь файл в RAM — без лимита это лёгкий memory-DoS для админа.
    # Дефолты подобраны под типичный кандидатский корпус (PDF до 50MB).
    upload_max_file_size_mb: int = 50
    upload_max_total_size_mb: int = 200
    upload_max_files_per_job: int = 50

    @property
    def trusted_hosts_list(self) -> list[str]:
        items = [h.strip() for h in self.trusted_hosts.split(",") if h.strip()]
        return items or ["*"]

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @field_validator("jwt_secret")
    @classmethod
    def _check_jwt_secret(cls, v: str) -> str:
        if v.strip().lower() in _FORBIDDEN_SECRETS:
            raise ValueError(
                "JWT_SECRET равен placeholder-значению из .env.example. "
                "Сгенерируй сильный секрет: `python -c 'import secrets; "
                "print(secrets.token_urlsafe(48))'`"
            )
        return v

    @field_validator("admin_password")
    @classmethod
    def _check_admin_password(cls, v: str) -> str:
        if v.strip().lower() in _FORBIDDEN_SECRETS:
            raise ValueError(
                "ADMIN_PASSWORD равен placeholder-значению. Задай сильный "
                "пароль администратора в .env (минимум 12 символов)."
            )
        return v

    @field_validator("llm_api_key")
    @classmethod
    def _check_llm_api_key(cls, v: str) -> str:
        if v.strip().lower() in _FORBIDDEN_SECRETS or not v.strip():
            raise ValueError(
                "LLM_API_KEY не задан или равен placeholder-значению. "
                "Получи ключ на https://openrouter.ai и положи в .env."
            )
        return v

    @model_validator(mode="after")
    def _enforce_strength_in_production(self):
        # В production требуем длину секретов; в dev только warning,
        # чтобы не ломать локальную разработку. Placeholder-значения
        # отвергаются всегда (см. field_validators выше).
        if self.app_env == "production":
            if len(self.jwt_secret) < _MIN_SECRET_LEN:
                raise ValueError(
                    f"В production JWT_SECRET должен быть минимум "
                    f"{_MIN_SECRET_LEN} символов (сейчас {len(self.jwt_secret)})."
                )
            if len(self.admin_password) < _MIN_PASSWORD_LEN:
                raise ValueError(
                    f"В production ADMIN_PASSWORD должен быть минимум "
                    f"{_MIN_PASSWORD_LEN} символов."
                )
        else:
            if len(self.jwt_secret) < _MIN_SECRET_LEN:
                _log.warning(
                    "JWT_SECRET короче %d символов — в production это будет "
                    "ошибкой запуска.",
                    _MIN_SECRET_LEN,
                )
        return self


settings = Settings()
