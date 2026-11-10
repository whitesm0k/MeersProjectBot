import time
from collections import defaultdict, deque
import discord
from config import (
    RAID_JOIN_FLOOD_WINDOW_SECONDS, RAID_JOIN_FLOOD_LIMIT,
    RAID_MAX_CHANNELS_PER_USER, RAID_MAX_ROLES_PER_USER,
    AUTO_REVERT_RAID_ACTIONS
)
from services.permissions import is_admin
from services.logs import send_raid_log
from services.moderation import apply_timeout

class AuditGuard:
    """Audit-log based anti-raid detection. Automatic reversals are opt-in."""
    def __init__(self, bot):
        self.bot = bot
        self.joins = defaultdict(deque)
        self.channel_creations = defaultdict(deque)
        self.role_creations = defaultdict(deque)
        self.webhook_alerts = set()

    def _push(self, store, key, limit, window):
        now = time.monotonic()
        q = store[key]
        while q and q[0] < now - window:
            q.popleft()
        q.append(now)
        return len(q), len(q) > limit

    async def _audit_actor(self, guild, action, target_id):
        me = guild.me
        if me is None or not me.guild_permissions.view_audit_log:
            return None
        try:
            async for entry in guild.audit_logs(limit=8, action=action):
                if getattr(entry.target, "id", None) == target_id:
                    age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                    if age <= 20:
                        return entry.user
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    async def record_join(self, member):
        count, detected = self._push(
            self.joins, member.guild.id, RAID_JOIN_FLOOD_LIMIT, RAID_JOIN_FLOOD_WINDOW_SECONDS
        )
        if detected:
            embed = discord.Embed(
                title="Возможный рейд: массовый вход",
                description=f"За {RAID_JOIN_FLOOD_WINDOW_SECONDS} сек. вошло {count} участников.\nПоследний вход: {member.mention}",
                color=discord.Color.red(), timestamp=discord.utils.utcnow()
            )
            await send_raid_log(self.bot, embed=embed)
            # Intentionally no automatic ban: a join burst alone is not proof of malicious intent.

    async def record_channel_create(self, channel):
        actor = await self._audit_actor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        if actor is None or actor.bot or is_admin(channel.guild.get_member(actor.id) or actor):
            return
        count, detected = self._push(
            self.channel_creations, (channel.guild.id, actor.id),
            RAID_MAX_CHANNELS_PER_USER, RAID_JOIN_FLOOD_WINDOW_SECONDS
        )
        if detected:
            await send_raid_log(self.bot, text=f"⚠️ Возможный рейд: {actor.mention} создал(а) {count} каналов за {RAID_JOIN_FLOOD_WINDOW_SECONDS} сек.")
            if AUTO_REVERT_RAID_ACTIONS:
                try:
                    await channel.delete(reason="Anti-raid: channel creation threshold exceeded")
                    member = channel.guild.get_member(actor.id)
                    if member:
                        await apply_timeout(member, 600, "Anti-raid: массовое создание каналов", self.bot)
                except (discord.Forbidden, discord.HTTPException):
                    pass

    async def record_role_create(self, role):
        actor = await self._audit_actor(role.guild, discord.AuditLogAction.role_create, role.id)
        if actor is None or actor.bot or is_admin(role.guild.get_member(actor.id) or actor):
            return
        count, detected = self._push(
            self.role_creations, (role.guild.id, actor.id),
            RAID_MAX_ROLES_PER_USER, RAID_JOIN_FLOOD_WINDOW_SECONDS
        )
        if detected:
            await send_raid_log(self.bot, text=f"⚠️ Возможный рейд: {actor.mention} создал(а) {count} ролей за {RAID_JOIN_FLOOD_WINDOW_SECONDS} сек.")
            if AUTO_REVERT_RAID_ACTIONS:
                try:
                    await role.delete(reason="Anti-raid: role creation threshold exceeded")
                    member = role.guild.get_member(actor.id)
                    if member:
                        await apply_timeout(member, 600, "Anti-raid: массовое создание ролей", self.bot)
                except (discord.Forbidden, discord.HTTPException):
                    pass

    async def inspect_webhooks(self, channel):
        guild = channel.guild
        me = guild.me
        if me is None or not me.guild_permissions.view_audit_log:
            return
        actor = None
        try:
            async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.webhook_create):
                age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                target = entry.target
                target_channel_id = getattr(target, "channel_id", None)
                extra_channel = getattr(getattr(entry, "extra", None), "channel", None)
                if target_channel_id is None and extra_channel is not None:
                    target_channel_id = getattr(extra_channel, "id", None)
                if target_channel_id == channel.id and age <= 20:
                    actor = entry.user
                    break
        except (discord.Forbidden, discord.HTTPException):
            return

        if actor is None or actor.bot or actor.id == self.bot.user.id:
            return
        member = guild.get_member(actor.id)
        if member and is_admin(member):
            return
        key = (guild.id, channel.id, actor.id)
        if key in self.webhook_alerts:
            return
        self.webhook_alerts.add(key)
        await send_raid_log(
            self.bot,
            text=f"⚠️ Создание вебхука: {actor.mention} в канале {channel.mention}. Проверьте аудит сервера."
        )
        # Do not auto-ban or delete a webhook solely from an event notification.
