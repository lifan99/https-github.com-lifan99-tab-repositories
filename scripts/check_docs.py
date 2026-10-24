"""Check local Markdown/HTML links, fragments and EPUB resources without network access."""

import argparse
import html
import posixpath
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parent.parent
DOCUMENT_SUFFIXES = {".md", ".html", ".htm", ".xhtml"}


class HTMLReferences(HTMLParser):
    """Collect actual attributes, ignoring escaped code examples."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.anchors = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.anchors.add(values["id"])
        if tag == "a" and values.get("name"):
            self.anchors.add(values["name"])
        for key in ("href", "src"):
            if values.get(key):
                self.links.append(values[key])

    handle_startendtag = handle_starttag


def references(text, suffix):
    """Return links and anchors; Markdown code fences are examples, not links."""
    if suffix == ".md":
        text = re.sub(r"^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$", "", text, flags=re.M | re.S)
    parsed = HTMLReferences()
    parsed.feed(text)
    links = list(parsed.links)
    anchors = set(parsed.anchors)
    if suffix == ".md":
        for match in re.finditer(r'!?\[[^\]\n]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+"[^"]*")?\s*\)', text):
            links.append(match.group(1) or match.group(2))
        definitions = dict(re.findall(r"^\s*\[([^]]+)\]:\s*<?([^\s>]+)>?", text, re.M))
        for label in re.findall(r"\[[^]\n]+\]\[([^]\n]+)\]", text):
            if label in definitions:
                links.append(definitions[label])
        used = {}
        for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.M):
            heading = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", heading)
            heading = re.sub(r"<[^>]+>", "", html.unescape(heading))
            slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
            duplicate = used.get(slug, 0)
            used[slug] = duplicate + 1
            anchors.add(f"{slug}-{duplicate}" if duplicate else slug)
    return links, anchors


def local_target(target):
    """External URLs remain unchanged and are outside this offline check."""
    value = urlsplit(html.unescape(target))
    if value.scheme or value.netloc:
        return None
    return unquote(value.path), unquote(value.fragment)


def check_documents(roots):
    documents = set()
    for root in roots:
        if root.is_file():
            documents.add(root.resolve())
        elif root.is_dir():
            documents.update(
                p.resolve() for p in root.rglob("*")
                if p.is_file() and p.suffix in DOCUMENT_SUFFIXES | {".epub"}
                and not any(part.startswith(".") or part == "__pycache__" for part in p.relative_to(root).parts)
            )
    missing = []
    checked = 0
    cache = {}

    def parsed(path):
        if path not in cache:
            cache[path] = references(path.read_text(encoding="utf-8"), path.suffix)
        return cache[path]

    for source in sorted(documents):
        if source.suffix == ".epub":
            try:
                with ZipFile(source) as archive:
                    names = set(archive.namelist())
                    archive_documents = {
                        name: references(archive.read(name).decode("utf-8"), Path(name).suffix)
                        for name in names if Path(name).suffix in {".html", ".xhtml", ".opf", ".ncx", ".xml"}
                    }
                    for name, (links, _) in archive_documents.items():
                        for target in links:
                            local = local_target(target)
                            if local is None:
                                continue
                            filename, fragment = local
                            linked = posixpath.normpath(posixpath.join(posixpath.dirname(name), filename)) if filename else name
                            checked += 1
                            if linked not in names:
                                missing.append(f"{source}!{name} -> {target}")
                            elif fragment and linked in archive_documents and fragment not in archive_documents[linked][1]:
                                missing.append(f"{source}!{name} -> {target} (missing fragment)")
            except (BadZipFile, UnicodeError) as exc:
                missing.append(f"{source}: {exc}")
            continue
        for target in parsed(source)[0]:
            local = local_target(target)
            if local is None:
                continue
            filename, fragment = local
            linked = (source.parent / filename).resolve() if filename else source
            checked += 1
            if not linked.exists():
                missing.append(f"{source} -> {target}")
            elif fragment and linked.suffix in DOCUMENT_SUFFIXES and fragment not in parsed(linked)[1]:
                missing.append(f"{source} -> {target} (missing fragment)")
    return checked, missing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="Explicit document files or directory roots")
    parser.add_argument("--include-personal", action="store_true", help="Also check workspace navigation, foundation courses, ~/career and ~/materials")
    args = parser.parse_args(argv)
    roots = args.paths or [ROOT / "README.md", ROOT / "docs", ROOT / "examples", ROOT / "study"]
    if args.include_personal:
        workspace = ROOT.parent.parent
        roots += [workspace / "README.md", workspace / "learning"]
        roots += [Path.home() / name for name in ("career", "materials")]
    absent = [str(root) for root in roots if not root.exists()]
    checked, missing = check_documents(roots)
    missing = [f"Missing root: {root}" for root in absent] + missing
    for entry in missing:
        print(f"Broken link: {entry}")
    print(f"Checked {checked} local links/resources and fragments; broken: {len(missing)}")
    return int(bool(missing))


if __name__ == "__main__":
    raise SystemExit(main())
