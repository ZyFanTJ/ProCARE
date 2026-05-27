import re
import shutil
from pathlib import Path
from typing import Sequence


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_PATTERN = re.compile(r"!\[(?P<alt>.*?)\]\((?P<path>.*?)\)")


def build_structured_report(
    markdown_text: str,
    asset_paths: Sequence[Path],
    *,
    report_name: str,
    figure_dir: Path,
) -> dict[str, object]:
    figure_dir.mkdir(parents=True, exist_ok=True)
    image_references = _collect_image_references(markdown_text)

    figure_entries: list[dict[str, object]] = []
    figure_lookup: dict[str, dict[str, object]] = {}
    renamed_paths: list[Path] = []

    for index, asset_path in enumerate(asset_paths, start=1):
        suffix = asset_path.suffix or ".bin"
        figure_name = f"figure{index}{suffix.lower()}"
        renamed_path = figure_dir / figure_name
        shutil.copy2(asset_path, renamed_path)
        renamed_paths.append(renamed_path)

        references = image_references.get(asset_path.name, [])
        captions = [item["caption"] for item in references if item["caption"]]
        section_headings = [item["section_heading"] for item in references if item["section_heading"]]
        entry = {
            "index": index,
            "figure_id": f"Figure {index}",
            "file_name": figure_name,
            "relative_path": f"figure/{figure_name}",
            "original_name": asset_path.name,
            "caption": captions[0] if captions else asset_path.stem,
            "captions": captions,
            "referenced_in_sections": _unique_preserve_order(section_headings),
        }
        figure_entries.append(entry)
        figure_lookup[asset_path.name] = entry

    title, sections = _extract_sections(markdown_text, figure_lookup, report_name)
    structured_report = {
        "report_title": report_name,
        "source_title": title,
        "figure_count": len(figure_entries),
        "section_count": len(sections),
        "figures": figure_entries,
        "sections": sections,
    }
    summary = {
        "title": title,
        "section_count": len(sections),
        "image_reference_count": sum(len(section["referenced_figures"]) for section in sections),
        "asset_count": len(asset_paths),
        "headings": [section["heading"] for section in sections if section["heading"]],
        "referenced_assets": [entry["file_name"] for entry in figure_entries],
    }
    return {
        "structured_report": structured_report,
        "summary": summary,
        "figure_entries": figure_entries,
        "figure_paths": renamed_paths,
    }


def rewrite_markdown_image_paths(markdown_text: str, figure_entries: Sequence[dict[str, object]]) -> str:
    figure_by_original = {str(item["original_name"]): str(item["relative_path"]) for item in figure_entries}

    def replace(match: re.Match[str]) -> str:
        original_path = match.group("path")
        file_name = Path(original_path).name
        rewritten = figure_by_original.get(file_name, original_path)
        return f"![{match.group('alt')}]({rewritten})"

    return IMAGE_PATTERN.sub(replace, markdown_text)


def _extract_sections(
    markdown_text: str,
    figure_lookup: dict[str, dict[str, object]],
    report_name: str,
) -> tuple[str, list[dict[str, object]]]:
    title = report_name
    sections: list[dict[str, object]] = []
    current_heading = report_name
    current_level = 1
    current_lines: list[str] = []

    for line in markdown_text.splitlines():
        stripped = line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match:
            if current_lines or sections:
                sections.append(_build_section(current_heading, current_level, current_lines, figure_lookup))
            current_heading = heading_match.group(2).strip()
            current_level = len(heading_match.group(1))
            if not sections:
                title = current_heading
            current_lines = []
            continue
        current_lines.append(line)

    if current_lines or not sections:
        sections.append(_build_section(current_heading, current_level, current_lines, figure_lookup))

    cleaned_sections = [section for section in sections if section["content_markdown"].strip() or section["referenced_figures"]]
    return title, cleaned_sections


def _build_section(
    heading: str,
    level: int,
    lines: Sequence[str],
    figure_lookup: dict[str, dict[str, object]],
) -> dict[str, object]:
    raw_markdown = "\n".join(lines).strip()
    paragraphs = _split_paragraphs(lines)
    referenced_figures: list[str] = []
    figure_files: list[str] = []
    for match in IMAGE_PATTERN.finditer(raw_markdown):
        original_name = Path(match.group("path")).name
        figure = figure_lookup.get(original_name)
        if figure is None:
            continue
        referenced_figures.append(str(figure["figure_id"]))
        figure_files.append(str(figure["relative_path"]))

    return {
        "heading": heading,
        "level": level,
        "content_markdown": raw_markdown,
        "paragraphs": paragraphs,
        "referenced_figures": _unique_preserve_order(referenced_figures),
        "figure_files": _unique_preserve_order(figure_files),
    }


def _split_paragraphs(lines: Sequence[str]) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append("\n".join(current).strip())
                current = []
            continue
        if IMAGE_PATTERN.fullmatch(stripped):
            continue
        current.append(stripped)

    if current:
        paragraphs.append("\n".join(current).strip())
    return paragraphs


def _collect_image_references(markdown_text: str) -> dict[str, list[dict[str, str]]]:
    references: dict[str, list[dict[str, str]]] = {}
    current_heading = ""
    for line in markdown_text.splitlines():
        stripped = line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match:
            current_heading = heading_match.group(2).strip()
            continue

        for match in IMAGE_PATTERN.finditer(line):
            original_name = Path(match.group("path")).name
            references.setdefault(original_name, []).append(
                {
                    "caption": match.group("alt").strip(),
                    "section_heading": current_heading,
                }
            )
    return references


def _unique_preserve_order(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
