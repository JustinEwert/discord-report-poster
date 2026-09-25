# Project context for Claude Code

Python CLI that posts PDF/text reports to a Discord channel via webhook.

- Entry point: `discord_report.py` (single file, argparse CLI)
- Dependencies: requests, pymupdf (PDF text + page rendering), python-dotenv
- Config: `DISCORD_WEBHOOK_URL` in `.env` (never commit `.env`)
- Test safely with `--dry-run`; sample files are in `samples/`
- Respect Discord limits: 4096 chars/description, 6000 chars & 10 embeds/message, ~10 MB uploads

The owner is new to Git and professional workflows. Explain git commands when
suggesting them, and prefer small, reviewable changes.
