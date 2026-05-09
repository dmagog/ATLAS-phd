import uuid
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError
from atlas.core.config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 hours

# Pre-computed Argon2-хеш заведомо невалидного пароля. Используется для
# constant-time-проверки в /auth/login, когда пользователь не найден или
# soft-deleted: мы всё равно вызываем verify против этого хеша, чтобы
# время ответа не выдавало факт существования аккаунта (user enumeration
# через тайминги). Хеш вычисляется лениво при первом обращении.
_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = pwd_context.hash("__atlas_dummy_password_for_timing_defense__")
    return _DUMMY_HASH


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def burn_dummy_verify(plain: str) -> None:
    """Вызвать verify против dummy-хеша, чтобы потратить столько же
    CPU-времени, как при реальном verify. Результат игнорируем."""
    try:
        pwd_context.verify(plain, _dummy_hash())
    except Exception:
        # Любая ошибка — не наша проблема, мы лишь жгём такты.
        pass


def create_access_token(user_id: str, role: str, jwt_version: int = 1) -> str:
    """Issue an access token. The `jv` claim binds it to a user.jwt_version
    snapshot — when the user's stored jwt_version is bumped (M4.C role
    revocation, BDD 7.5), tokens with stale `jv` become invalid on the
    next request.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "jv": jwt_version,
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise ValueError("Invalid token")
