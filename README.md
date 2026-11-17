# AISH Assignment

Enron email pipeline: parse raw maildir emails into structured records, store them in SQLite, detect duplicates, and send notification emails through a Gmail MCP server.

Status: Tasks 1-4 (extraction, database, duplicate detection, MCP notifications) are done. Final documentation is in progress. Full setup, architecture and design notes will be added here as the work completes.

## Quick start (current)
```
python -m venv .venv
.venv\Scripts\activate        # Windows; use `source .venv/bin/activate` elsewhere
pip install -r requirements.txt
python main.py                # first run downloads the dataset (~443 MB); extracts, parses, loads and deduplicates
python -m enron_pipeline.queries   # run sample_queries.sql against the database
python main.py --send-live --limit 1   # needs the Gmail MCP setup and NOTIFY_LIVE_TO in .env
python -m pytest
```

`python main.py --reset-db` rebuilds the database from scratch (clears duplicate flags and notification history).

Outputs so far:
- `error_log.txt`: parse failures (file path and reason)
- `output/extraction_stats.json`: extraction statistics and field completeness
- `output/enron.db`: SQLite database (schema in `schema.sql`, not committed)
- `output/db_stats.json`: database load statistics
- `duplicates_report.csv`: one row per flagged duplicate with its original and similarity score
- `output/dedup_stats.json`: duplicate detection statistics
- `output/replies/`: one draft notification `.eml` per flagged duplicate
- `output/send_log.csv`: live send attempts
