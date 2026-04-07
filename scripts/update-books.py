#!/usr/bin/env python3
"""
Lenny's Archive — Automated Book Updater
Checks lennysdata MCP for new podcast episodes and extracts book recommendations.
Run via cron every 2 days.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path(__file__).parent.parent
STATE_FILE = REPO_DIR / "data" / "state.json"
BOOKS_FILE = REPO_DIR / "data" / "books.json"
BOOKS_HTML  = REPO_DIR / "books.html"
INDEX_HTML  = REPO_DIR / "index.html"
LOG_FILE    = REPO_DIR / "data" / "update.log"

VALID_CATEGORIES = [
    "Product", "Strategy", "Leadership", "Growth",
    "Psychology", "Engineering", "Marketing", "Design", "Other"
]

# ── Logging ─────────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

# ── State ────────────────────────────────────────────────────────────────────

def load_state():
    with open(STATE_FILE) as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ── Books data ───────────────────────────────────────────────────────────────

def load_books():
    with open(BOOKS_FILE) as f:
        return json.load(f)

def save_books(books):
    with open(BOOKS_FILE, "w") as f:
        json.dump(books, f, indent=2, ensure_ascii=False)

# ── Claude CLI call ──────────────────────────────────────────────────────────

def run_claude(prompt: str) -> str:
    """
    Calls `claude --print` with the lennysdata MCP available.
    Returns the raw text output.
    """
    env = os.environ.copy()
    # Ensure Homebrew + local bin in PATH for cron environment
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")

    result = subprocess.run(
        ["claude", "--print", "--model", "claude-sonnet-4-6", prompt],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed:\n{result.stderr[:500]}")
    return result.stdout.strip()

# ── Extract books from a transcript via Claude ───────────────────────────────

EXTRACTION_PROMPT = """
You have access to the lennysdata MCP which has Lenny's Podcast transcripts.

Task: Read the podcast transcript for the file "{filename}" (guest: {guest}, date: {date}).
Use the read_content tool to get the full transcript.

Then extract ALL books mentioned in the conversation — whether recommended by the guest,
mentioned by Lenny, or referenced in passing. Include only real, published books with
a real title and author.

Return ONLY a valid JSON array (no markdown, no explanation). Each item:
{{
  "title": "Book Title",
  "author": "Author Name",
  "category": "one of: Product, Strategy, Leadership, Growth, Psychology, Engineering, Marketing, Design, Other",
  "recommender": "{guest}",
  "reason": "1-2 sentence summary of why they mentioned it or what they said about it. Do NOT use quotation marks — this is a summary, not a verbatim quote."
}}

If no books are mentioned, return an empty array: []
"""

def extract_books_from_episode(filename: str, guest: str, date: str) -> list:
    """Ask Claude to read a transcript and extract book recommendations."""
    prompt = EXTRACTION_PROMPT.format(filename=filename, guest=guest, date=date)
    log(f"  Extracting books from: {filename}")
    raw = run_claude(prompt)

    # Pull out JSON array from response
    match = re.search(r'\[[\s\S]*\]', raw)
    if not match:
        log(f"  WARNING: no JSON array found in response for {filename}")
        return []
    try:
        books = json.loads(match.group(0))
        log(f"  Found {len(books)} book(s)")
        return books
    except json.JSONDecodeError as e:
        log(f"  ERROR parsing JSON for {filename}: {e}")
        return []

# ── Find new episodes ────────────────────────────────────────────────────────

NEW_EPISODES_PROMPT = """
You have access to the lennysdata MCP.

Use the list_content tool with content_type="podcast" and limit=50 to list recent episodes.
Find all episodes with a date AFTER {last_date}.

Return ONLY a valid JSON array (no markdown). Each item:
{{
  "filename": "podcasts/guest-name.md",
  "guest": "Guest Name",
  "date": "YYYY-MM-DD",
  "title": "Episode title"
}}

If there are no new episodes, return: []
"""

def find_new_episodes(last_date: str) -> list:
    prompt = NEW_EPISODES_PROMPT.format(last_date=last_date)
    log(f"Checking for new episodes after {last_date}...")
    raw = run_claude(prompt)
    match = re.search(r'\[[\s\S]*\]', raw)
    if not match:
        log("No new episodes found (no JSON array in response)")
        return []
    try:
        episodes = json.loads(match.group(0))
        log(f"Found {len(episodes)} new episode(s)")
        return episodes
    except json.JSONDecodeError as e:
        log(f"ERROR parsing episodes JSON: {e}")
        return []

# ── Merge new books into existing list ───────────────────────────────────────

def merge_books(existing: list, new_books: list) -> tuple[list, int]:
    """
    Merge new books into existing list.
    If a book already exists (matched by title, case-insensitive), add the new
    recommender to its recommenders list. Otherwise append as a new entry.
    Returns (merged_list, count_added).
    """
    # Build lookup by normalized title
    index = {b["title"].lower().strip(): i for i, b in enumerate(existing)}
    added = 0

    for nb in new_books:
        title_key = nb["title"].lower().strip()
        if not nb.get("title") or not nb.get("author"):
            continue  # skip incomplete entries

        if title_key in index:
            # Book exists — add recommender if not already listed
            book = existing[index[title_key]]
            recs = book.get("recommenders", [])
            if nb["recommender"] not in recs:
                recs.append(nb["recommender"])
                book["recommenders"] = recs
                log(f"  + New recommender for '{nb['title']}': {nb['recommender']}")
        else:
            # New book
            category = nb.get("category", "Other")
            if category not in VALID_CATEGORIES:
                category = "Other"
            entry = {
                "title":        nb["title"],
                "author":       nb["author"],
                "category":     category,
                "recommenders": [nb["recommender"]],
                "reason":       nb.get("reason", ""),
            }
            existing.append(entry)
            index[title_key] = len(existing) - 1
            added += 1
            log(f"  + New book: '{nb['title']}' by {nb['author']}")

    return existing, added

# ── Rebuild HTML files ────────────────────────────────────────────────────────

def rebuild_html(books: list):
    """Inject updated books data back into books.html and index.html."""
    books_json = json.dumps(books, indent=2, ensure_ascii=False)

    for html_path in [BOOKS_HTML, INDEX_HTML]:
        with open(html_path) as f:
            html = f.read()

        new_html = re.sub(
            r'const BOOKS\s*=\s*\[[\s\S]*?\];',
            f'const BOOKS = {books_json};',
            html,
            count=1
        )

        if new_html == html:
            log(f"WARNING: could not find BOOKS array in {html_path.name}")
            continue

        with open(html_path, "w") as f:
            f.write(new_html)
        log(f"Rebuilt {html_path.name}")

# ── Git commit & push ─────────────────────────────────────────────────────────

def git_push(message: str):
    os.chdir(REPO_DIR)
    subprocess.run(["git", "add", "data/books.json", "data/state.json", "index.html", "books.html"], check=True)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if result.returncode == 0:
        log("Nothing to commit — no changes detected")
        return
    subprocess.run(["git", "commit", "-m", message], check=True)
    subprocess.run(["git", "push", "origin", "main"], check=True)
    log("Pushed to GitHub Pages")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log("=" * 50)
    log("Lenny's Archive update started")

    state   = load_state()
    books   = load_books()
    last_dt = state["last_processed_date"]

    new_episodes = find_new_episodes(last_dt)
    if not new_episodes:
        log("No new episodes. Done.")
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return

    total_added  = 0
    latest_date  = last_dt

    for ep in new_episodes:
        new_books_raw = extract_books_from_episode(
            ep["filename"], ep["guest"], ep["date"]
        )
        if new_books_raw:
            books, added = merge_books(books, new_books_raw)
            total_added += added

        # Track the furthest date we've processed
        if ep["date"] > latest_date:
            latest_date = ep["date"]

    if total_added > 0:
        save_books(books)
        rebuild_html(books)
        git_push(
            f"Auto-update: {total_added} new book(s) from {len(new_episodes)} episode(s)"
        )
    else:
        log("No new books found in new episodes")

    state["last_processed_date"] = latest_date
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["episodes_processed"] = state.get("episodes_processed", 293) + len(new_episodes)
    save_state(state)

    log(f"Done. {total_added} new book(s) added from {len(new_episodes)} episode(s).")

if __name__ == "__main__":
    main()
