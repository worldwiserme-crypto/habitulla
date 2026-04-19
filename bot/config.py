"""Centralized configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(key, default)
    if required and not value:
        raise RuntimeError(f"Missing required env variable: {key}")
    return value or ""


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _env_list_int(key: str, default: str = "") -> List[int]:
    raw = os.getenv(key, default)
    result = []
    for x in raw.split(","):
        x = x.strip()
        try:
            if x.lstrip("-").isdigit():
                result.append(int(x))
        except ValueError:
            continue
    return result


@dataclass(frozen=True)
class SubscriptionPlan:
    code: str
    name_uz: str
    duration_days: int
    price_uzs: int


@dataclass(frozen=True)
class Config:
    # Core
    bot_token: str = field(default_factory=lambda: _env("BOT_TOKEN", required=True))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY", required=True))
    supabase_url: str = field(default_factory=lambda: _env("SUPABASE_URL", required=True))
    supabase_key: str = field(default_factory=lambda: _env("SUPABASE_KEY", required=True))

    # Timezone & scheduling
    timezone: str = field(default_factory=lambda: _env("TIMEZONE", "Asia/Tashkent"))
    daily_reminder_hour: int = field(default_factory=lambda: _env_int("DAILY_REMINDER_HOUR", 21))
    daily_reminder_minute: int = field(default_factory=lambda: _env_int("DAILY_REMINDER_MINUTE", 0))
    weekly_report_weekday: int = field(default_factory=lambda: _env_int("WEEKLY_REPORT_WEEKDAY", 6))
    weekly_report_hour: int = field(default_factory=lambda: _env_int("WEEKLY_REPORT_HOUR", 20))
    monthly_report_day: int = field(default_factory=lambda: _env_int("MONTHLY_REPORT_DAY", 1))
    monthly_report_hour: int = field(default_factory=lambda: _env_int("MONTHLY_REPORT_HOUR", 9))

    # Admin
    admin_ids: List[int] = field(default_factory=lambda: _env_list_int("ADMIN_IDS"))
    admin_group_id: int = field(default_factory=lambda: _env_int("ADMIN_GROUP_ID", 0))

    # Subscription prices (UZS)
    price_1_month: int = field(default_factory=lambda: _env_int("PRICE_1_MONTH", 50000))
    price_3_months: int = field(default_factory=lambda: _env_int("PRICE_3_MONTHS", 135000))
    price_6_months: int = field(default_factory=lambda: _env_int("PRICE_6_MONTHS", 250000))

    # Payment details
    payment_card_number: str = field(default_factory=lambda: _env("PAYMENT_CARD_NUMBER", ""))
    payment_card_holder: str = field(default_factory=lambda: _env("PAYMENT_CARD_HOLDER", ""))
    payment_click_phone: str = field(default_factory=lambda: _env("PAYMENT_CLICK_PHONE", ""))
    payment_payme_phone: str = field(default_factory=lambda: _env("PAYMENT_PAYME_PHONE", ""))

    # Free tier limits
    free_daily_log_limit: int = field(default_factory=lambda: _env_int("FREE_DAILY_LOG_LIMIT", 10))
    free_report_max_days: int = field(default_factory=lambda: _env_int("FREE_REPORT_MAX_DAYS", 7))

    # Rate limit
    rate_limit_per_minute: int = field(default_factory=lambda: _env_int("RATE_LIMIT_MESSAGES_PER_MINUTE", 20))

    # Logging
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    # Webhook (optional)
    webhook_url: str = field(default_factory=lambda: _env("WEBHOOK_URL", ""))
    webhook_path: str = field(default_factory=lambda: _env("WEBHOOK_PATH", "/webhook"))
    webapp_host: str = field(default_factory=lambda: _env("WEBAPP_HOST", "0.0.0.0"))
    webapp_port: int = field(default_factory=lambda: _env_int("WEBAPP_PORT", 8080))

    @property
    def use_webhook(self) -> bool:
        return bool(self.webhook_url)

    @property
    def plans(self) -> Dict[str, SubscriptionPlan]:
        return {
            "1m": SubscriptionPlan("1m", "1 oylik", 30, self.price_1_month),
            "3m": SubscriptionPlan("3m", "3 oylik", 90, self.price_3_months),
            "6m": SubscriptionPlan("6m", "6 oylik", 180, self.price_6_months),
        }

    def get_plan(self, code: str) -> SubscriptionPlan | None:
        return self.plans.get(code)


config = Config()
