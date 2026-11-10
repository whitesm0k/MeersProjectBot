import discord
from config import ADMIN_IDS, ADMIN_ROLE_ID, SUPPORT_ROLE_ID, HR_ROLE_ID

def is_admin(member: discord.abc.User) -> bool:
    if getattr(member, "id", None) in ADMIN_IDS:
        return True
    if not isinstance(member, discord.Member):
        return False
    return (
        member.guild_permissions.administrator
        or (ADMIN_ROLE_ID != 0 and any(r.id == ADMIN_ROLE_ID for r in member.roles))
    )

def is_support(member: discord.abc.User) -> bool:
    if not isinstance(member, discord.Member):
        return False
    return is_admin(member) or (
        SUPPORT_ROLE_ID != 0 and any(r.id == SUPPORT_ROLE_ID for r in member.roles)
    )

def is_hr(member: discord.abc.User) -> bool:
    if not isinstance(member, discord.Member):
        return False
    return is_admin(member) or (
        HR_ROLE_ID != 0 and any(r.id == HR_ROLE_ID for r in member.roles)
    )

def can_submit_report(member: discord.Member) -> bool:
    return is_support(member)

def is_ticket_staff(member: discord.Member) -> bool:
    return is_support(member)

def is_owner_or_admin(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.user, discord.Member) and is_admin(interaction.user)
