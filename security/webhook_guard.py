"""Cross-webhook flood protection. Detects bursts across different webhook IDs."""
import asyncio
import logging
import time
from collections import defaultdict, deque

import discord
from config import (WEBHOOK_WINDOW_SECONDS, WEBHOOK_MESSAGE_LIMIT,
                    WEBHOOK_DISTINCT_LIMIT, WEBHOOK_ALLOWED_IDS,
                    WEBHOOK_DELETE_MESSAGES, WEBHOOK_DELETE_ON_DETECTION)
from services.logs import send_security_alert

log = logging.getLogger('meersproject.security.webhooks')

class WebhookGuard:
    def __init__(self, bot):
        self.bot = bot
        self.events = defaultdict(deque)
        self.locks = defaultdict(asyncio.Lock)
        self.cooldowns = {}
        self.blocked = defaultdict(dict)

    async def check(self, message: discord.Message):
        if not message.guild or not message.webhook_id:
            return False
        guild = message.guild
        hook_id = message.webhook_id
        if hook_id in WEBHOOK_ALLOWED_IDS:
            return False
        key = guild.id
        async with self.locks[key]:
            now = time.monotonic()
            events = self.events[key]
            while events and now - events[0][0] > WEBHOOK_WINDOW_SECONDS:
                events.popleft()
            events.append((now, hook_id, message))
            distinct = {item[1] for item in events}
            detected = len(events) >= WEBHOOK_MESSAGE_LIMIT or len(distinct) >= WEBHOOK_DISTINCT_LIMIT
            if not detected:
                return False
            # Keep the blocked IDs for the current window; also stop repeated alerts/deletions.
            blocked = self.blocked[key]
            for hid in distinct:
                blocked[hid] = now + WEBHOOK_WINDOW_SECONDS
            recent = list(events)
            events.clear()
            should_alert = now - self.cooldowns.get(key, -1e12) >= WEBHOOK_WINDOW_SECONDS
            if should_alert:
                self.cooldowns[key] = now
        if WEBHOOK_DELETE_MESSAGES:
            await self._delete_messages(recent)
        if WEBHOOK_DELETE_ON_DETECTION:
            await self._delete_webhooks(guild, distinct)
        if should_alert:
            embed = discord.Embed(title='Webhook Anti-Raid: обнаружен спам',
                description=(f'Сервер: **{discord.utils.escape_markdown(guild.name)}**\n'
                             f'Канал последнего сообщения: {message.channel.mention}\n'
                             f'Сообщений за {WEBHOOK_WINDOW_SECONDS} сек.: **{len(recent)}**\n'
                             f'Разных вебхуков: **{len(distinct)}**\n'
                             f'ID: {", ".join(map(str, sorted(distinct)))}\n'
                             f'Действие: удаление сообщений и вебхуков (при наличии прав).'),
                color=discord.Color.red(), timestamp=discord.utils.utcnow())
            await send_security_alert(self.bot, guild, embed=embed)
        return True

    async def _delete_messages(self, events):
        for _, _, msg in events:
            try:
                await msg.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
                log.warning('Не удалось удалить сообщение вебхука %s: %s', msg.id, exc)

    async def _delete_webhooks(self, guild, ids):
        # Fetch guild hooks, not only the current channel, to catch alternating hooks.
        try:
            hooks = await guild.webhooks()
        except (discord.Forbidden, discord.HTTPException) as exc:
            log.warning('Нельзя получить вебхуки сервера %s (нужно Manage Webhooks): %s', guild.id, exc)
            return
        for hook in hooks:
            if hook.id not in ids or hook.id in WEBHOOK_ALLOWED_IDS:
                continue
            try:
                await hook.delete(reason='MeersProject Webhook Anti-Raid: cross-webhook message flood')
                log.warning('Удалён вебхук %s на сервере %s', hook.id, guild.id)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
                log.warning('Не удалось удалить вебхук %s: %s', hook.id, exc)
