"""Central configuration: paths, dataset source and the chosen mailbox subset."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MAILDIR = DATA_DIR / "maildir"
OUTPUT_DIR = PROJECT_ROOT / "output"

DATASET_URL = "https://www.cs.cmu.edu/~enron/enron_mail_20150507.tar.gz"
TARBALL_PATH = DATA_DIR / "enron_mail_20150507.tar.gz"

# Chosen subset (5 mailboxes, 23,554 files). Reasoning is documented in README.md:
# mix of roles (two CEOs, an executive, two traders) and of mailbox styles
# (Lotus Notes era all_documents/_sent_mail folders vs Outlook era inbox/sent_items),
# with plenty of the same message stored in several folders for duplicate detection.
MAILBOXES = ("lay-k", "skilling-j", "kitchen-l", "arnold-j", "allen-p")
