"""Bot entry point.

Usage:
  python -m bot.main

Supports both polling (default) and webhook mode.
"""
from __future__ import annotations

import asyncio
import signal
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import (
    SimpleRequestHandler,
    setup_application,
)
from aiohttp import web

from bot.config import config
from bot.handlers import (
    admin_approval,
    admin_panel,
    cabinet,
    messages,
    reports,
    settings,
    start,
    subscription,
)
from bot.middlewares.error import ErrorMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.middlewares.user_context import UserContextMiddleware
from bot.services.scheduler import setup_scheduler
from bot.utils.logger import logger


BOT_COMMANDS_USER = [
    BotCommand(command="start", description="🚀 Boshlash"),
    BotCommand(command="cabinet", description="👤 Mening kabinetim"),
    BotCommand(command="habits", description="🎯 Odatlar xulosasi"),
    BotCommand(command="budget", description="💰 Budjet xulosasi"),
    BotCommand(command="report", description="📊 Excel/PDF hisobot"),
    BotCommand(command="premium", description="💎 Premium obuna"),
    BotCommand(command="settings", description="⚙️ Sozlamalar"),
    BotCommand(command="help", description="❓ Yordam"),
]


def build_dispatcher() -> Dispatcher:
    """Construct dispatcher with all routers and middlewares."""
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares (order matters: error → throttling → user_context)
    dp.update.outer_middleware(ErrorMiddleware())
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
    dp.message.middleware(UserContextMiddleware())
    dp.callback_query.middleware(UserContextMiddleware())

    # Routers — order matters! Admin group handlers first (higher priority)
    dp.include_router(admin_approval.router)
    dp.include_router(admin_panel.router)
    dp.include_router(subscription.router)
    dp.include_router(start.router)
    dp.include_router(cabinet.router)
    dp.include_router(settings.router)
    dp.include_router(reports.router)
    dp.include_router(messages.router)  # Catch-all last

    return dp


async def on_startup(bot: Bot) -> None:
    logger.info("═══ Bot starting up ═══")
    logger.info("Admin IDs: %s", config.admin_ids)
    logger.info("Admin group: %s", config.admin_group_id)
    logger.info("Timezone: %s", config.timezone)

    # Set bot commands
    try:
        await bot.set_my_commands(BOT_COMMANDS_USER)
    except Exception as e:
        logger.warning("Failed to set commands: %s", e)

    # Notify admins
    me = await bot.get_me()
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f"🚀 <b>Bot ishga tushdi</b>\n\n"
                f"Bot: @{me.username}\n"
                f"Rejim: {'Webhook' if config.use_webhook else 'Polling'}",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def on_shutdown(bot: Bot) -> None:
    logger.info("═══ Bot shutting down ═══")
    try:
        await bot.session.close()
    except Exception:
        pass


async def run_polling() -> None:
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    # Scheduler
    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started with jobs: %s", [j.id for j in scheduler.get_jobs()])

    await on_startup(bot)
    try:
        # Drop pending updates on startup
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await on_shutdown(bot)


async def run_webhook() -> None:
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    scheduler = setup_scheduler(bot)
    scheduler.start()

    await on_startup(bot)

    webhook_url = f"{config.webhook_url.rstrip('/')}{config.webhook_path}"
    await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    logger.info("Webhook set: %s", webhook_url)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=config.webhook_path)
    setup_application(app, dp, bot=bot)

    async def shutdown_hook(_):
        scheduler.shutdown(wait=False)
        await on_shutdown(bot)

    app.on_shutdown.append(shutdown_hook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=config.webapp_host, port=config.webapp_port)
    await site.start()
    logger.info("Webhook server started on %s:%d", config.webapp_host, config.webapp_port)

    # Keep running
    stop_event = asyncio.Event()

    def _stop(*_):
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    await stop_event.wait()
    await runner.cleanup()


def main() -> None:
    try:
        if config.use_webhook:
            asyncio.run(run_webhook())
        else:
            asyncio.run(run_polling())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
