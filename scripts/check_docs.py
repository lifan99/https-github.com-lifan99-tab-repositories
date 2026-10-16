"""Check local Markdown file links, without network access or anchor validation."""

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent


def main():
    missing = []
    checked = 0
    for source in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:
        for target in re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)', source.read_text(encoding="utf-8")):
            if target.startswith(("https:", "http:", "mailto:", "#")):
                continue
            target = unquote(target.split("#")[0])
            if target:
                checked += 1
                if not (source.parent / target).exists():
                    missing.append((source.relative_to(ROOT), target))
    for source, target in missing:
        print(f"Missing link: {source} -> {target}")
    print(f"Checked {checked} local file links; missing: {len(missing)}")
    return int(bool(missing))


if __name__ == "__main__":
    raise SystemExit(main())
