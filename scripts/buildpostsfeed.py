#!/usr/bin/env python3

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
URL = "http://www.yourpalaxl.com"  # No trailing

class TitleParser(HTMLParser):
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
    relative = path.relative_to(REPOROOT).as_posix()
    cmds = [
        ["git", "log", "--follow", "--diff-filter=A", "--format=%aI", "--", relative],
        ["git", "log", "--follow", "--format=%aI", "--", relative],
    ]

    for command in cmds:
        result = subprocess.run(command, cwd=REPOROOT, check=False, capture_output=True, text=True)
        dates = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if dates:
            return datetime.fromisoformat(dates[-1])

    return datetime.fromtimestamp(path.stat().st_mtime).astimezone()

def getPostDate(path: Path) -> datetime:
    if not re.fullmatch(r"\d{6}", path.stem): # Axl uses DDMMYY for posts
        raise ValueError("DDMMYY?")

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
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="windows-1252")

def getPostTitle(source: str, path: Path) -> str:
    parser = TitleParser()
    parser.feed(source)
    parser.close()
    return parser.getTitle() or path.stem

def getPublicURL(path: Path) -> str:
    relative = path.relative_to(REPOROOT).as_posix()
    return f"{URL}/{quote(relative, safe='/')}"

def getPostBody(source: str, postUrl: str) -> str:
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

    body = re.sub(r"(?i)\b(href|src|poster|background)\s*=\s*([\"'])(.*?)\2", makeAbsolute,body)
    return body.strip()

def addIndent(element: ET.Element, level: int = 0) -> None: # gotta have pretty feeds
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
    postsRoot = REPOROOT / "posts"
    if postsRoot.exists():
        for path in postsRoot.iterdir():
            if not path.is_file() or path.suffix.lower() not in {".htm", ".html"}:
                continue
            try:
                postDate = getPostDate(path)
                postUrl = getPublicURL(path)
                source = readPostSource(path)
                postTitle = getPostTitle(source, path)
                postBody = getPostBody(source, postUrl)
            except (ValueError, OSError) as error:
                print(f"Error for {path.relative_to(REPOROOT)}: {error}")
                continue
            posts.append((postDate, path, postTitle, postBody))

    posts.sort(key=lambda entry: (entry[0], entry[1].as_posix()), reverse=True)

    rss = ET.Element("rss", {"version": "2.0", "xmlns:atom": "http://www.w3.org/2005/Atom"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Axl's Cyberspace"
    ET.SubElement(channel, "link").text = URL + "/assets/Body/bodynews.htm"
    ET.SubElement(channel, "description").text = "Live from the Cerestix System"
    ET.SubElement(channel, "language").text = "en-gb"
    ET.SubElement(channel, "atom:link", {"href": URL + "/posts.xml", "rel": "self", "type": "application/rss+xml" })
    author = ET.SubElement(channel, "atom:author")
    ET.SubElement(author, "atom:name").text = "Axl Woodland"

    if posts:
        newestDate = max(postDate for postDate, _, _, _ in posts)
        ET.SubElement(channel, "lastBuildDate").text = format_datetime(newestDate)

    for postDate, path, title, body in posts:
        postUrl = getPublicURL(path)
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title.removeprefix("Axl's Cyberspace - ")
        ET.SubElement(item, "link").text = postUrl
        ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = postUrl
        ET.SubElement(item, "pubDate").text = format_datetime(postDate)

        if body:
            ET.SubElement(item, "description").text = body
        else:
            escapedUrl = html.escape(postUrl, quote=True)
            escapedTitle = html.escape(title)
            ET.SubElement(item, "description").text = (f'<p><a href="{escapedUrl}">{escapedTitle}</a></p>')

    addIndent(rss)
    xmlBody = ET.tostring(rss, encoding="unicode", short_empty_elements=True)
    outputFile = REPOROOT / "posts.xml"
    outputFile.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + xmlBody + "\n", encoding="utf-8", newline="\n")
    print(f"Gen: {len(posts)}")

if __name__ == "__main__":
    main()