import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from config import ADMIN_ROLE_ID, HR_ROLE_ID, VACANCY_CATEGORY_NAME
from services.permissions import is_admin
from services.storage import load_json, save_json
from cogs.tickets import TicketControls

STATUS_FILE = "vacancy_status.json"
status = load_json(STATUS_FILE, {"Media": False, "Support": False})

class VacancyChoice(Button):
    def __init__(self, vacancy):
        super().__init__(label=vacancy, style=discord.ButtonStyle.primary)
        self.vacancy = vacancy

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild, user = interaction.guild, interaction.user
        category = discord.utils.get(guild.categories, name=VACANCY_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(VACANCY_CATEGORY_NAME)
        number = 1 + sum(1 for c in category.text_channels if c.name.startswith("vac-"))
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        for rid in (HR_ROLE_ID, ADMIN_ROLE_ID):
            role = guild.get_role(rid) if rid else None
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        channel = await category.create_text_channel(
            name=f"vac-{number}", overwrites=overwrites,
            topic=f"vacancy|owner={user.id}|type={self.vacancy}",
            reason=f"Vacancy application by {user.id}"
        )
        if self.vacancy == "Media":
            questions = "1. Сколько вам лет?\n2. Умеете ли монтировать?\n3. Сколько вы находитесь на проекте?\n4. Есть ли у вас наш ключ?"
        else:
            questions = ("1. Сколько вам лет?\n2. Умеете ли помогать игрокам в тикетах?\n"
                         "3. Сколько вы находитесь на проекте?\n4. Есть ли у вас наш ключ?\n"
                         "5. Знаете ли вы основу и решение проблем с читом?")
        roles = [guild.get_role(x) for x in (HR_ROLE_ID, ADMIN_ROLE_ID) if x]
        ping = " ".join(r.mention for r in roles if r) or "HR"
        await channel.send(f"{ping} 🚨 **Новая заявка на вакансию!**")
        embed = discord.Embed(
            title="Ваша заявка создана!",
            description=f"🎯 **Вакансия: {self.vacancy}**\n\n👋 Привет, {user.mention}!\n\n📝 **Ответьте на вопросы:**\n{questions}",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Автор", value=user.mention, inline=True)
        embed.add_field(name="Статус", value="⏳ Ожидает заполнения", inline=True)
        await channel.send(embed=embed, view=TicketControls())
        await interaction.followup.send(f"✅ Канал заявки создан: {channel.mention}", ephemeral=True)

class VacancyStart(Button):
    def __init__(self):
        super().__init__(label="💼 Подать заявку на вакансию", style=discord.ButtonStyle.primary, custom_id="vacancy:start")

    async def callback(self, interaction):
        view = View(timeout=120)
        for name in ("Media", "Support"):
            if status.get(name, False):
                view.add_item(VacancyChoice(name))
            else:
                view.add_item(Button(label=f"{name} (Набор закрыт)", style=discord.ButtonStyle.secondary, disabled=True))
        await interaction.response.send_message("Выберите вакансию:", view=view, ephemeral=True)

class VacancyPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(VacancyStart())

class Vacancies(commands.Cog):
    def __init__(self, bot): self.bot = bot

    async def set_status(self, interaction, name, opened):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("Недостаточно прав.", ephemeral=True)
        status[name] = opened
        save_json(STATUS_FILE, status)
        await interaction.response.send_message(f"Набор **{name}** {'открыт' if opened else 'закрыт'}.", ephemeral=True)

    @app_commands.command(name="setup_vacancies", description="Опубликовать панель вакансий")
    async def setup_vacancies(self, interaction):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("Недостаточно прав.", ephemeral=True)
        media_open = status.get("Media", False)
        support_open = status.get("Support", False)
        media_state = "🟢 Набор открыт" if media_open else "🔴 Набор закрыт"
        support_state = "🟢 Набор открыт" if support_open else "🔴 Набор закрыт"
        embed = discord.Embed(
            title="💼  MEERSPROJECT  |  КАРЬЕРА В КОМАНДЕ",
            description=(
                "**Хотите стать частью команды MeersProject?**\n"
                "Выберите подходящее направление и отправьте заявку на рассмотрение.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0x2ECC71 if (media_open or support_open) else 0x5865F2
        )
        embed.add_field(
            name="🎬  MEDIA  |  Контент и продвижение",
            value=(
                f"**{media_state}**\n"
                "Создание и монтаж видеороликов, публикация контента, "
                "участие в продвижении проекта.\n"
                "**В анкете:** возраст, навыки монтажа, опыт на проекте и наличие ключа."
            ),
            inline=False
        )
        embed.add_field(
            name="🎧  SUPPORT  |  Поддержка игроков",
            value=(
                f"**{support_state}**\n"
                "Помощь пользователям, разбор обращений и решение технических вопросов.\n"
                "**В анкете:** возраст, опыт поддержки, время на проекте, "
                "наличие ключа и знание типичных проблем."
            ),
            inline=False
        )
        embed.add_field(
            name="📝  Как подать заявку",
            value=(
                "**1.** Нажмите **«Подать заявку на вакансию»**.\n"
                "**2.** Выберите направление с открытым набором.\n"
                "**3.** В приватном канале ответьте на все вопросы анкеты.\n"
                "**4.** Ожидайте решения HR-команды."
            ),
            inline=False
        )
        embed.add_field(
            name="📌  Перед отправкой",
            value=(
                "• Указывайте достоверную информацию.\n"
                "• Отвечайте подробно и по существу.\n"
                "• Заявка доступна только вам и уполномоченным сотрудникам.\n"
                "• Закрытые направления недоступны для выбора."
            ),
            inline=False
        )
        embed.set_footer(text="MeersProject • Набор в команду • Статусы указаны на момент публикации")
        await interaction.channel.send(embed=embed, view=VacancyPanelView())
        await interaction.response.send_message("✅ Панель вакансий опубликована.", ephemeral=True)

    @app_commands.command(name="openvacmed", description="Открыть набор Media")
    async def open_med(self, interaction): await self.set_status(interaction, "Media", True)

    @app_commands.command(name="closevacmed", description="Закрыть набор Media")
    async def close_med(self, interaction): await self.set_status(interaction, "Media", False)

    @app_commands.command(name="openvacsupp", description="Открыть набор Support")
    async def open_supp(self, interaction): await self.set_status(interaction, "Support", True)

    @app_commands.command(name="closevacsupp", description="Закрыть набор Support")
    async def close_supp(self, interaction): await self.set_status(interaction, "Support", False)

async def setup(bot): await bot.add_cog(Vacancies(bot))
