import re
import time
from collections import defaultdict, deque
import discord
from config import (
    SPAM_WINDOW_SECONDS, SPAM_LIMIT_PER_WINDOW, SPAM_MIN_INTERVAL_SECONDS,
    SPAM_TIMEOUT_SECONDS, SPAM_MAX_MENTIONS_PER_MESSAGE,
    SPAM_MAX_ATTACHMENTS_PER_MESSAGE, SPAM_MAX_EMOJI_PER_MESSAGE,
    SPAM_MAX_REPEATED_WORDS, SPAM_MAX_REPEATED_SYMBOLS,
    SPAM_MAX_REPEATED_LETTERS
)
from services.permissions import is_admin
from services.moderation import apply_timeout
from services.logs import send_raid_log

class SpamGuard:
    def __init__(self):
        self.messages = defaultdict(deque)
        self.recent_texts = defaultdict(deque)

    def is_exempt(self, member: discord.Member) -> bool:
        return member.bot or is_admin(member)

    def check(self, message: discord.Message):
        text = message.content or ""
        member = message.author
        key = (message.guild.id, member.id)

        if len(message.mentions) > SPAM_MAX_MENTIONS_PER_MESSAGE:
            return True, f"Слишком много упоминаний ({len(message.mentions)})"
        if len(message.attachments) > SPAM_MAX_ATTACHMENTS_PER_MESSAGE:
            return True, f"Слишком много вложений ({len(message.attachments)})"

        emoji_count = len(re.findall(r"<a?:[A-Za-z0-9_]+:\d+>|[\U0001F300-\U0001FAFF]", text))
        if emoji_count > SPAM_MAX_EMOJI_PER_MESSAGE:
            return True, f"Слишком много эмодзи ({emoji_count})"

        words = re.findall(r"\w+", text.lower())
        if words:
            most_common = max(words.count(w) for w in set(words))
            if most_common > SPAM_MAX_REPEATED_WORDS:
                return True, f"Повторяющиеся слова ({most_common})"

        # Check only long runs of the same character, not ordinary punctuation.
        if re.search(r"(.)\1{" + str(SPAM_MAX_REPEATED_SYMBOLS) + r",}", text):
            return True, "Слишком длинная последовательность одинаковых символов"
        if re.search(r"([A-Za-zА-Яа-яЁё])\1{" + str(SPAM_MAX_REPEATED_LETTERS) + r",}", text):
            return True, "Подозрительно длинная последовательность одинаковых букв"

        now = time.monotonic()
        queue = self.messages[key]
        while queue and queue[0] < now - SPAM_WINDOW_SECONDS:
            queue.popleft()
        previous = queue[-1] if queue else None
        queue.append(now)

        if len(queue) > SPAM_LIMIT_PER_WINDOW:
            return True, f"Превышен лимит сообщений: {len(queue)} за {SPAM_WINDOW_SECONDS} сек."
        normalized = ' '.join(text.casefold().split())
        if normalized and len(normalized) >= 8:
            recent = self.recent_texts[key]
            while recent and recent[0][0] < now - SPAM_WINDOW_SECONDS:
                recent.popleft()
            recent.append((now, normalized))
            if sum(1 for _, value in recent if value == normalized) >= 3:
                return True, "Повторение одинакового сообщения трижды"
        # One quick message is not sufficient evidence of spam.
        if len(queue) >= 4 and queue[-1] - queue[-4] < 3 * SPAM_MIN_INTERVAL_SECONDS:
            return True, "Четыре сообщения отправлены слишком быстро"
        return False, ""

    async def handle(self, message: discord.Message, reason: str, bot):
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

        member = message.author
        timed_out = await apply_timeout(member, SPAM_TIMEOUT_SECONDS, f"Anti-spam: {reason}", bot)
        embed = discord.Embed(
            title="Обнаружен спам",
            description=f"Участник: {member.mention} (`{member.id}`)\nПричина: {reason}\nТайм-аут: {'выдан' if timed_out else 'не удалось выдать'}",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        await send_raid_log(bot, embed=embed)
        try:
            await member.send(f"⚠️ Антиспам обнаружил подозрительную активность.\nПричина: {reason}\nТайм-аут: {SPAM_TIMEOUT_SECONDS} сек.")
        except (discord.Forbidden, discord.HTTPException):
            pass
