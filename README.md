# Discord Report Poster

Posts a PDF or text report into a Discord channel as formatted embeds, with the original file attached.

## 1. Create a Discord webhook
1. Discord → **Server Settings → Integrations → Webhooks → New Webhook**
2. Pick the channel, name it (e.g. "Report Bot"), click **Copy Webhook URL**
3. Treat the URL like a password.

## 2. Set up the project
```bash
cd discord-report-poster
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then paste your webhook URL into .env
```

## 3. Try it
```bash
# Preview without posting
python discord_report.py samples/sample_report.pdf --dry-run

# Post for real
python discord_report.py samples/sample_report.pdf --preview
python discord_report.py samples/sample_report.txt --title "Daily Report" --monospace
```

## Options
| Flag | What it does |
|---|---|
| `--title "..."` | Embed title (default: file name) |
| `--summary "..."` | Post this text instead of the full file text |
| `--max-parts N` | Only post the first N chunks of text |
| `--monospace` | Wrap text in code blocks (keeps tables/columns aligned) |
| `--preview` | Show PDF page 1 as an image in the embed |
| `--no-attach` | Don't attach the original file |
| `--color "#hex"` | Embed color |
| `--username "..."` | Override the webhook's display name |
| `--dry-run` | Print the payload instead of posting |

## Discord limits the script handles
- Embed description: 4,096 chars → long text is split into multiple embeds
- 6,000 chars total / 10 embeds per message → split across multiple messages
- File uploads over ~10 MB (non-boosted server) are skipped with a warning
- Rate limits (HTTP 429) are retried automatically

## Scanned PDFs
If a PDF is just images, no text can be extracted. Use `--preview` and `--summary` instead.
