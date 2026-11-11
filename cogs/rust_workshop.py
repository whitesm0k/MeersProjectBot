"""Rust Workshop submissions: private upload, human review, forum publication."""
import asyncio
import io
import json
import logging
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from services.permissions import is_admin
from config import ADMIN_ROLE_ID, SUPPORT_ROLE_ID, OWNER_USER_IDS

log = logging.getLogger(__name__)
DATA = Path('data/rust_workshop.json')
CATEGORY = os.getenv('RUST_WORKSHOP_CATEGORY', 'Rust Workshop | Проверка')
MAX_BYTES = int(os.getenv('RUST_WORKSHOP_MAX_BYTES', str(20 * 1024 * 1024)))

def staff(member):
    return is_admin(member) or (getattr(member, 'id', None) in OWNER_USER_IDS)

def load():
    try:
        return json.loads(DATA.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return {}

def save(data):
    DATA.parent.mkdir(parents=True, exist_ok=True)
    temp = DATA.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(DATA)

def details(item):
    e = discord.Embed(title='📦 MEERS PROJECT | Rust Workshop', color=0x8B5CF6)
    for title, key in [('Название', 'name'), ('Тип', 'kind'), ('Devblog', 'devblog'), ('Способ инжекта', 'opening')]:
        e.add_field(name=title, value=str(item[key])[:1024], inline=False)
    e.add_field(name='Автор', value=f"<@{item['owner']}>", inline=False)
    e.set_footer(text='Проверка файла выполняется вручную администрацией')
    return e

class SubmissionModal(discord.ui.Modal, title='Rust Workshop | Заявка'):
    name = discord.ui.TextInput(label='1. Название', max_length=90)
    kind = discord.ui.TextInput(label='2. Cheat / Spoofer / Sourse', max_length=80)
    devblog = discord.ui.TextInput(label='3. Версия Devblog', max_length=80)
    opening = discord.ui.TextInput(label='4. Способ инжекта', style=discord.TextStyle.paragraph, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message('Только на сервере.', ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        cog = interaction.client.get_cog('RustWorkshop')
        async with cog.lock:
            data = load()
            existing = next((key for key, value in data.items() if value.get('guild') == interaction.guild.id and value.get('owner') == interaction.user.id and value.get('status') in ('awaiting_file', 'reviewing', 'publishing')), None)
            if existing:
                channel = interaction.guild.get_channel(int(existing))
                return await interaction.followup.send(f'У вас уже есть активная заявка: {channel.mention if channel else existing}', ephemeral=True)
            guild = interaction.guild
            category = discord.utils.get(guild.categories, name=CATEGORY)
            if not category:
                category = await guild.create_category(CATEGORY, reason='Rust Workshop')
            overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False), interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, read_message_history=True), guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True)}
            for rid in (ADMIN_ROLE_ID, SUPPORT_ROLE_ID):
                role = guild.get_role(rid) if rid else None
                if role:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            channel = await category.create_text_channel(name=f'rust-{interaction.user.id}', overwrites=overwrites, topic=f'rustworkshop|owner={interaction.user.id}')
            item = {'guild': guild.id, 'owner': interaction.user.id, 'name': str(self.name.value), 'kind': str(self.kind.value), 'devblog': str(self.devblog.value), 'opening': str(self.opening.value), 'status': 'awaiting_file'}
            data[str(channel.id)] = item
            save(data)
        await channel.send(content=f'{interaction.user.mention} **5. Прикрепите файл** следующим сообщением в этот приватный тикет. Не отправляйте пароли или личные данные. Максимум {MAX_BYTES // (1024*1024)} МБ.', embed=details(item), view=ReviewView(), allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
        await interaction.followup.send(f'Тикет создан: {channel.mention}. Прикрепите файл в нём.', ephemeral=True)

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='📦 Предложить свой чит', style=discord.ButtonStyle.primary, custom_id='meers:rust:submit')
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SubmissionModal())

class ReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='✅ Проверено — опубликовать', style=discord.ButtonStyle.success, custom_id='meers:rust:approve')
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not staff(interaction.user):
            return await interaction.response.send_message('Только создатели и администраторы могут одобрять файлы.', ephemeral=True)
        cog = interaction.client.get_cog('RustWorkshop')
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with cog.lock:
            data = load()
            item = data.get(str(interaction.channel.id))
            if not item or item['status'] != 'reviewing':
                return await interaction.followup.send('Заявка не готова к публикации или уже обработана.', ephemeral=True)
            forum_id = int(os.getenv('RUST_WORKSHOP_FORUM_CHANNEL_ID', '0') or 0)
            forum = interaction.guild.get_channel(forum_id)
            if not isinstance(forum, discord.ForumChannel):
                return await interaction.followup.send('Укажите RUST_WORKSHOP_FORUM_CHANNEL_ID — ID форума Discord.', ephemeral=True)
            item['status'] = 'publishing'
            save(data)
            try:
                msg_channel = interaction.guild.get_channel(int(item['file_channel']))
                msg = await msg_channel.fetch_message(int(item['file_message']))
                attachment = next((a for a in msg.attachments if a.id == item['attachment']), None)
                if not attachment:
                    raise RuntimeError('Исходное вложение удалено')
                if attachment.size > MAX_BYTES:
                    raise RuntimeError('Файл превышает лимит')
                raw = await attachment.read()
                upload = discord.File(io.BytesIO(raw), filename=attachment.filename)
                thread = await forum.create_thread(name=item['name'][:100], content=f"**Проверено вручную:** {interaction.user.mention}\n**Автор:** <@{item['owner']}>\n**Тип:** {item['kind']}\n**Devblog:** {item['devblog']}\n**Способ открытия:** {item['opening']}\n\n⚠️ Проверка человеком не гарантирует абсолютную безопасность файла.", file=upload, allowed_mentions=discord.AllowedMentions.none())
                item['status'] = 'published'
                item['thread'] = thread.thread.id
                save(data)
            except (discord.HTTPException, discord.Forbidden, RuntimeError) as exc:
                item['status'] = 'reviewing'
                save(data)
                log.exception('Не удалось опубликовать Rust Workshop')
                return await interaction.followup.send(f'Публикация не удалась: {exc}. Тикет остаётся открытым.', ephemeral=True)
            await interaction.followup.send(f'Опубликовано: {thread.thread.mention}. Тикет закрывается.', ephemeral=True)
            await interaction.channel.delete(reason=f'Rust Workshop approved by {interaction.user.id}')

    @discord.ui.button(label='❌ Отклонить', style=discord.ButtonStyle.danger, custom_id='meers:rust:reject')
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not staff(interaction.user):
            return await interaction.response.send_message('Недостаточно прав.', ephemeral=True)
        cog = interaction.client.get_cog('RustWorkshop')
        async with cog.lock:
            data = load()
            item = data.get(str(interaction.channel.id))
            if not item or item['status'] not in ('awaiting_file', 'reviewing'):
                return await interaction.response.send_message('Заявка уже обработана.', ephemeral=True)
            item['status'] = 'rejected'
            save(data)
        await interaction.response.send_message('Заявка отклонена. Тикет закрывается.', ephemeral=True)
        await interaction.channel.delete(reason=f'Rust Workshop rejected by {interaction.user.id}')

class RustWorkshop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()

    @app_commands.command(name='setup_rust_workshop', description='Опубликовать панель подачи читов Rust')
    async def setup_rust_workshop(self, interaction: discord.Interaction):
        if not staff(interaction.user):
            return await interaction.response.send_message('Недостаточно прав.', ephemeral=True)
        embed = discord.Embed(title='✧ MEERS PROJECT | RUST WORKSHOP', color=0x8B5CF6, description='**Поделитесь своим читом/спуфером/сурcом для Rust с сообществом!**\n\n📦 Название продукта\n🎮 Сheat / Spoofer / Sourse\n🛠️ Версия Devblog (укажите сами)\n🔓 Способ открытия\n📎 Файл — загружается в приватный тикет после заполнения формы\n\n**Как это работает:** заполните форму → прикрепите файл → дождитесь ручной проверки создателей и администрации → после одобрения появится ветка форума с вашим файлом.\n\n🔒 До публикации файл виден только вам и команде. ⚠️ Не отправляйте вредоносные файлы. Подача не гарантирует публикацию.')
        embed.set_footer(text='MEERS PROJECT • Rust Workshop')
        await interaction.channel.send(embed=embed, view=PanelView())
        await interaction.response.send_message('Панель Rust Workshop опубликована.', ephemeral=True)

    @commands.Cog.listener('on_message')
    async def capture_attachment(self, message: discord.Message):
        if not message.guild or message.author.bot or message.webhook_id or not message.attachments:
            return
        async with self.lock:
            data = load()
            item = data.get(str(message.channel.id))
            if not item or item['status'] != 'awaiting_file' or item['owner'] != message.author.id:
                return
            attachment = message.attachments[0]
            if attachment.size > MAX_BYTES:
                await message.channel.send(f'Файл слишком большой. Максимум {MAX_BYTES // (1024*1024)} МБ.')
                return
            item.update(status='reviewing', file_channel=message.channel.id, file_message=message.id, attachment=attachment.id)
            save(data)
        await message.channel.send('📎 Файл получен. **Публикация запрещена до ручной проверки на вредоносное содержимое.** Администратор проверяет вложение и нажимает «Проверено — опубликовать» в первом сообщении тикета.')

async def setup(bot):
    await bot.add_cog(RustWorkshop(bot))
