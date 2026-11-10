from __future__ import annotations
import asyncio
import io
import logging
import discord
from discord import app_commands
from discord.ext import commands
from config import (WELCOME_CHANNEL_ID, WELCOME_ROLE_ID, ROLE_UNVERIFIED_ID, WELCOME_MESSAGE, SHOW_MEMBER_COUNT)
from services.permissions import is_admin
from services.welcome_card import generate_welcome_card
from services.logs import send_member_log

log = logging.getLogger("meersproject.welcome")

class WelcomeCog(commands.Cog):
    """Welcome new members, optionally assign a role and attach a generated card."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_welcome_channel(self, guild: discord.Guild):
        if not WELCOME_CHANNEL_ID:
            return None
        channel = guild.get_channel(WELCOME_CHANNEL_ID)
        if channel is None:
            try:
                channel = await guild.fetch_channel(WELCOME_CHANNEL_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
                log.warning("Не удалось получить welcome-канал %s: %s", WELCOME_CHANNEL_ID, exc)
                return None
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            return channel
        log.error("WELCOME_CHANNEL_ID указывает не на текстовый канал или ветку.")
        return None

    @staticmethod
    def _format_message(member: discord.Member) -> str:
        count = member.guild.member_count
        if count is None:
            count = len(member.guild.members)
        if not SHOW_MEMBER_COUNT:
            count = "скрыто"
        try:
            return WELCOME_MESSAGE.format(user=member.mention, count=count)
        except (KeyError, ValueError, IndexError) as exc:
            log.error("Ошибка форматирования WELCOME_MESSAGE: %s", exc)
            return f"Добро пожаловать на сервер, {member.mention}!"

    async def _assign_welcome_roles(self, member: discord.Member) -> None:
        """Assign the unverified role on join, plus the optional welcome role."""
        role_ids = []
        for role_id in (ROLE_UNVERIFIED_ID, WELCOME_ROLE_ID):
            if role_id and role_id not in role_ids:
                role_ids.append(role_id)

        if not role_ids:
            log.warning(
                "Не настроены ROLE_UNVERIFIED_ID и WELCOME_ROLE_ID; роли при входе не выдаются."
            )
            return

        me = member.guild.me
        if me is None or not me.guild_permissions.manage_roles:
            log.error("У бота нет Manage Roles; роли при входе не выданы.")
            return

        for role_id in role_ids:
            role = member.guild.get_role(role_id)
            if role is None:
                log.error("Роль ID=%s не найдена на сервере %s.", role_id, member.guild.id)
                continue
            if role >= me.top_role:
                log.error(
                    "Роль %s (ID=%s) находится выше или на уровне роли бота; пропускаю.",
                    role.name, role.id
                )
                continue
            if role in member.roles:
                continue
            try:
                await member.add_roles(
                    role,
                    reason="Автоматическая выдача роли при входе на сервер"
                )
                log.info("Выдана роль %s участнику %s.", role.id, member.id)
            except (discord.Forbidden, discord.HTTPException) as exc:
                log.warning(
                    "Не удалось выдать роль %s участнику %s: %s",
                    role.id, member.id, exc
                )

    async def _make_card(self, member: discord.Member) -> bytes | None:
        try:
            avatar_bytes = await member.display_avatar.with_size(256).read()
            count = member.guild.member_count
            if count is None:
                count = len(member.guild.members)
            return await asyncio.to_thread(generate_welcome_card, avatar_bytes, count)
        except (discord.HTTPException, OSError, ValueError) as exc:
            log.warning("Не удалось создать welcome-картинку для %s: %s", member.id, exc)
            return None
        except Exception:
            log.exception("Непредвиденная ошибка создания welcome-картинки для %s", member.id)
            return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Role assignment does not depend on the welcome channel or card generator.
        await self._assign_welcome_roles(member)
        channel = await self._get_welcome_channel(member.guild)
        if channel is None:
            log.warning("Приветственный канал не настроен или недоступен.")
            return

        content = self._format_message(member)
        card = await self._make_card(member)
        try:
            if card:
                await channel.send(
                    content=content,
                    file=discord.File(io.BytesIO(card), filename="welcome.png"),
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
            else:
                await channel.send(content=content, allowed_mentions=discord.AllowedMentions(users=True))
        except (discord.Forbidden, discord.HTTPException) as exc:
            log.error("Не удалось отправить приветствие в канал %s: %s", channel.id, exc)
            return

        embed = discord.Embed(
            title="Новый участник",
            description=f"{member.mention} (`{member.id}`) присоединился к серверу.",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        await send_member_log(self.bot, embed=embed)

    @app_commands.command(name="welcome_test", description="Отправить тестовое приветствие в настроенный канал")
    async def welcome_test(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("Недостаточно прав.", ephemeral=True)
        if interaction.guild is None:
            return await interaction.response.send_message("Команда доступна только на сервере.", ephemeral=True)
        channel = await self._get_welcome_channel(interaction.guild)
        if channel is None:
            return await interaction.response.send_message(
                "Приветственный канал не найден. Проверьте WELCOME_CHANNEL_ID в .env.",
                ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        member = interaction.user
        content = self._format_message(member) if isinstance(member, discord.Member) else "Тестовое приветствие."
        card = await self._make_card(member) if isinstance(member, discord.Member) else None
        try:
            if card:
                await channel.send(
                    content=content,
                    file=discord.File(io.BytesIO(card), filename="welcome-test.png"),
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
            else:
                await channel.send(content=content, allowed_mentions=discord.AllowedMentions(users=True))
            await interaction.followup.send(f"✅ Тестовое приветствие отправлено в {channel.mention}.", ephemeral=True)
        except (discord.Forbidden, discord.HTTPException) as exc:
            log.exception("Ошибка тестового приветствия: %s", exc)
            await interaction.followup.send(
                "❌ Не удалось отправить тест. Проверьте права View Channel, Send Messages и Attach Files.",
                ephemeral=True,
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
