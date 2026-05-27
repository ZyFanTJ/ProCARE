import re
import shutil
from pathlib import Path
from typing import Sequence

try:
    import fitz
except ImportError:  # pragma: no cover - optional dependency in some environments
    fitz = None


RIS_LINE_PATTERN = re.compile(r"^(?P<tag>[A-Z0-9]{2})\s{0,2}-\s?(?P<value>.*)$")
INLINE_WHITESPACE_PATTERN = re.compile(r"\s+")
KEY_SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9:_-]+")


def build_reference_library(
    reference_paths: Sequence[Path],
    *,
    reference_dir: Path,
) -> dict[str, object]:
    reference_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, object]] = []
    used_keys: set[str] = set()
    copied_paths: list[Path] = []

    for index, reference_path in enumerate(reference_paths, start=1):
        copied_path = reference_dir / reference_path.name
        shutil.copy2(reference_path, copied_path)
        copied_paths.append(copied_path)

        source_entries = _parse_reference_asset(copied_path, index)
        for source_entry in source_entries:
            citation_key = _ensure_unique_key(str(source_entry["citation_key"]), used_keys)
            source_entry["citation_key"] = citation_key
            source_entry["bibtex"] = _render_reference_bibtex(source_entry)
            entries.append(source_entry)

    entries = _finalize_reference_entries(entries)
    for entry in entries:
        entry["bibtex"] = _render_reference_bibtex(entry)

    manifest = {
        "reference_asset_count": len(reference_paths),
        "reference_entry_count": len(entries),
        "entries": [
            {
                "citation_key": str(entry["citation_key"]),
                "title": str(entry.get("title") or ""),
                "authors": list(entry.get("authors") or []),
                "year": str(entry.get("year") or ""),
                "entry_type": str(entry.get("entry_type") or "misc"),
                "source_file": str(entry.get("source_file") or ""),
                "journal": str(entry.get("journal") or ""),
                "volume": str(entry.get("volume") or ""),
                "pages": str(entry.get("pages") or ""),
                "doi": str(entry.get("doi") or ""),
                "content_excerpt": str(entry.get("content_excerpt") or ""),
                "source_kind": str(entry.get("source_kind") or ""),
            }
            for entry in entries
        ],
    }

    bibtex_text = "\n\n".join(str(entry["bibtex"]) for entry in entries).strip()
    if bibtex_text:
        bibtex_text += "\n"

    return {
        "entries": entries,
        "manifest": manifest,
        "bibtex": bibtex_text,
        "copied_paths": copied_paths,
    }


def _parse_reference_asset(reference_path: Path, index: int) -> list[dict[str, object]]:
    suffix = reference_path.suffix.lower()
    if suffix == ".bib":
        return _parse_bib_entries(reference_path.read_text(encoding="utf-8"), reference_path.name)
    if suffix == ".ris":
        return _parse_ris_entries(reference_path.read_text(encoding="utf-8"), reference_path.name)
    if suffix == ".pdf":
        return [_parse_pdf_entry(reference_path, index)]
    if suffix in {".txt", ".md"}:
        entries = _parse_plain_text_entries(reference_path.read_text(encoding="utf-8"), reference_path.name, index)
        if entries:
            return entries
    return [_build_placeholder_entry(reference_path, index)]


def _parse_bib_entries(content: str, source_file: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    cursor = 0
    length = len(content)

    while cursor < length:
        at_index = content.find("@", cursor)
        if at_index == -1:
            break

        brace_index = content.find("{", at_index)
        if brace_index == -1:
            break

        entry_type = content[at_index + 1 : brace_index].strip().lower() or "misc"
        depth = 1
        end_index = brace_index + 1
        while end_index < length and depth > 0:
            char = content[end_index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            end_index += 1

        raw_entry = content[brace_index + 1 : max(brace_index + 1, end_index - 1)].strip()
        cursor = end_index
        if not raw_entry or "," not in raw_entry:
            continue

        citation_key, field_blob = raw_entry.split(",", 1)
        citation_key = _sanitize_key(citation_key.strip()) or "reference"
        title = _extract_bib_field(field_blob, "title") or citation_key
        author_field = _extract_bib_field(field_blob, "author")
        year = _extract_bib_field(field_blob, "year") or ""
        journal = _extract_bib_field(field_blob, "journal")
        booktitle = _extract_bib_field(field_blob, "booktitle")
        publisher = _extract_bib_field(field_blob, "publisher")
        address = _extract_bib_field(field_blob, "address")
        school = _extract_bib_field(field_blob, "school")
        institution = _extract_bib_field(field_blob, "institution")
        volume = _extract_bib_field(field_blob, "volume")
        number = _extract_bib_field(field_blob, "number")
        pages = _extract_bib_field(field_blob, "pages")
        doi = _extract_bib_field(field_blob, "doi")
        url = _extract_bib_field(field_blob, "url")
        note = _extract_bib_field(field_blob, "note")

        entries.append(
            {
                "citation_key": citation_key,
                "title": _normalize_inline_whitespace(title),
                "authors": _split_bib_authors(author_field),
                "year": _normalize_inline_whitespace(year),
                "entry_type": entry_type,
                "source_file": source_file,
                "journal": _normalize_inline_whitespace(journal),
                "booktitle": _normalize_inline_whitespace(booktitle),
                "publisher": _normalize_inline_whitespace(publisher),
                "address": _normalize_inline_whitespace(address),
                "school": _normalize_inline_whitespace(school),
                "institution": _normalize_inline_whitespace(institution),
                "volume": _normalize_inline_whitespace(volume),
                "number": _normalize_inline_whitespace(number),
                "pages": _normalize_inline_whitespace(pages),
                "doi": _normalize_inline_whitespace(doi),
                "url": _normalize_inline_whitespace(url),
                "note": _normalize_inline_whitespace(note),
                "raw_bibtex": content[at_index:end_index].strip(),
                "source_kind": "bib",
            }
        )

    return entries


def _extract_bib_field(field_blob: str, field_name: str) -> str:
    patterns = [
        re.compile(
            rf"{re.escape(field_name)}\s*=\s*\{{(?P<value>(?:[^{{}}]|{{[^{{}}]*}})*)\}}",
            flags=re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            rf'{re.escape(field_name)}\s*=\s*"(?P<value>(?:[^"\\]|\\.)*)"',
            flags=re.IGNORECASE | re.DOTALL,
        ),
    ]

    for pattern in patterns:
        match = pattern.search(field_blob)
        if not match:
            continue
        value = match.group("value").replace("\n", " ").strip()
        return re.sub(r"[{}]", "", value).strip()
    return ""


def _parse_ris_entries(content: str, source_file: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    current: dict[str, list[str]] = {}

    for raw_line in content.splitlines():
        match = RIS_LINE_PATTERN.match(raw_line.rstrip())
        if not match:
            continue

        tag = match.group("tag")
        value = match.group("value").strip()
        if tag == "TY":
            if current:
                records.append(_build_ris_record(current, source_file, len(records) + 1))
            current = {"TY": [value]}
            continue
        if tag == "ER":
            if current:
                records.append(_build_ris_record(current, source_file, len(records) + 1))
                current = {}
            continue
        current.setdefault(tag, []).append(value)

    if current:
        records.append(_build_ris_record(current, source_file, len(records) + 1))

    return records


def _build_ris_record(record: dict[str, list[str]], source_file: str, index: int) -> dict[str, object]:
    title = _first_non_empty(record, "TI", "T1", "CT", default=f"Reference {index}")
    authors = record.get("AU") or record.get("A1") or []
    year = _extract_ris_year(_first_non_empty(record, "PY", "Y1", default=""))
    entry_type = _map_ris_entry_type(_first_non_empty(record, "TY", default="JOUR"))
    key_seed = f"{authors[0] if authors else title}_{year or index}"
    return {
        "citation_key": _sanitize_key(key_seed) or f"reference_{index}",
        "title": _normalize_inline_whitespace(title),
        "authors": [_normalize_inline_whitespace(author) for author in authors if author.strip()],
        "year": year,
        "entry_type": entry_type,
        "source_file": source_file,
        "journal": _normalize_inline_whitespace(_first_non_empty(record, "JO", "JF", "T2", default="")),
        "booktitle": _normalize_inline_whitespace(_first_non_empty(record, "BT", "T2", default="")),
        "publisher": _normalize_inline_whitespace(_first_non_empty(record, "PB", default="")),
        "address": _normalize_inline_whitespace(_first_non_empty(record, "CY", default="")),
        "school": _normalize_inline_whitespace(_first_non_empty(record, "PB", default="")),
        "institution": "",
        "volume": _normalize_inline_whitespace(_first_non_empty(record, "VL", default="")),
        "number": _normalize_inline_whitespace(_first_non_empty(record, "IS", default="")),
        "pages": _normalize_inline_whitespace(_first_non_empty(record, "SP", default="")),
        "doi": _normalize_inline_whitespace(_first_non_empty(record, "DO", default="")),
        "url": _normalize_inline_whitespace(_first_non_empty(record, "UR", default="")),
        "note": _normalize_inline_whitespace(_first_non_empty(record, "N1", default="")),
        "content_excerpt": "",
        "source_kind": "ris",
    }


def _parse_plain_text_entries(content: str, source_file: str, offset: int) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for index, raw_line in enumerate(content.splitlines(), start=offset):
        line = raw_line.strip()
        if not line:
            continue
        key_seed = _sanitize_key(line[:32]) or f"reference_{index}"
        entries.append(
            {
                "citation_key": key_seed,
                "title": _normalize_inline_whitespace(line),
                "authors": [],
                "year": "",
                "entry_type": "misc",
                "source_file": source_file,
                "content_excerpt": _normalize_inline_whitespace(line),
                "source_kind": "text",
            }
        )
    return entries


def _parse_pdf_entry(reference_path: Path, index: int) -> dict[str, object]:
    fallback_title = reference_path.stem.replace("_", " ").replace("-", " ").strip() or f"Reference {index}"
    title = fallback_title
    authors: list[str] = []
    year = ""
    journal = ""
    volume = ""
    pages = ""
    doi = ""
    content_excerpt = ""
    number = ""
    publisher = ""
    address = ""
    booktitle = ""

    if fitz is not None:
        try:
            with fitz.open(reference_path) as document:
                metadata = document.metadata or {}
                metadata_title = str(metadata.get("title") or "").strip()
                metadata_author = str(metadata.get("author") or "").strip()
                excerpt_parts: list[str] = []
                for page_index in range(min(3, document.page_count)):
                    page_text = document.load_page(page_index).get_text("text")
                    if page_text.strip():
                        excerpt_parts.append(page_text)

                excerpt_text = "\n".join(excerpt_parts)
                content_excerpt = _normalize_inline_whitespace(excerpt_text)[:4000]
                inferred_title = _infer_pdf_title(excerpt_text)
                if metadata_title and not _title_looks_generic(metadata_title):
                    title = metadata_title
                elif inferred_title:
                    title = inferred_title

                if metadata_author:
                    authors = _split_pdf_authors(metadata_author)
                elif excerpt_text:
                    authors = _infer_pdf_authors(excerpt_text)

                journal, volume, pages, doi, subject_year = _extract_pdf_bibliographic_fields(
                    excerpt_text,
                    str(metadata.get("subject") or ""),
                )

                year = _extract_year_from_text(
                    " ".join(
                        value
                        for value in (
                            subject_year,
                            str(metadata.get("creationDate") or ""),
                            str(metadata.get("modDate") or ""),
                            content_excerpt[:1000],
                        )
                        if value
                    )
                )
        except Exception:
            content_excerpt = ""

    return {
        "citation_key": _sanitize_key(reference_path.stem) or f"reference_{index}",
        "title": _normalize_inline_whitespace(title),
        "authors": authors,
        "year": year,
        "entry_type": "article" if journal else "misc",
        "source_file": reference_path.name,
        "journal": journal,
        "booktitle": booktitle,
        "publisher": publisher,
        "address": address,
        "volume": volume,
        "number": number,
        "pages": pages,
        "doi": doi,
        "url": "",
        "note": "",
        "school": "",
        "institution": "",
        "content_excerpt": content_excerpt,
        "source_kind": "pdf",
    }


def _build_placeholder_entry(reference_path: Path, index: int) -> dict[str, object]:
    title = reference_path.stem.replace("_", " ").replace("-", " ").strip() or f"Reference {index}"
    return {
        "citation_key": _sanitize_key(reference_path.stem) or f"reference_{index}",
        "title": _normalize_inline_whitespace(title),
        "authors": [],
        "year": "",
        "entry_type": "misc",
        "source_file": reference_path.name,
        "journal": "",
        "booktitle": "",
        "publisher": "",
        "address": "",
        "school": "",
        "institution": "",
        "volume": "",
        "number": "",
        "pages": "",
        "doi": "",
        "url": "",
        "note": "",
        "content_excerpt": "",
        "source_kind": "placeholder",
    }


def _finalize_reference_entries(entries: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    bib_entries = [dict(entry) for entry in entries if str(entry.get("source_kind") or "") == "bib"]
    if not bib_entries:
        return [dict(entry) for entry in entries]

    evidence_entries = [
        dict(entry)
        for entry in entries
        if str(entry.get("source_kind") or "") in {"pdf", "ris", "text", "placeholder"}
    ]
    if not evidence_entries:
        return bib_entries

    remaining = list(evidence_entries)
    merged_entries: list[dict[str, object]] = []
    sequential_fallback = len(remaining) == len(bib_entries)

    for index, bib_entry in enumerate(bib_entries):
        match_index = _find_best_evidence_match_index(bib_entry, remaining)
        if match_index is None and sequential_fallback and index < len(remaining):
            match_index = index
        matched = remaining.pop(match_index) if match_index is not None and match_index < len(remaining) else None
        merged_entries.append(_merge_reference_entry_with_evidence(bib_entry, matched))

    return merged_entries


def _find_best_evidence_match_index(
    canonical_entry: dict[str, object],
    evidence_entries: Sequence[dict[str, object]],
) -> int | None:
    canonical_doi = _normalize_identifier(str(canonical_entry.get("doi") or ""))
    canonical_title = _normalize_title_key(str(canonical_entry.get("title") or ""))
    best_index: int | None = None
    best_score = 0.0

    for index, evidence_entry in enumerate(evidence_entries):
        evidence_doi = _normalize_identifier(str(evidence_entry.get("doi") or ""))
        if canonical_doi and evidence_doi and canonical_doi == evidence_doi:
            return index

        evidence_title = _normalize_title_key(str(evidence_entry.get("title") or ""))
        if not canonical_title or not evidence_title:
            continue
        if canonical_title == evidence_title:
            return index

        score = _title_similarity_score(canonical_title, evidence_title)
        if score > best_score:
            best_score = score
            best_index = index

    if best_score >= 0.72:
        return best_index
    return None


def _merge_reference_entry_with_evidence(
    canonical_entry: dict[str, object],
    evidence_entry: dict[str, object] | None,
) -> dict[str, object]:
    merged = dict(canonical_entry)
    if evidence_entry is None:
        return merged

    for field_name in (
        "authors",
        "year",
        "journal",
        "booktitle",
        "publisher",
        "address",
        "school",
        "institution",
        "volume",
        "number",
        "pages",
        "doi",
        "url",
        "note",
    ):
        if _has_reference_value(merged.get(field_name)):
            continue
        candidate = evidence_entry.get(field_name)
        if _has_reference_value(candidate):
            merged[field_name] = candidate

    if not _has_reference_value(merged.get("content_excerpt")) and _has_reference_value(evidence_entry.get("content_excerpt")):
        merged["content_excerpt"] = evidence_entry.get("content_excerpt")

    merged["evidence_source_file"] = str(evidence_entry.get("source_file") or "")
    return merged


def _has_reference_value(value: object) -> bool:
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    return bool(str(value or "").strip())


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _normalize_title_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold())
    return " ".join(token for token in normalized.split() if len(token) > 1)


def _title_similarity_score(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    denominator = max(len(left_tokens), len(right_tokens))
    return overlap / denominator if denominator else 0.0


def _render_reference_bibtex(entry: dict[str, object]) -> str:
    raw_bibtex = str(entry.get("raw_bibtex") or "").strip()
    if raw_bibtex:
        return _rewrite_bibtex_key(raw_bibtex, str(entry.get("citation_key") or "reference"))
    return _render_bibtex_entry(entry)


def _render_bibtex_entry(entry: dict[str, object]) -> str:
    authors = entry.get("authors") or []
    year = str(entry.get("year") or "").strip()
    journal = str(entry.get("journal") or "").strip()
    booktitle = str(entry.get("booktitle") or "").strip()
    publisher = str(entry.get("publisher") or "").strip()
    address = str(entry.get("address") or "").strip()
    school = str(entry.get("school") or "").strip()
    institution = str(entry.get("institution") or "").strip()
    volume = str(entry.get("volume") or "").strip()
    number = str(entry.get("number") or "").strip()
    pages = str(entry.get("pages") or "").strip()
    doi = str(entry.get("doi") or "").strip()
    url = str(entry.get("url") or "").strip()
    note = str(entry.get("note") or "").strip()
    fields = [
        ("title", _escape_bib_value(str(entry.get("title") or ""))),
        ("author", " and ".join(_escape_bib_value(str(author)) for author in authors)),
        ("journal", _escape_bib_value(journal)),
        ("booktitle", _escape_bib_value(booktitle)),
        ("year", _escape_bib_value(year or "n.d.")),
        ("publisher", _escape_bib_value(publisher)),
        ("address", _escape_bib_value(address)),
        ("school", _escape_bib_value(school)),
        ("institution", _escape_bib_value(institution)),
        ("volume", _escape_bib_value(volume)),
        ("number", _escape_bib_value(number)),
        ("pages", _escape_bib_value(pages)),
        ("doi", _escape_bib_value(doi)),
        ("url", _escape_bib_value(url)),
        ("note", _escape_bib_value(note)),
        ("key", _escape_bib_value(str(entry.get("citation_key") or "")) if not authors else ""),
    ]
    if not authors and not journal and not booktitle and not volume and not pages and not doi and not note:
        fields.append(("note", _escape_bib_value(str(entry.get("source_file") or ""))))
    field_lines = [f"  {name} = {{{value}}}" for name, value in fields if value]
    return "@{entry_type}{{{citation_key},\n{fields}\n}}".format(
        entry_type=str(entry.get("entry_type") or "misc"),
        citation_key=str(entry.get("citation_key") or "reference"),
        fields=",\n".join(field_lines),
    )


def _rewrite_bibtex_key(raw_bibtex: str, citation_key: str) -> str:
    return re.sub(
        r"^(@[A-Za-z]+)\s*\{\s*([^,\s]+)",
        lambda match: f"{match.group(1)}{{{citation_key}",
        raw_bibtex,
        count=1,
    )


def _split_bib_authors(author_field: str) -> list[str]:
    if not author_field:
        return []
    return [_normalize_inline_whitespace(author) for author in author_field.split(" and ") if author.strip()]


def _ensure_unique_key(key: str, used_keys: set[str]) -> str:
    base_key = _sanitize_key(key) or "reference"
    candidate = base_key
    suffix = 2
    while candidate in used_keys:
        candidate = f"{base_key}_{suffix}"
        suffix += 1
    used_keys.add(candidate)
    return candidate


def _sanitize_key(value: str) -> str:
    return KEY_SANITIZE_PATTERN.sub("_", value).strip("_")


def _escape_bib_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    replacements = {
        "{": r"\{",
        "}": r"\}",
        "_": r"\_",
        "%": r"\%",
        "&": r"\&",
        "#": r"\#",
        "$": r"\$",
    }
    for source, target in replacements.items():
        escaped = escaped.replace(source, target)
    return escaped


def _normalize_inline_whitespace(value: str) -> str:
    return INLINE_WHITESPACE_PATTERN.sub(" ", value).strip()


def _map_ris_entry_type(value: str) -> str:
    mapping = {
        "JOUR": "article",
        "CONF": "inproceedings",
        "CHAP": "incollection",
        "BOOK": "book",
        "THES": "phdthesis",
    }
    return mapping.get(value.upper(), "misc")


def _extract_ris_year(value: str) -> str:
    match = re.search(r"\b(\d{4})\b", value)
    return match.group(1) if match else ""


def _first_non_empty(record: dict[str, list[str]], *tags: str, default: str = "") -> str:
    for tag in tags:
        values = record.get(tag) or []
        for value in values:
            if value.strip():
                return value.strip()
    return default


def _split_pdf_authors(author_field: str) -> list[str]:
    chunks = re.split(r"\s*(?:;| and )\s*", author_field)
    return [_normalize_inline_whitespace(chunk) for chunk in chunks if chunk.strip()]


def _infer_pdf_title(text: str) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, raw_line in enumerate(lines):
        candidate = _normalize_inline_whitespace(raw_line)
        if not candidate:
            continue
        if len(candidate) < 12:
            continue
        if len(candidate) > 220:
            continue
        if _looks_like_header_label(candidate):
            continue
        if candidate.lower().startswith(("abstract", "introduction", "keywords")):
            continue
        if index + 1 < len(lines):
            next_line = _normalize_inline_whitespace(lines[index + 1])
            combined = _normalize_inline_whitespace(f"{candidate} {next_line}")
            if (
                12 <= len(next_line) <= 160
                and _looks_like_title_continuation(next_line)
                and (candidate.endswith((",", "-", "—", ":")) or next_line[:1].islower())
            ):
                return combined
        return candidate
    return ""


def _title_looks_generic(value: str) -> bool:
    candidate = value.strip().lower()
    if not candidate:
        return True
    return candidate in {"untitled", "article", "paper", "document"} or candidate.startswith("microsoft word")


def _extract_year_from_text(text: str) -> str:
    years = re.findall(r"\b((?:19|20)\d{2})\b", text)
    return years[0] if years else ""


def _infer_pdf_authors(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    authors: list[str] = []
    title_seen = False
    for raw_line in lines[:40]:
        candidate = _normalize_inline_whitespace(raw_line)
        if not candidate:
            continue
        if not title_seen:
            if _looks_like_header_label(candidate):
                continue
            if len(candidate) >= 12 and not _looks_like_author_line(candidate):
                title_seen = True
            continue
        if re.match(r"^\d", candidate):
            break
        if candidate == "|":
            continue
        if _looks_like_author_line(candidate):
            cleaned = re.sub(r"\d+(?:,\d+)*$", "", candidate).strip(" |,")
            if cleaned and cleaned not in authors:
                authors.append(cleaned)
        elif authors:
            break
    return authors[:12]


def _extract_pdf_bibliographic_fields(text: str, subject: str) -> tuple[str, str, str, str, str]:
    joined = "\n".join([subject, text])
    doi_match = re.search(r"\b10\.\d{4,9}/[^\s;,)]+", joined, flags=re.IGNORECASE)
    doi = doi_match.group(0).rstrip(".") if doi_match else ""

    journal = ""
    volume = ""
    pages = ""
    year = ""

    subject_match = re.search(
        r"(?P<journal>[^,]+),\s*(?P<volume>\d+)\s*\((?P<year>\d{4})\)\s*(?P<pages>\d+\s*[-–]\s*\d+)",
        subject,
    )
    if subject_match:
        return (
            _normalize_inline_whitespace(subject_match.group("journal")),
            subject_match.group("volume"),
            subject_match.group("pages").replace("–", "--").replace(" ", ""),
            doi,
            subject_match.group("year"),
        )

    for raw_line in text.splitlines():
        candidate = _normalize_inline_whitespace(raw_line)
        if not candidate:
            continue
        journal_match = re.search(
            r"(?P<journal>[A-Z][A-Za-z&.\- ]+)\.\s*(?P<year>\d{4});(?P<volume>\d+):(?P<pages>\d+\s*[-–]\s*\d+)",
            candidate,
        )
        if journal_match:
            journal = _normalize_inline_whitespace(journal_match.group("journal"))
            volume = journal_match.group("volume")
            pages = journal_match.group("pages").replace("–", "--").replace(" ", "")
            year = journal_match.group("year")
            break

    return journal, volume, pages, doi, year


def _looks_like_header_label(text: str) -> bool:
    collapsed = text.replace(" ", "")
    upper_ratio = sum(1 for char in collapsed if char.isupper()) / max(1, len([c for c in collapsed if c.isalpha()]))
    return upper_ratio > 0.85 or text.lower() in {"summary", "practice guidance"}


def _looks_like_author_line(text: str) -> bool:
    if "|" in text:
        return True
    words = text.split()
    if not 2 <= len(words) <= 8:
        return False
    if any(char.isdigit() for char in text):
        return True
    return sum(1 for word in words if word[:1].isupper()) >= 2


def _looks_like_title_continuation(text: str) -> bool:
    return not _looks_like_author_line(text) and not re.match(r"^\d", text) and len(text.split()) >= 2
