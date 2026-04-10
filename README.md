# Lenny's Book Recs

A curated collection of **103 books** recommended by guests on [Lenny's Podcast](https://www.lennysnewsletter.com/podcast) — product managers, founders, operators, and investors sharing what they've actually read.

**Live site →** [lisaqiyali-0105.github.io/lennys-book-recs](https://lisaqiyali-0105.github.io/lennys-book-recs/)

---

## What it is

Every book is sourced directly from transcript mentions, with the guest's actual reason for recommending it. Filter by category, hover (or tap on mobile) to see the quote, click to buy on Amazon.

**8 categories:** Product & Design · Leadership · Strategy · Growth · Behavioral · Personal · Fiction & Memoir · Writing

---

## How it's built

- **Single source of truth:** `data/books.json` — all book data lives here
- **No backend:** pure HTML/CSS/JS, served via GitHub Pages
- **Covers:** downloaded locally to `covers/` — no external image URLs at runtime
- **Auto-updates:** `scripts/update-books.py` runs on a cron schedule, reads new podcast transcripts via the lennysdata MCP, and pushes new books automatically

### Making manual updates

Edit `data/books.json`, then rebuild:

```bash
python3 scripts/update-books.py
```

Or rebuild HTML only (no episode check):

```python
python3 << 'EOF'
import json, re
from pathlib import Path

REPO = Path(".")
with open(REPO / "data/books.json") as f:
    books = json.load(f)

books_json = json.dumps(books, indent=2, ensure_ascii=False)
for html_path in [REPO / "books.html", REPO / "index.html"]:
    with open(html_path) as f:
        html = f.read()
    new_html = re.sub(r'const BOOKS\s*=\s*\[[\s\S]*?\];', f'const BOOKS = {books_json};', html, count=1)
    with open(html_path, "w") as f:
        f.write(new_html)
    print(f"Rebuilt {html_path.name}")
EOF
```

### Book entry format

```json
{
  "title": "Book Title",
  "author": "Author Name",
  "category": "Product & Design",
  "recommenders": ["Guest Name"],
  "reason": "Why the guest recommended it, in their own words.",
  "cover": "covers/book-title.jpg"
}
```

`cover` must be a local file path — never a remote URL.

---

## Repo structure

```
books.html          Main page (also served as index.html)
index.html          Copy of books.html — GitHub Pages root
data/
  books.json        All book data (edit this, not the HTML)
  state.json        Tracks last-processed episode date for the auto-updater
covers/             Local cover images (one .jpg per book)
scripts/
  update-books.py   Auto-updater: checks for new episodes, extracts books, rebuilds HTML
  run-update.sh     Shell wrapper for cron
```

---

## Deploying

```bash
git add data/books.json books.html index.html covers/
git commit -m "your message"
git push origin main
```

GitHub Pages deploys automatically in ~2 minutes. Always do a visual QA pass locally before pushing — open `books.html` and check covers, filters, and hover states.
