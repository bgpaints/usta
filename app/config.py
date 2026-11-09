"""Настройки платформы. Всё берётся из переменных окружения (.env на сервере)."""
import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    # База: SQLite для разработки, PostgreSQL на сервере
    database_url: str = os.environ.get("DATABASE_URL", "sqlite:///./usta.db")
    # Секрет для подписи токенов. На сервере ОБЯЗАТЕЛЬНО свой длинный случайный.
    jwt_secret: str = os.environ.get("JWT_SECRET", "dev-only-change-me")
    master_token_days: int = _int("MASTER_TOKEN_DAYS", 30)
    staff_token_hours: int = _int("STAFF_TOKEN_HOURS", 12)
    # В режиме разработки SMS-код возвращается в ответе API, без отправки
    debug: bool = os.environ.get("DEBUG", "1") == "1"

    # SMS-коды
    otp_ttl_minutes: int = _int("OTP_TTL_MINUTES", 5)
    otp_max_per_hour: int = _int("OTP_MAX_PER_HOUR", 5)
    otp_max_attempts: int = _int("OTP_MAX_ATTEMPTS", 5)

    # Баллы
    welcome_bonus: int = _int("WELCOME_BONUS", 100)
    points_hold_days: int = _int("POINTS_HOLD_DAYS", 3)        # через сколько дней баллы можно выводить
    points_ttl_days: int = _int("POINTS_TTL_DAYS", 365)        # срок жизни баллов

    # Антифрод
    max_scans_per_day: int = _int("MAX_SCANS_PER_DAY", 30)
    burst_window_minutes: int = _int("BURST_WINDOW_MINUTES", 20)
    burst_max_scans: int = _int("BURST_MAX_SCANS", 15)         # больше — начисления замораживаются
    manual_fail_limit: int = _int("MANUAL_FAIL_LIMIT", 10)     # неверных вводов за 24 ч
    code_length: int = _int("CODE_LENGTH", 14)

    # Уровни: название -> сколько баллов заработано за 12 месяцев
    levels: tuple = field(default=(("Старт", 0), ("Бронза", 1000), ("Серебро", 5000), ("Золото", 15000)))


settings = Settings()
