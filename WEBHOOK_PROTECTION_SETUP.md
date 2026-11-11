# Webhook Anti-Raid

The bot tracks webhook messages across the **entire guild**, including messages from different webhook IDs and channels.

Default triggers (either condition): 6 messages in 10 seconds, or 3 distinct webhook IDs in 10 seconds. When triggered, it attempts to delete observed messages and the participating webhooks. The owner(s) receive a DM and the configured raid log channel receives an alert. Alerts are rate-limited.

Add these optional settings to your `.env`:

```env
WEBHOOK_WINDOW_SECONDS=10
WEBHOOK_MESSAGE_LIMIT=6
WEBHOOK_DISTINCT_LIMIT=3
WEBHOOK_ALLOWED_IDS=
WEBHOOK_DELETE_MESSAGES=true
WEBHOOK_DELETE_ON_DETECTION=true
```

Put comma-separated trusted webhook IDs in `WEBHOOK_ALLOWED_IDS`; they are ignored and never deleted by this guard. Set the two deletion flags to `false` to run alert-only testing first.

Required permissions: View Channel, Read Message History, Manage Messages, Manage Webhooks. Enable Message Content Intent and Server Members Intent in the Discord Developer Portal for other protections. Configure OWNER_USER_IDS for co-owner DMs; the guild owner is notified automatically. DMs may fail when users block the bot.

**Important:** Detection is based on activity thresholds and can affect legitimate multi-webhook integrations. Start in alert-only mode, adjust thresholds and allowlist legitimate integrations before enabling deletion. A bot cannot undo messages already delivered to external services. Discord API errors and missing permissions are logged in `bot.log`.
