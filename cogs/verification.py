import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from config import ROLE_UNVERIFIED_ID, ROLE_VERIFIED_ID
from services.permissions import is_admin
from services.logs import send_mod_log

class VerificationPanelView(View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Verification", style=discord.ButtonStyle.primary, custom_id="verify:member")
    async def verify(self, interaction: discord.Interaction, button: Button):
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Недоступно в личных сообщениях.", ephemeral=True)
        guild = interaction.guild
        unverified = guild.get_role(ROLE_UNVERIFIED_ID) if ROLE_UNVERIFIED_ID else None
        verified = guild.get_role(ROLE_VERIFIED_ID) if ROLE_VERIFIED_ID else None
        if verified is None:
            return await interaction.response.send_message("❌ Роль Verified не настроена.", ephemeral=True)
        if verified in interaction.user.roles:
            return await interaction.response.send_message("✅ У вас уже есть доступ.", ephemeral=True)
        me = guild.me
        if me is None or not me.guild_permissions.manage_roles or verified >= me.top_role:
            return await interaction.response.send_message("❌ Боту не хватает прав или его роль ниже роли Verified.", ephemeral=True)
        try:
            if unverified and unverified in interaction.user.roles:
                await interaction.user.remove_roles(unverified, reason="Member verification")
            await interaction.user.add_roles(verified, reason="Member verification")
            await interaction.response.send_message("✅ Доступ подтверждён!", ephemeral=True)
            embed = discord.Embed(title="Верификация пройдена", description=f"{interaction.user.mention} получил(а) роль {verified.mention}.", color=discord.Color.green())
            await send_mod_log(interaction.client, embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Discord запретил изменение ролей. Проверьте иерархию ролей.", ephemeral=True)

class Verification(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="setup_verification", description="Опубликовать панель верификации")
    async def setup_verification(self, interaction):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("Недостаточно прав.", ephemeral=True)
        if not ROLE_VERIFIED_ID:
            return await interaction.response.send_message("Укажите ROLE_VERIFIED_ID в .env.", ephemeral=True)
        embed = discord.Embed(
            title="🔒 Verification Required",
            description="На сервере установлена защита MeersProject Secure. Нажмите кнопку ниже, чтобы подтвердить личность.",
            color=0x2F3136
        )
        embed.set_footer(text="MeersProject Security System")
        await interaction.channel.send(embed=embed, view=VerificationPanelView())
        await interaction.response.send_message("✅ Панель верификации опубликована.", ephemeral=True)

async def setup(bot): await bot.add_cog(Verification(bot))
