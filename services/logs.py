import logging
from config import OWNER_USER_IDS
import discord
from config import LOG_MODERATION_CHANNEL_ID, LOG_RAID_CHANNEL_ID, LOG_MEMBER_CHANNEL_ID

async def _send(bot, channel_id: int, *, embed=None, content=None):
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
    try:
        await channel.send(content=content, embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass

async def send_mod_log(bot, embed=None, text=None):
    await _send(bot, LOG_MODERATION_CHANNEL_ID, embed=embed, content=text)

async def send_raid_log(bot, embed=None, text=None):
    await _send(bot, LOG_RAID_CHANNEL_ID, embed=embed, content=text)

async def send_member_log(bot, embed=None, text=None):
    await _send(bot, LOG_MEMBER_CHANNEL_ID, embed=embed, content=text)


async def notify_owners(bot, guild, *, embed=None, text=None):
    """DM actual guild owner plus explicitly configured co-owners; failures are logged."""
    if guild is None:
        return
    recipients = set(OWNER_USER_IDS)
    recipients.add(guild.owner_id)
    for user_id in recipients:
        if not user_id:
            continue
        try:
            user = bot.get_user(user_id) or await bot.fetch_user(user_id)
            await user.send(content=text, embed=embed)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
            logging.getLogger("meersproject.security").warning(
                "Не удалось отправить ЛС владельцу %s (сервер %s): %s", user_id, guild.id, exc
            )


async def send_security_alert(bot, guild, *, embed=None, text=None):
    await send_raid_log(bot, embed=embed, text=text)
    await notify_owners(bot, guild, embed=embed, text=text)
