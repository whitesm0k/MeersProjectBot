import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
from config import ADMIN_ROLE_ID, SUPPORT_ROLE_ID, REPORTS_CHANNEL_ID
from services.permissions import is_admin, is_support

class ReportVerifyView(View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="🔎 Проверить", style=discord.ButtonStyle.primary, custom_id="report:verify")
    async def verify(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ Проверять отчёты могут только администраторы.", ephemeral=True)
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            return await interaction.response.send_message("Кнопка работает только в ветке отчёта.", ephemeral=True)
        await interaction.response.send_message(f"✅ Отчёт проверен администратором {interaction.user.mention}. Ветка архивируется.")
        try:
            await thread.edit(locked=True, archived=True, reason=f"Report verified by {interaction.user.id}")
        except (discord.Forbidden, discord.HTTPException):
            await interaction.followup.send("Не удалось архивировать ветку. Проверьте Manage Threads.", ephemeral=True)

class ReportModal(Modal, title="Подача отчёта"):
    nickname = TextInput(label="Ваш никнейм", placeholder="Игровой ник", max_length=80)
    period = TextInput(label="Период отчёта", placeholder="Например: 01.11.2026–08.11.2026", max_length=100)
    details = TextInput(label="Дополнительная информация", style=discord.TextStyle.paragraph, required=False, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        parent = interaction.guild.get_channel(REPORTS_CHANNEL_ID) if REPORTS_CHANNEL_ID else None
        if not isinstance(parent, discord.TextChannel):
            return await interaction.response.send_message("❌ REPORTS_CHANNEL_ID должен указывать на текстовый канал.", ephemeral=True)
        try:
            thread = await parent.create_thread(
                name=f"Отчёт-{interaction.user.display_name}"[:100],
                type=discord.ChannelType.private_thread,
                invitable=False,
                reason=f"Report by {interaction.user.id}"
            )
            await thread.add_user(interaction.user)
            embed = discord.Embed(
                title="📋 Новый отчёт о закрытых тикетах",
                description=(
                    f"**Пользователь:** {interaction.user.mention}\n"
                    f"**Никнейм:** {self.nickname.value}\n**Период:** {self.period.value}\n"
                    f"**Дополнительно:** {self.details.value or '—'}\n\n"
                    "Прикрепите скриншоты и подтверждения сообщениями в этой ветке."
                ), color=discord.Color.blurple()
            )
            await thread.send(embed=embed, view=ReportVerifyView())
            await interaction.response.send_message(f"✅ Отчёт создан: {thread.mention}", ephemeral=True)
        except (discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message("❌ Не удалось создать приватную ветку. Проверьте права Create Private Threads, Send Messages in Threads и Manage Threads.", ephemeral=True)

class ReportStart(Button):
    def __init__(self): super().__init__(label="📋 Подать отчёт", style=discord.ButtonStyle.primary, custom_id="report:start")

    async def callback(self, interaction):
        if not is_support(interaction.user):
            return await interaction.response.send_message("❌ Отчёты могут подавать только саппорты и администраторы.", ephemeral=True)
        await interaction.response.send_modal(ReportModal())

class ReportPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ReportStart())

class Reports(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="setup_report", description="Опубликовать панель подачи отчётов")
    async def setup_report(self, interaction):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("Недостаточно прав.", ephemeral=True)
        embed = discord.Embed(
            title="📊 Панель подачи отчета о закрытых тикетах",
            description=(
                "Саппорты и администраторы могут подать отчет о закрытых тикетах за указанный период.\n\n"
                "📋 **Как подать отчет:**\n"
                "1. Нажмите кнопку **«Подать отчет»** ниже.\n"
                "2. Заполните форму (никнейм, даты периода).\n"
                "3. Бот создаст приватную ветку для скриншотов.\n"
                "4. Администратор проверит отчет и архивирует ветку.\n\n"
                "Только роли поддержки и администраторы могут подавать отчеты."
            ), color=0x24252B
        )
        await interaction.channel.send(embed=embed, view=ReportPanelView())
        await interaction.response.send_message("✅ Панель отчётов опубликована.", ephemeral=True)

async def setup(bot): await bot.add_cog(Reports(bot))
