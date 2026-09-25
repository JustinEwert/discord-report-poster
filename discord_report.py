#!/usr/bin/env python3
"""
discord_report.py - Post a PDF or text report into a Discord channel.

It reads the file, turns the text into Discord embeds (split automatically
to respect Discord's size limits), and attaches the original file to the
first message. Optionally renders page 1 of a PDF as a preview image.

Usage:
    python discord_report.py report.pdf
    python discord_report.py report.txt --title "Daily Report" --monospace
    python discord_report.py report.pdf --preview --summary "Markets up 1.2%"
    python discord_report.py report.pdf --dry-run
"""
import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Discord limits (see README for details)
DESC_LIMIT = 4096        # characters per embed description
MSG_TOTAL_LIMIT = 6000   # characters across all embeds in one message
MAX_EMBEDS = 10          # embeds per message
MAX_UPLOAD_MB = 10       # upload cap on a non-boosted server
CHUNK_SIZE = 3500        # chunk size, leaves headroom under DESC_LIMIT

TEXT_TYPES = {".txt", ".md", ".log", ".csv"}


# ---------- reading the report ----------

def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_TYPES:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        import pymupdf
        with pymupdf.open(path) as doc:
            return "\n\n".join(page.get_text() for page in doc)
    sys.exit(f"Unsupported file type '{suffix}'. Use a PDF or a text file.")


def render_first_page(pdf_path: Path, out_path: Path, zoom: float = 1.5) -> Path:
    import pymupdf
    with pymupdf.open(pdf_path) as doc:
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        pix.save(out_path)
    return out_path


# ---------- building embeds ----------

def split_text(text: str, size: int) -> list[str]:
    """Split text into chunks <= size, preferring paragraph, then line, then word breaks."""
    text = text.strip()
    chunks = []
    while len(text) > size:
        cut = -1
        for sep in ("\n\n", "\n", " "):
            cut = text.rfind(sep, 0, size)
            if cut >= size * 0.5:
                break
        if cut <= 0:
            cut = size
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


def build_embeds(title, chunks, color, source_name, monospace):
    embeds = []
    total = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        desc = f"```\n{chunk}\n```" if monospace else chunk
        embed = {"description": desc[:DESC_LIMIT], "color": color}
        if i == 1:
            embed["title"] = title[:256]
            embed["timestamp"] = datetime.now(timezone.utc).isoformat()
        footer = source_name if total == 1 else f"{source_name} · part {i}/{total}"
        embed["footer"] = {"text": footer[:2048]}
        embeds.append(embed)
    return embeds


def embed_size(embed):
    return (len(embed.get("title", ""))
            + len(embed.get("description", ""))
            + len(embed.get("footer", {}).get("text", "")))


def group_into_messages(embeds):
    """Pack embeds into messages without exceeding per-message limits."""
    groups, current, size = [], [], 0
    for e in embeds:
        s = embed_size(e)
        if current and (len(current) >= MAX_EMBEDS or size + s > MSG_TOTAL_LIMIT):
            groups.append(current)
            current, size = [], 0
        current.append(e)
        size += s
    if current:
        groups.append(current)
    return groups


# ---------- sending ----------

def post(webhook, payload, files=()):
    url = webhook + ("&" if "?" in webhook else "?") + "wait=true"
    for _ in range(5):
        handles = [open(p, "rb") for p in files]
        try:
            if handles:
                multipart = {
                    f"files[{i}]": (Path(p).name, h)
                    for i, (p, h) in enumerate(zip(files, handles))
                }
                r = requests.post(url, data={"payload_json": json.dumps(payload)},
                                  files=multipart, timeout=60)
            else:
                r = requests.post(url, json=payload, timeout=30)
        finally:
            for h in handles:
                h.close()

        if r.status_code == 429:  # rate limited: wait and retry
            wait = float(r.json().get("retry_after", 1))
            print(f"Rate limited, waiting {wait:.1f}s...")
            time.sleep(wait)
            continue
        if r.status_code >= 400:
            sys.exit(f"Discord returned {r.status_code}: {r.text}")
        return r
    sys.exit("Gave up after repeated rate limits.")


# ---------- main ----------

def parse_color(value: str) -> int:
    return int(value.lstrip("#"), 16)


def main():
    p = argparse.ArgumentParser(description="Post a PDF or text report to Discord via webhook.")
    p.add_argument("file", type=Path, help="Path to the .pdf or .txt report")
    p.add_argument("--title", help="Embed title (default: file name)")
    p.add_argument("--summary", help="Use this text instead of the file's full text")
    p.add_argument("--max-parts", type=int, default=0,
                   help="Only post the first N text chunks (0 = all)")
    p.add_argument("--color", default="#3498db", help="Embed color as hex (default #3498db)")
    p.add_argument("--monospace", action="store_true",
                   help="Wrap text in code blocks to keep column alignment")
    p.add_argument("--preview", action="store_true",
                   help="Render PDF page 1 as an image inside the first embed")
    p.add_argument("--no-attach", action="store_true", help="Don't attach the original file")
    p.add_argument("--username", help="Override the webhook's display name")
    p.add_argument("--webhook", default=os.getenv("DISCORD_WEBHOOK_URL"),
                   help="Webhook URL (default: DISCORD_WEBHOOK_URL from .env)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be sent without posting")
    args = p.parse_args()

    path = args.file
    if not path.exists():
        sys.exit(f"File not found: {path}")
    if not args.webhook and not args.dry_run:
        sys.exit("No webhook URL. Set DISCORD_WEBHOOK_URL in .env or pass --webhook.")

    # 1. Get the text
    text = args.summary if args.summary else extract_text(path)
    if not text.strip():
        print("Warning: no extractable text (the PDF may be scanned images).")
        text = "_No text could be extracted. See the attached file._"

    chunk_size = CHUNK_SIZE - (8 if args.monospace else 0)
    chunks = split_text(text, chunk_size)
    if args.max_parts > 0 and len(chunks) > args.max_parts:
        chunks = chunks[:args.max_parts]
        chunks[-1] += "\n\n_…truncated. Full report attached._"

    # 2. Build embeds and group them into messages
    embeds = build_embeds(args.title or path.stem, chunks, parse_color(args.color),
                          path.name, args.monospace)
    messages = group_into_messages(embeds)

    # 3. Work out attachments for the first message
    first_files = []
    tmpdir = tempfile.mkdtemp()
    if args.preview:
        if path.suffix.lower() == ".pdf":
            png = render_first_page(path, Path(tmpdir) / "preview.png")
            first_files.append(str(png))
            messages[0][0]["image"] = {"url": "attachment://preview.png"}
        else:
            print("Note: --preview only works with PDFs; skipping.")
    if not args.no_attach:
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_UPLOAD_MB:
            print(f"Warning: {path.name} is {size_mb:.1f} MB (over {MAX_UPLOAD_MB} MB); not attaching.")
        else:
            first_files.append(str(path))

    # 4. Send (or preview)
    for i, group in enumerate(messages):
        payload = {"embeds": group}
        if args.username:
            payload["username"] = args.username
        files = first_files if i == 0 else []

        if args.dry_run:
            print(f"--- message {i + 1}/{len(messages)} "
                  f"({len(group)} embed(s), files: {[Path(f).name for f in files]}) ---")
            print(json.dumps(payload, indent=2)[:1500])
            continue

        post(args.webhook, payload, files)
        print(f"Posted message {i + 1}/{len(messages)}")
        if i < len(messages) - 1:
            time.sleep(1)  # keep messages in order and stay under rate limits

    if not args.dry_run:
        print("Done.")


if __name__ == "__main__":
    main()
