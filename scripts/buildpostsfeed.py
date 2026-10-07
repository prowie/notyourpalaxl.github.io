#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import format_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin

REPOROOT = Path(__file__).resolve().parents[1]
POSTSROOT = REPOROOT / "posts"
OUTPUTFILE = REPOROOT / "posts.xml"
URL = "http://www.yourpalaxl.com"  # No trailing slash


class TitleParser(HTMLParser):
    """Extract text from the first HTML title element."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.inTitle = False
        self.foundTitle = False
        self.titleParts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.foundTitle and tag.lower() == "title":
            self.inTitle = True

    def handle_endtag(self, tag: str) -> None:
        if self.inTitle and tag.lower() == "title":
            self.inTitle = False
            self.foundTitle = True

    def handle_data(self, data: str) -> None:
        if self.inTitle:
            self.titleParts.append(data)

    def getTitle(self) -> str:
        return " ".join("".join(self.titleParts).split())


def getGitDate(path: Path) -> datetime:
    """Return the file's first Git author date, including time and offset."""
    relativePath = path.relative_to(REPOROOT).as_posix()
    commands = [
        ["git", "log", "--follow", "--diff-filter=A", "--format=%aI", "--", relativePath],
        ["git", "log", "--follow", "--format=%aI", "--", relativePath],
    ]

    for command in commands:
        result = subprocess.run(
            command,
            cwd=REPOROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        dates = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if dates:
            return datetime.fromisoformat(dates[-1])

    return datetime.fromtimestamp(path.stat().st_mtime).astimezone()


def getPostDate(path: Path) -> datetime:
    """Use DDMMYY from the filename and time/offset from the first Git date."""
    if not re.fullmatch(r"\d{6}", path.stem):
        raise ValueError("filename must be a six-digit date in DDMMYY format")

    fileDate = datetime.strptime(path.stem, "%d%m%y")
    gitDate = getGitDate(path)
    return datetime(
        year=fileDate.year,
        month=fileDate.month,
        day=fileDate.day,
        hour=gitDate.hour,
        minute=gitDate.minute,
        second=gitDate.second,
        tzinfo=gitDate.tzinfo,
    )


def readPostSource(path: Path) -> str:
    """Read modern UTF-8 pages and older Windows-1252 pages."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="windows-1252")


def getPostTitle(source: str, path: Path) -> str:
    """Read the first title element, falling back to the filename."""
    parser = TitleParser()
    parser.feed(source)
    parser.close()
    return parser.getTitle() or path.stem


def getPublicURL(path: Path) -> str:
    relativePath = path.relative_to(REPOROOT).as_posix()
    return f"{URL}/{quote(relativePath, safe='/')}"


def getPostBody(source: str, postUrl: str) -> str:
    """Return HTML inside body and make common relative URLs absolute."""
    bodyStart = re.search(r"<body\b[^>]*>", source, flags=re.IGNORECASE)
    if not bodyStart:
        return ""

    remainingSource = source[bodyStart.end():]
    bodyEnd = re.search(r"</body\s*>", remainingSource, flags=re.IGNORECASE)
    body = remainingSource[:bodyEnd.start()] if bodyEnd else remainingSource

    def makeAbsolute(match: re.Match[str]) -> str:
        attribute, quoteMark, value = match.groups()
        absoluteUrl = urljoin(postUrl, html.unescape(value))
        escapedUrl = html.escape(absoluteUrl, quote=True)
        return f"{attribute}={quoteMark}{escapedUrl}{quoteMark}"

    body = re.sub(
        r"(?i)\b(href|src|poster|background)\s*=\s*([\"'])(.*?)\2",
        makeAbsolute,
        body,
    )
    return body.strip()


def addIndent(element: ET.Element, level: int = 0) -> None:
    """Add indentation to make the generated XML readable."""
    spacing = "\n" + "  " * level
    if len(element):
        if not element.text or not element.text.strip():
            element.text = spacing + "  "
        for child in element:
            addIndent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = spacing
    if level and (not element.tail or not element.tail.strip()):
        element.tail = spacing


def main() -> None:
    posts: list[tuple[datetime, Path, str, str]] = []

    if POSTSROOT.exists():
        for path in POSTSROOT.iterdir():
            if not path.is_file() or path.suffix.lower() not in {".htm", ".html"}:
                continue

            try:
                postDate = getPostDate(path)
                postUrl = getPublicURL(path)
                source = readPostSource(path)
                postTitle = getPostTitle(source, path)
                postBody = getPostBody(source, postUrl)
            except (ValueError, OSError) as error:
                print(f"Skipping {path.relative_to(REPOROOT)}: {error}")
                continue

            posts.append((postDate, path, postTitle, postBody))

    posts.sort(key=lambda entry: (entry[0], entry[1].as_posix()), reverse=True)

    rss = ET.Element(
        "rss",
        {"version": "2.0", "xmlns:atom": "http://www.w3.org/2005/Atom"},
    )
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Not Your Pal Axl Posts"
    ET.SubElement(channel, "link").text = URL + "/posts/"
    ET.SubElement(channel, "description").text = "Posts from Not Your Pal Axl"
    ET.SubElement(channel, "language").text = "en-ca"
    ET.SubElement(
        channel,
        "atom:link",
        {
            "href": URL + "/posts.xml",
            "rel": "self",
            "type": "application/rss+xml",
        },
    )

    if posts:
        newestDate = max(postDate for postDate, _, _, _ in posts)
        ET.SubElement(channel, "lastBuildDate").text = format_datetime(newestDate)

    for postDate, path, title, body in posts:
        postUrl = getPublicURL(path)
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = postUrl
        ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = postUrl
        ET.SubElement(item, "pubDate").text = format_datetime(postDate)

        if body:
            ET.SubElement(item, "description").text = body
        else:
            escapedUrl = html.escape(postUrl, quote=True)
            escapedTitle = html.escape(title)
            ET.SubElement(item, "description").text = (
                f'<p><a href="{escapedUrl}">Read {escapedTitle}</a></p>'
            )

    addIndent(rss)
    xmlBody = ET.tostring(rss, encoding="unicode", short_empty_elements=True)
    OUTPUTFILE.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n' + xmlBody + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Generated posts.xml with {len(posts)} post(s).")


if __name__ == "__main__":
    main()
