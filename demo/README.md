# Demo output

These files are static samples rendered by MyArxiv. They let you see the output without configuring an API key or sending email.

| File | What it shows |
|---|---|
| `report.html` | Responsive HTML email digest. Open it in a browser. |
| `report.txt` | Plain-text alternative sent as the `text/plain` part. |
| `report.png` | Screenshot of the digest header and first paper, used in the README. |
| `tui.txt` | Illustrative terminal session for `python update.py`. |

The account name and email addresses are placeholders; paper titles, authors, abstracts and links are public arXiv metadata. The papers shown are a fixed snapshot and are not fetched when you open the demo.

## Regenerate

```bash
cp config.example.yaml config.yaml
cp .env.example .env          # add a real API key
python -m src.main --dry-run  # writes daily_report.html and daily_report.txt
```

The demo is not regenerated automatically, so a documentation-only change cannot trigger LLM calls or email.
