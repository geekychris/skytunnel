"""Telegram bot for remote tunnel management and alerts."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

if TYPE_CHECKING:
    from tunnelctl.agent.manager import TunnelManager
    from tunnelctl.config import TelegramConfig
    from tunnelctl.state import StateStore

logger = logging.getLogger(__name__)


def create_alert_callback(telegram_config: TelegramConfig):
    """Create an async callback that sends Telegram alerts on tunnel state changes."""
    from telegram import Bot

    bot = Bot(token=telegram_config.bot_token)
    chat_id = telegram_config.chat_id

    async def alert_callback(tunnel_key: str, old_status: str, new_status: str) -> None:
        if new_status == "disconnected" and not telegram_config.alert_on_disconnect:
            return
        if new_status == "connected" and not telegram_config.alert_on_reconnect:
            return

        icon = {"connected": "\u2705", "disconnected": "\u274c", "error": "\u26a0\ufe0f"}.get(
            new_status, "\u2139\ufe0f"
        )
        message = f"{icon} *Tunnel {tunnel_key}*\n{old_status} \u2192 {new_status}"
        try:
            await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
        except Exception:
            logger.exception("Failed to send Telegram alert")

    return alert_callback


async def start_bot(
    telegram_config: TelegramConfig,
    state: StateStore,
    manager: TunnelManager,
) -> None:
    """Start the Telegram bot polling loop."""
    application = Application.builder().token(telegram_config.bot_token).build()
    chat_id = telegram_config.chat_id

    def _authorized(update: Update) -> bool:
        return str(update.effective_chat.id) == str(chat_id)

    async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _authorized(update):
            return
        statuses = await state.get_all_statuses()
        if not statuses:
            await update.message.reply_text("No tunnels configured.")
            return

        lines = ["*Tunnel Status*\n"]
        icons = {"connected": "\u2705", "disconnected": "\u274c", "connecting": "\u23f3", "error": "\u26a0\ufe0f"}
        for s in statuses:
            icon = icons.get(s.status, "\u2753")
            lines.append(f"{icon} `{s.tunnel}@{s.endpoint}` - {s.status}")
            if s.error:
                lines.append(f"   _{s.error}_")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def cmd_tunnels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _authorized(update):
            return
        tunnels = manager.config.tunnels
        if not tunnels:
            await update.message.reply_text("No tunnels configured.")
            return

        lines = ["*Configured Tunnels*\n"]
        for t in tunnels:
            eps = ", ".join(t.endpoints) if t.endpoints else "all"
            lines.append(
                f"\u2022 `{t.name}` {t.internal_host}:{t.internal_port} "
                f"\u2192 :{t.remote_port} ({t.protocol}) [{eps}]"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _authorized(update):
            return
        logs = await state.get_logs(limit=10)
        if not logs:
            await update.message.reply_text("No logs yet.")
            return

        lines = ["*Recent Logs*\n"]
        for log in reversed(logs):
            dt = datetime.datetime.fromtimestamp(log.timestamp)
            tunnel_tag = f" [{log.tunnel}]" if log.tunnel else ""
            lines.append(f"`{dt.strftime('%H:%M:%S')}` {log.level}{tunnel_tag}: {log.message}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _authorized(update):
            return
        args = context.args
        if not args or len(args) < 4:
            await update.message.reply_text(
                "Usage: /add <name> <internal_host> <internal_port> <remote_port> [protocol]"
            )
            return

        from tunnelctl.config import TunnelConfig

        name, host, int_port, rem_port = args[0], args[1], int(args[2]), int(args[3])
        protocol = args[4] if len(args) > 4 else "tcp"

        tc = TunnelConfig(
            name=name,
            internal_host=host,
            internal_port=int_port,
            remote_port=rem_port,
            protocol=protocol,
        )
        manager.config.tunnels.append(tc)
        started = await manager.add_tunnel(name)
        await update.message.reply_text(
            f"\u2705 Added tunnel `{name}`, started {len(started)} connection(s)",
            parse_mode="Markdown",
        )

    async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _authorized(update):
            return
        if not context.args:
            await update.message.reply_text("Usage: /remove <tunnel_name>")
            return

        name = context.args[0]
        tunnel = next((t for t in manager.config.tunnels if t.name == name), None)
        if not tunnel:
            await update.message.reply_text(f"\u274c Tunnel `{name}` not found", parse_mode="Markdown")
            return

        removed = await manager.remove_tunnel(name)
        manager.config.tunnels.remove(tunnel)
        await update.message.reply_text(
            f"\u2705 Removed tunnel `{name}`, stopped {len(removed)} connection(s)",
            parse_mode="Markdown",
        )

    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("tunnels", cmd_tunnels))
    application.add_handler(CommandHandler("logs", cmd_logs))
    application.add_handler(CommandHandler("add", cmd_add))
    application.add_handler(CommandHandler("remove", cmd_remove))

    logger.info("Starting Telegram bot...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # Keep running until cancelled
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
