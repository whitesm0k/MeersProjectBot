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
