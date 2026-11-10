import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from config import ADMIN_ROLE_ID, SUPPORT_ROLE_ID, TICKET_CATEGORY_NAME, PURCHASE_NOTIFY_USER_IDS
from services.permissions import is_admin, is_support, is_hr

def _topic_value(topic: str, key: str):
    for part in (topic or "").split("|"):
        if part.startswith(key + "="):
            return part.split("=", 1)[1]
    return None

async def _notify_purchase(bot, user, channel, theme, product):
    for uid in PURCHASE_NOTIFY_USER_IDS[:2]:
        try:
            recipient = bot.get_user(uid) or await bot.fetch_user(uid)
            await recipient.send(
                f"🛒 **Новая заявка на покупку!**\n"
                f"Пользователь: {user.mention} (`{user.id}`)\n"
                f"Тема: **{theme}**\nПродукт: **{product}**\n"
                f"Канал: {channel.mention}\nСервер: **{channel.guild.name}**"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

class TicketControls(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Взять в работу", style=discord.ButtonStyle.success, custom_id="support_ticket:claim")
    async def claim(self, interaction: discord.Interaction, button: Button):
        channel = interaction.channel
        is_vacancy = (channel.topic or "").startswith("vacancy|")
        allowed_staff = is_support(interaction.user) or (is_vacancy and is_hr(interaction.user))
        if not allowed_staff:
            return await interaction.response.send_message("❌ Только поддержка/HR и администраторы могут брать этот тикет.", ephemeral=True)
        claimed_by = _topic_value(channel.topic, "claimed_by")
        if claimed_by:
            if int(claimed_by) == interaction.user.id:
                return await interaction.response.send_message("ℹ️ Этот тикет уже закреплён за вами.", ephemeral=True)
            member = interaction.guild.get_member(int(claimed_by))
            name = member.display_name if member else f"ID {claimed_by}"
            return await interaction.response.send_message(f"❌ Тикет уже забрал **{name}**.", ephemeral=True)

        parts = [p for p in (channel.topic or "").split("|") if p and not p.startswith("claimed_by=")]
        parts.append(f"claimed_by={interaction.user.id}")
        await channel.edit(topic="|".join(parts), reason=f"Claimed by {interaction.user.id}")
        await channel.send(embed=discord.Embed(
            title="Тикет взят в работу",
            description=f"{interaction.user.mention} взял тикет. Закрыть его сможет только этот сотрудник.",
            color=discord.Color.green()
        ))
        await interaction.response.send_message("✅ Вы взяли тикет в работу.", ephemeral=True)

    @discord.ui.button(label="Закрыть тикет", style=discord.ButtonStyle.danger, custom_id="support_ticket:close")
    async def close(self, interaction: discord.Interaction, button: Button):
        claimed_by = _topic_value(interaction.channel.topic, "claimed_by")
        if not claimed_by:
            return await interaction.response.send_message("❌ Сначала возьмите тикет в работу.", ephemeral=True)
        if int(claimed_by) != interaction.user.id:
            return await interaction.response.send_message("❌ Закрыть тикет может только сотрудник, который его забрал.", ephemeral=True)
        await interaction.response.send_message("🗑️ Тикет закрывается…", ephemeral=True)
        try:
            await interaction.channel.delete(reason=f"Closed by assigned staff {interaction.user.id}")
        except (discord.Forbidden, discord.HTTPException):
            await interaction.followup.send("Не удалось удалить канал. Проверьте право Manage Channels.", ephemeral=True)

class ProductButton(Button):
    def __init__(self, product):
        super().__init__(label=product, style=discord.ButtonStyle.success)
        self.product = product

    async def callback(self, interaction):
        data = interaction.client.ticket_sessions.get(interaction.user.id)
        if not data:
            return await interaction.response.send_message("Сессия истекла. Начните создание тикета заново.", ephemeral=True)
        data["product"] = self.product
        view = View(timeout=120)
        view.add_item(ConfirmTicketButton())
        embed = discord.Embed(
            title="Тикет готов к созданию",
            description=f"Тема: **{data['theme']}**\nПродукт: **{self.product}**\n\nНажмите кнопку ниже.",
            color=discord.Color.teal()
        )
        await interaction.response.edit_message(content=None, embed=embed, view=view)

class ThemeButton(Button):
    def __init__(self, theme):
        super().__init__(label=theme, style=discord.ButtonStyle.primary)
        self.theme = theme

    async def callback(self, interaction):
        interaction.client.ticket_sessions[interaction.user.id] = {"theme": self.theme}
        view = View(timeout=120)
        for product in ("MeersExternal", "MeersMacro", "Другое"):
            view.add_item(ProductButton(product))
        await interaction.response.edit_message(
            content=f"Вы выбрали тему **{self.theme}**. Теперь выберите продукт:",
            embed=None, view=view
        )

class ConfirmTicketButton(Button):
    def __init__(self):
        super().__init__(label="✅ Создать тикет", style=discord.ButtonStyle.success)

    async def callback(self, interaction):
        data = interaction.client.ticket_sessions.get(interaction.user.id)
        if not data or "product" not in data:
            return await interaction.response.send_message("Сессия истекла. Начните заново.", ephemeral=True)
        guild, user = interaction.guild, interaction.user
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(TICKET_CATEGORY_NAME)
        number = 1 + sum(1 for c in category.text_channels if c.name.startswith("ticket-"))
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        for rid in (SUPPORT_ROLE_ID, ADMIN_ROLE_ID):
            role = guild.get_role(rid) if rid else None
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        channel = await category.create_text_channel(
            name=f"ticket-{number}",
            overwrites=overwrites,
            topic=f"ticket|owner={user.id}|theme={data['theme']}|product={data['product']}",
            reason=f"Ticket created by {user.id}"
        )
        support = guild.get_role(SUPPORT_ROLE_ID) if SUPPORT_ROLE_ID else None
        admin = guild.get_role(ADMIN_ROLE_ID) if ADMIN_ROLE_ID else None
        mentions = " ".join(r.mention for r in (support, admin) if r) or "Поддержка"
        await channel.send(f"{mentions} 🚨 **Новый тикет!**\nТема: {data['theme']}\nПродукт: {data['product']}\nАвтор: {user.mention}\n\n👋 Привет, {user.mention}! Поддержка уведомлена.")
        embed = discord.Embed(
            title="Ваш тикет создан!",
            description=(
                f"**Тема:** {data['theme']}\n**Продукт:** {data['product']}\n\n"
                "👇 **Опишите ваш вопрос или проблему:**\n"
                "• Что произошло?\n• Что ожидали получить?\n• Приложите скриншоты или текст ошибки."
            ), color=discord.Color.blurple()
        )
        embed.add_field(name="Автор", value=user.mention, inline=True)
        embed.add_field(name="Статус", value="⏳ Ожидает ответа", inline=True)
        embed.set_footer(text=f"ID тикета: #{number}")
        await channel.send(embed=embed, view=TicketControls())
        if data["theme"] == "Покупка":
            await _notify_purchase(interaction.client, user, channel, data["theme"], data["product"])
        interaction.client.ticket_sessions.pop(user.id, None)
        await interaction.response.edit_message(content=f"✅ Тикет создан: {channel.mention}", embed=None, view=None)

class StartTicketButton(Button):
    def __init__(self):
        super().__init__(label="🎫 Создать тикет", style=discord.ButtonStyle.primary, custom_id="support_ticket:start")

    async def callback(self, interaction):
        view = View(timeout=120)
        for theme in ("Вопрос", "Проблема", "Покупка"):
            view.add_item(ThemeButton(theme))
        await interaction.response.send_message("Выберите тему обращения:", view=view, ephemeral=True)

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(StartTicketButton())

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.ticket_sessions = {}

    @app_commands.command(name="setup_tickets", description="Опубликовать панель обычных тикетов")
    async def setup_tickets(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("Недостаточно прав.", ephemeral=True)
        embed = discord.Embed(
            title="🎫  MEERSPROJECT  |  ЦЕНТР ПОДДЕРЖКИ",
            description=(
                "**Добро пожаловать в службу поддержки MeersProject!**\n"
                "Мы поможем разобраться с вопросами по продуктам, покупкам и техническим неполадкам.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0x5865F2
        )
        embed.add_field(
            name="💬  Консультация",
            value="Вопросы о проекте, функционале и использовании продуктов.",
            inline=False
        )
        embed.add_field(
            name="🛠️  Техническая помощь",
            value="Ошибки, проблемы с запуском, работой или настройкой.",
            inline=False
        )
        embed.add_field(
            name="🛒  Покупка продукта",
            value="Помощь с выбором, оплатой и получением продукта.",
            inline=False
        )
        embed.add_field(
            name="📋  Как открыть обращение",
            value=(
                "**1.** Нажмите **«Создать тикет»** ниже.\n"
                "**2.** Выберите тему обращения и продукт.\n"
                "**3.** Перейдите в созданный приватный канал и подробно опишите ситуацию.\n"
                "**4.** Дождитесь ответа сотрудника поддержки."
            ),
            inline=False
        )
        embed.add_field(
            name="🔒  Важно знать",
            value=(
                "• Ваш тикет виден только вам и уполномоченным сотрудникам.\n"
                "• При проблемах прикладывайте скриншоты и текст ошибки.\n"
                "• Не передавайте пароли, токены и другую конфиденциальную информацию.\n"
                "• Не создавайте повторные обращения по одному вопросу."
            ),
            inline=False
        )
        embed.set_footer(text="MeersProject • Поддержка пользователей • Нажмите кнопку ниже")
        await interaction.channel.send(embed=embed, view=TicketPanelView())
        await interaction.response.send_message("✅ Панель тикетов опубликована.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Tickets(bot))
