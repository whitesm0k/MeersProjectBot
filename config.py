import os
from dotenv import load_dotenv

load_dotenv()

def _int(name: str, default: int = 0) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else default

def _ids(name: str) -> list[int]:
    return [int(v.strip()) for v in os.getenv(name, "").split(",") if v.strip().isdigit()]

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = _ids("ADMIN_IDS")
PURCHASE_NOTIFY_USER_IDS = _ids("PURCHASE_NOTIFY_USER_IDS")

ROLE_UNVERIFIED_ID = _int("ROLE_UNVERIFIED_ID")
ROLE_VERIFIED_ID = _int("ROLE_VERIFIED_ID")
ADMIN_ROLE_ID = _int("ADMIN_ROLE_ID")
SUPPORT_ROLE_ID = _int("SUPPORT_ROLE_ID")
HR_ROLE_ID = _int("HR_ROLE_ID")

LOG_MODERATION_CHANNEL_ID = _int("LOG_MODERATION_CHANNEL_ID")
LOG_RAID_CHANNEL_ID = _int("LOG_RAID_CHANNEL_ID")
LOG_MEMBER_CHANNEL_ID = _int("LOG_MEMBER_CHANNEL_ID")
REPORTS_CHANNEL_ID = _int("REPORTS_CHANNEL_ID")

TICKET_CATEGORY_NAME = os.getenv("TICKET_CATEGORY_NAME", "✦ 𝗧𝗶𝗰𝗸𝗲𝘁 ✦")
VACANCY_CATEGORY_NAME = os.getenv("VACANCY_CATEGORY_NAME", "✦ 𝗩𝗮𝗰𝗮𝗻𝗰𝗶𝗲𝘀 ✦")

# Anti-spam thresholds
SPAM_WINDOW_SECONDS = _int("SPAM_WINDOW_SECONDS", 10)
SPAM_LIMIT_PER_WINDOW = _int("SPAM_LIMIT_PER_WINDOW", 7)
SPAM_MIN_INTERVAL_SECONDS = float(os.getenv("SPAM_MIN_INTERVAL_SECONDS", "0.8"))
SPAM_TIMEOUT_SECONDS = 600
SPAM_MAX_MENTIONS_PER_MESSAGE = _int("SPAM_MAX_MENTIONS_PER_MESSAGE", 5)
SPAM_MAX_ATTACHMENTS_PER_MESSAGE = _int("SPAM_MAX_ATTACHMENTS_PER_MESSAGE", 3)
SPAM_MAX_EMOJI_PER_MESSAGE = _int("SPAM_MAX_EMOJI_PER_MESSAGE", 10)
SPAM_MAX_REPEATED_WORDS = _int("SPAM_MAX_REPEATED_WORDS", 5)
SPAM_MAX_REPEATED_SYMBOLS = _int("SPAM_MAX_REPEATED_SYMBOLS", 15)
SPAM_MAX_REPEATED_LETTERS = _int("SPAM_MAX_REPEATED_LETTERS", 15)

# Anti-raid thresholds. Detection logs by default; optional reversals are OFF by default.
RAID_JOIN_FLOOD_WINDOW_SECONDS = _int("RAID_JOIN_FLOOD_WINDOW_SECONDS", 60)
RAID_JOIN_FLOOD_LIMIT = _int("RAID_JOIN_FLOOD_LIMIT", 8)
RAID_MAX_CHANNELS_PER_USER = _int("RAID_MAX_CHANNELS_PER_USER", 3)
RAID_MAX_ROLES_PER_USER = _int("RAID_MAX_ROLES_PER_USER", 3)
AUTO_REVERT_RAID_ACTIONS = os.getenv("AUTO_REVERT_RAID_ACTIONS", "false").lower() == "true"


# Welcome / invite greeting settings
WELCOME_CHANNEL_ID = _int("WELCOME_CHANNEL_ID")
WELCOME_ROLE_ID = _int("WELCOME_ROLE_ID")
WELCOME_MESSAGE = os.getenv(
    "WELCOME_MESSAGE",
    "{user} — Новый пользователь!\n\n**{count}** Число пользователей сервера."
)
SHOW_MEMBER_COUNT = os.getenv("SHOW_MEMBER_COUNT", "true").lower() == "true"

PARTNERSHIP_CATEGORY_NAME = os.getenv("PARTNERSHIP_CATEGORY_NAME", "✦ Partnerships ✦")
PARTNERSHIP_RULES_URL = os.getenv("PARTNERSHIP_RULES_URL", "").strip()

# Cooldown for repeated join-raid alerts (seconds).
RAID_ALERT_COOLDOWN_SECONDS = _int("RAID_ALERT_COOLDOWN_SECONDS", 120)

# IDs of server creators/co-owners who receive security DMs and are protected from mentions.
# The actual Discord guild owner is always included automatically.
OWNER_USER_IDS = _ids("OWNER_USER_IDS")
OWNER_MENTION_TIMEOUT_SECONDS = 3600

# Cross-webhook anti-raid (guild-wide, includes different webhook IDs/channels).
WEBHOOK_WINDOW_SECONDS = _int('WEBHOOK_WINDOW_SECONDS', 10)
WEBHOOK_MESSAGE_LIMIT = _int('WEBHOOK_MESSAGE_LIMIT', 6)
WEBHOOK_DISTINCT_LIMIT = _int('WEBHOOK_DISTINCT_LIMIT', 3)
WEBHOOK_ALLOWED_IDS = set(_ids('WEBHOOK_ALLOWED_IDS'))
WEBHOOK_DELETE_MESSAGES = os.getenv('WEBHOOK_DELETE_MESSAGES', 'true').lower() == 'true'
WEBHOOK_DELETE_ON_DETECTION = os.getenv('WEBHOOK_DELETE_ON_DETECTION', 'true').lower() == 'true'
