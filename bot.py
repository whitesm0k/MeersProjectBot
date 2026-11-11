import logging
import discord
from discord.ext import commands
from config import TOKEN, ROLE_UNVERIFIED_ID, ROLE_VERIFIED_ID
from cogs.tickets import TicketPanelView, TicketControls, PartnershipPanelView, SubscriptionView
from cogs.reviews import ReviewPanel
from cogs.vacancies import VacancyPanelView
from cogs.reports import ReportPanelView, ReportVerifyView
from cogs.verification import VerificationPanelView
from security.antispam import SpamGuard
from security.audit_guard import AuditGuard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()]
)
log = logging.getLogger("meersproject")

class MeersBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.message_content = True
        intents.moderation = True
        intents.webhooks = True
        super().__init__(command_prefix="!", intents=intents)
        self.spam_guard = SpamGuard()
        self.audit_guard = AuditGuard(self)

    async def setup_hook(self):
        for extension in (
            "cogs.tickets",
            "cogs.vacancies",
            "cogs.reports",
            "cogs.verification",
            "cogs.security_events",
            "cogs.welcome",
            "cogs.reviews",
        ):
            await self.load_extension(extension)

        # Persistent views: their buttons remain active after restart.
        self.add_view(TicketPanelView())
        self.add_view(TicketControls())
        self.add_view(VacancyPanelView())
        self.add_view(ReportPanelView())
        self.add_view(ReportVerifyView())
        self.add_view(PartnershipPanelView())
        self.add_view(SubscriptionView())
        self.add_view(ReviewPanel())
        if ROLE_UNVERIFIED_ID and ROLE_VERIFIED_ID:
            self.add_view(VerificationPanelView())

        synced = await self.tree.sync()
        log.info("Синхронизировано slash-команд: %s", len(synced))

bot = MeersBot()

@bot.event
async def on_ready():
    log.info("Бот онлайн: %s (%s)", bot.user, bot.user.id if bot.user else "?")

@bot.event
async def on_message(message: discord.Message):
    if message.guild and not message.author.bot and not message.webhook_id:
        member = message.author
        if isinstance(member, discord.Member) and not bot.spam_guard.is_exempt(member):
            detected, reason = bot.spam_guard.check(message)
            if detected:
                await bot.spam_guard.handle(message, reason, bot)
                return
    await bot.process_commands(message)

@bot.event
async def on_member_join(member: discord.Member):
    await bot.audit_guard.record_join(member)

@bot.event
async def on_member_remove(member: discord.Member):
    from services.logs import send_mod_log
    embed = discord.Embed(
        title="Участник покинул сервер",
        description=f"{member.mention} (`{member.id}`)",
        color=discord.Color.dark_grey(),
        timestamp=discord.utils.utcnow()
    )
    await send_mod_log(bot, embed=embed)

@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    await bot.audit_guard.record_channel_create(channel)

@bot.event
async def on_guild_role_create(role: discord.Role):
    await bot.audit_guard.record_role_create(role)

@bot.event
async def on_webhooks_update(channel: discord.abc.GuildChannel):
    await bot.audit_guard.inspect_webhooks(channel)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    from services.permissions import is_admin
    message = "Произошла ошибка при выполнении команды."
    if isinstance(error, discord.app_commands.CheckFailure):
        message = "Недостаточно прав для этой команды."
    log.error("Ошибка slash-команды: %s", error, exc_info=(type(error), error, error.__traceback__))
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN не найден. Создайте .env на основе .env.example")
    bot.run(TOKEN)
