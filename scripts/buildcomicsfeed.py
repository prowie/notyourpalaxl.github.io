#!/usr/bin/env python3

import html
import re
import subprocess
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET

REPOROOT = Path(__file__).resolve().parents[1]
URL = "http://www.yourpalaxl.com" # No trailing /

def getFileDate(path: Path) -> datetime:
    relative = path.relative_to(REPOROOT).as_posix()

    def getGitDate(*arguments: str) -> datetime | None:
        output = subprocess.run(["git", "log", "--follow", *arguments, "--format=%aI", "--", relative], cwd=REPOROOT, capture_output=True, text=True, check=False)

        dates = output.stdout.splitlines()
        if not dates:
            return None

        return datetime.fromisoformat(dates[-1]).astimezone(timezone.utc) # last date output is oldest in the git log, so comics stay in the right order of creation

    date = getGitDate("--diff-filter=A")
    if date is None:
        date = getGitDate()

    if date is None:
        date = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    return date

def getMimeType(path: Path) -> str:
    types = {
        ".gif": "image/gif",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg"
    }
    return types[path.suffix.lower()]

def main() -> None:
    comics = []
    archivedir = REPOROOT / "callie_online" / "archive"
    if archivedir.exists():
        for path in archivedir.rglob("printable/*"):
            if path.is_file() and path.suffix.lower() in {".gif", ".png", ".jpg"}:
                comics.append((getFileDate(path), path))

    comics.sort(key=lambda entry: (entry[0], entry[1].as_posix()), reverse=True)

    rss = ET.Element("rss", {"version": "2.0", "xmlns:atom": "http://www.w3.org/2005/Atom"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Callie Online"
    ET.SubElement(channel, "link").text = URL + "/callie_online/"
    ET.SubElement(channel, "description").text = "The Vionan Route Of The Information Superhighway"
    ET.SubElement(channel, "language").text = "en-gb"
    ET.SubElement(channel, "atom:link", { "href": URL + "/callie_online/feed.xml", "rel": "self", "type": "application/rss+xml" } )
    author = ET.SubElement(channel, "atom:author")
    ET.SubElement(author, "atom:name").text = "Axl Woodland"

    if comics:
        ET.SubElement(channel, "lastBuildDate").text = format_datetime(max(date for date, _ in comics), usegmt=True)

    for published, path in comics:
        words = re.sub(r"[_-]+", " ", path.stem).strip()
        title = words.title() or path.stem

        relative = path.relative_to(REPOROOT).as_posix()
        link = f"{URL}/{quote(relative, safe='/')}"

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = link
        ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = link
        ET.SubElement(item, "pubDate").text = format_datetime(published, usegmt=True)

        desc = (
            f'<p><a href="{html.escape(link, quote=True)}"><img src="{html.escape(link, quote=True)}"></a></p>'
        )
        ET.SubElement(item, "description").text = desc

        ET.SubElement(item, "enclosure", {
                "url": link,
                "length": str(path.stat().st_size),
                "type": getMimeType(path)
            }
        )
    ET.indent(rss, space="  ")
    stringrss = ET.tostring(rss, encoding="unicode", short_empty_elements=True)
    output = REPOROOT / "callie_online" / "feed.xml"
    output.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + stringrss + "\n", encoding="utf-8", newline="\n")
    print(f"Gen: {len(comics)}")

if __name__ == "__main__":
    main()