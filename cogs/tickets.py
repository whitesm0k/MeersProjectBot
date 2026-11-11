import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from config import ADMIN_ROLE_ID, SUPPORT_ROLE_ID, TICKET_CATEGORY_NAME, PURCHASE_NOTIFY_USER_IDS, PARTNERSHIP_CATEGORY_NAME, PARTNERSHIP_RULES_URL
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

SUBSCRIPTION_LOTS = {
    "7 дней": "https://funpay.com/lots/offer?id=77983009",
    "14 дней": "https://funpay.com/lots/offer?id=81805241",
    "30 дней (выгодно)": "https://funpay.com/lots/offer?id=81805374",
    "Lifetime": "https://funpay.com/lots/offer?id=81805500",
}

class SubscriptionSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Выберите срок подписки",
            custom_id="meers:subscription:select",
            options=[discord.SelectOption(label=label, value=label, emoji="💎" if label.startswith("30") else "🛒", description="Выгодный вариант" if label.startswith("30") else "Получить ссылку на оплату") for label in SUBSCRIPTION_LOTS],
        )

    async def callback(self, interaction: discord.Interaction):
        owner = _topic_value(interaction.channel.topic, "owner")
        if str(interaction.user.id) != owner:
            return await interaction.response.send_message("Выбирать подписку может только автор тикета.", ephemeral=True)
        if _topic_value(interaction.channel.topic, "theme") != "Покупка":
            return await interaction.response.send_message("Это не тикет покупки.", ephemeral=True)
        duration = self.values[0]
        link = SUBSCRIPTION_LOTS[duration]
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(
            f"🛍️ {interaction.user.mention}, вы выбрали **{duration}**.\n"
            f"🔗 **Ссылка на покупку FunPay:** {link}\n\n"
            "После оплаты сообщите об этом в тикете. Не передавайте никому пароли или коды подтверждения.",
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )
        await interaction.followup.send("Ссылка на выбранную подписку отправлена в тикет.", ephemeral=True)

class SubscriptionView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SubscriptionSelect())

class PartnershipModal(discord.ui.Modal, title="Заявка на сотрудничество"):
    project = discord.ui.TextInput(label="Название проекта / команды", max_length=100, placeholder="Название вашего проекта")
    contact = discord.ui.TextInput(label="Контакт для связи", max_length=150, placeholder="Discord / Telegram / сайт")
    proposal = discord.ui.TextInput(label="Предложение о сотрудничестве", style=discord.TextStyle.paragraph, max_length=1200, placeholder="Расскажите о проекте и вашем предложении")
    benefit = discord.ui.TextInput(label="Взаимная выгода", style=discord.TextStyle.paragraph, max_length=700, required=False, placeholder="Чем сотрудничество будет полезно обеим сторонам?")

    async def on_submit(self, interaction: discord.Interaction):
        guild, user = interaction.guild, interaction.user
        await interaction.response.defer(ephemeral=True, thinking=True)
        category = discord.utils.get(guild.categories, name=PARTNERSHIP_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(PARTNERSHIP_CATEGORY_NAME)
        existing = next((c for c in category.text_channels if _topic_value(c.topic, "owner") == str(user.id) and (c.topic or "").startswith("partnership|")), None)
        if existing:
            return await interaction.followup.send(f"У вас уже есть заявка: {existing.mention}", ephemeral=True)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        for rid in (SUPPORT_ROLE_ID, ADMIN_ROLE_ID):
            role = guild.get_role(rid) if rid else None
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        channel = await category.create_text_channel(
            name=f"partner-{user.id}", overwrites=overwrites,
            topic=f"partnership|owner={user.id}|rules_accepted=yes",
            reason=f"Partnership application by {user.id}",
        )
        embed = discord.Embed(title="🤝 MEERS PROJECT | Заявка на сотрудничество", color=0x8B5CF6,
            description=f"**Автор:** {user.mention}\n**Проект:** {self.project.value}\n**Контакт:** {self.contact.value}")
        embed.add_field(name="📋 Предложение", value=self.proposal.value, inline=False)
        embed.add_field(name="✨ Взаимная выгода", value=self.benefit.value or "Не указана", inline=False)
        embed.add_field(name="📜 Правила", value="Заявитель подтвердил ознакомление и согласие.", inline=False)
        roles = [guild.get_role(rid) for rid in (SUPPORT_ROLE_ID, ADMIN_ROLE_ID) if rid]
        mentions = " ".join(role.mention for role in roles if role)
        await channel.send(content=f"{mentions} Новая заявка от {user.mention}", embed=embed, view=TicketControls(),
            allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=False))
        await interaction.followup.send(f"✅ Заявка отправлена! Ваш тикет: {channel.mention}", ephemeral=True)

class PartnershipRulesView(View):
    def __init__(self):
        super().__init__(timeout=300)
        self.accepted = False

    @discord.ui.button(label="Я ознакомился и согласен с правилами", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PartnershipModal())

class PartnershipPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🤝 Подать заявку на сотрудничество", style=discord.ButtonStyle.primary, custom_id="meers:partnership:start")
    async def start(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="📜 Правила сотрудничества MeersProject", color=0x8B5CF6,
            description=("**Перед подачей заявки внимательно прочитайте условия:**\n\n"
                "1. Указывайте достоверные сведения о проекте и контакты.\n"
                "2. Опишите конкретный формат сотрудничества и взаимную пользу.\n"
                "3. Запрещены спам, обман, реклама запрещённых услуг и повторные заявки.\n"
                "4. Решение принимается командой MeersProject индивидуально; подача заявки не гарантирует одобрения.\n"
                "5. Общайтесь уважительно и не публикуйте конфиденциальные данные.\n\n"
                "**Нажимая кнопку согласия, вы подтверждаете ознакомление с этими правилами.**"))
        if PARTNERSHIP_RULES_URL:
            embed.add_field(name="🔗 Полные правила", value=PARTNERSHIP_RULES_URL, inline=False)
        await interaction.response.send_message(embed=embed, view=PartnershipRulesView(), ephemeral=True)

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
            await channel.send(embed=discord.Embed(
                title="🛒 Выберите срок подписки",
                description="Выберите подходящий срок в меню ниже. После выбора ссылка на нужный лот FunPay появится в этом тикете.\n\n⭐ **30 дней — выгодно!**",
                color=0x8B5CF6,
            ), view=SubscriptionView())
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

    @app_commands.command(name="setup_partnership", description="Опубликовать панель заявок на сотрудничество")
    async def setup_partnership(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("Недостаточно прав.", ephemeral=True)
        embed = discord.Embed(
            title="✧ MEERS PROJECT | Сотрудничество",
            description=("**Хотите стать партнёром MeersProject?**\n"
                "Мы открыты к интересным предложениям, совместным проектам и взаимовыгодным инициативам.\n\n"
                "✨ **Кому подойдёт:** владельцам проектов, авторам контента, сообществам и командам.\n"
                "📝 **Что указать:** название проекта, контакт, суть предложения и взаимную выгоду.\n\n"
                "**Как это работает**\n"
                "Ознакомьтесь с правилами → подтвердите согласие → заполните форму → "
                "получите приватный тикет и дождитесь ответа команды.\n\n"
                "🔒 Заявка видна только вам и уполномоченным сотрудникам.\n"
                "⚠️ Отправка заявки не гарантирует сотрудничество."),
            color=0x8B5CF6,
        )
        embed.set_footer(text="MEERS PROJECT • Partnerships")
        await interaction.channel.send(embed=embed, view=PartnershipPanelView())
        await interaction.response.send_message("Панель сотрудничества опубликована.", ephemeral=True)

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
