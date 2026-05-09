import re
import structlog
from atlas.core.config import settings


# Поля, которые маскируем в любом логе. Идея в том, что даже если
# разработчик случайно положит секрет/PII в logger.info, оно не уедет
# в plaintext. Список умеренно-агрессивный: сюда стоит добавлять
# вместо споров «маскировать или нет».
_SENSITIVE_KEYS = {
    "password", "passwd", "pwd",
    "token", "access_token", "refresh_token", "id_token", "jwt",
    "api_key", "apikey", "secret", "client_secret",
    "authorization", "cookie", "set_cookie",
    "hashed_password",
}

# Поля с email — маскируем частично, сохраняя первый символ и домен.
# Для аудита (login_failed) этого достаточно, чтобы понять «кто-то
# атакует ту же учётку», но недостаточно для слива списка email'ов
# из логов.
_EMAIL_KEYS = {"email", "user_email", "admin_email", "actor_email"}

_EMAIL_RE = re.compile(r"^([^@])([^@]*)(@.+)$")


def _mask_email(value: str) -> str:
    m = _EMAIL_RE.match(value)
    if not m:
        return "***"
    first, middle, domain = m.groups()
    return f"{first}{'*' * max(len(middle), 1)}{domain}"


def _redact(_logger, _name, event_dict):
    """structlog-процессор, заменяющий значения sensitive-ключей на маркер."""
    for key in list(event_dict.keys()):
        lk = key.lower()
        if lk in _SENSITIVE_KEYS:
            event_dict[key] = "***REDACTED***"
        elif lk in _EMAIL_KEYS:
            v = event_dict[key]
            if isinstance(v, str) and "@" in v:
                event_dict[key] = _mask_email(v)
    return event_dict


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact,  # ДО рендеринга, чтобы маска попадала в финальный JSON
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(__import__("logging"), settings.log_level)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
    )


logger = structlog.get_logger()
