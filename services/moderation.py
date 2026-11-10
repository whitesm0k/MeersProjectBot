from datetime import timedelta
import discord
from services.logs import send_mod_log

async def apply_timeout(member: discord.Member, seconds: int, reason: str, bot) -> bool:
    me = member.guild.me
    if me is None or not me.guild_permissions.moderate_members:
        return False
    if member.id == member.guild.owner_id or member.top_role >= me.top_role:
        return False
    try:
        await member.timeout(timedelta(seconds=seconds), reason=reason)
        embed = discord.Embed(title="Выдан тайм-аут", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Участник", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="Причина", value=reason[:1000], inline=False)
        embed.add_field(name="Длительность", value=f"{seconds} сек.", inline=True)
        await send_mod_log(bot, embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False
