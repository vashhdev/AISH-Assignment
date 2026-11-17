# AISH Assignment

Enron email pipeline: parse raw maildir emails into structured records, store them in SQLite, detect duplicates, and send notification emails through a Gmail MCP server.

Status: Task 1 (data extraction) is done. Database storage, duplicate detection and MCP notifications are in progress. Full setup, architecture and design notes will be added here as the work completes.

## Quick start (current)
```
python -m venv .venv
.venv\Scripts\activate        # Windows; use `source .venv/bin/activate` elsewhere
pip install -r requirements.txt
python main.py                # first run downloads the dataset (~443 MB) and extracts 5 mailboxes
python -m pytest
```

Outputs so far: `error_log.txt` (parse failures) and `output/extraction_stats.json` (extraction statistics).
