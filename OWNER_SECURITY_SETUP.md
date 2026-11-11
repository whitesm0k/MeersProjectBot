# Security alerts / owner mentions

In your hosting environment or `.env` set `OWNER_USER_IDS=123456789012345678,234567890123456789` to identify additional co-owners. The Discord guild owner is included automatically; do not add them twice. IDs must be numeric, not @names. Without OWNER_USER_IDS only the actual guild owner receives alerts and is protected from direct mentions.

Spam: timeout **600 seconds (10 minutes)**. Directly mentioning the guild owner or any configured co-owner: timeout **3600 seconds (1 hour)** for ordinary members. Admins, bot accounts and users exempted by the existing `is_admin` check are excluded. This protection applies to explicit user mentions, not replies, role mentions or `@everyone`.

Security alerts about spam, join floods, suspicious channel/role creation and webhook creation go to the configured raid log channel and to the owners' DMs. Discord users can disable DMs from server members; such failures are logged to `bot.log`.

Enable Message Content Intent and Server Members Intent in Discord Developer Portal. Grant the bot Manage Messages and Moderate Members and place its role above ordinary members. The bot cannot timeout the server owner, administrators or members with equal/higher roles.

**Testing:** Use a non-admin test account. Send 7 messages in 10 seconds (or 3 identical messages) and check for a 10-minute timeout and owner DM. After timeout expires, mention a configured owner and check for a 1-hour timeout and DM. For raid alerts, test in a dedicated server. Actual live Discord behavior is not tested in this package.
