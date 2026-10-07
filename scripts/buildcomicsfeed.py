#!/usr/bin/env python3

from __future__ import annotations

import html
import re
import subprocess
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET

REPOROOT = Path(__file__).resolve().parents[1]
URL = "http://www.yourpalaxl.com/callie_online" # No trailing / here

def getFileDate(path: Path) -> datetime:
    relativePath = path.relative_to(REPOROOT).as_posix()
    cmds = [
        ["git", "log", "--follow", "--diff-filter=A", "--format=%aI", "--", relativePath],
        ["git", "log", "--follow", "--format=%aI", "--", relativePath],
    ]

    for command in cmds:
        result = subprocess.run(command, cwd=REPOROOT, check=False, capture_output=True, text=True)
        dates = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if dates:
            return datetime.fromisoformat(dates[-1]).astimezone(timezone.utc)
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

def getComicTitle(path: Path) -> str:
    words = re.sub(r"[_-]+", " ", path.stem).strip()
    return words.title() or path.stem

def getPublicURL(path: Path) -> str:
    relative = path.relative_to(REPOROOT).as_posix()
    return f"{URL}/{quote(relative, safe='/')}"

def getMimeType(path: Path) -> str:
    MIMETypes = {
        ".gif": "image/gif",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg"
    }
    return MIMETypes[path.suffix.lower()]

def addIdent(element: ET.Element, level: int = 0) -> None: # gotta have pretty feeds
    spacing = "\n" + "  " * level
    if len(element):
        if not element.text or not element.text.strip():
            element.text = spacing + "  "
        for child in element:
            addIdent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = spacing
    if level and (not element.tail or not element.tail.strip()):
        element.tail = spacing

def main() -> None:
    comics = []
    ARCHIVEROOT = REPOROOT / "callie_online" / "archive"
    if ARCHIVEROOT.exists():
        for path in ARCHIVEROOT.rglob("printable/*"):
            if path.is_file() and path.suffix.lower() in {".gif", ".png", ".jpg"}:
                comics.append((getFileDate(path), path))

    comics.sort(key=lambda entry: (entry[0], entry[1].as_posix()), reverse=True)

    rss = ET.Element("rss", {"version": "2.0", "xmlns:atom": "http://www.w3.org/2005/Atom"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Callie Online"
    ET.SubElement(channel, "link").text = URL + "/"
    ET.SubElement(channel, "description").text = "The Vionan Route Of The Information Superhighway"
    ET.SubElement(channel, "language").text = "en-gb"
    ET.SubElement(channel, "atom:link", { "href": URL + "/callie_online/feed.xml", "rel": "self", "type": "application/rss+xml" } )

    if comics:
        ET.SubElement(channel, "lastBuildDate").text = format_datetime(max(date for date, _ in comics), usegmt=True)

    for published, path in comics:
        title = getComicTitle(path)
        url = getPublicURL(path)
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = url
        ET.SubElement(item, "pubDate").text = format_datetime(published, usegmt=True)
        ET.SubElement(item, "author").text = "Axl Woodland"
        desc = (
            f'<p><a href="{html.escape(url, quote=True)}">'
            f'<img src="{html.escape(url, quote=True)}" '
            f'alt="{html.escape(title, quote=True)}"></a></p>'
        )
        ET.SubElement(item, "description").text = desc
        ET.SubElement(item, "enclosure", { "url": url, "length": str(path.stat().st_size), "type": getMimeType(path) })

    addIdent(rss)
    xml_body = ET.tostring(rss, encoding="unicode", short_empty_elements=True)
    outputFile = REPOROOT / "callie_online" / "feed.xml"
    outputFile.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Gen: {len(comics)}")


if __name__ == "__main__":
    main()
