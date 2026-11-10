import discord
from discord.ext import commands
from services.logs import send_raid_log, send_mod_log
from services.permissions import is_admin

class SecurityEvents(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel):
        # AuditGuard is called by the main bot event; this listener intentionally does not poll the API.
        return

async def setup(bot): await bot.add_cog(SecurityEvents(bot))
