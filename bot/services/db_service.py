"""Async Supabase wrapper.

Supabase Python client is sync — we run blocking calls in a thread
executor to avoid blocking aiogram's event loop.
"""
from __future__ import annotations

import asyncio
import traceback
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from bot.config import config
from bot.services.cache_service import (
    subscription_cache,
    usage_cache,
    user_cache,
)
from bot.utils.formatters import today_local
from bot.utils.logger import logger


class DatabaseError(Exception):
    pass


class DBService:
    def __init__(self) -> None:
        self._client: Client = create_client(config.supabase_url, config.supabase_key)

    async def _run(self, fn, *args, **kwargs):
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))
        except Exception as e:
            logger.error("DB error: %s\n%s", e, traceback.format_exc())
            raise DatabaseError(str(e)) from e

    # ═══════════════════ USERS ═══════════════════
    async def get_or_create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        cache_key = f"user:{user_id}"
        cached = user_cache.get(cache_key)
        if cached:
            return cached

        def _get():
            return (
                self._client.table("users").select("*").eq("id", user_id).limit(1).execute()
            )

        res = await self._run(_get)
        if res.data:
            # Update last_active
            await self._touch_user(user_id)
            user_cache.set(cache_key, res.data[0])
            return res.data[0]

        def _insert():
            return self._client.table("users").insert({
                "id": user_id,
                "username": (username or "")[:100],
                "full_name": (full_name or "")[:200],
            }).execute()

        res = await self._run(_insert)
        user_data = res.data[0] if res.data else {"id": user_id, "currency": "UZS"}
        user_cache.set(cache_key, user_data)
        await self._create_default_subscription(user_id)
        return user_data

    async def _touch_user(self, user_id: int) -> None:
        def _update():
            return self._client.table("users").update({
                "last_active_at": datetime.utcnow().isoformat()
            }).eq("id", user_id).execute()
        try:
            await self._run(_update)
        except DatabaseError:
            pass

    async def update_user(self, user_id: int, fields: Dict[str, Any]) -> None:
        def _update():
            return self._client.table("users").update(fields).eq("id", user_id).execute()
        await self._run(_update)
        user_cache.delete(f"user:{user_id}")

    async def delete_user_data(self, user_id: int) -> None:
        """CASCADE handles children."""
        def _delete():
            return self._client.table("users").delete().eq("id", user_id).execute()
        await self._run(_delete)
        user_cache.delete(f"user:{user_id}")
        subscription_cache.delete(f"sub:{user_id}")
        usage_cache.delete(f"usage:{user_id}:{today_local().isoformat()}")

    async def ban_user(self, user_id: int, banned: bool = True) -> None:
        await self.update_user(user_id, {"is_banned": banned})

    async def is_banned(self, user_id: int) -> bool:
        user = await self.get_or_create_user(user_id)
        return bool(user.get("is_banned"))

    # ═══════════════════ HABITS ═══════════════════
    async def add_habit_log(
        self,
        user_id: int,
        habit_name: str,
        duration: Optional[float],
        unit: Optional[str],
        logged_date: date,
        raw_text: str,
    ) -> None:
        def _insert():
            return self._client.table("habit_logs").insert({
                "user_id": user_id,
                "habit_name": habit_name[:200],
                "duration": duration,
                "unit": (unit or "")[:20] or None,
                "logged_date": logged_date.isoformat(),
                "raw_text": raw_text[:1000] if raw_text else None,
            }).execute()
        await self._run(_insert)
        await self._bump_usage(user_id)

    async def get_habits_in_range(
        self, user_id: int, start: date, end: date
    ) -> List[Dict[str, Any]]:
        def _get():
            return (
                self._client.table("habit_logs")
                .select("*")
                .eq("user_id", user_id)
                .gte("logged_date", start.isoformat())
                .lte("logged_date", end.isoformat())
                .order("logged_date", desc=False)
                .execute()
            )
        res = await self._run(_get)
        return res.data or []

    async def get_habit_stats(self, user_id: int) -> Dict[str, int]:
        today = today_local()
        week_start = today - timedelta(days=6)
        month_start = today - timedelta(days=29)

        def _get(start):
            return (
                self._client.table("habit_logs")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .gte("logged_date", start.isoformat())
                .execute()
            )

        today_res, week_res, month_res = await asyncio.gather(
            self._run(_get, today),
            self._run(_get, week_start),
            self._run(_get, month_start),
        )
        return {
            "today": today_res.count or 0,
            "week": week_res.count or 0,
            "month": month_res.count or 0,
        }

    # ═══════════════════ BUDGET ═══════════════════
    async def add_budget_log(
        self,
        user_id: int,
        type_: str,
        category: Optional[str],
        amount: float,
        currency: str,
        note: Optional[str],
        logged_date: date,
        raw_text: str,
    ) -> None:
        def _insert():
            return self._client.table("budget_logs").insert({
                "user_id": user_id,
                "type": type_,
                "category": (category or "boshqa")[:100],
                "amount": amount,
                "currency": currency[:3],
                "note": note[:500] if note else None,
                "logged_date": logged_date.isoformat(),
                "raw_text": raw_text[:1000] if raw_text else None,
            }).execute()
        await self._run(_insert)
        await self._bump_usage(user_id)

    async def get_budget_in_range(
        self, user_id: int, start: date, end: date
    ) -> List[Dict[str, Any]]:
        def _get():
            return (
                self._client.table("budget_logs")
                .select("*")
                .eq("user_id", user_id)
                .gte("logged_date", start.isoformat())
                .lte("logged_date", end.isoformat())
                .order("logged_date", desc=False)
                .execute()
            )
        res = await self._run(_get)
        return res.data or []

    async def get_budget_stats(self, user_id: int) -> Dict[str, float]:
        today = today_local()
        month_start = today.replace(day=1)

        def _get(start, type_):
            return (
                self._client.table("budget_logs")
                .select("amount")
                .eq("user_id", user_id)
                .eq("type", type_)
                .gte("logged_date", start.isoformat())
                .execute()
            )

        today_exp, today_inc, month_exp, month_inc = await asyncio.gather(
            self._run(_get, today, "expense"),
            self._run(_get, today, "income"),
            self._run(_get, month_start, "expense"),
            self._run(_get, month_start, "income"),
        )
        return {
            "today_expense": sum(float(r["amount"]) for r in (today_exp.data or [])),
            "today_income": sum(float(r["amount"]) for r in (today_inc.data or [])),
            "month_expense": sum(float(r["amount"]) for r in (month_exp.data or [])),
            "month_income": sum(float(r["amount"]) for r in (month_inc.data or [])),
        }

    # ═══════════════════ SUBSCRIPTIONS ═══════════════════
    async def _create_default_subscription(self, user_id: int) -> None:
        def _insert():
            return self._client.table("subscriptions").insert({
                "user_id": user_id,
                "tier": "free",
            }).execute()
        try:
            await self._run(_insert)
        except DatabaseError:
            pass

    async def get_subscription(self, user_id: int) -> Dict[str, Any]:
        cache_key = f"sub:{user_id}"
        cached = subscription_cache.get(cache_key)
        if cached:
            return cached

        def _get():
            return (
                self._client.table("subscriptions")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

        res = await self._run(_get)
        sub = res.data[0] if res.data else {"tier": "free", "expires_at": None}
        subscription_cache.set(cache_key, sub)
        return sub

    async def activate_premium(
        self,
        user_id: int,
        plan_code: str,
        duration_days: int,
        price_uzs: int,
        payment_request_id: int,
        approved_by: int,
    ) -> datetime:
        """Activate or extend premium subscription."""
        sub = await self.get_subscription(user_id)
        base = datetime.utcnow()

        # Stack extensions if already premium
        if sub.get("tier") == "premium" and sub.get("expires_at"):
            try:
                exp = datetime.fromisoformat(str(sub["expires_at"]).replace("Z", "+00:00"))
                exp = exp.replace(tzinfo=None)
                if exp > base:
                    base = exp
            except (ValueError, AttributeError):
                pass

        new_expiry = base + timedelta(days=duration_days)

        def _insert():
            return self._client.table("subscriptions").insert({
                "user_id": user_id,
                "tier": "premium",
                "plan_code": plan_code,
                "started_at": datetime.utcnow().isoformat(),
                "expires_at": new_expiry.isoformat(),
                "price_uzs": price_uzs,
                "payment_request_id": payment_request_id,
                "approved_by": approved_by,
            }).execute()

        await self._run(_insert)
        subscription_cache.delete(f"sub:{user_id}")
        return new_expiry

    # ═══════════════════ PAYMENT REQUESTS ═══════════════════
    async def create_payment_request(
        self,
        user_id: int,
        plan_code: str,
        expected_amount: int,
        receipt_file_id: str,
        receipt_file_type: str,
    ) -> int:
        def _insert():
            return self._client.table("payment_requests").insert({
                "user_id": user_id,
                "plan_code": plan_code,
                "expected_amount": expected_amount,
                "receipt_file_id": receipt_file_id[:300],
                "receipt_file_type": receipt_file_type,
                "status": "pending",
            }).execute()

        res = await self._run(_insert)
        if not res.data:
            raise DatabaseError("Failed to create payment request")
        return int(res.data[0]["id"])

    async def update_payment_admin_message(
        self, request_id: int, admin_chat_id: int, admin_message_id: int
    ) -> None:
        def _update():
            return self._client.table("payment_requests").update({
                "admin_chat_id": admin_chat_id,
                "admin_message_id": admin_message_id,
            }).eq("id", request_id).execute()
        await self._run(_update)

    async def get_payment_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        def _get():
            return (
                self._client.table("payment_requests")
                .select("*")
                .eq("id", request_id)
                .limit(1)
                .execute()
            )
        res = await self._run(_get)
        return res.data[0] if res.data else None

    async def mark_payment_approved(
        self, request_id: int, admin_id: int
    ) -> None:
        def _update():
            return self._client.table("payment_requests").update({
                "status": "approved",
                "approved_by": admin_id,
                "resolved_at": datetime.utcnow().isoformat(),
            }).eq("id", request_id).execute()
        await self._run(_update)

    async def mark_payment_rejected(
        self, request_id: int, admin_id: int, reason: str
    ) -> None:
        def _update():
            return self._client.table("payment_requests").update({
                "status": "rejected",
                "approved_by": admin_id,
                "rejection_reason": reason[:500],
                "resolved_at": datetime.utcnow().isoformat(),
            }).eq("id", request_id).execute()
        await self._run(_update)

    async def get_pending_payment_requests(self, limit: int = 50) -> List[Dict[str, Any]]:
        def _get():
            return (
                self._client.table("payment_requests")
                .select("*, users(full_name, username)")
                .eq("status", "pending")
                .order("submitted_at", desc=True)
                .limit(limit)
                .execute()
            )
        res = await self._run(_get)
        return res.data or []

    async def count_pending_requests(self) -> int:
        def _get():
            return (
                self._client.table("payment_requests")
                .select("id", count="exact")
                .eq("status", "pending")
                .execute()
            )
        try:
            res = await self._run(_get)
            return res.count or 0
        except DatabaseError:
            return 0

    async def user_has_pending_request(self, user_id: int) -> bool:
        def _get():
            return (
                self._client.table("payment_requests")
                .select("id")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .limit(1)
                .execute()
            )
        try:
            res = await self._run(_get)
            return bool(res.data)
        except DatabaseError:
            return False

    # ═══════════════════ USAGE / RATE LIMITING ═══════════════════
    async def _bump_usage(self, user_id: int, field: str = "log_count") -> None:
        today_str = today_local().isoformat()
        cache_key = f"usage:{user_id}:{today_str}"

        def _upsert():
            existing = (
                self._client.table("daily_usage")
                .select(field)
                .eq("user_id", user_id)
                .eq("usage_date", today_str)
                .execute()
            )
            if existing.data:
                new_val = (existing.data[0].get(field) or 0) + 1
                return (
                    self._client.table("daily_usage")
                    .update({field: new_val})
                    .eq("user_id", user_id)
                    .eq("usage_date", today_str)
                    .execute()
                )
            return self._client.table("daily_usage").insert({
                "user_id": user_id,
                "usage_date": today_str,
                field: 1,
            }).execute()

        try:
            await self._run(_upsert)
        except DatabaseError:
            pass
        usage_cache.delete(cache_key)

    async def get_today_usage(self, user_id: int) -> int:
        today_str = today_local().isoformat()
        cache_key = f"usage:{user_id}:{today_str}"
        cached = usage_cache.get(cache_key)
        if cached is not None:
            return cached

        def _get():
            return (
                self._client.table("daily_usage")
                .select("log_count")
                .eq("user_id", user_id)
                .eq("usage_date", today_str)
                .limit(1)
                .execute()
            )

        try:
            res = await self._run(_get)
            count = res.data[0]["log_count"] if res.data else 0
        except DatabaseError:
            count = 0
        usage_cache.set(cache_key, count)
        return count

    # ═══════════════════ ADMIN / METRICS ═══════════════════
    async def log_metric(
        self, metric_type: str, user_id: Optional[int] = None, metadata: Optional[Dict] = None
    ) -> None:
        def _insert():
            return self._client.table("bot_metrics").insert({
                "metric_type": metric_type,
                "user_id": user_id,
                "metadata": metadata or {},
            }).execute()
        try:
            await self._run(_insert)
        except DatabaseError:
            pass

    async def get_users_with_reminders(self) -> List[Dict[str, Any]]:
        def _get():
            return (
                self._client.table("users")
                .select("id, currency, timezone, reminders_on, is_banned")
                .eq("reminders_on", True)
                .eq("is_banned", False)
                .execute()
            )
        res = await self._run(_get)
        return res.data or []

    async def get_all_active_user_ids(self) -> List[int]:
        def _get():
            return (
                self._client.table("users")
                .select("id")
                .eq("is_banned", False)
                .execute()
            )
        res = await self._run(_get)
        return [u["id"] for u in (res.data or [])]

    async def admin_stats(self) -> Dict[str, Any]:
        today = today_local()
        week_ago = today - timedelta(days=6)
        month_ago = today - timedelta(days=29)
        yesterday = today - timedelta(days=1)

        def _count(table: str, filters: list[tuple[str, str, Any]] | None = None):
            q = self._client.table(table).select("id", count="exact")
            for col, op, val in (filters or []):
                if op == "eq":
                    q = q.eq(col, val)
                elif op == "gte":
                    q = q.gte(col, val)
                elif op == "lte":
                    q = q.lte(col, val)
            return q.execute()

        def _sum_subs():
            return (
                self._client.table("subscriptions")
                .select("price_uzs")
                .eq("tier", "premium")
                .execute()
            )

        def _sum_subs_range(start):
            return (
                self._client.table("subscriptions")
                .select("price_uzs")
                .eq("tier", "premium")
                .gte("created_at", start.isoformat())
                .execute()
            )

        total_users, users_today, users_week, habits_today, budget_today, pending, subs_all, subs_month = await asyncio.gather(
            self._run(_count, "users"),
            self._run(_count, "users", [("last_active_at", "gte", today.isoformat())]),
            self._run(_count, "users", [("last_active_at", "gte", week_ago.isoformat())]),
            self._run(_count, "habit_logs", [("logged_date", "eq", today.isoformat())]),
            self._run(_count, "budget_logs", [("logged_date", "eq", today.isoformat())]),
            self._run(_count, "payment_requests", [("status", "eq", "pending")]),
            self._run(_sum_subs),
            self._run(_sum_subs_range, month_ago),
        )

        # Premium active count
        def _premium_active():
            return (
                self._client.table("subscriptions")
                .select("user_id")
                .eq("tier", "premium")
                .gt("expires_at", datetime.utcnow().isoformat())
                .execute()
            )
        premium_res = await self._run(_premium_active)
        premium_user_ids = {s["user_id"] for s in (premium_res.data or [])}

        total_revenue = sum(
            int(s["price_uzs"] or 0) for s in (subs_all.data or [])
        )
        month_revenue = sum(
            int(s["price_uzs"] or 0) for s in (subs_month.data or [])
        )

        return {
            "total_users": total_users.count or 0,
            "dau": users_today.count or 0,
            "wau": users_week.count or 0,
            "premium_active": len(premium_user_ids),
            "habits_today": habits_today.count or 0,
            "budget_today": budget_today.count or 0,
            "pending_requests": pending.count or 0,
            "total_revenue_uzs": total_revenue,
            "month_revenue_uzs": month_revenue,
        }

    async def log_broadcast(
        self, admin_id: int, text: str, sent: int, failed: int
    ) -> None:
        def _insert():
            return self._client.table("broadcasts").insert({
                "admin_id": admin_id,
                "text": text[:2000],
                "sent_count": sent,
                "failed_count": failed,
            }).execute()
        try:
            await self._run(_insert)
        except DatabaseError:
            pass

    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """For admin user lookup."""
        def _get():
            return (
                self._client.table("users")
                .select("*")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
        res = await self._run(_get)
        return res.data[0] if res.data else None


db = DBService()
