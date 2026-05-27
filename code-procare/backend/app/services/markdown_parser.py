import re
from pathlib import Path
from typing import Sequence


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_PATTERN = re.compile(r"!\[(?P<alt>.*?)\]\((?P<path>.*?)\)")


def parse_markdown_summary(markdown_text: str, asset_names: Sequence[str]) -> dict[str, object]:
    headings: list[str] = []
    title = ""

    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match:
            heading_text = heading_match.group(2).strip()
            headings.append(heading_text)
            if not title:
                title = heading_text
            continue

        if not title:
            title = stripped[:80]

    referenced_assets = {
        Path(match.group("path")).name
        for match in IMAGE_PATTERN.finditer(markdown_text)
        if match.group("path")
    }

    for asset_name in asset_names:
        if asset_name in markdown_text:
            referenced_assets.add(asset_name)

    return {
        "title": title or "Generated Report",
        "section_count": len(headings),
        "image_reference_count": len(list(IMAGE_PATTERN.finditer(markdown_text))),
        "asset_count": len(asset_names),
        "headings": headings,
        "referenced_assets": sorted(referenced_assets),
    }
