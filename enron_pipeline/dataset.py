"""Download the Enron tarball and extract only the chosen mailboxes.

Every file in the archive is named like ``1.`` (trailing dot). Windows silently
drops trailing dots, so path components are normalized explicitly (``1.`` -> ``1``)
to get identical paths on every OS. This also matches the spec's example path
``maildir/lay-k/inbox/45``.

Members are written one by one from the stream instead of using ``extractall``,
so only regular files under ``maildir/<chosen mailbox>/`` are ever written and
path traversal (``..``, absolute paths, links) is impossible.
"""
from __future__ import annotations

import json
import logging
import shutil
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Iterable

from . import config

log = logging.getLogger(__name__)

MARKER_NAME = ".extracted.json"


def download(url: str = config.DATASET_URL, dest: Path = config.TARBALL_PATH) -> Path:
    """Download the dataset tarball unless it is already present."""
    if dest.exists() and dest.stat().st_size > 0:
        log.info("Tarball already present: %s", dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    log.info("Downloading %s (about 420 MB, takes a few minutes)", url)
    with urllib.request.urlopen(url) as resp, open(tmp, "wb") as fh:
        shutil.copyfileobj(resp, fh, length=1024 * 1024)
    tmp.replace(dest)
    return dest


def safe_relative_path(member_name: str, mailboxes: set[str]) -> PurePosixPath | None:
    """Map an archive member name to a normalized relative path, or None to skip it.

    Keeps only ``maildir/<mailbox>/...`` entries for the chosen mailboxes, rejects
    any traversal component and strips trailing dots/spaces from every component.
    """
    parts = PurePosixPath(member_name).parts
    if len(parts) < 3 or parts[0] != "maildir" or parts[1] not in mailboxes:
        return None
    cleaned = []
    for part in parts:
        if part in ("", ".", "..") or "/" in part or "\\" in part:
            return None
        part = part.rstrip(". ")
        if not part:
            return None
        cleaned.append(part)
    return PurePosixPath(*cleaned)


def _read_marker(marker: Path) -> dict:
    try:
        return json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def extract_mailboxes(
    tar_path: Path = config.TARBALL_PATH,
    data_dir: Path = config.DATA_DIR,
    mailboxes: Iterable[str] = config.MAILBOXES,
) -> dict[str, int]:
    """Extract the chosen mailboxes into ``data_dir/maildir``. Returns files per mailbox.

    Skips the work when a marker file shows the same mailbox set was already extracted.
    """
    mailboxes = tuple(mailboxes)
    maildir = data_dir / "maildir"
    marker = maildir / MARKER_NAME
    info = _read_marker(marker)
    if sorted(info.get("mailboxes", [])) == sorted(mailboxes):
        log.info("Mailboxes already extracted (%s files), skipping", info.get("total"))
        return info["counts"]

    wanted = set(mailboxes)
    counts = {box: 0 for box in mailboxes}
    seen: set[PurePosixPath] = set()
    log.info("Extracting %d mailboxes from %s", len(mailboxes), tar_path)
    with tarfile.open(tar_path, "r:gz") as tf:
        for member in tf:
            if not member.isfile():
                continue
            rel = safe_relative_path(member.name, wanted)
            if rel is None:
                continue
            if rel in seen:
                log.warning("Name collision after normalizing, skipped: %s", member.name)
                continue
            seen.add(rel)
            src = tf.extractfile(member)
            if src is None:
                continue
            target = data_dir.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            counts[rel.parts[1]] += 1

    maildir.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({"mailboxes": list(mailboxes), "counts": counts, "total": sum(counts.values())}, indent=1),
        encoding="utf-8",
    )
    log.info("Extracted %d files", sum(counts.values()))
    return counts


def ensure_dataset() -> dict[str, int]:
    """Download (if needed) and extract (if needed) the chosen mailboxes."""
    download()
    return extract_mailboxes()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = ensure_dataset()
    print(json.dumps(result, indent=1), "total", sum(result.values()))
