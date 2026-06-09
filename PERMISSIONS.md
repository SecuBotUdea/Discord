Required Discord intents and permissions for reaction-based rescan UX

Intents (Bot application settings + client):
- Guilds: to receive guild information
- Guild Messages / Message Content: to fetch messages (if needed)
- Message Reactions: for raw reaction events (on_raw_reaction_add)

Permissions the bot needs in the guild (role or webhook owner):
- Send Messages: to publish alerts and DMs
- Manage Messages: required to remove reactions from messages (to hide reaction when points are lost)
- Read Message History / View Channel: to fetch messages when necessary

Operational notes:
- `on_raw_reaction_add` works even if the message is not in cache, but the bot will need `fetch_channel` and `fetch_message` permissions to remove reactions.
- When deploying, ensure the bot role has `Manage Messages` in channels where alerts are posted, or the reaction removal will silently fail.

Testing locally:
- Run tests from the project root so imports resolve correctly:

```bash
python -m pytest -q
```

- If running a single test file from an editor, ensure the PYTHONPATH includes the project root, or run:

```bash
PYTHONPATH=. python -m pytest tests/test_alert_message_repository.py -q
```

Security:
- Removing reactions requires higher privileges; document this change in release notes so server admins can consent.
