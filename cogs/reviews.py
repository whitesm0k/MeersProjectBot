"""Product reviews with persistent staff moderation and role-based permissions."""
import asyncio
import time
import uuid
import discord
from discord import app_commands
from discord.ext import commands, tasks
from services import review_bridge
from services.permissions import is_admin
from services.storage import load_json, save_json

STATE_FILE = 'reviews_settings.json'
PRODUCTS = ('MeersExternal',)
COOLDOWN = 86400


def remaining_cooldown(cfg, user_id, now=None):
    """Return this user's remaining review cooldown in seconds, scoped to a guild."""
    now = time.time() if now is None else now
    last = float(cfg.get('last_reviews', {}).get(str(user_id), 0))
    return max(0, int(COOLDOWN - (now - last) + 0.999999))


def cooldown_message(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes = (remainder + 59) // 60
    if minutes == 60:
        hours += 1
        minutes = 0
    return f'Вы уже отправляли отзыв. Следующий можно отправить через {hours} ч. {minutes} мин.'


def settings():
    return load_json(STATE_FILE, {})


def has_role(member, ids):
    return isinstance(member, discord.Member) and bool({r.id for r in member.roles} & set(ids))


def safe(text):
    return discord.utils.escape_mentions(discord.utils.escape_markdown(str(text)))


def review_embed(item, approved=False):
    score = item['rating']
    embed = discord.Embed(
        title='✦ MEERS PROJECT  •  ' + ('Проверенный отзыв' if approved else 'Отзыв на проверке'),
        description=f'**{safe(item["product"])}**\n\n**📝 Содержание отзыва**\n{safe(item["text"])}',
        color=0x35C6A4 if approved else 0x8B7CF6,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name='Оценка', value='⭐' * score + f'  **{score}/5**', inline=False)
    embed.add_field(name='Автор отзыва', value=f'<@{item["author_id"]}>', inline=True)
    if approved:
        embed.add_field(name='Одобрил', value=f'<@{item["moderator_id"]}>', inline=True)
    embed.add_field(name='Продукт', value=safe(item['product']), inline=True)
    embed.set_footer(text='MEERS PROJECT • Отзывы о продуктах • ID ' + item['id'][:8])
    return embed


class ReviewModal(discord.ui.Modal, title='MEERS PROJECT • Отзыв о продукте'):
    review = discord.ui.TextInput(label='Ваш отзыв', placeholder='Опишите опыт использования продукта...', style=discord.TextStyle.paragraph, min_length=5, max_length=1500)
    rating = discord.ui.TextInput(label='Оценка (1–5)', placeholder='5', min_length=1, max_length=1)

    def __init__(self, product):
        super().__init__()
        self.product = product

    async def on_submit(self, interaction):
        cog = interaction.client.get_cog('Reviews')
        if cog is None or not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message('Модуль отзывов недоступен.', ephemeral=True)
        try:
            score = int(self.rating.value.strip())
            if not 1 <= score <= 5:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message('Оценка должна быть целым числом от 1 до 5.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with cog.lock:
            data = settings()
            cfg = data.get(str(interaction.guild_id), {})
            if not has_role(interaction.user, cfg.get('submit_role_ids', [])):
                return await interaction.followup.send('У вас нет роли для отправки отзывов.', ephemeral=True)
            if self.product not in PRODUCTS:
                return await interaction.followup.send('Этот продукт недоступен.', ephemeral=True)
            channel = interaction.guild.get_channel(cfg.get('moderation_channel_id', 0))
            if not isinstance(channel, discord.TextChannel):
                return await interaction.followup.send('Канал модерации не настроен.', ephemeral=True)
            now = time.time()
            seconds = remaining_cooldown(cfg, interaction.user.id, now)
            if seconds:
                return await interaction.followup.send(cooldown_message(seconds), ephemeral=True)
            item = {'id': uuid.uuid4().hex, 'author_id': interaction.user.id, 'product': self.product,
                    'rating': score, 'text': self.review.value, 'status': 'pending', 'created_at': now}
            try:
                msg = await channel.send(embed=review_embed(item), view=ModerationView(item['id']), allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                return await interaction.followup.send('Не удалось отправить отзыв на модерацию. Проверьте права бота.', ephemeral=True)
            item['moderation_message_id'] = msg.id
            cfg.setdefault('reviews', {})[item['id']] = item
            cfg.setdefault('last_reviews', {})[str(interaction.user.id)] = now
            data[str(interaction.guild_id)] = cfg
            save_json(STATE_FILE, data)
            review_bridge.insert(item, interaction.user.display_name)
        await interaction.followup.send('Отзыв о **' + self.product + '** отправлен на модерацию. После одобрения он появится в канале отзывов.', ephemeral=True)


class ProductSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder='Выберите продукт для отзыва', min_values=1, max_values=1,
                         options=[discord.SelectOption(label=p, description='Оставить отзыв о ' + p, emoji='✨', value=p) for p in PRODUCTS],
                         custom_id='meers:reviews:product')

    async def callback(self, interaction):
        cfg = settings().get(str(interaction.guild_id), {})
        if not has_role(interaction.user, cfg.get('submit_role_ids', [])):
            return await interaction.response.send_message('У вас нет роли для отправки отзывов.', ephemeral=True)
        seconds = remaining_cooldown(cfg, interaction.user.id)
        if seconds:
            return await interaction.response.send_message(cooldown_message(seconds), ephemeral=True)
        await interaction.response.send_modal(ReviewModal(self.values[0]))


class ProductPicker(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(ProductSelect())


class ReviewPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Оставить отзыв', emoji='⭐', style=discord.ButtonStyle.primary, custom_id='meers:reviews:open')
    async def open_review(self, interaction, button):
        cfg = settings().get(str(interaction.guild_id), {})
        if not has_role(interaction.user, cfg.get('submit_role_ids', [])):
            return await interaction.response.send_message('Отправка отзывов недоступна для ваших ролей.', ephemeral=True)
        seconds = remaining_cooldown(cfg, interaction.user.id)
        if seconds:
            return await interaction.response.send_message(cooldown_message(seconds), ephemeral=True)
        await interaction.response.send_message('**Выберите продукт**, о котором хотите оставить отзыв:', view=ProductPicker(), ephemeral=True)


class ModerationView(discord.ui.View):
    def __init__(self, review_id):
        super().__init__(timeout=None)
        self.review_id = review_id
        approve = discord.ui.Button(label='Одобрить и опубликовать', emoji='✅', style=discord.ButtonStyle.success,
                                    custom_id=f'meers:review:approve:{review_id}')
        reject = discord.ui.Button(label='Отклонить', emoji='❌', style=discord.ButtonStyle.danger,
                                   custom_id=f'meers:review:reject:{review_id}')
        approve.callback = self.approve
        reject.callback = self.reject
        self.add_item(approve)
        self.add_item(reject)

    async def approve(self, interaction):
        await self.decide(interaction, True)

    async def reject(self, interaction):
        await self.decide(interaction, False)

    async def decide(self, interaction, approved):
        cog = interaction.client.get_cog('Reviews')
        if cog is None or not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message('Модуль недоступен.', ephemeral=True)
        cfg = settings().get(str(interaction.guild_id), {})
        if not has_role(interaction.user, cfg.get('moderator_role_ids', [])):
            return await interaction.response.send_message('Только выбранные роли могут модерировать отзывы.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with cog.lock:
            data = settings()
            cfg = data.get(str(interaction.guild_id), {})
            item = cfg.get('reviews', {}).get(self.review_id)
            if not item or item.get('status') != 'pending':
                return await interaction.followup.send('Отзыв уже обработан или не найден.', ephemeral=True)
            if item.get('moderation_message_id') != interaction.message.id:
                return await interaction.followup.send('Сообщение модерации не совпадает.', ephemeral=True)
            if approved:
                channel = interaction.guild.get_channel(cfg.get('channel_id', 0))
                if not isinstance(channel, discord.TextChannel):
                    return await interaction.followup.send('Канал публикации недоступен.', ephemeral=True)
                item['moderator_id'] = interaction.user.id
                try:
                    published = await channel.send(embed=review_embed(item, approved=True), allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException:
                    return await interaction.followup.send('Публикация не удалась. Отзыв остался на модерации.', ephemeral=True)
                item['published_message_id'] = published.id
            item['status'] = 'approved' if approved else 'rejected'
            item['moderator_id'] = interaction.user.id
            item['decided_at'] = time.time()
            save_json(STATE_FILE, data)
            review_bridge.update(item['id'],item['status'],published_message_id=item.get('published_message_id'))
            for child in self.children:
                child.disabled = True
            embed = review_embed(item, approved=False)
            embed.title = '✦ MEERS PROJECT • ' + ('Отзыв одобрен' if approved else 'Отзыв отклонён')
            embed.color = 0x35C6A4 if approved else 0xED6673
            embed.add_field(name='Решение принял', value=f'<@{interaction.user.id}>', inline=False)
            try:
                await interaction.message.edit(embed=embed, view=self, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass
        await interaction.followup.send('Отзыв опубликован.' if approved else 'Отзыв отклонён.', ephemeral=True)


class Reviews(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.site_queue.start()

    def cog_unload(self):
        self.site_queue.cancel()

    @tasks.loop(seconds=12)
    async def site_queue(self):
        for row in await asyncio.to_thread(review_bridge.pending):
            # Only guilds with /reviews_config receive website submissions.
            for guild_id, cfg in settings().items():
                guild=self.bot.get_guild(int(guild_id))
                if guild is None or not cfg.get('moderation_channel_id'): continue
                channel=guild.get_channel(cfg['moderation_channel_id'])
                if not isinstance(channel,discord.TextChannel): continue
                # Website and bot share the same moderation queue and buttons.
                async with self.lock:
                    data=settings(); current=data.get(guild_id,{})
                    if row['id'] in current.get('reviews',{}):
                        review_bridge.update(row['id'],'queued')
                        break
                    item={'id':row['id'],'author_id':int(row['author_id']),'product':row['product'],
                          'rating':row['rating'],'text':row['text'],'status':'pending','created_at':row['created_at']}
                    try:
                        msg=await channel.send(embed=review_embed(item),view=ModerationView(item['id']),allowed_mentions=discord.AllowedMentions.none())
                    except discord.HTTPException:
                        continue
                    item['moderation_message_id']=msg.id
                    current.setdefault('reviews',{})[item['id']]=item
                    current.setdefault('last_reviews',{})[str(item['author_id'])]=item['created_at']
                    data[guild_id]=current
                    save_json(STATE_FILE,data)
                    review_bridge.update(row['id'],'queued')
                    break

    @site_queue.before_loop
    async def before_site_queue(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        if getattr(self, '_registered', False):
            return
        self._registered = True
        for guild_cfg in settings().values():
            for item in guild_cfg.get('reviews', {}).values():
                if item.get('status') == 'pending' and item.get('moderation_message_id'):
                    self.bot.add_view(ModerationView(item['id']), message_id=item['moderation_message_id'])

    @app_commands.command(name='reviews_config', description='Настроить отзывы о продуктах и модерацию')
    @app_commands.describe(channel='Публичный канал одобренных отзывов', moderation_channel='Закрытый канал проверки',
                           submit_role='Роль пользователей, которые могут отправлять отзывы',
                           moderator_role='Роль сотрудников, которые одобряют отзывы',
                           extra_moderator_role='Вторая роль модераторов (необязательно)',
                           extra_submit_role='Вторая роль авторов (необязательно)')
    async def reviews_config(self, interaction: discord.Interaction, channel: discord.TextChannel,
                             moderation_channel: discord.TextChannel, submit_role: discord.Role,
                             moderator_role: discord.Role, extra_moderator_role: discord.Role | None = None,
                             extra_submit_role: discord.Role | None = None):
        if not is_admin(interaction.user):
            return await interaction.response.send_message('Только администратор может изменять настройки.', ephemeral=True)
        if channel.id == moderation_channel.id:
            return await interaction.response.send_message('Публичный канал и канал модерации должны отличаться.', ephemeral=True)
        if any(r.is_default() for r in (submit_role, moderator_role, extra_moderator_role, extra_submit_role) if r):
            return await interaction.response.send_message('Роль @everyone нельзя использовать для ограничения доступа.', ephemeral=True)
        async with self.lock:
            data = settings()
            cfg = data.setdefault(str(interaction.guild_id), {})
            cfg['channel_id'] = channel.id
            cfg['moderation_channel_id'] = moderation_channel.id
            cfg['submit_role_ids'] = list(dict.fromkeys([r.id for r in (submit_role, extra_submit_role) if r]))
            cfg['moderator_role_ids'] = list(dict.fromkeys([r.id for r in (moderator_role, extra_moderator_role) if r]))
            save_json(STATE_FILE, data)
        await interaction.response.send_message(f'Настроено. Публикация: {channel.mention}; модерация: {moderation_channel.mention}.\n'
                                                f'Авторы: {submit_role.mention}; модераторы: {moderator_role.mention}.\n'
                                                'Проверьте, что канал модерации закрыт для обычных участников.', ephemeral=True)

    @app_commands.command(name='reviews_panel', description='Опубликовать панель отзывов о продуктах')
    async def reviews_panel(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            return await interaction.response.send_message('Только администратор может публиковать панель.', ephemeral=True)
        cfg = settings().get(str(interaction.guild_id), {})
        if not all(cfg.get(k) for k in ('channel_id', 'moderation_channel_id', 'submit_role_ids', 'moderator_role_ids')):
            return await interaction.response.send_message('Сначала настройте /reviews_config.', ephemeral=True)
        embed = discord.Embed(title='✦ MEERS PROJECT  |  Отзывы о продуктах',
                              description='**Ваш опыт помогает другим сделать выбор.**\n\n'
                                          '✨ **Продукт:** MeersExternal\n'
                                          '⭐ **Оценка:** от 1 до 5 звёзд\n'
                                          '📝 **Отзыв:** поделитесь впечатлениями\n\n'
                                          '**Как это работает**\n'
                                          'Выберите продукт → заполните форму → дождитесь проверки. '
                                          'После одобрения отзыв появится в публичном канале с указанием автора и модератора.\n\n'
                                          'Один отзыв в 24 часа • Публикуются только проверенные отзывы.',
                              color=0x8875F5)
        embed.set_footer(text='MEERS PROJECT • Product Reviews')
        try:
            await interaction.channel.send(embed=embed, view=ReviewPanel(), allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            return await interaction.response.send_message('Не удалось опубликовать панель. Проверьте права бота.', ephemeral=True)
        await interaction.response.send_message('Панель отзывов опубликована.', ephemeral=True)


async def setup(bot):
    await bot.add_cog(Reviews(bot))
