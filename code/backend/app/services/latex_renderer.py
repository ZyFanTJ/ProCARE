import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
ORDERED_LIST_PATTERN = re.compile(r"^\d+\.\s+(.*)$")
IMAGE_PATTERN = re.compile(r"!\[(?P<alt>.*?)\]\((?P<path>.*?)\)")
MARKDOWN_CITATION_PATTERN = re.compile(r"\[(?P<body>\s*@[^]]+)\]")
TABLE_SEPARATOR_CELL_PATTERN = re.compile(r"^:?-{3,}:?$")
TABLE_SEPARATOR_ROW_PATTERN = re.compile(r"^\|?\s*:?-{3,}:?(?:\s*\|\s*:?-{3,}:?)+\s*\|?$")
SPECIAL_CHARS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
TEMPLATE_CANDIDATES = ("main.tex", "template.tex", "paper.tex", "manuscript.tex")
LATEX_ENGINES = ("xelatex", "lualatex", "pdflatex")
ABSTRACT_TITLES = {"abstract", "摘要"}
ABSTRACT_TITLES = {"abstract", "摘要"}
ABSTRACT_TITLES = {"abstract", "\u6458\u8981"}
KEYWORD_TITLES = {"keywords", "key words", "\u5173\u952e\u8bcd"}

WINDOWS_TEXLIVE_ROOTS = (
    *(Path(f"{drive}:\\texlive") for drive in "CDEFG"),
    *(Path(f"{drive}:\\texlive4") for drive in "CDEFG"),
)
WINDOWS_MIKTEX_ROOTS = (
    Path(r"C:\Program Files\MiKTeX"),
    Path(r"C:\Program Files (x86)\MiKTeX"),
    Path(r"C:\Users\ryw\AppData\Local\Programs\MiKTeX"),
    Path(r"F:\academic-writer\latex\miktex"),
)


@dataclass(frozen=True)
class LatexCompilerProfile:
    engine_name: str
    engine_path: str
    distribution: str
    bibtex_path: str | None = None

    @property
    def display_name(self) -> str:
        return f"{self.distribution} | {self.engine_name} | {self.engine_path}"


class LatexRenderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        intermediate_files: list[dict[str, str]],
        compile_engine: str | None = None,
    ) -> None:
        super().__init__(message)
        self.intermediate_files = intermediate_files
        self.compile_engine = compile_engine


def render_report_latex(
    *,
    report_name: str,
    report_language: str | None = None,
    asset_paths: Iterable[Path],
    intermediate_dir: Path,
    output_path: Path,
    latex_body: str,
    template_path: str | None = None,
    bibliography_bib_path: str | None = None,
    reference_entries: Sequence[dict[str, object]] | None = None,
) -> dict[str, object]:
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = intermediate_dir / "latex_runtime"
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    manual_bibliography_block = _build_gbt7714_bibliography(reference_entries or [])

    entry_file, artifact_files = _prepare_template(
        runtime_dir=runtime_dir,
        intermediate_dir=intermediate_dir,
        report_name=report_name,
        report_language=report_language,
        latex_body=latex_body,
        template_path=template_path,
        include_bibliography=bool(bibliography_bib_path or manual_bibliography_block),
        bibliography_block=manual_bibliography_block,
    )

    if manual_bibliography_block:
        bibliography_snapshot = intermediate_dir / "14b_gbt7714_bibliography.tex"
        bibliography_snapshot.write_text(manual_bibliography_block, encoding="utf-8")
        artifact_files.append(
            {"name": "14b_gbt7714_bibliography", "path": str(bibliography_snapshot), "category": "reference"}
        )

    asset_manifest = _copy_assets(asset_paths, entry_file.parent / "assets")
    asset_manifest_path = intermediate_dir / "15_latex_asset_manifest.json"
    asset_manifest_path.write_text(
        json.dumps(asset_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rendered_main_snapshot = intermediate_dir / "16_rendered_main.tex"
    rendered_main_snapshot.write_text(entry_file.read_text(encoding="utf-8"), encoding="utf-8")

    compile_log_path = intermediate_dir / "17_compile_log.log"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_files.extend(
        [
            {"name": "15_latex_asset_manifest", "path": str(asset_manifest_path), "category": "input"},
            {"name": "16_rendered_main_tex", "path": str(rendered_main_snapshot), "category": "latex"},
            {"name": "17_compile_log", "path": str(compile_log_path), "category": "latex"},
        ]
    )

    runtime_bibliography_path = None
    if bibliography_bib_path:
        runtime_bibliography_path = entry_file.parent / "references.bib"
        shutil.copy2(bibliography_bib_path, runtime_bibliography_path)

    try:
        compile_result = _compile_latex(
            entry_file,
            output_path,
            compile_log_path,
            run_bibtex=bool(runtime_bibliography_path) and not bool(manual_bibliography_block),
        )
    except Exception as exc:
        raise LatexRenderError(
            str(exc),
            intermediate_files=artifact_files,
            compile_engine=getattr(exc, "compile_engine", None),
        ) from exc

    return {
        "output_file": str(output_path),
        "tex_file": str(rendered_main_snapshot),
        "latex_project_dir": str(entry_file.parent),
        "latex_entry_file": str(entry_file),
        "output_type": output_path.suffix.lstrip("."),
        "compile_engine": compile_result["engine"],
        "intermediate_files": artifact_files,
    }


def markdown_to_latex(markdown_text: str, *, enable_citations: bool = False) -> str:
    lines: list[str] = []
    list_stack: list[str] = []
    in_code_block = False
    pending_list_break = False
    render_context = _build_render_context(markdown_text)
    heading_index = 0
    figure_index = 0
    source_lines = markdown_text.splitlines()
    line_index = 0

    while line_index < len(source_lines):
        raw_line = source_lines[line_index]
        stripped = raw_line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                lines.append(r"\end{verbatim}")
                in_code_block = False
            else:
                lines.extend(_close_lists(list_stack))
                lines.append(r"\begin{verbatim}")
                in_code_block = True
            pending_list_break = False
            line_index += 1
            continue

        if in_code_block:
            lines.append(raw_line)
            line_index += 1
            continue

        if stripped in {"---", "***", "___"}:
            lines.extend(_close_lists(list_stack))
            pending_list_break = False
            line_index += 1
            continue

        if not stripped:
            if list_stack:
                pending_list_break = True
                line_index += 1
                continue
            lines.extend(_close_lists(list_stack))
            lines.append("")
            pending_list_break = False
            line_index += 1
            continue

        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match:
            lines.extend(_close_lists(list_stack))
            pending_list_break = False
            level = _normalize_heading_level(len(heading_match.group(1)))
            heading_text = heading_match.group(2).strip()
            normalized_heading = heading_text.strip().lower()

            if normalized_heading in KEYWORD_TITLES:
                lines.append(
                    rf"\noindent\textbf{{{_convert_inline_markdown(heading_text, enable_citations=enable_citations, crossref_context=render_context)}}}"
                )
                lines.append(r"\par")
                labels = render_context["heading_labels"][heading_index] if heading_index < len(render_context["heading_labels"]) else []
                heading_index += 1
                for label in labels:
                    lines.append(rf"\label{{{label}}}")
                line_index += 1
                continue

            command = {
                1: r"\section",
                2: r"\subsection",
                3: r"\subsubsection",
                4: r"\paragraph",
                5: r"\subparagraph",
                6: r"\subparagraph",
            }[min(level, 6)]
            lines.append(
                f"{command}{{{_convert_inline_markdown(heading_text, enable_citations=enable_citations, crossref_context=render_context)}}}"
            )
            labels = render_context["heading_labels"][heading_index] if heading_index < len(render_context["heading_labels"]) else []
            heading_index += 1
            for label in labels:
                lines.append(rf"\label{{{label}}}")
            line_index += 1
            continue

        ordered_match = ORDERED_LIST_PATTERN.match(stripped)
        if ordered_match:
            lines.extend(_ensure_list(list_stack, "enumerate"))
            lines.append(
                rf"\item {_convert_inline_markdown(ordered_match.group(1).strip(), enable_citations=enable_citations, crossref_context=render_context)}"
            )
            pending_list_break = False
            line_index += 1
            continue

        if stripped.startswith(("- ", "* ")):
            lines.extend(_ensure_list(list_stack, "itemize"))
            lines.append(
                rf"\item {_convert_inline_markdown(stripped[2:].strip(), enable_citations=enable_citations, crossref_context=render_context)}"
            )
            pending_list_break = False
            line_index += 1
            continue

        image_matches = list(IMAGE_PATTERN.finditer(stripped))
        if image_matches and stripped == image_matches[0].group(0):
            lines.extend(_close_lists(list_stack))
            pending_list_break = False
            image_entries: list[dict[str, str | int]] = []
            while line_index < len(source_lines):
                candidate_line = source_lines[line_index].strip()
                candidate_matches = list(IMAGE_PATTERN.finditer(candidate_line))
                if not candidate_matches or candidate_line != candidate_matches[0].group(0):
                    break
                for match in candidate_matches:
                    image_entries.append(
                        _resolve_markdown_image_entry(
                            match=match,
                            render_context=render_context,
                            figure_index=figure_index,
                        )
                    )
                    figure_index += 1
                line_index += 1
            lines.extend(_render_markdown_image_group(image_entries))
            continue

        table_match = _consume_markdown_table(source_lines, line_index)
        if table_match:
            lines.extend(_close_lists(list_stack))
            pending_list_break = False
            rendered_table, line_index = table_match
            lines.extend(rendered_table)
            continue

        if list_stack and not pending_list_break:
            lines.append(
                _convert_inline_markdown(
                    raw_line,
                    enable_citations=enable_citations,
                    crossref_context=render_context,
                )
            )
            line_index += 1
            continue

        lines.extend(_close_lists(list_stack))
        lines.append(_convert_inline_markdown(raw_line, enable_citations=enable_citations, crossref_context=render_context))
        pending_list_break = False
        line_index += 1

    if in_code_block:
        lines.append(r"\end{verbatim}")
    lines.extend(_close_lists(list_stack))
    return _finalize_latex_body("\n".join(lines).strip() + "\n")


def _consume_markdown_table(source_lines: Sequence[str], start_index: int) -> tuple[list[str], int] | None:
    if start_index + 1 >= len(source_lines):
        return None
    header_line = source_lines[start_index].strip()
    separator_line = source_lines[start_index + 1].strip()
    if "|" not in header_line or not TABLE_SEPARATOR_ROW_PATTERN.fullmatch(separator_line):
        return None

    header_cells = _split_markdown_table_row(header_line)
    separator_cells = _split_markdown_table_row(separator_line)
    if len(header_cells) < 2 or len(header_cells) != len(separator_cells):
        return None
    if not all(TABLE_SEPARATOR_CELL_PATTERN.fullmatch(cell.strip()) for cell in separator_cells):
        return None

    rows: list[list[str]] = []
    line_index = start_index + 2
    while line_index < len(source_lines):
        candidate = source_lines[line_index].strip()
        if not candidate or "|" not in candidate or HEADING_PATTERN.match(candidate):
            break
        row_cells = _split_markdown_table_row(candidate)
        if len(row_cells) != len(header_cells):
            break
        rows.append(row_cells)
        line_index += 1

    if not rows:
        return None
    return _render_markdown_table(header_cells, rows), line_index


def _split_markdown_table_row(raw_line: str) -> list[str]:
    stripped = raw_line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _render_markdown_table(header_cells: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    column_spec = "p{0.22\\linewidth}" + " ".join("p{0.18\\linewidth}" for _ in header_cells[1:])
    rendered = [
        r"\begin{table}[H]",
        r"\centering",
        rf"\begin{{tabular}}{{{column_spec}}}",
        r"\toprule",
        " & ".join(_escape_latex(cell) for cell in header_cells) + r" \\",
        r"\midrule",
    ]
    for row in rows:
        rendered.append(" & ".join(_escape_latex(cell) for cell in row) + r" \\")
    rendered.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])
    return rendered


def _resolve_markdown_image_entry(
    *,
    match: re.Match[str],
    render_context: dict[str, object],
    figure_index: int,
) -> dict[str, str | int]:
    image_name = Path(match.group("path")).name
    fallback_caption = (
        render_context["figure_captions"][figure_index]
        if figure_index < len(render_context["figure_captions"])
        else ""
    )
    caption = _escape_latex(_normalize_figure_caption(match.group("alt"), image_name, fallback_caption))
    figure_number = (
        render_context["figure_numbers"][figure_index]
        if figure_index < len(render_context["figure_numbers"])
        else figure_index + 1
    )
    return {
        "image_name": image_name,
        "caption": caption,
        "figure_number": figure_number,
    }


def _render_markdown_image_group(image_entries: Sequence[dict[str, str | int]]) -> list[str]:
    if not image_entries:
        return []
    if len(image_entries) == 2 and _should_render_as_compact_curve_pair(image_entries):
        return _render_compact_curve_pair(image_entries)

    rendered: list[str] = []
    for entry in image_entries:
        image_name = str(entry["image_name"])
        figure_number = int(entry["figure_number"])
        rendered.extend(
            [
                r"\begin{figure}[H]",
                r"\centering",
                rf"{_build_figure_includegraphics(image_name, str(entry['caption']))}",
                rf"\caption{{{entry['caption']}}}",
                rf"\label{{fig:{figure_number}}}",
                r"\end{figure}",
            ]
        )
    return rendered


def _should_render_as_compact_curve_pair(image_entries: Sequence[dict[str, str | int]]) -> bool:
    return False


def _is_compact_curve_image(image_entry: dict[str, str | int]) -> bool:
    haystack = f"{image_entry.get('image_name', '')} {image_entry.get('caption', '')}".casefold()
    return any(token in haystack for token in ("kaplan", "meier", "survival", "curve", "生存曲线"))


def _render_compact_curve_pair(image_entries: Sequence[dict[str, str | int]]) -> list[str]:
    left_entry, right_entry = image_entries
    return [
        r"\begin{figure}[H]",
        r"\centering",
        r"\begin{minipage}[t]{0.485\linewidth}",
        r"\centering",
        rf"{_build_compact_pair_includegraphics(str(left_entry['image_name']))}",
        rf"\captionof{{figure}}{{{left_entry['caption']}}}",
        rf"\label{{fig:{int(left_entry['figure_number'])}}}",
        r"\end{minipage}\hfill",
        r"\begin{minipage}[t]{0.485\linewidth}",
        r"\centering",
        rf"{_build_compact_pair_includegraphics(str(right_entry['image_name']))}",
        rf"\captionof{{figure}}{{{right_entry['caption']}}}",
        rf"\label{{fig:{int(right_entry['figure_number'])}}}",
        r"\end{minipage}",
        r"\end{figure}",
    ]


def _prepare_template(
    *,
    runtime_dir: Path,
    intermediate_dir: Path,
    report_name: str,
    report_language: str | None,
    latex_body: str,
    template_path: str | None,
    include_bibliography: bool,
    bibliography_block: str | None,
) -> tuple[Path, list[dict[str, str]]]:
    artifact_files: list[dict[str, str]] = []
    generated_at = _format_generated_at(report_language)
    override_with_reference_layout = _should_override_template_for_chinese_medical(report_language, template_path)

    if template_path and not override_with_reference_layout:
        template_root, entry_file = _copy_template(Path(template_path), runtime_dir / "template")
        raw_template_text = entry_file.read_text(encoding="utf-8")
        if report_language == "en":
            raw_template_text = _englishify_template_frontmatter(raw_template_text)
        template_text = _ensure_template_language_support(
            raw_template_text,
            report_name,
            latex_body,
            report_language=report_language,
        )
        original_entry_path = intermediate_dir / "14_template_entry_original.tex"
        original_entry_path.write_text(raw_template_text, encoding="utf-8")
        rendered = _inject_into_template(template_text, report_name, latex_body, generated_at)
        if include_bibliography:
            rendered = _ensure_bibliography_block(rendered, bibliography_block=bibliography_block)
        else:
            rendered = _remove_bibliography_block(rendered)
        entry_file.write_text(rendered, encoding="utf-8")
        artifact_files.append(
            {"name": "14_template_entry_original", "path": str(original_entry_path), "category": "template"}
        )
        return entry_file, artifact_files

    entry_file = runtime_dir / "main.tex"
    entry_file.write_text(
        _default_document(
            report_name=report_name,
            report_language=report_language,
            latex_body=latex_body,
            generated_at=generated_at,
            include_bibliography=include_bibliography,
            bibliography_block=bibliography_block,
        ),
        encoding="utf-8",
    )
    return entry_file, artifact_files


def _copy_template(template_path: Path, destination_root: Path) -> tuple[Path, Path]:
    if not template_path.exists():
        raise FileNotFoundError(f"LaTeX template not found: {template_path}")

    if template_path.is_dir():
        shutil.copytree(template_path, destination_root, dirs_exist_ok=True)
        _patch_template_runtime_files(destination_root)
        entry_file = _find_entry_file(destination_root)
        return destination_root, entry_file

    destination_root.mkdir(parents=True, exist_ok=True)
    source_root = template_path.parent
    shutil.copytree(source_root, destination_root, dirs_exist_ok=True)
    _patch_template_runtime_files(destination_root)
    entry_file = destination_root / template_path.name
    if not entry_file.exists():
        raise FileNotFoundError(f"Template entry file missing after copy: {entry_file}")
    return destination_root, entry_file


def _patch_template_runtime_files(template_root: Path) -> None:
    for sty_file in template_root.rglob("rvdtx.sty"):
        original = sty_file.read_text(encoding="utf-8", errors="ignore")
        patched = re.sub(
            r"\\RequirePackage\[(?P<options>[^\]]*?)pdftex(?P<tail>[^\]]*)\]\{hyperref\}",
            lambda match: (
                r"\RequirePackage["
                + ",".join(
                    option.strip()
                    for option in (match.group("options") + match.group("tail")).split(",")
                    if option.strip()
                )
                + "]{hyperref}"
            ),
            original,
            flags=re.IGNORECASE,
        )
        if patched != original:
            sty_file.write_text(patched, encoding="utf-8")


def _find_entry_file(template_root: Path) -> Path:
    for candidate in TEMPLATE_CANDIDATES:
        match = next(template_root.rglob(candidate), None)
        if match is not None:
            return match

    tex_files = sorted(template_root.rglob("*.tex"))
    if not tex_files:
        raise FileNotFoundError(f"No .tex entry file found in template directory: {template_root}")
    return tex_files[0]


def _inject_into_template(
    template_text: str,
    report_name: str,
    latex_body: str,
    generated_at: str,
) -> str:
    if "{{ report_body }}" in template_text:
        replacements = {
            "{{ report_title }}": _escape_latex(report_name),
            "{{ report_body }}": latex_body,
            "{{ generated_at }}": _escape_latex(generated_at),
        }

        rendered = template_text
        for placeholder, value in replacements.items():
            rendered = rendered.replace(placeholder, value)
        return rendered

    return _auto_adapt_template(
        template_text=template_text,
        report_name=report_name,
        latex_body=latex_body,
        generated_at=generated_at,
    )


def _default_document(
    *,
    report_name: str,
    report_language: str | None,
    latex_body: str,
    generated_at: str,
    include_bibliography: bool,
    bibliography_block: str | None,
) -> str:
    if report_language == "zh":
        return _default_chinese_medical_document(
            report_name=report_name,
            latex_body=latex_body,
            include_bibliography=include_bibliography,
            bibliography_block=bibliography_block,
        )

    rendered_bibliography_block = bibliography_block or ""
    if include_bibliography:
        if not rendered_bibliography_block:
            rendered_bibliography_block = (
                "\n"
                r"\bibliographystyle{plainnat}" "\n"
                r"\bibliography{references}" "\n"
            )
    abstract_name = r"\renewcommand{\abstractname}{摘要}" "\n" if report_language == "zh" else ""
    document_class = r"\documentclass[12pt]{ctexart}" if report_language == "zh" else r"\documentclass[12pt]{article}"
    cleveref_setup = _chinese_cleveref_setup() if report_language == "zh" else ""
    return (
        document_class + "\n"
        r"\usepackage[margin=1in]{geometry}" "\n"
        r"\usepackage{graphicx}" "\n"
        r"\usepackage{indentfirst}" "\n"
        r"\usepackage{hyperref}" "\n"
        r"\hypersetup{hidelinks}" "\n"
        r"\usepackage{cleveref}" "\n"
        f"{cleveref_setup}"
        r"\usepackage{float}" "\n"
        r"\usepackage{enumitem}" "\n"
        r"\setlist{itemsep=0.35em,topsep=0.2em,parsep=0pt,partopsep=0pt,leftmargin=*}" "\n"
        r"\setlength{\parindent}{2em}" "\n"
        r"\setlength{\parskip}{0pt}" "\n"
        r"\abovecaptionskip=4pt" "\n"
        r"\widowpenalty=10000" "\n"
        r"\clubpenalty=10000" "\n"
        r"\interfootnotelinepenalty=10000" "\n"
        r"\usepackage{natbib}" "\n"
        r"\setcitestyle{numbers,square}" "\n"
        r"\usepackage{verbatim}" "\n"
        r"\raggedbottom" "\n"
        r"\setcounter{secnumdepth}{3}" "\n"
        r"\setlength{\belowcaptionskip}{2pt}" "\n"
        r"\setlength{\intextsep}{6pt plus 2pt minus 2pt}" "\n"
        r"\setlength{\textfloatsep}{8pt plus 2pt minus 2pt}" "\n"
        r"\setlength{\floatsep}{8pt plus 2pt minus 2pt}" "\n"
        r"\renewcommand{\topfraction}{0.92}" "\n"
        r"\renewcommand{\bottomfraction}{0.85}" "\n"
        r"\renewcommand{\textfraction}{0.06}" "\n"
        r"\renewcommand{\floatpagefraction}{0.82}" "\n"
        r"\setcounter{topnumber}{3}" "\n"
        r"\setcounter{bottomnumber}{2}" "\n"
        r"\setcounter{totalnumber}{6}" "\n"
        "\n"
        r"\title{" + _escape_latex(report_name) + "}\n"
        r"\date{" + _escape_latex(generated_at) + "}\n"
        "\n"
        f"{abstract_name}"
        r"\begin{document}" "\n"
        r"\maketitle" "\n"
        "\n"
        f"{latex_body}\n"
        f"{rendered_bibliography_block}"
        r"\end{document}" "\n"
    )


def _default_chinese_medical_document(
    *,
    report_name: str,
    latex_body: str,
    include_bibliography: bool,
    bibliography_block: str | None,
) -> str:
    rendered_bibliography_block = bibliography_block or ""
    if include_bibliography and not rendered_bibliography_block:
        rendered_bibliography_block = (
            "\n"
            r"\bibliographystyle{plainnat}" "\n"
            r"\bibliography{references}" "\n"
        )

    abstract_text, remaining_body = _extract_abstract_section(latex_body)
    abstract_block = ""
    if abstract_text:
        abstract_block = (
            r"\begin{center}" "\n"
            r"{\bfseries\zihao{4} 摘要\par}" "\n"
            r"\end{center}" "\n"
            r"\noindent "
            + abstract_text.strip()
            + "\n\n"
        )

    body_block = remaining_body.strip()
    if body_block:
        body_block += "\n"

    return (
        r"\documentclass[UTF8,a4paper,zihao=5]{ctexart}" "\n"
        r"\usepackage[left=2.28cm,right=2.28cm,top=1.85cm,bottom=2.1cm]{geometry}" "\n"
        r"\usepackage{graphicx}" "\n"
        r"\usepackage{booktabs}" "\n"
        r"\usepackage{indentfirst}" "\n"
        r"\usepackage{hyperref}" "\n"
        r"\hypersetup{hidelinks}" "\n"
        r"\usepackage{cleveref}" "\n"
        f"{_chinese_cleveref_setup()}"
        r"\usepackage{float}" "\n"
        r"\usepackage{enumitem}" "\n"
        r"\usepackage{titlesec}" "\n"
        r"\usepackage{fancyhdr}" "\n"
        r"\usepackage{xcolor}" "\n"
        r"\usepackage[font=small,labelfont=normalfont]{caption}" "\n"
        r"\usepackage{natbib}" "\n"
        r"\setcitestyle{numbers,square}" "\n"
        r"\definecolor{journalred}{RGB}{157,59,54}" "\n"
        r"\setlist{itemsep=0.16em,topsep=0.1em,parsep=0pt,partopsep=0pt,leftmargin=*}" "\n"
        r"\setlength{\parindent}{2em}" "\n"
        r"\setlength{\parskip}{0pt}" "\n"
        r"\linespread{1.12}" "\n"
        r"\captionsetup{skip=2pt}" "\n"
        r"\setlength{\belowcaptionskip}{0pt}" "\n"
        r"\titleformat{\section}{\color{journalred}\bfseries\zihao{4}}{\thesection.}{0.38em}{}" "\n"
        r"\titleformat{\subsection}{\color{journalred}\bfseries\zihao{-4}}{\thesubsection.}{0.38em}{}" "\n"
        r"\titleformat{\subsubsection}{\bfseries\zihao{5}}{\thesubsubsection.}{0.35em}{}" "\n"
        r"\titlespacing*{\section}{0pt}{0.95ex plus 0.2ex minus 0.15ex}{0.38ex}" "\n"
        r"\titlespacing*{\subsection}{0pt}{0.72ex plus 0.18ex minus 0.12ex}{0.26ex}" "\n"
        r"\titlespacing*{\subsubsection}{0pt}{0.55ex plus 0.15ex minus 0.1ex}{0.18ex}" "\n"
        r"\pagestyle{fancy}" "\n"
        r"\fancyhf{}" "\n"
        rf"\fancyhead[C]{{\zihao{{-5}} {_escape_latex(report_name)}}}" "\n"
        r"\fancyfoot[C]{\thepage}" "\n"
        r"\renewcommand{\headrulewidth}{0.4pt}" "\n"
        r"\renewcommand{\footrulewidth}{0pt}" "\n"
        r"\setlength{\headheight}{14pt}" "\n"
        r"\setlength{\textfloatsep}{5pt plus 1pt minus 1pt}" "\n"
        r"\setlength{\floatsep}{5pt plus 1pt minus 1pt}" "\n"
        r"\setlength{\intextsep}{5pt plus 1pt minus 1pt}" "\n"
        r"\renewcommand{\topfraction}{0.92}" "\n"
        r"\renewcommand{\bottomfraction}{0.82}" "\n"
        r"\renewcommand{\textfraction}{0.05}" "\n"
        r"\renewcommand{\floatpagefraction}{0.82}" "\n"
        r"\setcounter{topnumber}{3}" "\n"
        r"\setcounter{bottomnumber}{2}" "\n"
        r"\setcounter{totalnumber}{5}" "\n"
        r"\setcounter{secnumdepth}{3}" "\n"
        r"\renewcommand{\abstractname}{摘要}" "\n"
        "\n"
        r"\begin{document}" "\n"
        r"\thispagestyle{fancy}" "\n"
        r"\begin{center}" "\n"
        + "{\\bfseries\\fontsize{18pt}{22pt}\\selectfont "
        + _escape_latex(report_name)
        + r"\par}" "\n"
        r"\end{center}" "\n"
        r"\vspace{0.2em}" "\n\n"
        + abstract_block
        + body_block
        + rendered_bibliography_block
        + r"\end{document}" "\n"
    )


def _should_override_template_for_chinese_medical(report_language: str | None, template_path: str | None) -> bool:
    if report_language != "zh":
        return False
    if not template_path:
        return False
    return "arxiv" in Path(template_path).name.casefold()


def _ensure_template_language_support(
    template_text: str,
    report_name: str,
    latex_body: str,
    *,
    report_language: str | None = None,
) -> str:
    should_enable_cjk = report_language == "zh" or _contains_cjk(report_name + latex_body)
    if not should_enable_cjk:
        return _ensure_template_support_packages(template_text, report_language=report_language)

    sanitized = _sanitize_template_for_cjk(template_text)
    sanitized = _ensure_template_support_packages(sanitized, report_language=report_language)
    sanitized = _ensure_abstract_name_for_cjk(sanitized)
    lowered = sanitized.lower()
    if any(token in lowered for token in ("ctex", "xecjk", "cjkutf8")):
        return sanitized

    documentclass_match = re.search(r"\\documentclass(?:\[[^\]]*\])?\{[^}]+\}", sanitized)
    insertion = "\n\\usepackage[UTF8]{ctex}\n"
    if documentclass_match:
        insert_at = documentclass_match.end()
        return sanitized[:insert_at] + insertion + sanitized[insert_at:]
    return insertion + sanitized


def _auto_adapt_template(
    *,
    template_text: str,
    report_name: str,
    latex_body: str,
    generated_at: str,
) -> str:
    rendered = _replace_first_command_argument(template_text, "title", _escape_latex(report_name))
    rendered = _replace_first_command_argument(rendered, "date", _escape_latex(generated_at), allow_missing=True)
    rendered = _set_or_insert_renewcommand(rendered, "shorttitle", _escape_latex(report_name))
    rendered = _set_or_insert_renewcommand(rendered, "headeright", "")
    rendered = _set_or_insert_renewcommand(rendered, "undertitle", "")
    rendered = re.sub(r"\\today\b", _escape_latex(generated_at), rendered)
    rendered = re.sub(
        r"pdftitle\s*=\s*\{.*?\}",
        lambda _: f"pdftitle={{{_escape_latex(report_name)}}}",
        rendered,
        count=1,
        flags=re.DOTALL,
    )

    document_match = re.search(
        r"(?P<prefix>.*?\\begin\{document\})(?P<body>.*?)(?P<suffix>\\end\{document\}.*)$",
        rendered,
        flags=re.DOTALL,
    )
    if not document_match:
        return rendered + "\n\\begin{document}\n" + _build_auto_template_body(rendered, latex_body) + "\n\\end{document}\n"

    prefix = document_match.group("prefix")
    original_body = document_match.group("body")
    suffix = document_match.group("suffix")
    adapted_body = _build_auto_template_body(original_body, latex_body)
    return prefix + "\n" + adapted_body + "\n" + suffix


def _format_generated_at(report_language: str | None) -> str:
    now = datetime.now()
    if report_language == "en":
        return now.strftime("%B %d, %Y").replace(" 0", " ")
    if report_language == "zh":
        return f"{now.year}年{now.month}月{now.day}日"
    return now.strftime("%Y-%m-%d %H:%M:%S")


def _englishify_template_frontmatter(template_text: str) -> str:
    document_match = re.search(
        r"(?P<preamble>.*?)(?P<body>\\begin\{document\}.*)$",
        template_text,
        flags=re.DOTALL,
    )
    if not document_match:
        return _translate_template_metadata_to_english(template_text)

    preamble = document_match.group("preamble")
    body = document_match.group("body")
    return _translate_template_metadata_to_english(preamble) + body


def _translate_template_metadata_to_english(text: str) -> str:
    updated = text
    direct_replacements = [
        ("作者", "Author"),
        ("作者一", "Author 1"),
        ("作者二", "Author 2"),
        ("作者三", "Author 3"),
        ("作者四", "Author 4"),
        ("单位", "Affiliation"),
        ("单位一", "Affiliation 1"),
        ("单位二", "Affiliation 2"),
        ("单位三", "Affiliation 3"),
        ("单位四", "Affiliation 4"),
        ("作者单位", "Affiliation"),
        ("通信作者", "Corresponding author"),
        ("通讯作者", "Corresponding author"),
        ("电子邮箱", "Email"),
        ("邮箱", "Email"),
        ("浣滆€?", "Author"),
        ("鍗曚綅", "Affiliation"),
        ("浣滆€", "Author"),
    ]
    for source, target in direct_replacements:
        updated = updated.replace(source, target)

    updated = re.sub(r"Author\s*([0-9]+)", r"Author \1", updated)
    updated = re.sub(r"Affiliation\s*([0-9]+)", r"Affiliation \1", updated)
    updated = re.sub(
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        lambda match: _format_explicit_english_date(match.group(1), match.group(2), match.group(3)),
        updated,
    )
    updated = re.sub(
        r"(\d{4})\s*骞?\s*(\d{1,2})\s*鏈?\s*(\d{1,2})\s*鏃?",
        lambda match: _format_explicit_english_date(match.group(1), match.group(2), match.group(3)),
        updated,
    )
    return updated


def _format_explicit_english_date(year_text: str, month_text: str, day_text: str) -> str:
    month_names = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December",
    }
    month_value = int(month_text)
    day_value = int(day_text)
    return f"{month_names.get(month_value, 'January')} {day_value}, {year_text}"


def _build_auto_template_body(original_body: str, latex_body: str) -> str:
    abstract_text, remaining_body = _extract_abstract_section(latex_body)
    parts: list[str] = []

    maketitle_match = re.search(r"\\maketitle\b", original_body)
    if maketitle_match:
        frontmatter = original_body[: maketitle_match.start()].strip()
        if frontmatter:
            parts.append(frontmatter)
        parts.append(r"\maketitle")

    if abstract_text:
        parts.append("\\begin{abstract}\n" + abstract_text.strip() + "\n\\end{abstract}")

    cleaned_body = remaining_body.strip()
    if cleaned_body:
        parts.append(cleaned_body)

    if not parts:
        parts.append(latex_body.strip())
    return "\n\n".join(parts).strip()


def _extract_abstract_section(latex_body: str) -> tuple[str | None, str]:
    pattern = re.compile(
        r"^\s*(?P<cmd>\\(?:section|chapter)\*?\{(?P<title>[^}]*)\})\s*(?P<body>.*?)(?=^\s*\\(?:section|chapter)\*?\{|^\s*\\end\{document\}|\Z)",
        flags=re.DOTALL | re.MULTILINE,
    )
    for match in pattern.finditer(latex_body):
        title = match.group("title").strip().lower()
        if title not in ABSTRACT_TITLES:
            continue

        abstract_text = match.group("body").strip()
        remaining = (latex_body[: match.start()] + latex_body[match.end() :]).strip()
        return abstract_text, remaining
    return None, latex_body


def _ensure_bibliography_block(template_text: str, *, bibliography_block: str | None = None) -> str:
    rendered = _ensure_numeric_citation_style(template_text)
    if bibliography_block:
        return _replace_bibliography_block(rendered, bibliography_block)
    rendered = re.sub(
        r"^[^%\n]*\\bibliographystyle\{[^}]+\}[^\n]*$",
        r"\bibliographystyle{plainnat}",
        rendered,
        count=1,
        flags=re.MULTILINE,
    )
    bibliography_match = re.search(r"^(?P<prefix>[^%\n]*\\bibliography\{)(?P<name>[^}]+)(?P<suffix>\})", rendered, flags=re.MULTILINE)
    if bibliography_match:
        rendered = (
            rendered[: bibliography_match.start("name")]
            + "references"
            + rendered[bibliography_match.end("name") :]
        )
        if re.search(r"^[^%\n]*\\bibliographystyle\{", rendered, flags=re.MULTILINE):
            return rendered
        insert_at = bibliography_match.start()
        return rendered[:insert_at] + "\\bibliographystyle{plainnat}\n" + rendered[insert_at:]
    if re.search(r"^[^%\n]*\\printbibliography\b", rendered, flags=re.MULTILINE):
        return rendered
    if re.search(r"^[^%\n]*\\begin\{thebibliography\}", rendered, flags=re.MULTILINE):
        return rendered

    bibliography_block = "\n\\bibliographystyle{plainnat}\n\\bibliography{references}\n"
    end_document_match = re.search(r"\\end\{document\}", rendered)
    if not end_document_match:
        return rendered + bibliography_block
    insert_at = end_document_match.start()
    return rendered[:insert_at] + bibliography_block + rendered[insert_at:]


def _replace_bibliography_block(template_text: str, bibliography_block: str) -> str:
    rendered = re.sub(
        r"^[^%\n]*\\bibliographystyle\{[^}]+\}[^\n]*\n?",
        "",
        template_text,
        flags=re.MULTILINE,
    )
    rendered = re.sub(
        r"^[^%\n]*\\bibliography\{[^}]+\}[^\n]*\n?",
        "",
        rendered,
        flags=re.MULTILINE,
    )
    rendered = re.sub(
        r"^[^%\n]*\\printbibliography\b[^\n]*\n?",
        "",
        rendered,
        flags=re.MULTILINE,
    )
    rendered = re.sub(
        r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}\s*",
        "",
        rendered,
        flags=re.DOTALL,
    )

    block = "\n" + bibliography_block.strip() + "\n"
    end_document_match = re.search(r"\\end\{document\}", rendered)
    if not end_document_match:
        return rendered.rstrip() + block
    insert_at = end_document_match.start()
    return rendered[:insert_at] + block + rendered[insert_at:]


def _remove_bibliography_block(template_text: str) -> str:
    rendered = re.sub(
        r"^[^%\n]*\\bibliographystyle\{[^}]+\}[^\n]*\n?",
        "",
        template_text,
        flags=re.MULTILINE,
    )
    rendered = re.sub(
        r"^[^%\n]*\\bibliography\{[^}]+\}[^\n]*\n?",
        "",
        rendered,
        flags=re.MULTILINE,
    )
    rendered = re.sub(
        r"^[^%\n]*\\printbibliography\b[^\n]*\n?",
        "",
        rendered,
        flags=re.MULTILINE,
    )
    rendered = re.sub(
        r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}\s*",
        "",
        rendered,
        flags=re.DOTALL,
    )
    return rendered


def _compile_latex(
    entry_file: Path,
    output_path: Path,
    compile_log_path: Path,
    *,
    run_bibtex: bool,
) -> dict[str, str]:
    compiler = _find_compiler_profile(run_bibtex=run_bibtex)
    if compiler is None:
        error = RuntimeError(
            "No LaTeX compiler found. The program searched PATH and common TeX Live / MiKTeX install locations."
        )
        setattr(error, "compile_engine", None)
        raise error

    logs: list[str] = []
    last_returncode = 0
    logs.append(f"[compiler selection] {compiler.display_name}")

    latex_runs = 2 if not run_bibtex else 1
    for run_index in range(latex_runs):
        process = _run_subprocess(
            [compiler.engine_path, "-interaction=nonstopmode", "-halt-on-error", entry_file.name],
            cwd=entry_file.parent,
            label=f"latex run {run_index + 1}",
        )
        logs.append(process["log"])
        last_returncode = process["returncode"]
        if last_returncode != 0:
            break

    if last_returncode == 0 and run_bibtex:
        bibtex = compiler.bibtex_path or _find_bibtex_near_engine(Path(compiler.engine_path))
        if not bibtex:
            error = RuntimeError("Bibliography compilation requested, but `bibtex` was not found in PATH.")
            setattr(error, "compile_engine", compiler.display_name)
            raise error

        bibtex_result = _run_subprocess([bibtex, entry_file.stem], cwd=entry_file.parent, label="bibtex run")
        logs.append(bibtex_result["log"])
        last_returncode = bibtex_result["returncode"]

        if last_returncode == 0:
            for run_index in range(2):
                process = _run_subprocess(
                    [compiler.engine_path, "-interaction=nonstopmode", "-halt-on-error", entry_file.name],
                    cwd=entry_file.parent,
                    label=f"latex post-bibtex run {run_index + 1}",
                )
                logs.append(process["log"])
                last_returncode = process["returncode"]
                if last_returncode != 0:
                    break

    compile_log_path.write_text("\n\n" + ("\n" + ("-" * 80) + "\n\n").join(logs), encoding="utf-8")
    compiled_pdf = entry_file.with_suffix(".pdf")
    if last_returncode != 0 or not compiled_pdf.exists():
        error = RuntimeError(_build_latex_failure_message(entry_file.name, compile_log_path, logs))
        setattr(error, "compile_engine", compiler.display_name)
        raise error

    shutil.copy2(compiled_pdf, output_path)
    return {"engine": compiler.display_name}


def _run_subprocess(command: list[str], *, cwd: Path, label: str) -> dict[str, object]:
    process = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "returncode": process.returncode,
        "log": (
            f"[{label}] exit_code={process.returncode}\n"
            f"command: {' '.join(command)}\n"
            f"stdout:\n{process.stdout}\n\nstderr:\n{process.stderr}"
        ),
    }


def _build_latex_failure_message(entry_name: str, compile_log_path: Path, logs: Sequence[str]) -> str:
    joined_logs = "\n".join(logs)
    missing_file = _extract_missing_latex_file(joined_logs)
    if missing_file:
        suffix = missing_file.rsplit(".", 1)[-1].lower() if "." in missing_file else ""
        missing_kind = {
            "sty": "LaTeX package",
            "cls": "LaTeX class",
            "bst": "BibTeX style",
            "bbx": "BibLaTeX style",
            "cbx": "BibLaTeX citation style",
        }.get(suffix, "LaTeX dependency")
        return (
            f"LaTeX compilation failed for {entry_name}. Missing {missing_kind} `{missing_file}`. "
            "If you are using MiKTeX locally, install the package providing this file or enable "
            '"Install missing packages on-the-fly" in MiKTeX Console, then retry. '
            f"See compile log: {compile_log_path}"
        )

    return f"LaTeX compilation failed for {entry_name}. See compile log: {compile_log_path}"


def _extract_missing_latex_file(log_text: str) -> str | None:
    match = re.search(r"! LaTeX Error: File `([^`]+)' not found\.", log_text)
    if match:
        return match.group(1).strip()

    match = re.search(r"! I can't find file `([^`]+)'\.", log_text)
    if match:
        return match.group(1).strip()

    return None


def _find_compiler_profile(*, run_bibtex: bool) -> LatexCompilerProfile | None:
    candidates = _discover_latex_compiler_profiles()
    if run_bibtex:
        candidates = [candidate for candidate in candidates if candidate.bibtex_path]
    return candidates[0] if candidates else None


def _discover_latex_compiler_profiles() -> list[LatexCompilerProfile]:
    profiles: list[LatexCompilerProfile] = []
    seen: set[tuple[str, str]] = set()

    for engine_name in LATEX_ENGINES:
        resolved = shutil.which(engine_name)
        if resolved:
            _append_compiler_profile(
                profiles,
                seen,
                engine_name=engine_name,
                engine_path=resolved,
            )

    for engine_name, engine_path in _iter_common_windows_engine_paths():
        _append_compiler_profile(
            profiles,
            seen,
            engine_name=engine_name,
            engine_path=str(engine_path),
        )

    profiles.sort(key=_latex_profile_sort_key)
    return profiles


def _append_compiler_profile(
    profiles: list[LatexCompilerProfile],
    seen: set[tuple[str, str]],
    *,
    engine_name: str,
    engine_path: str,
) -> None:
    normalized_path = str(Path(engine_path)).lower()
    key = (engine_name, normalized_path)
    if key in seen:
        return
    seen.add(key)

    engine_file = Path(engine_path)
    distribution = _infer_latex_distribution(engine_file)
    bibtex_path = _find_bibtex_near_engine(engine_file) or shutil.which("bibtex")
    profiles.append(
        LatexCompilerProfile(
            engine_name=engine_name,
            engine_path=str(engine_file),
            distribution=distribution,
            bibtex_path=bibtex_path,
        )
    )


def _iter_common_windows_engine_paths() -> list[tuple[str, Path]]:
    results: list[tuple[str, Path]] = []

    for root in WINDOWS_TEXLIVE_ROOTS:
        if not root.exists():
            continue
        version_dirs = [path for path in root.iterdir() if path.is_dir() and path.name.isdigit()]
        for version_dir in sorted(version_dirs, reverse=True):
            bin_dir = version_dir / "bin" / "windows"
            for engine_name in LATEX_ENGINES:
                engine_path = bin_dir / f"{engine_name}.exe"
                if engine_path.exists():
                    results.append((engine_name, engine_path))

    for root in WINDOWS_MIKTEX_ROOTS:
        if not root.exists():
            continue
        for relative in (
            Path("miktex/bin/x64"),
            Path("bin/x64"),
            Path("miktex/bin"),
            Path("bin"),
        ):
            bin_dir = root / relative
            if not bin_dir.exists():
                continue
            for engine_name in LATEX_ENGINES:
                engine_path = bin_dir / f"{engine_name}.exe"
                if engine_path.exists():
                    results.append((engine_name, engine_path))

    return results


def _infer_latex_distribution(engine_path: Path) -> str:
    normalized = str(engine_path).casefold()
    if "texlive" in normalized:
        return "TeX Live"
    if "miktex" in normalized:
        return "MiKTeX"
    return "PATH"


def _find_bibtex_near_engine(engine_path: Path) -> str | None:
    bibtex_path = engine_path.with_name("bibtex.exe")
    if bibtex_path.exists():
        return str(bibtex_path)

    bibtex_path = engine_path.with_name("bibtex")
    if bibtex_path.exists():
        return str(bibtex_path)

    return None


def _latex_profile_sort_key(profile: LatexCompilerProfile) -> tuple[int, int, str]:
    distribution_rank = {"TeX Live": 0, "MiKTeX": 1, "PATH": 2}.get(profile.distribution, 3)
    engine_rank = {name: index for index, name in enumerate(LATEX_ENGINES)}.get(profile.engine_name, 99)
    return distribution_rank, engine_rank, profile.engine_path.casefold()


def _copy_assets(asset_paths: Iterable[Path], destination_dir: Path) -> list[dict[str, str]]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    copied_assets: list[dict[str, str]] = []

    for asset_path in asset_paths:
        destination = destination_dir / asset_path.name
        shutil.copy2(asset_path, destination)
        copied_assets.append({"name": asset_path.name, "path": str(destination)})

    return copied_assets


def _normalize_figure_caption(raw_caption: str, image_name: str, fallback_caption: str = "") -> str:
    caption = raw_caption.strip()
    if not caption:
        return fallback_caption.strip()

    generic_patterns = [
        re.compile(r"^figure\s*\d+$", flags=re.IGNORECASE),
        re.compile(r"^fig\.?\s*\d+$", flags=re.IGNORECASE),
        re.compile(r"^图\s*\d+$"),
        re.compile(r"^(?:Kaplan-?Meier)?\s*(?:生存曲线|结果图|趋势图)$", flags=re.IGNORECASE),
    ]
    normalized = caption.strip().strip(":").strip()
    if any(pattern.fullmatch(normalized) for pattern in generic_patterns):
        return fallback_caption.strip()

    image_stem = Path(image_name).stem
    if normalized.casefold() == image_stem.casefold():
        return fallback_caption.strip()

    normalized = re.sub(r"^(?:figure|fig\.?|图)\s*\d+\s*[:：.\-]?\s*", "", normalized, flags=re.IGNORECASE)
    if not normalized:
        return fallback_caption.strip()

    return normalized


def _build_figure_includegraphics(image_name: str, caption: str = "") -> str:
    lower_name = f"{image_name} {caption}".casefold()
    if any(token in lower_name for token in ("distribution", "pie", "proportion", "composition")):
        return rf"\includegraphics[width=0.52\linewidth,height=0.17\textheight,keepaspectratio]{{assets/{image_name}}}"
    if any(token in lower_name for token in ("km", "kaplan", "survival", "curve")):
        return rf"\includegraphics[width=0.84\linewidth,height=0.32\textheight,keepaspectratio]{{assets/{image_name}}}"
    if any(token in lower_name for token in ("wide", "landscape", "heatmap", "roc")):
        return rf"\includegraphics[width=0.70\linewidth,height=0.22\textheight,keepaspectratio]{{assets/{image_name}}}"
    return rf"\includegraphics[width=0.62\linewidth,height=0.18\textheight,keepaspectratio]{{assets/{image_name}}}"


def _build_compact_pair_includegraphics(image_name: str) -> str:
    lower_name = image_name.casefold()
    trim = "trim=10 6 8 2,clip,"
    if any(token in lower_name for token in ("km", "survival", "curve")):
        trim = "trim=14 8 10 4,clip,"
    return rf"\includegraphics[{trim}width=\linewidth,height=0.14\textheight,keepaspectratio]{{assets/{image_name}}}"


def _build_gbt7714_bibliography(reference_entries: Sequence[dict[str, object]]) -> str:
    if not reference_entries:
        return ""

    width = "99" if len(reference_entries) >= 10 else "9"
    items: list[str] = [rf"\begin{{thebibliography}}{{{width}}}"]
    for entry in reference_entries:
        citation_key = _sanitize_citation_key(str(entry.get("citation_key") or "reference"))
        if not citation_key:
            continue
        rendered_entry = _render_gbt7714_entry(entry)
        if not rendered_entry:
            continue
        items.append(rf"\bibitem{{{citation_key}}} {rendered_entry}")
    items.append(r"\end{thebibliography}")
    return "\n\n".join(items) + "\n"


def _render_gbt7714_entry(entry: dict[str, object]) -> str:
    entry_type = str(entry.get("entry_type") or "misc").lower()
    authors = _format_gbt_authors(entry.get("authors") or [])
    title = _latex_sentence(str(entry.get("title") or "Untitled"))
    year = _escape_latex(str(entry.get("year") or "").strip())
    journal = _latex_sentence(str(entry.get("journal") or "").strip())
    booktitle = _latex_sentence(str(entry.get("booktitle") or "").strip())
    publisher = _latex_sentence(str(entry.get("publisher") or "").strip())
    address = _latex_sentence(str(entry.get("address") or "").strip())
    school = _latex_sentence(str(entry.get("school") or "").strip())
    institution = _latex_sentence(str(entry.get("institution") or "").strip())
    volume = _escape_latex(str(entry.get("volume") or "").strip())
    number = _escape_latex(str(entry.get("number") or "").strip())
    pages = _escape_latex(str(entry.get("pages") or "").strip().replace("--", "-"))
    doi = _escape_latex(str(entry.get("doi") or "").strip())
    url = str(entry.get("url") or "").strip()
    note = _latex_sentence(str(entry.get("note") or "").strip())

    marker = _reference_marker_for_entry(
        entry_type,
        bool(url),
        title=str(entry.get("title") or ""),
        note=str(entry.get("note") or ""),
    )
    lead = f"{authors}. " if authors else ""
    container_url = f". \\url{{{url}}}" if url else ""

    if entry_type == "article" or journal:
        journal_part = journal
        volume_part = volume
        if number:
            volume_part = f"{volume_part}({number})" if volume_part else f"({number})"
        tail = _join_non_empty(", ", [year, volume_part])
        if pages:
            tail = f"{tail}: {pages}" if tail else pages
        body = f"{lead}{title}[{marker}]"
        if journal_part:
            body += f". {journal_part}"
        if tail:
            body += f", {tail}" if journal_part else f". {tail}"
        if doi:
            body += f". DOI: {doi}"
        elif url:
            body += container_url
        return body + "."

    if entry_type in {"inproceedings", "conference"} or booktitle:
        container = booktitle or journal
        publication = _join_publication(address, publisher, year, pages)
        body = f"{lead}{title}[{marker}]"
        if container:
            body += f"//{container}"
        if publication:
            body += f". {publication}"
        elif year:
            body += f". {year}"
        if doi:
            body += f". DOI: {doi}"
        elif url:
            body += container_url
        return body + "."

    if entry_type == "book":
        publication = _join_publication(address, publisher, year, pages)
        body = f"{lead}{title}[{marker}]"
        if publication:
            body += f". {publication}"
        elif year:
            body += f". {year}"
        if url:
            body += container_url
        return body + "."

    if entry_type in {"phdthesis", "mastersthesis"}:
        location = _join_non_empty(": ", [address, school])
        body = f"{lead}{title}[{marker}]"
        if location and year:
            body += f". {location}, {year}"
        elif location:
            body += f". {location}"
        elif year:
            body += f". {year}"
        if url:
            body += container_url
        return body + "."

    if entry_type in {"techreport", "report"}:
        location = _join_non_empty(": ", [address, institution or publisher])
        body = f"{lead}{title}[{marker}]"
        if location and year:
            body += f". {location}, {year}"
        elif location:
            body += f". {location}"
        elif year:
            body += f". {year}"
        if url:
            body += container_url
        return body + "."

    body = f"{lead}{title}[{marker}]"
    details = _join_non_empty(". ", [journal, booktitle, note])
    if details:
        body += f". {details}"
    if year:
        body += f". {year}"
    if url:
        body += container_url
    if doi:
        body += f". DOI: {doi}"
    return body + "."


def _reference_marker_for_entry(entry_type: str, has_url: bool, *, title: str = "", note: str = "") -> str:
    mapping = {
        "article": "J",
        "book": "M",
        "inproceedings": "C",
        "conference": "C",
        "phdthesis": "D",
        "mastersthesis": "D",
        "techreport": "R",
        "report": "R",
        "patent": "P",
        "standard": "S",
        "newspaper": "N",
    }
    online_mapping = {
        "article": "J/OL",
        "book": "M/OL",
        "inproceedings": "C/OL",
        "conference": "C/OL",
        "phdthesis": "D/OL",
        "mastersthesis": "D/OL",
        "techreport": "R/OL",
        "report": "R/OL",
        "standard": "S/OL",
        "newspaper": "N/OL",
    }
    if has_url and entry_type in online_mapping:
        return online_mapping[entry_type]
    if entry_type in mapping:
        return mapping[entry_type]
    if has_url:
        haystack = f"{title} {note}".casefold()
        if any(keyword in haystack for keyword in ("database", "dataset", "数据库", "data set", "cnki")):
            return "DB/OL"
        return "EB/OL"
    return "Z"


def _format_gbt_authors(authors: Sequence[object]) -> str:
    normalized = [_format_gbt_author_name(str(author)) for author in authors if str(author).strip()]
    if not normalized:
        return ""
    if len(normalized) > 3:
        tail = "等" if any(_contains_cjk(author) for author in normalized) else "et al"
        return ", ".join(normalized[:3]) + f", {tail}"
    return ", ".join(normalized)


def _format_gbt_author_name(author: str) -> str:
    cleaned = re.sub(r"\s+", " ", author.replace(".", " ")).strip(" ,;")
    if not cleaned:
        return ""
    if _contains_cjk(cleaned):
        return cleaned
    if "," in cleaned:
        family, given = [part.strip() for part in cleaned.split(",", 1)]
        initials = _initials_from_text(given)
        return _join_non_empty(" ", [family.upper(), initials]).strip()
    tokens = [token for token in cleaned.split(" ") if token]
    if len(tokens) == 1:
        return tokens[0].upper()
    family = tokens[-1].upper()
    initials = " ".join(token[0].upper() for token in tokens[:-1] if token[:1].isalpha())
    return _join_non_empty(" ", [family, initials]).strip()


def _initials_from_text(text: str) -> str:
    return " ".join(token[0].upper() for token in text.split() if token[:1].isalpha())


def _join_non_empty(separator: str, parts: Sequence[str]) -> str:
    return separator.join(part for part in parts if part)


def _join_publication(address: str, publisher: str, year: str, pages: str) -> str:
    left = _join_non_empty(": ", [address, publisher])
    if left and year:
        result = f"{left}, {year}"
    else:
        result = left or year
    if pages:
        result = f"{result}: {pages}" if result else pages
    return result


def _latex_sentence(text: str) -> str:
    return _escape_latex(text.rstrip(" ."))


def _ensure_list(list_stack: list[str], list_type: str) -> list[str]:
    if list_stack and list_stack[-1] == list_type:
        return []
    output = _close_lists(list_stack)
    output.append(rf"\begin{{{list_type}}}")
    list_stack.append(list_type)
    return output


def _close_lists(list_stack: list[str]) -> list[str]:
    output: list[str] = []
    while list_stack:
        output.append(rf"\end{{{list_stack.pop()}}}")
    return output


def _escape_latex(text: str) -> str:
    escaped = []
    for char in text:
        escaped.append(SPECIAL_CHARS.get(char, char))
    return "".join(escaped)


def _convert_inline_markdown(
    text: str,
    *,
    enable_citations: bool = False,
    crossref_context: dict[str, object] | None = None,
) -> str:
    placeholders: dict[str, str] = {}

    def store(value: str) -> str:
        token = f"@@INLINE_{len(placeholders)}@@"
        placeholders[token] = value
        return token

    escaped = _escape_latex(text)
    if enable_citations:
        escaped = MARKDOWN_CITATION_PATTERN.sub(_replace_markdown_citation, escaped)
    escaped = _replace_inline_crossrefs(escaped, crossref_context or {})
    escaped = re.sub(r"`([^`]+)`", lambda match: store(r"\texttt{" + match.group(1) + "}"), escaped)
    escaped = re.sub(r"\*\*([^*\n]+)\*\*", lambda match: store(r"\textbf{" + match.group(1) + "}"), escaped)
    escaped = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", lambda match: store(r"\emph{" + match.group(1) + "}"), escaped)

    for token, value in placeholders.items():
        escaped = escaped.replace(token, value)
    return escaped


def _normalize_heading_level(level: int) -> int:
    if level <= 2:
        return level
    return level - 1


def _build_render_context(markdown_text: str) -> dict[str, object]:
    heading_labels: list[list[str]] = []
    section_labels: set[str] = set()
    figure_numbers: list[int] = []
    figure_labels: set[str] = set()
    figure_captions: list[str] = []
    counters = [0, 0, 0, 0, 0, 0]
    used_slug_labels: set[str] = set()
    source_lines = markdown_text.splitlines()

    for index, raw_line in enumerate(source_lines):
        stripped = raw_line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match:
            heading_text = heading_match.group(2).strip()
            labels: list[str] = []
            if not _is_abstract_heading(heading_text):
                level = min(_normalize_heading_level(len(heading_match.group(1))), 6)
                _advance_heading_counters(counters, level)
                if level <= 3:
                    section_number = ".".join(str(item) for item in counters[:level] if item)
                    if section_number:
                        numeric_label = _section_number_to_label(section_number)
                        labels.append(numeric_label)
                        section_labels.add(numeric_label)

                    slug = _slugify_reference_label(heading_text)
                    slug_label = f"sec:{slug}" if slug else ""
                    if slug_label and slug_label not in used_slug_labels:
                        labels.append(slug_label)
                        used_slug_labels.add(slug_label)
                        section_labels.add(slug_label)
            heading_labels.append(labels)
            continue

        image_matches = list(IMAGE_PATTERN.finditer(stripped))
        if image_matches and stripped == image_matches[0].group(0):
            for match in image_matches:
                figure_number = _extract_figure_number(match.group("path"), len(figure_numbers) + 1)
                figure_numbers.append(figure_number)
                figure_labels.add(f"fig:{figure_number}")
                figure_captions.append(
                    _infer_figure_caption(
                        source_lines,
                        index + 1,
                        figure_number,
                        Path(match.group("path")).name,
                    )
                )

    return {
        "heading_labels": heading_labels,
        "section_labels": section_labels,
        "figure_numbers": figure_numbers,
        "figure_labels": figure_labels,
        "figure_captions": figure_captions,
    }


def _advance_heading_counters(counters: list[int], level: int) -> None:
    if level < 1:
        return
    counters[level - 1] += 1
    for index in range(level, len(counters)):
        counters[index] = 0


def _is_abstract_heading(title: str) -> bool:
    return title.strip().lower() in ABSTRACT_TITLES


def _section_number_to_label(section_number: str) -> str:
    return "sec:" + section_number.replace(".", "-")


def _slugify_reference_label(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:64]


def _extract_figure_number(path_text: str, fallback_number: int) -> int:
    match = re.search(r"figure(\d+)", Path(path_text).name, flags=re.IGNORECASE)
    if match:
        return max(1, int(match.group(1)))
    return max(1, fallback_number)


def _replace_inline_crossrefs(text: str, crossref_context: dict[str, object]) -> str:
    section_labels = set(crossref_context.get("section_labels") or [])
    figure_labels = set(crossref_context.get("figure_labels") or [])

    def replace_section(match: re.Match[str]) -> str:
        label = _section_number_to_label(match.group("number"))
        return rf"\Cref{{{label}}}" if label in section_labels else match.group(0)

    def replace_figure(match: re.Match[str]) -> str:
        label = f"fig:{match.group('number')}"
        return rf"\Cref{{{label}}}" if label in figure_labels else match.group(0)

    replaced = re.sub(
        r"(?i)\bsection\s+(?P<number>\d+(?:\.\d+)*)\b",
        replace_section,
        text,
    )
    replaced = re.sub(
        r"(?i)\bfig(?:ure)?\.?\s*(?P<number>\d+)\b",
        replace_figure,
        replaced,
    )
    replaced = re.sub(
        r"第(?P<number>\d+(?:\.\d+)*)节",
        replace_section,
        replaced,
    )
    replaced = re.sub(
        r"图(?P<number>\d+)",
        replace_figure,
        replaced,
    )
    return replaced


def _infer_figure_caption(source_lines: Sequence[str], start_index: int, figure_number: int, image_name: str) -> str:
    figure_prefixes = (
        f"Figure {figure_number}",
        f"Fig. {figure_number}",
        f"Fig {figure_number}",
        f"图{figure_number}",
    )
    if re.fullmatch(r"figure\d+\.(?:png|jpg|jpeg|pdf)", image_name.casefold()):
        if figure_number == 1:
            return "不同治疗方案分布"
        if figure_number == 2:
            return "不同治疗组无复发生存曲线"
        if figure_number == 3:
            return "不同治疗组总生存曲线"

    context_candidates = list(source_lines[start_index : min(len(source_lines), start_index + 8)])
    if not context_candidates:
        context_candidates = []
    if start_index > 0:
        context_candidates.extend(reversed(source_lines[max(0, start_index - 6) : start_index]))

    context_window = " ".join(
        raw_line.strip()
        for raw_line in source_lines[max(0, start_index - 6) : min(len(source_lines), start_index + 8)]
        if raw_line.strip() and not raw_line.strip().startswith("![")
    )
    context_caption = _heuristic_figure_title(context_window)
    if context_caption:
        return context_caption

    for raw_line in context_candidates:
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("!["):
            break
        if stripped.startswith(("- ", "* ")) or ORDERED_LIST_PATTERN.match(stripped):
            continue

        candidate = stripped
        for prefix in figure_prefixes:
            if candidate.startswith(prefix):
                candidate = re.sub(r"^[^:：.。-]*[:：.。\-]\s*", "", candidate).strip()
                break

        shortened = _shorten_figure_caption(candidate)
        if shortened:
            return shortened

    inferred_from_name = _infer_figure_caption_from_image_name(image_name)
    if inferred_from_name:
        return inferred_from_name
    if figure_number == 1:
        return "不同治疗方案分布"
    if figure_number == 2:
        return "不同治疗组无复发生存曲线"
    if figure_number == 3:
        return "不同治疗组总生存曲线"
    return "Result overview"


def _infer_figure_caption_from_image_name(image_name: str) -> str:
    lower_name = image_name.casefold()
    if any(token in lower_name for token in ("distribution", "pie", "proportion", "composition")):
        return "不同治疗方案分布"
    if any(token in lower_name for token in ("rfs", "recurrence")) and any(
        token in lower_name for token in ("km", "kaplan", "curve", "survival")
    ):
        return "不同治疗组无复发生存曲线"
    if any(token in lower_name for token in ("os", "overall")) and any(
        token in lower_name for token in ("km", "kaplan", "curve", "survival")
    ):
        return "不同治疗组总生存曲线"
    if any(token in lower_name for token in ("km", "kaplan", "curve", "survival")):
        return "Kaplan-Meier生存曲线"
    return ""


def _shorten_figure_caption(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"\[(?P<body>\s*@[^]]+)\]", "", cleaned).strip()
    cleaned = re.sub(r"(?i)^as shown in (?:\\Cref\{fig:\d+\}|fig(?:ure)?\.?\s*\d+),?\s*", "", cleaned).strip()
    cleaned = re.sub(r"^如(?:\\Cref\{fig:\d+\}|图\s*\d+)所示[，,]?\s*", "", cleaned).strip()
    cleaned = cleaned.strip("*").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return ""

    clause_parts = re.split(r"[。；;:：.!?]", cleaned, maxsplit=1)
    head = clause_parts[0].strip(" ,，")
    if not head:
        return ""

    if _contains_cjk(head):
        head = re.sub(r"^(?:该图|本图|图中)", "", head).strip()
        head = re.sub(r"^(?:展示了|显示了|呈现了|给出了|反映了|说明了)", "", head).strip()
        head = re.sub(r"^(?:不同治疗组(?:的)?|各治疗组(?:的)?)(?=\S)", "", head).strip()
        if "无复发生存" in head and "曲线" in head:
            return "无复发生存曲线"
        if "总生存" in head and "曲线" in head:
            return "总生存曲线"
        if "Kaplan-Meier" in head and "曲线" in head:
            return "Kaplan-Meier曲线"
        compact = re.sub(r"\s+", "", head)
        return compact[:14] if compact else ""

    head = re.sub(
        r"(?i)^(?:this|the)\s+(?:figure|chart|plot|graph)\s+(?:presents|shows|illustrates|reports)\s+",
        "",
        head,
    ).strip()
    head = re.sub(r"(?i)^(?:the|a|an)\s+", "", head).strip()
    if not head:
        return ""

    words = [word for word in head.split(" ") if word]
    if not words:
        return ""
    return " ".join(words[:4]).strip(" ,")


def _heuristic_figure_title(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    normalized = compact.lower()
    normalized_spaced = re.sub(r"\s+", " ", text).lower()

    if _contains_cjk(text):
        if ("无复发生存" in compact or "rfs" in normalized) and ("曲线" in compact or "kaplan-meier" in normalized):
            return "不同治疗组无复发生存曲线"
        if ("总生存" in compact or re.search(r"\bos\b", normalized)) and ("曲线" in compact or "kaplan-meier" in normalized):
            return "不同治疗组总生存曲线"
        if "治疗" in compact and any(keyword in compact for keyword in ("占比", "构成", "比例", "分布")):
            return "不同治疗组别分布"
        if "治疗" in compact and any(keyword in compact for keyword in ("示意", "分组")):
            return "不同治疗组别示意图"
        if any(keyword in compact for keyword in ("基线特征", "患者特征", "临床特征")):
            return "患者基线特征比较"
        if "随访" in compact and any(keyword in compact for keyword in ("流程", "路径", "示意")):
            return "随访流程示意图"
        return ""

    if ("recurrence-free survival" in normalized_spaced or re.search(r"\brfs\b", normalized_spaced)) and (
        "curve" in normalized_spaced or "kaplan-meier" in normalized_spaced
    ):
        return "Recurrence-free survival by treatment"
    if ("overall survival" in normalized_spaced or re.search(r"\bos\b", normalized_spaced)) and (
        "curve" in normalized_spaced or "kaplan-meier" in normalized_spaced
    ):
        return "Overall survival by treatment"
    if "treatment" in normalized_spaced and any(
        keyword in normalized_spaced for keyword in ("distribution", "proportion", "composition")
    ):
        return "Treatment group distribution"
    if "baseline" in normalized_spaced and "characteristic" in normalized_spaced:
        return "Baseline characteristics"
    return ""


def _shorten_figure_caption(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"\[(?P<body>\s*@[^]]+)\]", "", cleaned).strip()
    cleaned = re.sub(r"(?i)^as shown in (?:\\Cref\{fig:\d+\}|fig(?:ure)?\.?\s*\d+),?\s*", "", cleaned).strip()
    cleaned = re.sub(r"^(?:如|见)?(?:\\Cref\{fig:\d+\}|图\s*\d+)[所示见]*[，,:：]?\s*", "", cleaned).strip()
    cleaned = cleaned.strip("*").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return ""

    heuristic_title = _heuristic_figure_title(cleaned)
    if heuristic_title:
        return heuristic_title

    clause_parts = re.split(r"[;:：。！？!?]", cleaned, maxsplit=1)
    head = clause_parts[0].strip(" ,.:;:：")
    if not head:
        return ""

    if _contains_cjk(head):
        head = re.sub(r"^(?:该图|本图|图中|结果显示|结果表明|结果提示|展示了|显示了|呈现了|反映了|比较了|描述了|说明了)", "", head).strip()
        compact = re.sub(r"\s+", "", head)
        return compact[:12] if compact else ""

    head = re.sub(
        r"(?i)^(?:this|the)\s+(?:figure|chart|plot|graph)\s+(?:presents|shows|illustrates|reports|compares)\s+",
        "",
        head,
    ).strip()
    head = re.sub(r"(?i)^(?:the|a|an)\s+", "", head).strip()
    if not head:
        return ""

    words = [word for word in head.split(" ") if word]
    if not words:
        return ""
    return " ".join(words[:4]).strip(" ,")


def _finalize_latex_body(latex_body: str) -> str:
    labeled = _ensure_table_labels(latex_body)
    replaced = _replace_table_crossrefs(labeled)
    return _inject_section_intro_paragraphs(replaced)


def _inject_section_intro_paragraphs(latex_body: str) -> str:
    return latex_body

    """Insert a brief introductory sentence only for top-level sections when a
    chapter starts directly with a list or figure environment.

    We intentionally avoid adding these transition sentences after subsections,
    subsubsections, or standalone bold subheadings, because that produces noisy
    filler such as "关于……，现概述如下" under every small block.
    """
    block_pattern = re.compile(
        r"(?P<prefix>"
        r"(?:\\section\{(?P<section_title>[^}]*)\}(?:\s*\\label\{[^}]*\})*)"
        r")"
        r"(?P<gap>\s*)"
        r"(?P<list_begin>\\begin\{(?:enumerate|itemize|figure)\})",
    )

    def _clean_intro_title(title: str) -> str:
        cleaned = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", "", title)
        cleaned = re.sub(r"^\s*\d+(?:\.\d+)*\.??\s*", "", cleaned)
        return cleaned.strip(" ：:，,；;。")

    def _make_intro(title: str, list_type: str) -> str:
        clean_title = _clean_intro_title(title)
        if not clean_title:
            return ""
        if _contains_cjk(clean_title):
            if list_type == "figure":
                return f"\\noindent {clean_title}如下所示。"
            return f"\\noindent 关于{clean_title}，现概述如下："
        if list_type == "figure":
            return f"\\noindent The following presents the results for {clean_title}."
        return f"\\noindent An overview of {clean_title} is provided below:"

    def replace(match: re.Match[str]) -> str:
        title = (match.group("section_title") or "").strip()
        list_begin = match.group("list_begin")
        list_type = (
            "enumerate" if "enumerate" in list_begin
            else "figure" if "figure" in list_begin
            else "itemize"
        )
        intro = _make_intro(title, list_type)
        if not intro:
            return match.group(0)
        return f"{match.group('prefix')}\n{intro}\n{list_begin}"

    return block_pattern.sub(replace, latex_body)


def _ensure_numeric_citation_style(template_text: str) -> str:
    if r"\setcitestyle{numbers,square}" in template_text:
        return template_text

    lowered = template_text.lower()
    if r"\usepackage{natbib}" not in lowered:
        return template_text

    natbib_match = re.search(
        r"^[^\n]*\\usepackage(?:\[[^\]]*\])?\{natbib\}[^\n]*$",
        template_text,
        flags=re.MULTILINE,
    )
    if natbib_match is None:
        begin_document = re.search(r"\\begin\{document\}", template_text)
        insertion = "\n\\setcitestyle{numbers,square}\n"
        if begin_document is None:
            return template_text.rstrip() + insertion
        return template_text[: begin_document.start()] + insertion + template_text[begin_document.start() :]

    insert_at = natbib_match.end()
    return template_text[:insert_at] + "\n\\setcitestyle{numbers,square}" + template_text[insert_at:]


def _ensure_table_labels(latex_body: str) -> str:
    counter = 0
    pattern = re.compile(r"\\begin\{table\}.*?\\end\{table\}", flags=re.DOTALL)

    def replace(match: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        block = match.group(0)
        if r"\label{" in block:
            return block
        caption_match = re.search(r"\\caption(?:\[[^\]]*\])?\{.*?\}", block, flags=re.DOTALL)
        if caption_match is None:
            return block
        insert_at = caption_match.end()
        return block[:insert_at] + f"\n\\label{{tab:{counter}}}" + block[insert_at:]

    return pattern.sub(replace, latex_body)


def _replace_table_crossrefs(latex_body: str) -> str:
    table_labels = {f"tab:{number}" for number in re.findall(r"\\label\{tab:(\d+)\}", latex_body)}
    if not table_labels:
        return latex_body

    def replace_table(match: re.Match[str]) -> str:
        label = f"tab:{match.group('number')}"
        return rf"\Cref{{{label}}}" if label in table_labels else match.group(0)

    processed_lines: list[str] = []
    for raw_line in latex_body.splitlines():
        stripped = raw_line.lstrip()
        if stripped.startswith((r"\caption{", r"\label{")):
            processed_lines.append(raw_line)
            continue
        updated_line = re.sub(r"(?i)\btable\s+(?P<number>\d+)\b", replace_table, raw_line)
        updated_line = re.sub(r"表(?P<number>\d+)", replace_table, updated_line)
        processed_lines.append(updated_line)
    return "\n".join(processed_lines).strip() + "\n"


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _replace_markdown_citation(match: re.Match[str]) -> str:
    keys = [
        _sanitize_citation_key(item.strip().removeprefix("@"))
        for item in match.group("body").split(";")
        if item.strip()
    ]
    keys = [key for key in keys if key]
    if not keys:
        return ""
    return r"\citep{" + ",".join(keys) + "}"


def _sanitize_citation_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9:_-]+", "", value)


def _sanitize_template_for_cjk(template_text: str) -> str:
    patterns = [
        r"(?mi)^\s*\\usepackage(?:\[[^\]]*\])?\{inputenc\}[^\n]*\n?",
        r"(?mi)^\s*\\usepackage(?:\[[^\]]*\])?\{fontenc\}[^\n]*\n?",
        r"(?mi)^\s*\\usepackage(?:\[[^\]]*\])?\{microtype\}[^\n]*\n?",
        r"(?mi)^\s*\\usepackage(?:\[[^\]]*\])?\{times\}[^\n]*\n?",
        r"(?mi)^\s*\\usepackage(?:\[[^\]]*\])?\{mathptmx\}[^\n]*\n?",
        r"(?mi)^\s*\\usepackage(?:\[[^\]]*\])?\{txfonts\}[^\n]*\n?",
        r"(?mi)^\s*\\usepackage(?:\[[^\]]*\])?\{newtxtext\}[^\n]*\n?",
        r"(?mi)^\s*\\usepackage(?:\[[^\]]*\])?\{newtxmath\}[^\n]*\n?",
    ]
    sanitized = template_text
    for pattern in patterns:
        sanitized = re.sub(pattern, "", sanitized)
    return sanitized


def _template_declares_package(template_text: str, package_name: str) -> bool:
    pattern = rf"\\(?:usepackage|RequirePackage)(?:\[[^\]]*\])?\{{[^}}]*\b{re.escape(package_name)}\b[^}}]*\}}"
    return re.search(pattern, template_text, flags=re.IGNORECASE) is not None


def _template_likely_loads_hyperref(template_text: str) -> bool:
    if _template_declares_package(template_text, "hyperref"):
        return True
    lowered = template_text.lower()
    return "rvdtx" in lowered


def _ensure_template_support_packages(template_text: str, *, report_language: str | None = None) -> str:
    lowered = template_text.lower()
    additions: list[str] = []
    template_loads_hyperref = _template_likely_loads_hyperref(template_text)

    if not template_loads_hyperref:
        additions.append(r"\usepackage{hyperref}")
    if r"\hypersetup{hidelinks}" not in lowered:
        additions.append(r"\hypersetup{hidelinks}")
    if not _template_declares_package(template_text, "cleveref"):
        additions.append(r"\usepackage{cleveref}")
    if report_language == "zh" and r"\crefname{figure}{图}{图}" not in template_text:
        additions.append(_chinese_cleveref_setup().rstrip())
    if not _template_declares_package(template_text, "indentfirst"):
        additions.append(r"\usepackage{indentfirst}")
    if r"\usepackage{float}" not in lowered:
        additions.append(r"\usepackage{float}")
    if r"\usepackage{natbib}" not in lowered:
        additions.append(r"\usepackage{natbib}")
    if r"\usepackage{enumitem}" not in lowered:
        additions.append(r"\usepackage{enumitem}")
    if r"\setlist{itemsep=0.35em,topsep=0.2em,parsep=0pt,partopsep=0pt,leftmargin=*}" not in lowered:
        additions.append(r"\setlist{itemsep=0.35em,topsep=0.2em,parsep=0pt,partopsep=0pt,leftmargin=*}")
    if r"\setlength{\parindent}{2em}" not in lowered:
        additions.append(r"\setlength{\parindent}{2em}")
    if r"\setlength{\parskip}{0pt}" not in lowered:
        additions.append(r"\setlength{\parskip}{0pt}")
    if r"\raggedbottom" not in lowered:
        additions.append(r"\raggedbottom")
    if r"\widowpenalty=10000" not in lowered:
        additions.append(r"\widowpenalty=10000")
    if r"\clubpenalty=10000" not in lowered:
        additions.append(r"\clubpenalty=10000")
    if r"\interfootnotelinepenalty=10000" not in lowered:
        additions.append(r"\interfootnotelinepenalty=10000")
    if r"\setlength{\abovecaptionskip}{4pt}" not in lowered:
        additions.append(r"\setlength{\abovecaptionskip}{4pt}")
    if r"\setlength{\belowcaptionskip}{2pt}" not in lowered:
        additions.append(r"\setlength{\belowcaptionskip}{2pt}")
    if r"\setlength{\intextsep}{6pt plus 2pt minus 2pt}" not in lowered:
        additions.append(r"\setlength{\intextsep}{6pt plus 2pt minus 2pt}")
    if r"\setlength{\textfloatsep}{8pt plus 2pt minus 2pt}" not in lowered:
        additions.append(r"\setlength{\textfloatsep}{8pt plus 2pt minus 2pt}")
    if r"\setlength{\floatsep}{8pt plus 2pt minus 2pt}" not in lowered:
        additions.append(r"\setlength{\floatsep}{8pt plus 2pt minus 2pt}")
    if r"\setcounter{secnumdepth}{3}" not in lowered:
        additions.append(r"\setcounter{secnumdepth}{3}")
    if r"\renewcommand{\topfraction}{0.92}" not in lowered:
        additions.append(r"\renewcommand{\topfraction}{0.92}")
    if r"\renewcommand{\bottomfraction}{0.85}" not in lowered:
        additions.append(r"\renewcommand{\bottomfraction}{0.85}")
    if r"\renewcommand{\textfraction}{0.06}" not in lowered:
        additions.append(r"\renewcommand{\textfraction}{0.06}")
    if r"\renewcommand{\floatpagefraction}{0.82}" not in lowered:
        additions.append(r"\renewcommand{\floatpagefraction}{0.82}")
    if r"\setcounter{topnumber}{3}" not in lowered:
        additions.append(r"\setcounter{topnumber}{3}")
    if r"\setcounter{bottomnumber}{2}" not in lowered:
        additions.append(r"\setcounter{bottomnumber}{2}")
    if r"\setcounter{totalnumber}{6}" not in lowered:
        additions.append(r"\setcounter{totalnumber}{6}")
    if not additions:
        return template_text

    insertion = "\n" + "\n".join(additions) + "\n"
    begin_document = re.search(r"\\begin\{document\}", template_text)
    if begin_document:
        insert_at = begin_document.start()
        return template_text[:insert_at] + insertion + template_text[insert_at:]

    documentclass_match = re.search(r"\\documentclass(?:\[[^\]]*\])?\{[^}]+\}", template_text)
    if documentclass_match:
        insert_at = documentclass_match.end()
        return template_text[:insert_at] + insertion + template_text[insert_at:]
    return insertion + template_text


def _chinese_cleveref_setup() -> str:
    return (
        r"\crefname{figure}{图}{图}" "\n"
        r"\Crefname{figure}{图}{图}" "\n"
        r"\crefname{table}{表}{表}" "\n"
        r"\Crefname{table}{表}{表}" "\n"
    )


def _ensure_abstract_name_for_cjk(template_text: str) -> str:
    replacement = r"\renewcommand{\abstractname}{摘要}"
    pattern = re.compile(r"^[ \t]*%?[ \t]*\\renewcommand\s*\{\\abstractname\}\s*\{.*?\}[ \t]*$", flags=re.MULTILINE)
    if pattern.search(template_text):
        return pattern.sub(replacement, template_text, count=1)

    begin_document = re.search(r"\\begin\{document\}", template_text)
    if begin_document is None:
        return template_text.rstrip() + "\n" + replacement + "\n"
    return template_text[: begin_document.start()] + replacement + "\n" + template_text[begin_document.start() :]


def _replace_first_command_argument(
    template_text: str,
    command: str,
    new_value: str,
    *,
    allow_missing: bool = False,
) -> str:
    command_match = re.search(rf"\\{command}(?![A-Za-z])", template_text)
    if command_match is None:
        return template_text if allow_missing else template_text

    index = command_match.end()
    while index < len(template_text) and template_text[index].isspace():
        index += 1

    while index < len(template_text) and template_text[index] == "[":
        optional_end = _find_balanced_block(template_text, index, "[", "]")
        if optional_end is None:
            return template_text if allow_missing else template_text
        index = optional_end + 1
        while index < len(template_text) and template_text[index].isspace():
            index += 1

    if index >= len(template_text) or template_text[index] != "{":
        return template_text if allow_missing else template_text

    argument_end = _find_balanced_block(template_text, index, "{", "}")
    if argument_end is None:
        return template_text if allow_missing else template_text

    command_prefix = template_text[command_match.start() : index]
    return template_text[: command_match.start()] + command_prefix + "{" + new_value + "}" + template_text[argument_end + 1 :]


def _set_or_insert_renewcommand(template_text: str, command: str, new_value: str) -> str:
    pattern = re.compile(rf"^[ \t]*%?[ \t]*\\renewcommand\s*\{{\\{command}\}}", flags=re.MULTILINE)
    command_match = pattern.search(template_text)
    replacement = rf"\renewcommand{{\{command}}}{{{new_value}}}"
    fallback_replacement = rf"\newcommand{{\{command}}}{{{new_value}}}"

    if command_match is None:
        insertion_anchor = re.search(r"\\hypersetup\s*\{", template_text)
        if insertion_anchor is None:
            insertion_anchor = re.search(r"\\begin\{document\}", template_text)
        if insertion_anchor is None:
            return template_text.rstrip() + "\n" + fallback_replacement + "\n"
        return (
            template_text[: insertion_anchor.start()]
            + fallback_replacement
            + "\n"
            + template_text[insertion_anchor.start() :]
        )

    index = command_match.end()
    while index < len(template_text) and template_text[index].isspace():
        index += 1

    if index >= len(template_text) or template_text[index] != "{":
        line_end = template_text.find("\n", command_match.start())
        if line_end == -1:
            line_end = len(template_text)
        return template_text[: command_match.start()] + replacement + template_text[line_end:]

    argument_end = _find_balanced_block(template_text, index, "{", "}")
    if argument_end is None:
        line_end = template_text.find("\n", command_match.start())
        if line_end == -1:
            line_end = len(template_text)
        return template_text[: command_match.start()] + replacement + template_text[line_end:]

    line_end = template_text.find("\n", argument_end)
    if line_end == -1:
        line_end = len(template_text)
    return template_text[: command_match.start()] + replacement + template_text[line_end:]


def _find_balanced_block(text: str, start: int, open_char: str, close_char: str) -> int | None:
    if start >= len(text) or text[start] != open_char:
        return None

    depth = 1
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None
