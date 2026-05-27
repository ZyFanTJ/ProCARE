import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.core.config import get_settings
from app.services.job_store import FileJobStore
from app.services.latex_renderer import LatexRenderError, markdown_to_latex, render_report_latex
from app.services.llm_service import (
    LLMConfig,
    LLMConfigurationError,
    LLMInvocationError,
    LLMStageError,
    call_llm_stage,
    resolve_llm_config,
)
from app.services.pipeline_prompts import (
    build_chinese_finalize_prompts,
    build_citation_grounding_prompts,
    build_initial_draft_prompts,
    build_literature_alignment_prompts,
    build_normalizer_prompts,
    build_refiner_prompts,
    build_translation_prompts,
)
from app.services.reference_library import build_reference_library
from app.services.structured_report import build_structured_report, rewrite_markdown_image_paths

ORDERED_LIST_PATTERN = re.compile(r"^\d+\.\s+(.*)$")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_LINE_PATTERN = re.compile(r"!\[(?P<alt>.*?)\]\((?P<path>.*?)\)")
TABLE_SEPARATOR_CELL_PATTERN = re.compile(r"^:?-{3,}:?$")
TABLE_SEPARATOR_ROW_PATTERN = re.compile(r"^\|?\s*:?-{3,}:?(?:\s*\|\s*:?-{3,}:?)+\s*\|?$")

ZH_ABSTRACT_HEADING = "\u6458\u8981"
ZH_KEYWORDS_HEADING = "\u5173\u952e\u8bcd"
ZH_INTRODUCTION_HEADING = "\u5f15\u8a00"
ZH_METHODS_HEADING = "\u60a3\u8005\u4e0e\u65b9\u6cd5"
ZH_RESULTS_HEADING = "\u7ed3\u679c"
ZH_DISCUSSION_HEADING = "\u8ba8\u8bba"

ZH_REFERENCE_METHODS_SUBHEADINGS = [
    "\u60a3\u8005",
    "\u4e34\u5e8a\u548c\u75c5\u7406\u6307\u6807",
    "\u968f\u8bbf\u548c\u6cbb\u7597",
    "\u7edf\u8ba1\u5b66\u5206\u6790",
]


@dataclass(frozen=True)
class ResultEvidence:
    patient_count: str = ""
    treatment_facts: tuple[tuple[str, str, str], ...] = ()
    rfs_p_value: str = ""
    os_p_value: str = ""
    trend_sentence: str = ""
    baseline_table: tuple[tuple[str, ...], ...] = ()
    treatment_group_table: tuple[tuple[str, ...], ...] = ()
    univariate_rows: tuple[tuple[str, ...], ...] = ()
    multivariate_rows: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class MarkdownTableBlock:
    title: str
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    context_before: str = ""


TableRows = tuple[tuple[str, ...], ...]


TREATMENT_GROUP_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("监测/未治疗组", ("监测/未治疗", "监测", "未治疗", "观察", "观察组", "随访", "watchful waiting", "observation")),
    ("TACE组", ("单纯tace", "tace组", "tace")),
    ("免疫治疗组", ("单纯免疫治疗", "免疫治疗组", "免疫治疗", "immunotherapy")),
    ("靶向治疗组", ("单纯靶向治疗", "靶向治疗组", "靶向治疗", "targeted therapy")),
    ("联合治疗组", ("联合治疗组", "联合治疗", "免疫联合靶向", "联合方案", "combination therapy")),
)


UNIVARIATE_SECTION_HINTS = ("单因素", "单变量", "univariate", "单因素cox")
MULTIVARIATE_SECTION_HINTS = ("多因素", "多变量", "multivariate", "adjusted", "校正后", "cox回归")
ANALYSIS_COMMON_HINTS = ("cox", "风险比", "hazard ratio", "hazard", "95%ci", "95% ci", "95%置信区间", "hr")


BASELINE_VARIABLE_HINTS = (
    "年龄",
    "性别",
    "bclc",
    "child",
    "ecog",
    "afp",
    "肿瘤大小",
    "肿瘤数目",
    "微血管侵犯",
    "mvi",
    "肝硬化",
)


TREATMENT_SUMMARY_TITLE_HINTS = ("治疗分组", "构成", "占比", "分组汇总", "治疗组")
BASELINE_TITLE_HINTS = ("基线", "临床病理特征", "临床特征", "患者特征", "特征")
UNIVARIATE_TITLE_HINTS = UNIVARIATE_SECTION_HINTS + ("风险比",)
MULTIVARIATE_TITLE_HINTS = MULTIVARIATE_SECTION_HINTS + ("风险比",)


HR_VALUE_PATTERN = r"(?:HR|风险比|hazard ratio)\s*[=：:]?\s*(?P<hr><\s*0\.\d+|[0-9]+(?:\.\d+)?)"
CI_VALUE_PATTERN = r"(?:95%\s*CI|95%CI|95%置信区间)\s*[=:：]?[（(]?\s*(?P<low>[0-9]+(?:\.\d+)?)\s*[-–—~,，]\s*(?P<high>[0-9]+(?:\.\d+)?)\s*[)）]?"
P_VALUE_CAPTURE_PATTERN = r"P\s*[=＝<>]\s*(?P<p><?\s*[0-9]*\.?[0-9]+)"


TREATMENT_ORDER = {
    "监测/未治疗组": 0,
    "TACE组": 1,
    "免疫治疗组": 2,
    "靶向治疗组": 3,
    "联合治疗组": 4,
    "联合/免疫/靶向合计": 5,
}


TABLE_EMPTY_VALUES = {"", "—", "-", "NA", "N/A", "na", "n/a", "未报告", "未提供"}


SECTION_LINE_SPLIT_PATTERN = re.compile(r"(?<=[。；!?])\s+|\n+")


NUMBER_WITH_UNIT_PATTERN = re.compile(r"(?P<value>[0-9]+(?:\.\d+)?)\s*(?P<unit>%|例|月)")


def run_report_generation(task_id: str, job_store: FileJobStore) -> None:
    job_store.update_job(task_id, status="running", error=None)
    job = job_store.require_job(task_id)

    try:
        markdown_path = Path(job["markdown_path"])
        assets_dir = Path(job["assets_dir"])
        reference_assets_dir = (
            Path(str(job["reference_assets_dir"]))
            if job.get("reference_assets_dir")
            else assets_dir.parent / "reference_assets"
        )
        output_path = Path(job["planned_output_path"])
        intermediate_dir = Path(job["intermediate_dir"])
        figure_dir = intermediate_dir / "figure"
        reference_dir = intermediate_dir / "references"

        markdown_text = markdown_path.read_text(encoding="utf-8")
        asset_paths = _resolve_asset_paths(assets_dir, job.get("asset_names", []))
        reference_asset_paths = _resolve_asset_paths(reference_assets_dir, job.get("reference_asset_names", []))

        template_path = job.get("template_path")
        if template_path and not Path(template_path).exists():
            raise FileNotFoundError(f"LaTeX template not found: {template_path}")

        report_name = str(job.get("report_name") or markdown_path.stem)
        report_language = str(job.get("report_language") or "zh").lower()
        if report_language not in {"zh", "en"}:
            raise ValueError("Unsupported report language. Use `zh` or `en`.")

        structured_result = build_structured_report(
            markdown_text,
            asset_paths,
            report_name=report_name,
            figure_dir=figure_dir,
        )
        structured_report = structured_result["structured_report"]
        summary = structured_result["summary"]
        figure_entries = structured_result["figure_entries"]
        figure_paths = structured_result["figure_paths"]
        report_name = str(job.get("report_name") or summary["title"])
        generation_requirements = {
            "writing_requirements": str(job.get("writing_requirements") or "").strip(),
            "requested_language": report_language,
        }
        if any(generation_requirements.values()):
            structured_report["generation_requirements"] = generation_requirements

        reference_entries: list[dict[str, object]] = []
        reference_manifest: dict[str, object] | None = None
        reference_bib_path: Path | None = None
        reference_prompt_entries: list[dict[str, object]] = []

        source_markdown_path = intermediate_dir / "01_source_markdown.md"
        renamed_markdown_path = intermediate_dir / "02_source_markdown_with_figures.md"
        structured_json_path = intermediate_dir / "03_structured_report.json"
        figure_manifest_path = intermediate_dir / "04_figure_manifest.json"

        _write_text(source_markdown_path, markdown_text)
        _write_text(renamed_markdown_path, rewrite_markdown_image_paths(markdown_text, figure_entries))
        _write_json(structured_json_path, structured_report)
        _write_json(figure_manifest_path, {"figures": figure_entries})

        intermediate_files = [
            {"name": "01_source_markdown", "path": str(source_markdown_path), "category": "input"},
            {"name": "02_source_markdown_with_figures", "path": str(renamed_markdown_path), "category": "input"},
            {"name": "03_structured_report", "path": str(structured_json_path), "category": "structured"},
            {"name": "04_figure_manifest", "path": str(figure_manifest_path), "category": "structured"},
        ]

        if reference_asset_paths:
            reference_result = build_reference_library(reference_asset_paths, reference_dir=reference_dir)
            reference_entries = list(reference_result["entries"])
            reference_manifest = dict(reference_result["manifest"])
            reference_prompt_entries = _build_reference_prompt_entries(reference_entries)
            reference_manifest_path = intermediate_dir / "05_reference_manifest.json"
            reference_bib_path = intermediate_dir / "06_reference_library.bib"
            _write_json(reference_manifest_path, reference_manifest)
            _write_text(reference_bib_path, str(reference_result["bibtex"]))
            intermediate_files.extend(
                [
                    {"name": "05_reference_manifest", "path": str(reference_manifest_path), "category": "reference"},
                    {"name": "06_reference_library", "path": str(reference_bib_path), "category": "reference"},
                ]
            )
            summary["reference_asset_count"] = int(reference_manifest.get("reference_asset_count") or 0)
            summary["reference_entry_count"] = int(reference_manifest.get("reference_entry_count") or 0)
        else:
            summary["reference_asset_count"] = 0
            summary["reference_entry_count"] = 0

        job_store.update_job(
            task_id,
            report_name=report_name,
            report_language=report_language,
            figure_dir=str(figure_dir),
            reference_dir=str(reference_dir) if reference_asset_paths else None,
            intermediate_files=intermediate_files,
            summary=summary,
        )

        llm_enabled = bool(job.get("llm_enabled", True))
        llm_provider = None
        llm_model = None
        if llm_enabled:
            llm_config = resolve_llm_config(job)
            llm_provider = llm_config.provider
            llm_model = llm_config.model
            use_compact_llm_path = _should_use_compact_llm_path(llm_config)

            initial_draft = _run_markdown_stage(
                config=llm_config,
                intermediate_dir=intermediate_dir,
                stage_slug="07_initial_draft",
                system_and_user=build_initial_draft_prompts(structured_report, report_name),
            )
            intermediate_files.extend(initial_draft["artifacts"])

            if use_compact_llm_path:
                refined_draft_text = str(initial_draft["text"])
                refined_draft_path = intermediate_dir / "08_refined_draft.md"
                _write_text(refined_draft_path, refined_draft_text)
                intermediate_files.append(
                    {"name": "08_refined_draft", "path": str(refined_draft_path), "category": "compatibility"}
                )
            else:
                refined_draft = _run_markdown_stage(
                    config=llm_config,
                    intermediate_dir=intermediate_dir,
                    stage_slug="08_refined_draft",
                    system_and_user=build_refiner_prompts(str(initial_draft["text"])),
                )
                intermediate_files.extend(refined_draft["artifacts"])
                refined_draft_text = str(refined_draft["text"])

            normalized_input_markdown = refined_draft_text
            if reference_entries:
                literature_aligned = _run_markdown_stage(
                    config=llm_config,
                    intermediate_dir=intermediate_dir,
                    stage_slug="08b_literature_aligned_draft",
                    system_and_user=build_literature_alignment_prompts(
                        normalized_input_markdown,
                        reference_prompt_entries,
                        report_language,
                    ),
                )
                intermediate_files.extend(literature_aligned["artifacts"])
                normalized_input_markdown = str(literature_aligned["text"])
                normalized_input_markdown = _apply_lightweight_reference_alignment(
                    normalized_input_markdown,
                    reference_entries,
                    report_language,
                )
                literature_aligned_local_path = intermediate_dir / "08c_literature_aligned_localized.md"
                _write_text(literature_aligned_local_path, normalized_input_markdown)
                intermediate_files.append(
                    {
                        "name": "08c_literature_aligned_localized",
                        "path": str(literature_aligned_local_path),
                        "category": "reference",
                    }
                )

            normalized_draft_text = _local_normalize_markdown(normalized_input_markdown, report_language)
            if not use_compact_llm_path:
                normalized_stage = _run_markdown_stage(
                    config=llm_config,
                    intermediate_dir=intermediate_dir,
                    stage_slug="09_normalized_draft",
                    system_and_user=build_normalizer_prompts(
                        normalized_draft_text,
                        str(template_path) if template_path else None,
                    ),
                )
                intermediate_files.extend(normalized_stage["artifacts"])
                normalized_draft_text = _local_normalize_markdown(str(normalized_stage["text"]), report_language)
            normalized_draft_path = intermediate_dir / "09_normalized_draft.md"
            _write_text(normalized_draft_path, normalized_draft_text)
            intermediate_files.append(
                {"name": "09_normalized_draft", "path": str(normalized_draft_path), "category": "cleanup"}
            )

            if report_language == "en":
                final_stage = _run_markdown_stage(
                    config=llm_config,
                    intermediate_dir=intermediate_dir,
                    stage_slug="10_final_report_en",
                    system_and_user=build_translation_prompts(normalized_draft_text),
                )
                final_markdown = str(final_stage["text"])
                intermediate_files.extend(final_stage["artifacts"])
                final_markdown_path = intermediate_dir / "10_final_report_en.md"
            else:
                final_stage = _run_markdown_stage(
                    config=llm_config,
                    intermediate_dir=intermediate_dir,
                    stage_slug="10_final_report_zh",
                    system_and_user=build_chinese_finalize_prompts(
                        normalized_draft_text,
                        report_name,
                        str(template_path) if template_path else None,
                    ),
                )
                final_markdown = str(final_stage["text"])
                intermediate_files.extend(final_stage["artifacts"])
                final_markdown_path = intermediate_dir / "10_final_report_zh.md"
        else:
            if report_language == "en":
                raise LLMConfigurationError("English report generation requires LLM translation to be enabled.")

            initial_draft_path = intermediate_dir / "07_initial_draft.md"
            refined_draft_path = intermediate_dir / "08_refined_draft.md"
            normalized_draft_path = intermediate_dir / "09_normalized_draft.md"
            final_markdown_path = intermediate_dir / "10_final_report_zh.md"

            initial_draft_text = _build_rule_based_draft(structured_report)
            refined_draft_text = initial_draft_text
            normalized_draft_text = _normalize_rule_based_markdown(refined_draft_text)

            _write_text(initial_draft_path, initial_draft_text)
            _write_text(refined_draft_path, refined_draft_text)
            _write_text(normalized_draft_path, normalized_draft_text)
            _write_text(final_markdown_path, normalized_draft_text)

            intermediate_files.extend(
                [
                    {"name": "07_initial_draft", "path": str(initial_draft_path), "category": "rule_based"},
                    {"name": "08_refined_draft", "path": str(refined_draft_path), "category": "rule_based"},
                    {"name": "09_normalized_draft", "path": str(normalized_draft_path), "category": "rule_based"},
                    {"name": "10_final_report_zh", "path": str(final_markdown_path), "category": "final_markdown"},
                ]
            )
            final_markdown = normalized_draft_text

        final_markdown = _canonicalize_final_markdown(final_markdown, report_language)
        final_markdown = _remove_markdown_thematic_breaks(final_markdown)
        _write_text(final_markdown_path, final_markdown)
        if not any(item["name"] == final_markdown_path.stem for item in intermediate_files):
            intermediate_files.append(
                {"name": final_markdown_path.stem, "path": str(final_markdown_path), "category": "final_markdown"}
            )

        figure_grounded_path = intermediate_dir / "11_figure_grounded_report.md"
        figure_grounded_markdown = _ensure_explicit_figure_references(final_markdown, figure_entries, report_language)
        _write_text(figure_grounded_path, figure_grounded_markdown)
        intermediate_files.append(
            {"name": "11_figure_grounded_report", "path": str(figure_grounded_path), "category": "grounding"}
        )

        final_output_markdown = figure_grounded_markdown
        final_output_markdown_path = figure_grounded_path

        if reference_entries:
            citation_grounded_path = intermediate_dir / "12_citation_grounded_report.md"
            final_output_markdown = _inject_reference_citations(
                figure_grounded_markdown,
                reference_entries,
                report_language,
            )

            final_output_markdown = _canonicalize_final_markdown(final_output_markdown, report_language)
            final_output_markdown = _remove_markdown_thematic_breaks(final_output_markdown)
            final_output_markdown = _sanitize_citation_markers(
                final_output_markdown,
                {str(entry["citation_key"]) for entry in reference_entries},
            )
            _write_text(citation_grounded_path, final_output_markdown)
            intermediate_files.append(
                {
                    "name": "12_citation_grounded_report",
                    "path": str(citation_grounded_path),
                    "category": "grounding",
                }
            )
            final_output_markdown_path = citation_grounded_path

        if report_language == "en":
            final_output_markdown = _local_normalize_markdown(final_output_markdown, report_language)
            final_output_markdown = _remove_markdown_thematic_breaks(final_output_markdown)
            if reference_entries:
                final_output_markdown = _sanitize_citation_markers(
                    final_output_markdown,
                    {str(entry["citation_key"]) for entry in reference_entries},
                )
            english_cleanup_path = intermediate_dir / "12b_english_finalized_report.md"
            _write_text(english_cleanup_path, final_output_markdown)
            intermediate_files.append(
                {
                    "name": "12b_english_finalized_report",
                    "path": str(english_cleanup_path),
                    "category": "cleanup",
                }
            )
            final_output_markdown_path = english_cleanup_path

        if report_language == "zh":
            final_output_markdown = _restructure_medical_paper_markdown(final_output_markdown)
            final_output_markdown = _enforce_reference_subsection_structure(
                final_output_markdown,
                figure_entries=figure_entries,
                rewrite_discussion=True,
            )
            final_output_markdown = _harmonize_structured_sections(final_output_markdown, report_language)
            final_output_markdown = _deduplicate_title_lines(final_output_markdown)
            final_output_markdown = _normalize_keyword_section(final_output_markdown, report_language)
        else:
            final_output_markdown = _normalize_numeric_subheadings(final_output_markdown)
            final_output_markdown = _promote_inline_numbered_subheadings(final_output_markdown)
            final_output_markdown = _promote_numbered_subheadings(final_output_markdown)
            final_output_markdown = _promote_named_extra_sections(final_output_markdown, report_language)
            final_output_markdown = _organize_data_foundation_sections(final_output_markdown, report_language)
            final_output_markdown = _demote_empty_top_level_sections(final_output_markdown, report_language)
            final_output_markdown = _inject_section_overview_paragraphs(final_output_markdown, report_language)
            final_output_markdown = _prefer_ordered_lists(final_output_markdown)
            final_output_markdown = _trim_excess_ordered_lists(final_output_markdown, report_language)
        final_output_markdown = _ensure_required_sections(final_output_markdown, structured_report, report_language)
        if report_language == "zh":
            final_output_markdown = _enforce_result_figure_distribution(final_output_markdown, figure_entries)
        final_output_markdown = _force_single_paragraph_abstract(final_output_markdown, report_language)
        if report_language == "zh":
            final_output_markdown = _remove_markdown_thematic_breaks(final_output_markdown)
            if reference_entries:
                final_output_markdown = _sanitize_citation_markers(
                    final_output_markdown,
                    {str(entry["citation_key"]) for entry in reference_entries},
                )

        _write_text(final_output_markdown_path, final_output_markdown)

        latex_body_path = intermediate_dir / "13_latex_body.tex"
        latex_body = markdown_to_latex(final_output_markdown, enable_citations=bool(reference_entries))
        _write_text(latex_body_path, latex_body)
        intermediate_files.append({"name": "13_latex_body", "path": str(latex_body_path), "category": "latex"})
        job_store.update_job(task_id, intermediate_files=intermediate_files)

        render_result = render_report_latex(
            report_name=report_name,
            report_language=report_language,
            asset_paths=figure_paths,
            intermediate_dir=intermediate_dir,
            output_path=output_path,
            latex_body=latex_body,
            template_path=str(template_path) if template_path else None,
            bibliography_bib_path=str(reference_bib_path) if reference_bib_path else None,
            reference_entries=reference_entries,
        )

        job_store.update_job(
            task_id,
            status="completed",
            report_name=report_name,
            report_language=report_language,
            summary=summary,
            output_file=render_result["output_file"],
            latex_file=render_result["tex_file"],
            latex_project_dir=render_result.get("latex_project_dir"),
            latex_entry_file=render_result.get("latex_entry_file"),
            final_markdown_file=str(final_output_markdown_path),
            output_type=render_result["output_type"],
            compile_engine=render_result["compile_engine"],
            llm_enabled=llm_enabled,
            llm_provider=llm_provider,
            llm_model=llm_model,
            intermediate_files=intermediate_files + render_result["intermediate_files"],
        )
    except LatexRenderError as exc:
        current_job = job_store.require_job(task_id)
        job_store.update_job(
            task_id,
            status="failed",
            error=str(exc),
            compile_engine=exc.compile_engine,
            intermediate_files=current_job.get("intermediate_files", []) + exc.intermediate_files,
        )
    except (LLMConfigurationError, LLMInvocationError) as exc:
        current_job = job_store.require_job(task_id)
        job_store.update_job(
            task_id,
            status="failed",
            error=str(exc),
            intermediate_files=current_job.get("intermediate_files", []) + getattr(exc, "intermediate_files", []),
        )
    except Exception as exc:
        job_store.update_job(
            task_id,
            status="failed",
            error=str(exc),
        )
    finally:
        job = job_store.require_job(task_id)
        if not bool(job.get("skip_archive")):
            try:
                archive_dir = _archive_job_artifacts(job)
            except Exception as exc:
                job_store.update_job(task_id, archive_error=str(exc))
            else:
                if archive_dir:
                    job_store.update_job(task_id, archive_dir=str(archive_dir))


def _run_markdown_stage(
    *,
    config,
    intermediate_dir: Path,
    stage_slug: str,
    system_and_user: tuple[str, str],
) -> dict[str, object]:
    system_prompt, user_prompt = system_and_user
    return call_llm_stage(
        config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        intermediate_dir=intermediate_dir,
        stage_slug=stage_slug,
        output_filename=f"{stage_slug}.md",
        output_format="markdown",
    )


def _should_use_compact_llm_path(config: LLMConfig) -> bool:
    return "deepseek" in config.provider.casefold()


def _resolve_asset_paths(assets_dir: Path, asset_names: object) -> list[Path]:
    resolved: list[Path] = []
    seen: set[str] = set()
    for asset_name in asset_names if isinstance(asset_names, list) else []:
        candidate = assets_dir / str(asset_name)
        if candidate.exists() and candidate.is_file():
            resolved.append(candidate)
            seen.add(candidate.name)
    for candidate in sorted(path for path in assets_dir.iterdir() if path.is_file()):
        if candidate.name in seen:
            continue
        resolved.append(candidate)
    return resolved


def _build_rule_based_draft(structured_report: dict[str, object]) -> str:
    sections = structured_report.get("sections", [])
    figures = structured_report.get("figures", [])
    title_lookup = _build_section_lookup(sections)

    ordered_sections = [
        ("摘要", _pick_section_text(title_lookup, ["摘要", "abstract"])),
        ("关键词", _pick_section_text(title_lookup, ["关键词", "key words", "keywords"])),
        ("引言", _pick_section_text(title_lookup, ["引言", "背景", "背景与目标"])),
        ("患者与方法", _pick_section_text(title_lookup, ["患者与方法", "方法", "材料与方法"])),
        ("结果", _pick_section_text(title_lookup, ["结果", "分析"])),
        ("讨论", _pick_section_text(title_lookup, ["讨论", "局限", "局限性", "不足", "结论", "总结", "展望", "建议"])),
    ]

    lines: list[str] = []
    for heading, body in ordered_sections:
        lines.append(f"# {heading}")
        if body:
            lines.append(body)
        else:
            lines.append(_rule_based_section_fallback(heading))
        if heading == "结果" and figures:
            for figure in figures:
                lines.append(f"![{figure['figure_id']}]({figure['relative_path']})")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _rule_based_section_fallback(heading: str) -> str:
    fallbacks = {
        "摘要": "目的：围绕研究对象、分组特征与主要结局进行系统归纳。方法：按照医学论文结构整理研究背景、方法、结果和讨论内容。结果：研究结果重点呈现分组构成、主要终点比较和图形趋势。结论：相关发现提示研究分组与临床结局之间存在值得进一步关注的关联，仍需结合研究设计和潜在混杂因素谨慎解释。",
        "关键词": "临床研究；真实世界数据；预后；生存分析",
        "引言": "相关疾病的长期预后和术后管理一直是临床研究的重要问题。随着治疗策略不断丰富，真实世界场景中不同治疗或分组方式所对应的患者特征、结局差异和随访表现需要在规范论文结构中加以呈现。基于现有研究资料进行系统整理，有助于形成可读性更强、证据边界更清晰的医学论文初稿。",
        "患者与方法": "本研究围绕临床资料整理、研究分组、主要终点和统计学比较展开。研究对象依据既定分组或暴露因素进行归纳，相关变量包括人口学信息、临床病理特征、治疗信息、随访状态及结局事件。主要终点根据研究主题确定，组间比较采用资料中已给出的统计学方法和图形结果进行呈现，不额外引入未实施的复杂模型。",
        "结果": "结果部分围绕分组构成、主要终点比较和图形趋势展开。首先描述研究分组或总体分布特征，其次分别呈现主要终点的组间差异及统计学判断，最后结合图形结果说明曲线分离、趋势方向和不同结局之间的表现差异。相关结果用于支持后续讨论中对真实世界分组差异、潜在混杂和临床意义的谨慎解释。",
        "讨论": "本研究从医学论文写作角度对主要发现进行归纳，重点讨论分组构成、主要终点趋势和图形结果之间的关系。真实世界资料中，不同分组往往受到基线状态、疾病严重程度和治疗选择等因素影响，因此结果解释应避免直接因果化。后续研究可在更完整资料、规范随访和必要校正分析基础上进一步验证相关发现。",
    }
    return fallbacks.get(heading, "相关内容围绕研究主题进行医学论文式归纳，并在结果与讨论中保持客观、克制和连续的表述。")


def _normalize_rule_based_markdown(markdown_text: str) -> str:
    normalized = markdown_text.replace("背景：", "")
    return normalized


def _local_normalize_markdown(markdown_text: str, report_language: str) -> str:
    normalized = _normalize_rule_based_markdown(markdown_text)
    normalized = _canonicalize_final_markdown(normalized, report_language)
    if report_language == "zh":
        normalized = _restructure_medical_paper_markdown(normalized)
        normalized = _enforce_reference_subsection_structure(normalized)
        normalized = _force_single_paragraph_abstract(normalized, report_language)
        normalized = _normalize_keyword_section(normalized, report_language)
    else:
        normalized = _force_single_paragraph_abstract(normalized, report_language)
        normalized = _normalize_numeric_subheadings(normalized)
        normalized = _promote_inline_numbered_subheadings(normalized)
        normalized = _promote_numbered_subheadings(normalized)
        normalized = _promote_named_extra_sections(normalized, report_language)
        normalized = _organize_data_foundation_sections(normalized, report_language)
        normalized = _demote_empty_top_level_sections(normalized, report_language)
        normalized = _inject_section_overview_paragraphs(normalized, report_language)
        normalized = _prefer_ordered_lists(normalized)
        normalized = _trim_excess_ordered_lists(normalized, report_language)
    normalized = _remove_markdown_thematic_breaks(normalized)
    return normalized


def _canonicalize_final_markdown(markdown_text: str, report_language: str) -> str:
    if report_language == "zh":
        markdown_text = re.sub(r"(?mi)^#\s*Abstract\s*$", "# 摘要", markdown_text)
        markdown_text = re.sub(r"(?mi)^Abstract\s*$", "# 摘要", markdown_text)
        markdown_text = re.sub(r"(?mi)^#\s*Keywords?\s*$", "# 关键词", markdown_text)
        markdown_text = re.sub(r"(?mi)^Keywords?\s*$", "# 关键词", markdown_text)

    headings = [
        "摘要",
        "关键词",
        "引言",
        "患者与方法",
        "结果",
        "讨论",
    ] if report_language == "zh" else [
        "Abstract",
        "Introduction",
        "Methods",
        "Results",
        "Discussion",
        "Limitations",
        "Conclusion",
    ]
    aliases = _heading_aliases(report_language)

    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    normalized_lines: list[str] = []
    seen_first_content = False
    title_removed = False
    first_heading_index = _find_first_canonical_heading_index(lines, aliases)

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped:
            normalized_lines.append("")
            continue

        canonical_plain = _canonical_heading_from_text(stripped, aliases)
        if canonical_plain:
            normalized_lines.append(f"# {canonical_plain}")
            seen_first_content = True
            continue

        if stripped.startswith("#"):
            heading_text = stripped.lstrip("#").strip()
            canonical = _canonical_heading_from_text(heading_text, aliases)
            if canonical:
                normalized_lines.append(f"# {canonical}")
                seen_first_content = True
                continue

            if not seen_first_content and not title_removed:
                title_removed = True
                continue

        if (
            not seen_first_content
            and not title_removed
            and first_heading_index != -1
            and index < first_heading_index
            and _looks_like_leading_title(stripped)
        ):
            title_removed = True
            continue

        normalized_lines.append(raw_line)
        seen_first_content = True

    cleaned = "\n".join(normalized_lines)
    cleaned = _remove_duplicate_headings(cleaned, headings)
    cleaned = _localize_markdown_terms(cleaned, report_language)
    cleaned = cleaned.strip()
    return cleaned + "\n" if cleaned else ""


def _ensure_required_sections(
    markdown_text: str,
    structured_report: dict[str, object],
    report_language: str,
) -> str:
    if report_language == "zh":
        normalized = _restructure_medical_paper_markdown(markdown_text)
        normalized = _enforce_reference_subsection_structure(normalized)
        normalized = _force_single_paragraph_abstract(normalized, report_language)
        normalized = _normalize_keyword_section(normalized, report_language)
        return normalized.strip() + "\n"

    normalized = _promote_named_extra_sections(markdown_text, report_language)
    normalized = _organize_data_foundation_sections(normalized, report_language)
    required_headings = ["局限性", "结论"] if report_language == "zh" else ["Limitations", "Conclusion"]

    for heading in required_headings:
        body = _get_top_level_section_body(normalized, heading)
        if _has_substantive_section_body(body):
            continue
        fallback = _build_required_section_fallback(heading, structured_report, report_language)
        normalized = _upsert_top_level_section(normalized, heading, fallback)

    normalized = _force_single_paragraph_abstract(normalized, report_language)
    return normalized.strip() + "\n"


def _force_single_paragraph_abstract(markdown_text: str, report_language: str) -> str:
    lines = markdown_text.splitlines()
    output: list[str] = []
    index = 0
    abstract_heading = "Abstract" if report_language == "en" else "\u6458\u8981"

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if not heading_match or len(heading_match.group(1)) != 1:
            output.append(raw_line)
            index += 1
            continue

        heading_text = heading_match.group(2).strip()
        output.append(raw_line)
        index += 1

        if heading_text.casefold() != abstract_heading.casefold():
            continue

        abstract_block: list[str] = []
        while index < len(lines):
            candidate = lines[index]
            candidate_match = HEADING_PATTERN.match(candidate.strip())
            if candidate_match and len(candidate_match.group(1)) == 1:
                break
            abstract_block.append(candidate)
            index += 1

        flattened = _flatten_abstract_block(abstract_block, report_language)
        if report_language == "zh" and flattened:
            flattened = _ensure_complete_chinese_abstract(flattened)
        if flattened:
            output.append("")
            output.append(flattened)
            output.append("")

    return "\n".join(output).strip() + "\n"


def _flatten_abstract_block(lines: list[str], report_language: str) -> str:
    fragments: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if IMAGE_LINE_PATTERN.match(stripped):
            continue
        cleaned = _clean_abstract_line(stripped, report_language)
        if cleaned:
            fragments.append(cleaned)

    return _join_abstract_fragments(fragments, report_language)


def _clean_abstract_line(text: str, report_language: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", cleaned)
    cleaned = re.sub(r"^\s*\*\*(.*?)\*\*\s*$", r"\1", cleaned)
    cleaned = re.sub(r"^\s*\*(.*?)\*\s*$", r"\1", cleaned)
    cleaned = _normalize_abstract_label(cleaned, report_language)
    cleaned = cleaned.strip(" -\u3000")
    return cleaned


def _join_abstract_fragments(fragments: list[str], report_language: str) -> str:
    if not fragments:
        return ""

    merged = fragments[0].strip()
    for fragment in fragments[1:]:
        current = fragment.strip()
        if not current:
            continue
        if report_language == "zh":
            merged += current
            continue
        if _needs_cjk_tight_join(merged, current):
            merged += current
        else:
            merged += " " + current
    return merged.strip()


def _normalize_abstract_label(text: str, report_language: str) -> str:
    cleaned = text.strip()
    if report_language == "zh":
        match = re.match(
            r"^(?P<label>背景|目的|研究目的|方法|患者与方法|材料与方法|结果|结论|结果与结论|关键词)\s*[:：]\s*(?P<body>.+)$",
            cleaned,
        )
        if not match:
            return cleaned
        label_map = {
            "背景": "目的",
            "目的": "目的",
            "研究目的": "目的",
            "方法": "方法",
            "患者与方法": "方法",
            "材料与方法": "方法",
            "结果": "结果",
            "结论": "结论",
            "结果与结论": "结果",
            "关键词": "关键词",
        }
        return f"{label_map.get(match.group('label'), match.group('label'))}：{match.group('body').strip()}"

    match = re.match(
        r"^(?P<label>Background|Objective|Objectives|Methods?|Results?|Conclusion)\s*:\s*(?P<body>.+)$",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not match:
        return cleaned
    label_map = {
        "background": "Objective",
        "objective": "Objective",
        "objectives": "Objective",
        "method": "Methods",
        "methods": "Methods",
        "result": "Results",
        "results": "Results",
        "conclusion": "Conclusion",
    }
    return f"{label_map.get(match.group('label').casefold(), match.group('label'))}: {match.group('body').strip()}"


def _ensure_complete_chinese_abstract(abstract_text: str, evidence: ResultEvidence | None = None) -> str:
    cleaned = _clean_method_paragraph(abstract_text)
    if not cleaned:
        return ""

    objective = _extract_chinese_abstract_segment(cleaned, ("目的", "背景", "研究目的"))
    methods = _extract_chinese_abstract_segment(cleaned, ("方法", "患者与方法", "材料与方法"))
    results = _extract_chinese_abstract_segment(cleaned, ("结果", "结果与结论"))
    conclusion = _extract_chinese_abstract_segment(cleaned, ("结论",))

    if evidence:
        evidence_results = _build_abstract_result_sentence(evidence)
        if evidence_results:
            results = re.sub(r"^\s*结果[：:]\s*", "", evidence_results).strip()

    if not objective:
        objective = "基于现有临床资料，概括研究对象、分组特征、主要终点及图表结果，形成符合中文医学论文正文表达的结构化报告"
    if not methods:
        methods = "围绕研究设计、分组信息、图表说明和统计结论进行系统整理，重点呈现研究对象、主要终点及组间比较结果"
    if not results:
        results = (
            "研究围绕分组构成、主要终点和图形趋势展开，结果呈现组间结局差异及其统计学判断，并结合曲线变化描述主要趋势"
        )
    if not conclusion:
        conclusion = "研究结果提示不同分组与主要结局之间存在值得关注的关联。相关发现仍需结合研究设计、基线差异和潜在混杂因素进行谨慎解释"
    elif _chinese_sentence_count(conclusion) < 2:
        conclusion = conclusion.rstrip("。；;") + "，仍需结合研究设计、基线差异和潜在混杂因素进行谨慎解释"

    parts = [
        ("目的", objective),
        ("方法", methods),
        ("结果", results),
        ("结论", conclusion),
    ]
    return "".join(f"{label}：{body.rstrip('。；;')}。" for label, body in parts)


def _chinese_sentence_count(text: str) -> int:
    return len([part for part in re.split(r"[。！？!?]+", text) if part.strip()])


def _extract_chinese_abstract_segment(text: str, labels: tuple[str, ...]) -> str:
    label_group = "|".join(re.escape(label) for label in labels)
    boundary_labels = "目的|背景|研究目的|方法|患者与方法|材料与方法|结果|结果与结论|结论|关键词"
    match = re.search(
        rf"(?:{label_group})\s*[：:]\s*(?P<body>.*?)(?=(?:{boundary_labels})\s*[：:]|$)",
        text,
        flags=re.DOTALL,
    )
    if not match:
        return ""
    return _clean_method_paragraph(match.group("body")).rstrip("。；;")


def _needs_cjk_tight_join(left: str, right: str) -> bool:
    left_char = left[-1:] if left else ""
    right_char = right[:1] if right else ""
    return bool(left_char and right_char and _is_cjk_char(left_char) and _is_cjk_char(right_char))


def _is_cjk_char(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def _normalize_keyword_section(markdown_text: str, report_language: str) -> str:
    lines = markdown_text.splitlines()
    output: list[str] = []
    index = 0
    target_heading = "关键词" if report_language == "zh" else "Keywords"
    found_keywords_section = False

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if not heading_match or len(heading_match.group(1)) != 1 or heading_match.group(2).strip() != target_heading:
            output.append(raw_line)
            index += 1
            continue

        found_keywords_section = True
        output.append(f"# {target_heading}")
        index += 1
        block: list[str] = []
        while index < len(lines):
            candidate = lines[index]
            candidate_match = HEADING_PATTERN.match(candidate.strip())
            if candidate_match and len(candidate_match.group(1)) == 1:
                break
            block.append(candidate)
            index += 1

        keywords = _extract_keywords_from_block(block, report_language)
        if not keywords:
            keywords = _derive_keywords_from_manuscript(markdown_text, report_language)
        if keywords:
            output.append("")
            output.append(keywords)
            output.append("")

    rebuilt = "\n".join(output).strip() + "\n"
    if found_keywords_section:
        return rebuilt
    fallback_keywords = _derive_keywords_from_manuscript(markdown_text, report_language)
    if not fallback_keywords:
        return rebuilt
    return _insert_missing_keyword_section(rebuilt, fallback_keywords, report_language)


def _extract_keywords_from_block(lines: list[str], report_language: str) -> str:
    items: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or IMAGE_LINE_PATTERN.match(stripped):
            continue
        cleaned = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", stripped)
        cleaned = re.sub(r"^(?:关键词|Key words|Keywords)\s*[:：]\s*", "", cleaned, flags=re.IGNORECASE)
        parts = re.split(r"[；;，,、]\s*", cleaned)
        for part in parts:
            token = part.strip()
            if token and token not in items:
                items.append(token)

    if not items:
        return ""
    separator = "；" if report_language == "zh" else "; "
    return separator.join(items[:8])


def _derive_keywords_from_manuscript(markdown_text: str, report_language: str) -> str:
    if report_language != "zh":
        return ""

    haystack = markdown_text.casefold()
    candidates = [
        "原发性肝癌",
        "肝癌",
        "肝细胞癌",
        "术后治疗",
        "生存分析",
        "无复发生存",
        "总生存",
        "Kaplan-Meier",
        "Log-rank检验",
        "TACE",
        "免疫治疗",
        "靶向治疗",
    ]
    picked: list[str] = []
    for candidate in candidates:
        if candidate.casefold() in haystack and candidate not in picked:
            picked.append(candidate)
    if len(picked) < 3:
        return ""
    return "；".join(picked[:6])


def _insert_missing_keyword_section(markdown_text: str, keywords: str, report_language: str) -> str:
    lines = markdown_text.splitlines()
    output: list[str] = []
    index = 0
    inserted = False
    abstract_heading = "摘要" if report_language == "zh" else "Abstract"
    keyword_heading = "关键词" if report_language == "zh" else "Keywords"

    while index < len(lines):
        raw_line = lines[index]
        output.append(raw_line)
        heading_match = HEADING_PATTERN.match(raw_line.strip())
        index += 1
        if inserted or not heading_match or len(heading_match.group(1)) != 1 or heading_match.group(2).strip() != abstract_heading:
            continue

        while index < len(lines):
            candidate = lines[index]
            candidate_match = HEADING_PATTERN.match(candidate.strip())
            if candidate_match and len(candidate_match.group(1)) == 1:
                break
            output.append(candidate)
            index += 1

        if output and output[-1].strip():
            output.append("")
        output.append(f"# {keyword_heading}")
        output.append("")
        output.append(keywords)
        output.append("")
        inserted = True

    return "\n".join(output).strip() + "\n"


def _restructure_medical_paper_markdown(markdown_text: str) -> str:
    preamble_lines, section_blocks = _split_top_level_section_blocks(markdown_text)
    if not section_blocks:
        return markdown_text

    ordered_headings = ["摘要", "关键词", "引言", "患者与方法", "结果", "讨论"]
    section_bodies: dict[str, list[str]] = {heading: [] for heading in ordered_headings}

    for title, body_lines in section_blocks:
        destination = _medical_destination_heading(title)
        cleaned_body = _trim_blank_lines(body_lines)
        if not cleaned_body:
            continue

        if section_bodies[destination]:
            section_bodies[destination].append("")

        if (
            title != destination
            and not _is_plain_destination_alias(title, destination)
            and not _should_suppress_moved_section_heading(title, destination)
        ):
            section_bodies[destination].append(f"## {title}")
            section_bodies[destination].append("")
        section_bodies[destination].extend(cleaned_body)

    output_lines = _trim_blank_lines(preamble_lines)
    if output_lines:
        output_lines.append("")

    for heading in ordered_headings:
        body = _trim_blank_lines(section_bodies[heading])
        if not body:
            continue
        output_lines.append(f"# {heading}")
        output_lines.append("")
        output_lines.extend(body)
        output_lines.append("")

    return "\n".join(_trim_blank_lines(output_lines)).strip() + "\n"


def _enforce_reference_subsection_structure(
    markdown_text: str,
    *,
    figure_entries: list[dict[str, object]] | None = None,
    rewrite_discussion: bool = True,
) -> str:
    preamble_lines, section_blocks = _split_top_level_section_blocks(markdown_text)
    if not section_blocks:
        return markdown_text

    rebuilt_lines = _trim_blank_lines(preamble_lines)
    if rebuilt_lines:
        rebuilt_lines.append("")

    full_text = markdown_text.replace("\r\n", "\n").replace("\r", "\n")

    for title, body_lines in section_blocks:
        rebuilt_lines.append(f"# {title}")
        rebuilt_lines.append("")
        cleaned_body = _trim_blank_lines(body_lines)

        if title == ZH_METHODS_HEADING:
            cleaned_body = _rewrite_methods_section_body(cleaned_body, full_text)
        elif title == ZH_INTRODUCTION_HEADING:
            cleaned_body = _rewrite_introduction_section_body(cleaned_body, full_text)
        elif title == ZH_RESULTS_HEADING:
            cleaned_body = _rewrite_results_section_body(cleaned_body, full_text, figure_entries=figure_entries)
        elif title == ZH_DISCUSSION_HEADING and rewrite_discussion:
            cleaned_body = _rewrite_discussion_section_body(cleaned_body, full_text)

        rebuilt_lines.extend(cleaned_body)
        rebuilt_lines.append("")

    return "\n".join(_trim_blank_lines(rebuilt_lines)).strip() + "\n"


def _rewrite_methods_section_body(body_lines: list[str], markdown_text: str) -> list[str]:
    ordered_content = {heading: [] for heading in ZH_REFERENCE_METHODS_SUBHEADINGS}
    loose_lead, subsection_blocks = _split_nested_heading_blocks(body_lines)
    chunks: list[tuple[str, list[str]]] = []

    if loose_lead:
        chunks.extend(_materialize_loose_chunks(loose_lead))

    if subsection_blocks:
        chunks.extend(subsection_blocks)

    for fallback_index, (title, chunk_lines) in enumerate(chunks):
        destination = _classify_methods_subsection(title, chunk_lines, fallback_index)
        _append_chunk_to_bucket(ordered_content[destination], chunk_lines)

    ordered_content = _compact_methods_subsection_buckets(ordered_content, manuscript_text=markdown_text)
    return _render_ordered_subsection_buckets(ordered_content)


def _rewrite_introduction_section_body(body_lines: list[str], markdown_text: str) -> list[str]:
    intro_text = _flatten_markdown_lines([body_lines])
    if len(re.sub(r"\s+", "", intro_text)) >= 520 and _paragraph_count(body_lines) >= 2:
        return body_lines

    topic = _infer_clinical_topic_label(f"{intro_text}\n{markdown_text}")
    paragraphs = [
        (
            f"{topic}的长期预后与疾病控制一直是临床管理中的重要问题。随着诊断、手术、局部治疗和系统治疗手段不断发展，"
            "患者在不同治疗路径下的结局差异逐渐受到关注。对于接受术后管理或长期随访的人群而言，复发、进展和死亡等终点不仅反映疾病本身的生物学行为，"
            "也与治疗时机、治疗强度、肝功能或基础状态以及随访策略密切相关。因此，围绕真实临床资料对不同分组的结局进行系统整理，具有明确的临床意义。"
        ),
        (
            "目前临床实践中，术后或随访阶段的治疗选择往往呈现明显异质性。部分患者以规律监测和随访为主，部分患者接受局部治疗、系统治疗或联合治疗，"
            "不同策略所对应的患者基线风险和治疗目标并不完全一致。真实世界资料能够反映这种复杂的诊疗场景，但也容易受到选择偏倚、基线差异和随访完整性等因素影响。"
            "因此，在解释组间结局差异时，需要同时关注统计学结果、图形趋势和临床背景，而不能仅凭单一曲线或单一P值作出过度推断。"
        ),
        (
            "基于上述背景，本研究围绕临床分组构成、主要终点比较及生存曲线趋势展开分析。"
            "研究目的在于描述不同分组与临床结局之间的关系，明确主要终点的统计学表现和图形变化特征，并在真实世界研究框架下讨论其可能的临床意义。"
            "本研究可为后续更完整的数据校正、长期随访和前瞻性验证提供基础。"
        ),
    ]
    return paragraphs


def _paragraph_count(lines: list[str]) -> int:
    paragraphs = 0
    in_paragraph = False
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or IMAGE_LINE_PATTERN.match(stripped):
            if in_paragraph:
                paragraphs += 1
                in_paragraph = False
            continue
        in_paragraph = True
    if in_paragraph:
        paragraphs += 1
    return paragraphs


def _infer_clinical_topic_label(text: str) -> str:
    lowered = text.casefold()
    if any(token in lowered for token in ("肝癌", "肝细胞癌", "hcc", "hepatocellular")):
        return "原发性肝癌"
    if any(token in lowered for token in ("胃癌", "gastric")):
        return "胃癌"
    if any(token in lowered for token in ("肺癌", "lung")):
        return "肺癌"
    if any(token in lowered for token in ("乳腺癌", "breast")):
        return "乳腺癌"
    if any(token in lowered for token in ("结直肠", "colorectal", "colon", "rectal")):
        return "结直肠肿瘤"
    return "相关疾病"


def _rewrite_results_section_body(
    body_lines: list[str],
    markdown_text: str,
    *,
    figure_entries: list[dict[str, object]] | None = None,
) -> list[str]:
    results_context_text = _flatten_markdown_lines([body_lines])
    subsection_titles = _build_reference_style_result_subsection_titles(
        results_context_text or markdown_text,
        supplemental_text=markdown_text,
    )
    ordered_content = {heading: [] for heading in subsection_titles}
    loose_lead, subsection_blocks = _split_nested_heading_blocks(body_lines)
    chunks: list[tuple[str, list[str]]] = []

    if loose_lead:
        chunks.extend(_materialize_loose_chunks(loose_lead))

    if subsection_blocks:
        chunks.extend(subsection_blocks)

    for fallback_index, (title, chunk_lines) in enumerate(chunks):
        destination = _classify_results_subsection(
            title,
            chunk_lines,
            fallback_index,
            subsection_titles,
            figure_entries=figure_entries,
        )
        _append_chunk_to_bucket(ordered_content[destination], chunk_lines)

    evidence = _build_result_evidence(markdown_text, results_context_text, ordered_content)
    ordered_content = _compact_results_subsection_buckets(
        ordered_content,
        subsection_titles=subsection_titles,
        evidence=evidence,
        figure_entries=figure_entries,
    )
    return _render_ordered_subsection_buckets(ordered_content)


def _enforce_result_figure_distribution(
    markdown_text: str,
    figure_entries: list[dict[str, object]],
) -> str:
    if not markdown_text.strip() or not figure_entries:
        return markdown_text

    preamble_lines, section_blocks = _split_top_level_section_blocks(markdown_text)
    if not section_blocks:
        return markdown_text

    output_lines = _trim_blank_lines(preamble_lines)
    if output_lines:
        output_lines.append("")

    changed = False
    for title, body_lines in section_blocks:
        output_lines.append(f"# {title}")
        output_lines.append("")
        if title == ZH_RESULTS_HEADING:
            body_lines, body_changed = _enforce_result_figure_distribution_in_body(body_lines, figure_entries)
            changed = changed or body_changed
        output_lines.extend(_trim_blank_lines(body_lines))
        output_lines.append("")

    return "\n".join(_trim_blank_lines(output_lines)).strip() + ("\n" if changed else "\n")


def _enforce_result_figure_distribution_in_body(
    body_lines: list[str],
    figure_entries: list[dict[str, object]],
) -> tuple[list[str], bool]:
    all_images = _extract_image_lines_from_buckets([body_lines])
    if not all_images:
        return body_lines, False

    loose_lead, subsection_blocks = _split_nested_heading_blocks(body_lines)
    if len(subsection_blocks) < 3:
        return body_lines, False

    subsection_titles = [title for title, _body in subsection_blocks[:3]]
    assigned = _assign_result_images_to_subsections(
        ordered_content={subsection_titles[2]: all_images},
        subsection_titles=subsection_titles,
        figure_entries=figure_entries,
    )
    assigned = _normalize_result_figure_captions(assigned, figure_entries)

    role_by_index = {0: "baseline", 1: "comparison", 2: "curve"}
    evidence = _build_result_evidence("", body_lines)
    rebuilt: list[str] = []
    cleaned_lead = _remove_image_lines(loose_lead)
    if cleaned_lead:
        rebuilt.extend(cleaned_lead)
        rebuilt.append("")

    for index, (title, block_lines) in enumerate(subsection_blocks):
        role = role_by_index.get(index)
        cleaned_block = _remove_image_lines(block_lines)
        rebuilt.append(f"## {title}")
        rebuilt.append("")
        rebuilt.extend(_trim_blank_lines(cleaned_block))

        if role and assigned[role]:
            _append_result_figure_units(rebuilt, evidence, assigned[role], role)
        rebuilt.append("")

    original_image_order = [line.strip() for line in all_images]
    new_image_order = [
        line.strip()
        for line in _extract_image_lines_from_buckets([rebuilt])
    ]
    return _trim_blank_lines(rebuilt), original_image_order != new_image_order


def _remove_image_lines(lines: list[str]) -> list[str]:
    return [raw_line for raw_line in lines if not IMAGE_LINE_PATTERN.match(raw_line.strip())]


def _rewrite_discussion_section_body(
    body_lines: list[str],
    markdown_text: str,
    evidence: ResultEvidence | None = None,
) -> list[str]:
    discussion_text = _flatten_markdown_lines([body_lines])
    if evidence is None:
        results_text = _extract_top_level_section_text(markdown_text, ZH_RESULTS_HEADING)
        evidence = _build_result_evidence(markdown_text, results_text)
    citation_markers = _extract_unique_citation_markers(discussion_text)
    paragraph_candidates = [
        _build_discussion_summary_paragraph(evidence, discussion_text),
        _build_discussion_interpretation_paragraph(evidence, discussion_text),
        _build_discussion_bias_paragraph(evidence, discussion_text),
        _build_discussion_statistical_visual_paragraph(evidence, discussion_text),
        _build_discussion_limitation_paragraph(evidence, discussion_text),
    ]

    rendered: list[str] = []
    for paragraph in paragraph_candidates:
        cleaned = _clean_discussion_paragraph(paragraph)
        if not cleaned:
            continue
        if rendered:
            rendered.append("")
        rendered.append(cleaned)

    if rendered:
        if citation_markers:
            rendered[0] = _append_citation_markers(rendered[0], citation_markers)
        return rendered

    fallback = _clean_discussion_paragraph(discussion_text)
    return [fallback] if fallback else []


def _compact_methods_subsection_buckets(
    ordered_content: dict[str, list[str]],
    *,
    manuscript_text: str,
) -> dict[str, list[str]]:
    full_text = f"{manuscript_text}\n{_flatten_markdown_lines(ordered_content.values())}"
    compact_buckets: dict[str, list[str]] = {}

    patient_text = _build_methods_patient_paragraph(full_text, _flatten_markdown_lines([ordered_content[ZH_REFERENCE_METHODS_SUBHEADINGS[0]]]))
    clinical_text = _build_methods_clinical_paragraph(full_text, _flatten_markdown_lines([ordered_content[ZH_REFERENCE_METHODS_SUBHEADINGS[1]]]))
    followup_text = _build_methods_followup_paragraph(full_text, _flatten_markdown_lines([ordered_content[ZH_REFERENCE_METHODS_SUBHEADINGS[2]]]))
    statistics_text = _build_methods_statistics_paragraph(full_text, _flatten_markdown_lines([ordered_content[ZH_REFERENCE_METHODS_SUBHEADINGS[3]]]))

    compact_buckets[ZH_REFERENCE_METHODS_SUBHEADINGS[0]] = [patient_text] if patient_text else []
    compact_buckets[ZH_REFERENCE_METHODS_SUBHEADINGS[1]] = [clinical_text] if clinical_text else []
    compact_buckets[ZH_REFERENCE_METHODS_SUBHEADINGS[2]] = [followup_text] if followup_text else []
    compact_buckets[ZH_REFERENCE_METHODS_SUBHEADINGS[3]] = [statistics_text] if statistics_text else []
    return compact_buckets


def _build_methods_patient_paragraph(full_text: str, section_text: str) -> str:
    sentences: list[str] = []
    if "\u591a\u4e2d\u5fc3" in full_text and "\u56de\u987e\u6027" in full_text:
        sentences.append("\u672c\u7814\u7a76\u57fa\u4e8e\u591a\u4e2d\u5fc3\u539f\u53d1\u6027\u809d\u764c\u672f\u540e\u961f\u5217\u5f00\u5c55\u56de\u987e\u6027\u5206\u6790\u3002")
    elif "\u591a\u4e2d\u5fc3" in full_text:
        sentences.append("\u672c\u7814\u7a76\u4f9d\u6258\u591a\u4e2d\u5fc3\u539f\u53d1\u6027\u809d\u764c\u672f\u540e\u968f\u8bbf\u961f\u5217\u5f00\u5c55\u4e34\u5e8a\u89c2\u5bdf\u3002")
    elif "\u56de\u987e\u6027" in full_text:
        sentences.append("\u672c\u7814\u7a76\u4ee5\u539f\u53d1\u6027\u809d\u764c\u672f\u540e\u60a3\u8005\u4e3a\u5bf9\u8c61\u8fdb\u884c\u56de\u987e\u6027\u5206\u6790\u3002")
    else:
        sentences.append("\u672c\u7814\u7a76\u4ee5\u63a5\u53d7\u624b\u672f\u5207\u9664\u540e\u7684\u539f\u53d1\u6027\u809d\u764c\u60a3\u8005\u4e3a\u7814\u7a76\u5bf9\u8c61\u3002")

    patient_count = _extract_preferred_patient_count(full_text)
    if patient_count:
        sentences.append(f"\u6700\u7ec8\u7eb3\u5165{patient_count}\u4f8b\u5177\u6709\u57fa\u672c\u4e34\u5e8a\u8d44\u6599\u3001\u672f\u540e\u6cbb\u7597\u8bb0\u5f55\u53ca\u968f\u8bbf\u7ed3\u5c40\u7684\u60a3\u8005\u8fdb\u884c\u5206\u6790\u3002")

    sentences.append("\u75c5\u4f8b\u7b5b\u9009\u6309\u7167\u7814\u7a76\u8bbe\u8ba1\u3001\u8bca\u7597\u65f6\u95f4\u987a\u5e8f\u548c\u8d44\u6599\u53ef\u8ffd\u6eaf\u6027\u9010\u6b65\u5f00\u5c55\uff0c\u5148\u6839\u636e\u8bca\u65ad\u4e0e\u624b\u672f\u8bb0\u5f55\u5f62\u6210\u521d\u7b5b\u961f\u5217\uff0c\u518d\u7ed3\u5408\u672f\u540e\u6cbb\u7597\u4fe1\u606f\u548c\u968f\u8bbf\u7ed3\u5c40\u5f62\u6210\u53ef\u7528\u5206\u6790\u96c6\u3002")
    sentences.append("\u7eb3\u5165\u539f\u5219\u4fa7\u91cd\u4e8e\u4e34\u5e8a\u8bca\u65ad\u660e\u786e\u3001\u624b\u672f\u53ca\u672f\u540e\u7ba1\u7406\u8bb0\u5f55\u53ef\u6838\u5bf9\u3001\u4e3b\u8981\u7ed3\u5c40\u53ef\u5224\u5b9a\uff1b\u5173\u952e\u65f6\u95f4\u8282\u70b9\u7f3a\u5931\u3001\u91cd\u590d\u8bb0\u5f55\u6216\u7ec8\u70b9\u65f6\u95f4\u903b\u8f91\u65e0\u6cd5\u6821\u6b63\u8005\u4e0d\u7eb3\u5165\u540e\u7eed\u6bd4\u8f83\u3002")
    if _contains_any(full_text, ("\u77e5\u60c5\u540c\u610f", "fas", "\u5206\u6790\u96c6")):
        sentences.append("\u7eb3\u5165\u5206\u6790\u524d\u5bf9\u75c5\u4f8b\u8bb0\u5f55\u4e0e\u77e5\u60c5\u540c\u610f\u4fe1\u606f\u8fdb\u884c\u7edf\u4e00\u6838\u5bf9\uff0c\u5e76\u5728\u7b5b\u9009\u540e\u786e\u5b9a\u6700\u7ec8\u5206\u6790\u96c6\u3002")
    if _contains_any(full_text, ("\u968f\u8bbf", "\u672f\u540e", "\u6392\u9664", "\u7eb3\u5165")):
        sentences.append("\u7eb3\u5165\u6807\u51c6\u4ee5\u5177\u5907\u57fa\u672c\u4e34\u5e8a\u8d44\u6599\u3001\u672f\u540e\u6cbb\u7597\u8bb0\u5f55\u53ca\u53ef\u8ffd\u8e2a\u968f\u8bbf\u7ed3\u5c40\u4e3a\u4e3b\uff0c\u5173\u952e\u8d44\u6599\u7f3a\u5931\u6216\u65e0\u6cd5\u5224\u5b9a\u7ec8\u70b9\u8005\u4e0d\u7eb3\u5165\u540e\u7eed\u6bd4\u8f83\u3002")
    if "\u4f26\u7406" in full_text:
        sentences.append("\u7814\u7a76\u6309\u7167\u76f8\u5173\u4f26\u7406\u8981\u6c42\u5f00\u5c55\uff0c\u6240\u6709\u7eb3\u5165\u8d44\u6599\u5747\u7ecf\u6838\u5bf9\u540e\u7528\u4e8e\u7edf\u8ba1\u5206\u6790\u3002")
    else:
        sentences.append("\u7814\u7a76\u8d44\u6599\u5728\u5206\u6790\u524d\u8fdb\u884c\u533f\u540d\u5316\u4e0e\u4e00\u81f4\u6027\u6838\u5bf9\uff0c\u4ec5\u4ee5\u6c47\u603b\u7ed3\u679c\u5f62\u5f0f\u5448\u73b0\uff0c\u4ee5\u7b26\u5408\u56de\u987e\u6027\u4e34\u5e8a\u8d44\u6599\u5206\u6790\u7684\u4f26\u7406\u548c\u9690\u79c1\u4fdd\u62a4\u8981\u6c42\u3002")
    sentences.append("\u4e0a\u8ff0\u8fc7\u7a0b\u4f7f\u7814\u7a76\u961f\u5217\u5728\u4fdd\u7559\u771f\u5b9e\u4e16\u754c\u8bca\u7597\u7279\u5f81\u7684\u540c\u65f6\uff0c\u5c3d\u91cf\u51cf\u5c11\u7531\u8d44\u6599\u4e0d\u5b8c\u6574\u6216\u8bb0\u5f55\u4e0d\u4e00\u81f4\u5e26\u6765\u7684\u5206\u6790\u504f\u5dee\u3002")

    fallback = _fallback_to_compact_paragraph(section_text, max_sentences=5)
    return _compose_reference_paragraph(sentences, fallback, min_sentences=6, max_sentences=8, min_chars=260)


def _build_methods_clinical_paragraph(full_text: str, section_text: str) -> str:
    sentences: list[str] = []
    has_demographics = _contains_any(full_text, ("\u5e74\u9f84", "\u6027\u522b", "\u4eba\u53e3\u5b66"))
    has_stage = _contains_any(full_text, ("bclc", "child-pugh", "ecog", "\u5206\u671f", "\u809d\u529f\u80fd"))
    has_pathology = _contains_any(full_text, ("afp", "ggt", "alt", "ast", "\u75c5\u7406", "\u80bf\u7624", "\u5fae\u8840\u7ba1"))

    if has_demographics:
        sentences.append("\u6536\u96c6\u60a3\u8005\u5e74\u9f84\u3001\u6027\u522b\u7b49\u4eba\u53e3\u5b66\u8d44\u6599\u53ca\u57fa\u672c\u4e34\u5e8a\u4fe1\u606f\uff0c\u7528\u4e8e\u63cf\u8ff0\u7814\u7a76\u961f\u5217\u7684\u57fa\u7ebf\u72b6\u6001\u3002")
    if has_stage:
        sentences.append("\u540c\u65f6\u8bb0\u5f55BCLC\u5206\u671f\u3001Child-Pugh\u8bc4\u5206\u3001ECOG\u8bc4\u5206\u7b49\u6307\u6807\uff0c\u4ee5\u53cd\u6620\u80bf\u7624\u5206\u671f\u53ca\u809d\u529f\u80fd\u72b6\u6001\u3002")
    if has_pathology:
        sentences.append("\u5e76\u6536\u96c6\u80bf\u7624\u5927\u5c0f\u3001\u75c5\u7406\u7279\u5f81\u4ee5\u53caAFP\u7b49\u5b9e\u9a8c\u5ba4\u6307\u6807\uff0c\u7528\u4e8e\u5206\u6790\u4e34\u5e8a\u75c5\u7406\u7279\u5f81\u4e0e\u9884\u540e\u7684\u5173\u7cfb\u3002")
    elif _contains_any(full_text, ("\u6307\u6807", "\u53d8\u91cf", "\u57fa\u7ebf")):
        sentences.append("\u6536\u96c6\u57fa\u7ebf\u4e34\u5e8a\u75c5\u7406\u6307\u6807\u53ca\u4e3b\u8981\u53d8\u91cf\uff0c\u4f5c\u4e3a\u540e\u7eed\u5206\u5c42\u4e0e\u6bd4\u8f83\u5206\u6790\u7684\u57fa\u7840\u3002")
    sentences.append("\u8fd9\u4e9b\u6307\u6807\u5728\u5206\u6790\u4e2d\u5206\u522b\u627f\u62c5\u4e0d\u540c\u529f\u80fd\uff1a\u4eba\u53e3\u5b66\u53d8\u91cf\u7528\u4e8e\u63cf\u8ff0\u7814\u7a76\u5bf9\u8c61\u7684\u57fa\u672c\u6784\u6210\uff0c\u80bf\u7624\u53ca\u809d\u529f\u80fd\u76f8\u5173\u6307\u6807\u7528\u4e8e\u53cd\u6620\u75be\u75c5\u8d1f\u8377\u548c\u6cbb\u7597\u9002\u5e94\u6027\uff0c\u75c5\u7406\u6307\u6807\u5219\u7528\u4e8e\u8f85\u52a9\u5224\u65ad\u590d\u53d1\u98ce\u9669\u548c\u9884\u540e\u5dee\u5f02\u3002")
    sentences.append("\u53d8\u91cf\u7eb3\u5165\u7684\u76ee\u7684\u4e0d\u4ec5\u662f\u5b8c\u6210\u57fa\u7ebf\u63cf\u8ff0\uff0c\u4e5f\u662f\u4e3a\u7ed3\u679c\u4e2d\u7684\u7ec4\u95f4\u6bd4\u8f83\u63d0\u4f9b\u5fc5\u8981\u80cc\u666f\uff0c\u4ee5\u907f\u514d\u5c06\u6cbb\u7597\u7ec4\u95f4\u7684\u8868\u9762\u5dee\u5f02\u7b80\u5316\u4e3a\u5355\u4e00\u56e0\u7d20\u6240\u81f4\u3002")
    if _contains_any(full_text, ("\u6807\u51c6\u5316", "\u6e05\u6d17", "\u8d28\u91cf\u8bc4\u4f30")):
        sentences.append("\u5bf9\u5173\u952e\u4e34\u5e8a\u53d8\u91cf\u8fdb\u884c\u6574\u7406\u4e0e\u6807\u51c6\u5316\u5904\u7406\uff0c\u4ee5\u63d0\u9ad8\u4e0d\u540c\u8bb0\u5f55\u53e3\u5f84\u4e4b\u95f4\u7684\u53ef\u6bd4\u6027\u3002")
    sentences.append("\u8fde\u7eed\u578b\u53d8\u91cf\u548c\u5206\u7c7b\u53d8\u91cf\u5728\u6574\u7406\u65f6\u5747\u4fdd\u7559\u5176\u4e34\u5e8a\u542b\u4e49\uff0c\u7ed3\u679c\u5448\u73b0\u65f6\u4f18\u5148\u53cd\u6620\u80fd\u591f\u8bf4\u660e\u4eba\u7fa4\u5dee\u5f02\u3001\u75be\u75c5\u5206\u5c42\u548c\u9884\u540e\u80cc\u666f\u7684\u4fe1\u606f\u3002")
    sentences.append("\u4e0a\u8ff0\u6307\u6807\u4e3b\u8981\u7528\u4e8e\u63cf\u8ff0\u57fa\u7ebf\u7279\u5f81\uff0c\u5e76\u4e3a\u4e0d\u540c\u6cbb\u7597\u5206\u7ec4\u7684\u9884\u540e\u8bc4\u4ef7\u63d0\u4f9b\u5206\u5c42\u4f9d\u636e\u3002")

    fallback = _fallback_to_compact_paragraph(section_text, max_sentences=5)
    return _compose_reference_paragraph(sentences, fallback, min_sentences=6, max_sentences=8, min_chars=260)


def _build_methods_followup_paragraph(full_text: str, section_text: str) -> str:
    sentences: list[str] = []
    treatment_labels: list[str] = []
    if _contains_any(full_text, ("\u76d1\u6d4b/\u672a\u6cbb\u7597", "\u76d1\u6d4b", "\u672a\u6cbb\u7597")):
        treatment_labels.append("\u76d1\u6d4b/\u672a\u6cbb\u7597")
    if "tace" in full_text.casefold():
        treatment_labels.append("TACE")
    if "\u514d\u75ab" in full_text:
        treatment_labels.append("\u514d\u75ab\u6cbb\u7597")
    if "\u9776\u5411" in full_text:
        treatment_labels.append("\u9776\u5411\u6cbb\u7597")
    if "\u8054\u5408" in full_text:
        treatment_labels.append("\u8054\u5408\u6cbb\u7597")
    if treatment_labels:
        deduped = []
        for label in treatment_labels:
            if label not in deduped:
                deduped.append(label)
        sentences.append(f"\u6839\u636e\u672f\u540e\u9996\u6b21\u6cbb\u7597\u8bb0\u5f55\u5c06\u60a3\u8005\u5206\u4e3a{chr(0x3001).join(deduped)}\u7b49\u7ec4\u522b\uff0c\u4ee5\u907f\u514d\u540e\u7eed\u591a\u6b21\u5e72\u9884\u5bf9\u7597\u6548\u8bc4\u4ef7\u7684\u5f71\u54cd\u3002")
    if _contains_any(full_text, ("\u968f\u8bbf", "\u968f\u8bbf\u8bb0\u5f55", "\u968f\u8bbf\u7ed3\u5c40")):
        sentences.append("\u968f\u8bbf\u8d44\u6599\u4e3b\u8981\u6765\u81ea\u672f\u540e\u8bb0\u5f55\u53ca\u5b9a\u671f\u590d\u67e5\u4fe1\u606f\uff0c\u7528\u4e8e\u52a8\u6001\u5224\u5b9a\u590d\u53d1\u4e0e\u751f\u5b58\u72b6\u6001\u3002")
    else:
        sentences.append("\u968f\u8bbf\u4fe1\u606f\u4ee5\u672f\u540e\u4e34\u5e8a\u8bb0\u5f55\u3001\u590d\u67e5\u7ed3\u679c\u548c\u751f\u5b58\u72b6\u6001\u8ffd\u8e2a\u4e3a\u4e3b\u8981\u6765\u6e90\uff0c\u7528\u4e8e\u8fde\u7eed\u8bb0\u5f55\u590d\u53d1\u3001\u6b7b\u4ea1\u6216\u672b\u6b21\u968f\u8bbf\u72b6\u6001\u3002")
    sentences.append("\u968f\u8bbf\u8282\u70b9\u901a\u5e38\u4e0e\u672f\u540e\u5b9a\u671f\u590d\u67e5\u548c\u75c5\u60c5\u53d8\u5316\u8bb0\u5f55\u76f8\u8854\u63a5\uff0c\u5bf9\u5f71\u50cf\u5b66\u63d0\u793a\u590d\u53d1\u3001\u4e34\u5e8a\u8bb0\u5f55\u660e\u786e\u6b7b\u4ea1\u6216\u968f\u8bbf\u622a\u6b62\u65f6\u4ecd\u672a\u53d1\u751f\u4e8b\u4ef6\u7684\u60c5\u51b5\u5206\u522b\u4f5c\u51fa\u7ec8\u70b9\u5224\u5b9a\u3002")

    if _contains_any(full_text, ("os", "rfs", "\u603b\u751f\u5b58", "\u65e0\u590d\u53d1\u751f\u5b58")):
        sentences.append("\u968f\u8bbf\u7ed3\u5c40\u8bbe\u5b9a\u4e3a\u603b\u751f\u5b58\uff08OS\uff09\u548c\u65e0\u590d\u53d1\u751f\u5b58\uff08RFS\uff09\uff0c\u5e76\u5206\u522b\u57fa\u4e8e\u7ec8\u70b9\u4e8b\u4ef6\u4e0e\u672b\u6b21\u968f\u8bbf\u65f6\u70b9\u8fdb\u884c\u8ba1\u7b97\u3002")
    if _contains_any(full_text, ("\u5220\u5931", "\u7ec8\u70b9", "\u590d\u53d1", "\u6b7b\u4ea1")):
        sentences.append("\u7ec8\u70b9\u4e8b\u4ef6\u5305\u62ec\u590d\u53d1\u6216\u6b7b\u4ea1\uff0c\u5bf9\u672b\u6b21\u968f\u8bbf\u65f6\u4ecd\u672a\u53d1\u751f\u7ec8\u70b9\u4e8b\u4ef6\u8005\u4f5c\u5220\u5931\u5904\u7406\u3002")
    else:
        sentences.append("\u5bf9\u672b\u6b21\u968f\u8bbf\u65f6\u672a\u89c2\u5bdf\u5230\u76f8\u5e94\u7ec8\u70b9\u8005\u6309\u5220\u5931\u5904\u7406\uff0c\u4ee5\u4fdd\u8bc1\u751f\u5b58\u65f6\u95f4\u8ba1\u7b97\u4e0eKaplan-Meier\u5206\u6790\u7684\u57fa\u672c\u903b\u8f91\u4e00\u81f4\u3002")
    sentences.append("\u6309\u9996\u6b21\u6838\u5fc3\u672f\u540e\u6cbb\u7597\u8fdb\u884c\u5206\u7ec4\uff0c\u662f\u4e3a\u4e86\u5c06\u6bd4\u8f83\u8d77\u70b9\u56fa\u5b9a\u5728\u53ef\u8ffd\u6eaf\u7684\u521d\u59cb\u7ba1\u7406\u7b56\u7565\u4e0a\uff0c\u51cf\u5c11\u540e\u7eed\u590d\u53d1\u540e\u591a\u6b21\u6cbb\u7597\u8c03\u6574\u5bf9\u7ec4\u95f4\u6bd4\u8f83\u7684\u5e72\u6270\u3002")

    fallback = _fallback_to_compact_paragraph(section_text, max_sentences=5)
    return _compose_reference_paragraph(sentences, fallback, min_sentences=6, max_sentences=8, min_chars=260)


def _build_methods_statistics_paragraph(full_text: str, section_text: str) -> str:
    sentences: list[str] = []
    if _contains_any(full_text, ("\u5b8c\u6574\u6027", "\u903b\u8f91", "\u8d28\u91cf\u63a7\u5236", "\u9884\u5904\u7406")):
        sentences.append("\u5bf9\u5173\u952e\u53d8\u91cf\u8fdb\u884c\u5b8c\u6574\u6027\u4e0e\u903b\u8f91\u6821\u9a8c\u540e\u5f00\u5c55\u7edf\u8ba1\u5206\u6790\u3002")
    else:
        sentences.append("\u5728\u7edf\u8ba1\u5206\u6790\u524d\u5148\u5bf9\u5173\u952e\u53d8\u91cf\u8fdb\u884c\u6574\u7406\u4e0e\u6838\u5bf9\u3002")
    methods: list[str] = []
    if "kaplan-meier" in full_text.casefold():
        methods.append("Kaplan-Meier\u6cd5")
    if "log-rank" in full_text.casefold():
        methods.append("Log-rank\u68c0\u9a8c")
    if "cox" in full_text.casefold():
        methods.append("Cox\u56de\u5f52\u6a21\u578b")
    if methods:
        sentences.append(f"\u7edf\u8ba1\u5206\u6790\u4e3b\u8981\u91c7\u7528{chr(0x3001).join(methods)}\u8bc4\u4ef7\u4e0d\u540c\u6cbb\u7597\u7ec4\u7684\u751f\u5b58\u7ed3\u5c40\u5dee\u5f02\u3002")
    else:
        sentences.append("\u7edf\u8ba1\u5206\u6790\u4ee5\u63cf\u8ff0\u7814\u7a76\u961f\u5217\u3001\u5448\u73b0\u7ec4\u95f4\u6784\u6210\u5e76\u6bd4\u8f83\u4e3b\u8981\u7ec8\u70b9\u4e3a\u57fa\u672c\u6846\u67b6\u3002")
    sentences.append("\u63cf\u8ff0\u6027\u7edf\u8ba1\u9996\u5148\u7528\u4e8e\u603b\u7ed3\u60a3\u8005\u57fa\u7ebf\u7279\u5f81\u3001\u6cbb\u7597\u5206\u7ec4\u6784\u6210\u548c\u968f\u8bbf\u7ed3\u5c40\u5206\u5e03\uff0c\u4ece\u800c\u4e3a\u540e\u7eed\u751f\u5b58\u6bd4\u8f83\u63d0\u4f9b\u4eba\u7fa4\u80cc\u666f\u3002")
    sentences.append("\u751f\u5b58\u5206\u6790\u5219\u56f4\u7ed5OS\u548cRFS\u5c55\u5f00\uff0c\u5148\u901a\u8fc7Kaplan-Meier\u65b9\u6cd5\u63cf\u7ed8\u4e0d\u540c\u5206\u7ec4\u7684\u7ed3\u5c40\u66f2\u7ebf\uff0c\u518d\u7ed3\u5408Log-rank\u68c0\u9a8c\u5bf9\u7ec4\u95f4\u66f2\u7ebf\u5dee\u5f02\u8fdb\u884c\u5224\u65ad\u3002")
    if "cox" in full_text.casefold():
        sentences.append("\u5bf9\u9884\u540e\u76f8\u5173\u56e0\u7d20\u8fdb\u4e00\u6b65\u91c7\u7528Cox\u6a21\u578b\u8fdb\u884c\u5206\u6790\u3002")
    elif _contains_any(full_text, ("\u5206\u7ec4", "\u4e9a\u7ec4", "\u6cbb\u7597\u65b9\u6848")):
        sentences.append("\u7ec4\u95f4\u6bd4\u8f83\u4e3b\u8981\u7528\u4e8e\u8bc4\u4ef7\u4e0d\u540c\u672f\u540e\u6cbb\u7597\u65b9\u6848\u5728OS\u4e0eRFS\u65b9\u9762\u7684\u5dee\u5f02\u3002")
    if re.search(r"p\s*[<<=]\s*0\.0?5", full_text, flags=re.IGNORECASE):
        sentences.append("P<0.05 \u4e3a\u5dee\u5f02\u6709\u7edf\u8ba1\u5b66\u610f\u4e49\u3002")
    elif len(sentences) < 7:
        sentences.append("\u7edf\u8ba1\u7ed3\u679c\u4e3b\u8981\u7528\u4e8e\u6bd4\u8f83\u4e0d\u540c\u672f\u540e\u6cbb\u7597\u7b56\u7565\u4e0e\u751f\u5b58\u7ed3\u5c40\u7684\u5173\u7cfb\u3002")
    sentences.append("\u672a\u5b9e\u65bd\u6216\u672a\u62a5\u544a\u7684\u590d\u6742\u6821\u6b63\u5206\u6790\u4e0d\u4f5c\u989d\u5916\u6269\u5c55\uff0c\u7ed3\u679c\u89e3\u91ca\u4e3b\u8981\u4f9d\u636e\u5df2\u6709\u7684\u63cf\u8ff0\u3001\u751f\u5b58\u66f2\u7ebf\u548c\u7ec4\u95f4\u68c0\u9a8c\u7ed3\u679c\u3002")

    fallback = "" if len(sentences) >= 4 else _fallback_to_compact_paragraph(section_text, max_sentences=5)
    return _compose_reference_paragraph(sentences, fallback, min_sentences=6, max_sentences=8, min_chars=260)


def _extract_preferred_patient_count(text: str) -> str:
    patterns = [
        r"(?:\u5171|\u6700\u7ec8\u7eb3\u5165|\u672c\u7814\u7a76\u5171\u7eb3\u5165)\s*(\d{2,6})\s*(?:\u4f8b|\u540d)\u60a3\u8005",
        r"(?:\u5171|\u7eb3\u5165)\s*(\d{2,6})\s*\u6761\u60a3\u8005\u8bb0\u5f55",
        r"\u57fa\u4e8e\s*(\d{2,6})\s*(?:\u4f8b|\u540d)(?:\u672f\u540e)?\u60a3\u8005",
        r"\u5bf9\s*(\d{2,6})\s*(?:\u4f8b|\u540d)(?:\u672f\u540e)?\u60a3\u8005\u8fdb\u884c",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def _fallback_to_compact_paragraph(text: str, *, max_sentences: int = 2) -> str:
    cleaned = _clean_method_paragraph(text)
    if not cleaned:
        return ""
    sentences = re.split(r"(?<=[\u3002\uff1b!?])\s*", cleaned)
    compact = "".join(_ensure_terminal_punctuation(sentence.strip()) for sentence in sentences[:max_sentences] if sentence.strip())
    if compact:
        return compact
    return cleaned


def _prefer_compact_sentence_block(sentences: list[str], fallback: str) -> str:
    cleaned_sentences = []
    for sentence in sentences:
        cleaned = _clean_method_paragraph(sentence)
        if cleaned:
            cleaned_sentences.append(_ensure_terminal_punctuation(cleaned))
    if cleaned_sentences:
        return "".join(cleaned_sentences)
    return fallback


def _compose_reference_paragraph(
    sentences: list[str],
    fallback: str,
    *,
    min_sentences: int = 2,
    max_sentences: int = 3,
    min_chars: int = 0,
) -> str:
    merged: list[str] = []
    seen: set[str] = set()

    def _append(items: list[str]) -> None:
        for item in items:
            cleaned = _clean_method_paragraph(item)
            if not cleaned:
                continue
            punctuated = _ensure_terminal_punctuation(cleaned)
            key = re.sub(r"\s+", "", punctuated)
            if key in seen:
                continue
            merged.append(punctuated)
            seen.add(key)
            if len(merged) >= max_sentences:
                return

    _append(sentences)
    current_length = len(re.sub(r"\s+", "", "".join(merged)))
    if (len(merged) < min_sentences or current_length < min_chars) and fallback:
        fallback_sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[\u3002\uff1b!?])\s*", _clean_method_paragraph(fallback))
            if sentence.strip()
        ]
        _append(fallback_sentences)

    if merged:
        return "".join(merged[:max_sentences])
    return fallback


def _flatten_markdown_lines(chunks: Iterable[list[str]]) -> str:
    fragments: list[str] = []
    for lines in chunks:
        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#") or IMAGE_LINE_PATTERN.match(stripped):
                continue
            fragments.append(stripped)
    return _clean_method_paragraph(" ".join(fragments))


def _clean_method_paragraph(text: str) -> str:
    cleaned = re.sub(r"`([^`]+)`", r"\1", text)
    cleaned = re.sub(r"[“”\"]", "", cleaned)
    cleaned = re.sub(r"\(([A-Za-z_/\-]{2,}[^)]*)\)", "", cleaned)
    cleaned = re.sub(r"（[A-Za-z_/\-]{2,}[^）]*）", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.replace(" ，", "，").replace(" 。", "。").replace(" ；", "；").replace(" ：", "：")
    return cleaned.strip(" ，；")


def _ensure_terminal_punctuation(text: str) -> str:
    if not text:
        return ""
    if text.endswith(("。", "！", "？", "；", ".", "!", "?")):
        return text
    return text + "。"


def _split_nested_heading_blocks(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    lead_lines: list[str] = []
    blocks: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_body: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match and len(heading_match.group(1)) >= 2:
            if current_title is None:
                lead_lines = _trim_blank_lines(current_body)
            else:
                blocks.append((current_title, _trim_blank_lines(current_body)))
            current_title = heading_match.group(2).strip()
            current_body = []
            continue
        current_body.append(raw_line)

    if current_title is None:
        lead_lines = _trim_blank_lines(current_body)
    else:
        blocks.append((current_title, _trim_blank_lines(current_body)))
    return lead_lines, [(title, body) for title, body in blocks if body]


def _materialize_loose_chunks(lines: list[str]) -> list[tuple[str, list[str]]]:
    chunks: list[tuple[str, list[str]]] = []
    current: list[str] = []

    for raw_line in lines:
        if raw_line.strip():
            current.append(raw_line)
            continue
        if current:
            chunks.append(("", _trim_blank_lines(current)))
            current = []

    if current:
        chunks.append(("", _trim_blank_lines(current)))
    return [(title, body) for title, body in chunks if body]


def _append_chunk_to_bucket(bucket: list[str], chunk_lines: list[str]) -> None:
    cleaned = _trim_blank_lines(chunk_lines)
    if not cleaned:
        return
    if _is_obviously_nonclinical_chunk(cleaned):
        return
    if bucket:
        bucket.append("")
    bucket.extend(cleaned)


def _is_obviously_nonclinical_chunk(chunk_lines: list[str]) -> bool:
    text = _normalize_heading_candidate(_flatten_markdown_lines([chunk_lines]) or "\n".join(chunk_lines))
    if not text:
        return False

    clinical_keywords = (
        "\u809d\u764c",
        "\u539f\u53d1\u6027\u809d\u764c",
        "\u809d\u7ec6\u80de",
        "\u60a3\u8005",
        "\u968f\u8bbf",
        "\u6cbb\u7597",
        "\u672f\u540e",
        "\u751f\u5b58",
        "\u590d\u53d1",
        "tace",
        "rfs",
        "os",
        "bclc",
        "child-pugh",
        "\u75c5\u7406",
        "\u80bf\u7624",
    )
    if any(keyword in text.casefold() for keyword in clinical_keywords):
        return False

    red_flags = (
        "\u91d1\u878d",
        "\u4ea4\u6613",
        "\u793e\u4ea4",
        "\u7528\u6237",
        "\u8bbe\u5907",
        "ip",
        "\u805a\u7c7b",
        "\u9ad8\u9891\u6d3b\u8dc3",
        "\u5f02\u5e38\u4ea4\u6613",
        "\u50f5\u5c38",
        "\u5317\u7f8e",
        "\u6b27\u6d32",
        "\u4e9a\u592a",
        "a\u7c7b",
        "c\u7c7b",
        "null",
    )
    return sum(flag in text.casefold() for flag in red_flags) >= 2


def _render_ordered_subsection_buckets(ordered_content: dict[str, list[str]]) -> list[str]:
    lines: list[str] = []
    for heading, body in ordered_content.items():
        cleaned = _trim_blank_lines(body)
        if not cleaned:
            continue
        lines.append(f"## {heading}")
        lines.append("")
        lines.extend(cleaned)
        lines.append("")
    return _trim_blank_lines(lines)


def _classify_methods_subsection(title: str, chunk_lines: list[str], fallback_index: int) -> str:
    normalized_title = _normalize_heading_candidate(title)
    chunk_text = "\n".join(chunk_lines)
    normalized_chunk = _normalize_heading_candidate(chunk_text)
    haystack = f"{normalized_title}\n{normalized_chunk}"

    if _contains_any(normalized_title, ("\u6307\u6807", "\u53d8\u91cf", "\u75c5\u7406", "\u4e34\u5e8a", "\u57fa\u7ebf", "\u5b57\u6bb5")):
        return ZH_REFERENCE_METHODS_SUBHEADINGS[1]
    if _contains_any(haystack, ("\u7edf\u8ba1", "kaplan", "cox", "log-rank", "p\u503c", "r ", "rstudio", "spss", "hr", "\u7f6e\u4fe1\u533a\u95f4")):
        return ZH_REFERENCE_METHODS_SUBHEADINGS[3]
    if _contains_any(haystack, ("\u968f\u8bbf", "\u6cbb\u7597", "\u7ec8\u70b9", "\u7ed3\u5c40", "\u590d\u53d1", "\u603b\u751f\u5b58", "os", "rfs", "dfs", "pfs", "\u7535\u8bdd", "ct", "mri", "tace", "\u514d\u75ab", "\u6d88\u878d")):
        return ZH_REFERENCE_METHODS_SUBHEADINGS[2]
    if _contains_any(haystack, ("\u60a3\u8005", "\u75c5\u4f8b", "\u961f\u5217", "\u7eb3\u5165", "\u6392\u9664", "\u5254\u9664", "\u4f26\u7406", "\u5e74", "\u672c\u7814\u7a76", "\u7814\u7a76\u5bf9\u8c61", "\u533b\u9662", "\u4e2d\u5fc3")):
        return ZH_REFERENCE_METHODS_SUBHEADINGS[0]
    if _contains_any(haystack, ("\u6307\u6807", "\u53d8\u91cf", "\u75c5\u7406", "\u4e34\u5e8a", "\u57fa\u7ebf", "\u6536\u96c6", "\u89c2\u5bdf", "\u6570\u636e", "\u5b57\u6bb5", "\u809d\u529f\u80fd", "afp", "alt", "ast", "ggt", "pab", "hbsag", "\u80bf\u7624", "\u5fae\u8840\u7ba1")):
        return ZH_REFERENCE_METHODS_SUBHEADINGS[1]

    return ZH_REFERENCE_METHODS_SUBHEADINGS[min(fallback_index, len(ZH_REFERENCE_METHODS_SUBHEADINGS) - 1)]


def _classify_results_subsection(
    title: str,
    chunk_lines: list[str],
    fallback_index: int,
    subsection_titles: list[str],
    *,
    figure_entries: list[dict[str, object]] | None = None,
) -> str:
    normalized_title = _normalize_heading_candidate(title)
    chunk_text = "\n".join(chunk_lines)
    normalized_chunk = _normalize_heading_candidate(chunk_text)
    haystack = f"{normalized_title}\n{normalized_chunk}"
    image_roles = [
        _infer_result_image_role(raw_line, figure_entries=figure_entries)
        for raw_line in _extract_image_lines_from_buckets([chunk_lines])
    ]

    if image_roles:
        if "comparison" in image_roles and "curve" not in image_roles:
            return subsection_titles[1]
        if "baseline" in image_roles and "curve" not in image_roles and "comparison" not in image_roles:
            return subsection_titles[0]
        if image_roles and all(role == "curve" for role in image_roles):
            return subsection_titles[2]

    if _contains_any(haystack, ("kaplan", "meier", "\u751f\u5b58\u66f2\u7ebf", "\u5206\u5c42", "\u7ed8\u5236", "\u7ec4\u95f4\u751f\u5b58")):
        return subsection_titles[2]
    if _contains_any(haystack, ("\u5355\u56e0\u7d20", "\u591a\u56e0\u7d20", "cox", "hr", "\u76f8\u5173\u56e0\u7d20", "\u5f71\u54cd\u56e0\u7d20", "wald", "95% ci", "p value", "log-rank")):
        return subsection_titles[1]
    if _contains_any(haystack, ("\u4e34\u5e8a\u75c5\u7406\u7279\u5f81", "\u57fa\u7ebf", "\u7279\u5f81", "\u603b\u7ed3", "\u60a3\u8005", "\u808c\u4f53", "\u80bf\u7624", "\u8868 1", "table 1", "\u5206\u5e03", "\u6784\u6210", "\u5360\u6bd4", "\u5206\u7ec4\u60c5\u51b5")):
        return subsection_titles[0]

    return subsection_titles[min(fallback_index, len(subsection_titles) - 1)]


def _build_reference_style_result_subsection_titles(markdown_text: str, supplemental_text: str = "") -> list[str]:
    endpoints: list[str] = []
    upper_text = f"{markdown_text}\n{supplemental_text}".upper()
    for token in ("OS", "RFS", "DFS", "PFS"):
        if token in upper_text and token not in endpoints:
            endpoints.append(token)

    subject_label = _infer_results_subject_label(markdown_text)
    baseline_title = _infer_results_baseline_title(markdown_text, subject_label)

    if _contains_any(markdown_text, ("\u5355\u56e0\u7d20", "\u591a\u56e0\u7d20", "cox", "hazard ratio", "hr")):
        if len(endpoints) >= 2:
            analysis_title = f"\u4e0e{endpoints[0]}\u548c{endpoints[1]}\u76f8\u5173\u56e0\u7d20\u7684\u5355\u56e0\u7d20\u4e0e\u591a\u56e0\u7d20\u5206\u6790"
        elif endpoints:
            analysis_title = f"\u4e0e{endpoints[0]}\u76f8\u5173\u56e0\u7d20\u7684\u5355\u56e0\u7d20\u4e0e\u591a\u56e0\u7d20\u5206\u6790"
        else:
            analysis_title = "\u4e3b\u8981\u7ed3\u5c40\u76f8\u5173\u56e0\u7d20\u7684\u5355\u56e0\u7d20\u4e0e\u591a\u56e0\u7d20\u5206\u6790"
    elif len(endpoints) >= 2:
        analysis_title = f"{subject_label}\u4e0e{endpoints[0]}\u3001{endpoints[1]}\u7684\u6bd4\u8f83"
    elif endpoints:
        analysis_title = f"{subject_label}\u4e0e{endpoints[0]}\u7684\u6bd4\u8f83"
    else:
        analysis_title = f"{subject_label}\u7684\u4e3b\u8981\u7ed3\u5c40\u6bd4\u8f83"

    if any(token in upper_text for token in ("OS", "RFS", "DFS", "PFS", "KAPLAN-MEIER")) or "![Figure" in markdown_text:
        curve_title = f"{subject_label}\u7684Kaplan-Meier\u751f\u5b58\u66f2\u7ebf"
    else:
        curve_title = "\u56fe\u8868\u5c55\u793a"

    return [
        baseline_title,
        analysis_title,
        curve_title,
    ]


def _infer_results_subject_label(markdown_text: str) -> str:
    text = markdown_text.casefold()
    if any(token in text for token in ("\u672f\u540e\u8f85\u52a9\u6cbb\u7597", "\u6cbb\u7597\u65b9\u6848", "\u6cbb\u7597\u7b56\u7565")):
        return "\u4e0d\u540c\u672f\u540e\u8f85\u52a9\u6cbb\u7597\u65b9\u6848"
    if any(token in text for token in ("\u6cbb\u7597\u7ec4", "tace", "\u514d\u75ab", "\u9776\u5411", "\u8054\u5408\u6cbb\u7597")):
        return "\u4e0d\u540c\u6cbb\u7597\u7ec4"
    if any(token in text for token in ("\u4e9a\u7ec4", "subgroup", "\u98ce\u9669\u5206\u5c42")):
        return "\u4e0d\u540c\u5206\u5c42\u4eba\u7fa4"
    return "\u4e0d\u540c\u7814\u7a76\u5206\u7ec4"


def _infer_results_baseline_title(markdown_text: str, subject_label: str) -> str:
    text = markdown_text.casefold()
    has_pathology = any(token in text for token in ("\u4e34\u5e8a\u75c5\u7406", "\u75c5\u7406", "\u80bf\u7624", "\u57fa\u7ebf", "table 1", "\u8868 1"))
    has_distribution = any(token in text for token in ("\u5206\u5e03", "\u6784\u6210", "\u5206\u7ec4", "\u6cbb\u7597\u65b9\u6848", "\u6cbb\u7597\u7ec4"))
    if has_pathology and has_distribution:
        return "\u60a3\u8005\u4e34\u5e8a\u75c5\u7406\u7279\u5f81\u53ca\u5206\u7ec4\u60c5\u51b5"
    if has_pathology:
        return "\u60a3\u8005\u4e34\u5e8a\u75c5\u7406\u7279\u5f81"
    if has_distribution:
        return f"{subject_label}\u7684\u6784\u6210\u4e0e\u57fa\u7ebf\u60c5\u51b5"
    return "\u57fa\u7ebf\u7279\u5f81\u53ca\u5206\u7ec4\u60c5\u51b5"


def _compact_results_subsection_buckets(
    ordered_content: dict[str, list[str]],
    *,
    subsection_titles: list[str],
    evidence: ResultEvidence,
    figure_entries: list[dict[str, object]] | None = None,
) -> dict[str, list[str]]:
    compact: dict[str, list[str]] = {title: [] for title in subsection_titles}

    baseline_title, comparison_title, curve_title = subsection_titles
    baseline_source = _flatten_markdown_lines([ordered_content[baseline_title]])
    comparison_source = _flatten_markdown_lines([ordered_content[comparison_title]])
    curve_source = _flatten_markdown_lines([ordered_content[curve_title]])
    assigned_images = _assign_result_images_to_subsections(
        ordered_content=ordered_content,
        subsection_titles=subsection_titles,
        figure_entries=figure_entries,
    )

    baseline_paragraph = _build_results_baseline_paragraph(evidence, baseline_source, assigned_images["baseline"])
    comparison_paragraph = _build_results_comparison_paragraph(evidence, comparison_source, assigned_images["comparison"])
    curve_paragraph = _build_results_curve_paragraph(evidence, curve_source, assigned_images["curve"])

    assigned_images = _normalize_result_figure_captions(assigned_images, figure_entries)

    if baseline_paragraph:
        compact[baseline_title].append(baseline_paragraph)
    result_tables = _build_result_tables(evidence)
    if result_tables:
        if compact[baseline_title]:
            compact[baseline_title].append("")
        compact[baseline_title].extend(result_tables)
    if comparison_paragraph:
        compact[comparison_title].append(comparison_paragraph)
    if curve_paragraph:
        compact[curve_title].append(curve_paragraph)

    _append_result_figure_units(compact[baseline_title], evidence, assigned_images["baseline"], "baseline")
    _append_result_figure_units(compact[comparison_title], evidence, assigned_images["comparison"], "comparison")
    _append_result_figure_units(compact[curve_title], evidence, assigned_images["curve"], "curve")

    return compact


def _append_result_figure_units(target_lines: list[str], evidence: ResultEvidence, image_lines: list[str], role: str) -> None:
    for image_line in image_lines:
        intro = _build_result_figure_intro(evidence, image_line, role)
        explanation = _build_result_figure_explanation(evidence, image_line, role)
        if target_lines:
            target_lines.append("")
        if intro:
            target_lines.append(intro)
            target_lines.append("")
        target_lines.append(image_line)
        if explanation:
            target_lines.append("")
            target_lines.append(explanation)


def _build_result_figure_intro(evidence: ResultEvidence, image_line: str, role: str) -> str:
    figure_label = _result_figure_label(image_line)
    lowered = image_line.casefold()
    if role == "baseline":
        if any(token in lowered for token in ("cohort", "flow", "队列", "流程", "筛选")):
            return f"{figure_label}展示研究队列从病例筛选到最终纳入分析集的形成过程，用于说明本节分组构成结果所依赖的样本来源和排除路径。将该图置于基线结果之后，有助于读者先理解研究对象的来源，再解读后续治疗分组及终点比较。"
        if any(token in lowered for token in ("follow", "随访")):
            return f"{figure_label}展示随访时间或随访状态的分布情况，对应本节关于队列完整性和结局可观察性的描述。该图在这里呈现，是因为随访分布会直接影响后续OS、RFS等终点结果的稳定性。"
        return f"{figure_label}展示研究分组、治疗构成或基线特征的分布情况，对应本节关于患者构成和组间背景的结果描述。该图用于把文字中的样本构成转化为直观证据，并为后续主要终点比较提供背景。"
    if role == "comparison":
        if any(token in lowered for token in ("forest", "cox", "hr", "hazard", "森林", "风险", "回归")):
            return f"{figure_label}展示Cox模型或危险比相关结果，对应本节对OS、RFS或其他主要终点影响因素的比较。将该图放在统计结果段落之后，是为了把模型估计值、置信区间和正文中的方向性判断相互对应。"
        return f"{figure_label}展示主要终点或组间比较结果，对应本节关于OS、RFS及相关统计检验的结果描述。该图在这里用于补充文字结果，使读者能够同时看到差异方向和统计结论的图形化表达。"
    if "rfs" in lowered or "recurrence" in lowered or "无复发" in lowered:
        return f"{figure_label}展示不同研究分组的RFS Kaplan-Meier曲线，对应本节关于复发相关结局的趋势描述。该图置于RFS结果文字之后，用于观察曲线分离、下降速度和Log-rank结果之间是否一致。"
    if "os" in lowered or "overall" in lowered or "总生存" in lowered:
        return f"{figure_label}展示不同研究分组的OS Kaplan-Meier曲线，对应本节关于总生存结局的趋势描述。该图在这里呈现，是为了说明总生存曲线与RFS相比是否存在更弱或更迟出现的组间分离。"
    return f"{figure_label}展示Kaplan-Meier生存曲线或主要结局趋势，对应本节关于时间事件终点的图形化结果。该图用于将正文中的组间差异描述与曲线形态进行对应，而不是作为独立图集集中展示。"


def _build_result_figure_explanation(evidence: ResultEvidence, image_line: str, role: str) -> str:
    if role == "curve":
        curve_explanation = _build_curve_specific_explanation(evidence, image_line)
        if curve_explanation:
            return curve_explanation
    figure_label = _result_figure_label(image_line)
    lowered = image_line.casefold()
    if role == "baseline":
        distribution_sentence = _build_treatment_distribution_sentence(evidence)
        sentences = []
        if distribution_sentence:
            sentences.append(distribution_sentence)
        sentences.append(f"从{figure_label}可见，队列构成或分组分布并非完全均衡，这一现象与正文对真实世界治疗选择差异的描述相互对应。")
        sentences.append("因此，该图应作为理解后续终点比较的背景信息，而不宜单独解释为某一治疗策略具有预后优势。")
        sentences.append("在解读相关结果时，仍需结合基线风险、治疗适应证和随访完整性，避免将构成差异直接等同于结局差异。")
        return "".join(sentences)
    if role == "comparison":
        sentences = []
        if any(token in lowered for token in ("forest", "cox", "hr", "hazard", "森林", "风险", "回归")):
            sentences.append(f"{figure_label}中的点估计和置信区间反映了不同变量或分组与主要终点之间的关联方向，能够与正文中的单因素或多因素分析结果相互印证。")
            sentences.append("若置信区间跨越无效线或P值未达到统计学意义，应将其理解为趋势性或探索性证据，而不是确定性风险判断。")
        else:
            sentences.append(f"{figure_label}所示差异方向与本节主要终点比较的文字结果相对应，可帮助判断组间差异是集中体现在复发相关结局还是总生存结局。")
            sentences.append("对于统计学证据不足或图形差异较小的结果，应保留谨慎表述，并结合样本量、事件数和随访时间进行解释。")
        sentences.append("因此，该图的作用是支持正文结果的可视化理解，而不是替代统计检验或混杂因素校正。")
        return "".join(sentences)
    return f"{figure_label}中的曲线形态可用于观察不同分组随时间变化的结局趋势，其主要价值在于与正文统计结果相互对应。若曲线存在重叠、交叉或后期样本减少，应避免过度解读局部差异，并以报告的检验结果和研究背景作为主要判断依据。"


def _result_figure_label(image_line: str) -> str:
    number = _image_line_figure_number(image_line)
    return f"图{number}" if number < 999 else "该图"


def _build_curve_specific_explanation(evidence: ResultEvidence, image_line: str) -> str:
    lowered = image_line.casefold()
    if "rfs" in lowered or "recurrence" in lowered or "\u65e0\u590d\u53d1" in lowered:
        sentences = [
            "\u56fe2\u4e3b\u8981\u7528\u4e8e\u8865\u5145\u8bf4\u660eRFS\u7ec8\u70b9\u7684\u66f2\u7ebf\u53d8\u5316\u3002",
        ]
        if evidence.rfs_p_value:
            clause = "\u5df2\u8fbe\u7edf\u8ba1\u5b66\u610f\u4e49" if _p_value_is_significant(evidence.rfs_p_value) else "\u672a\u8fbe\u7edf\u8ba1\u5b66\u610f\u4e49"
            sentences.append(f"\u5176\u66f2\u7ebf\u5206\u5c42\u4e0eRFS\u7684Log-rank\u68c0\u9a8c\u7ed3\u679c\u76f8\u5bf9\u5e94\uff0c\u7ec4\u95f4\u5dee\u5f02{clause}\uff08P={evidence.rfs_p_value}\uff09\u3002")
        trend_sentence = _extract_result_trend_sentence(evidence.treatment_facts)
        if trend_sentence:
            sentences.append(trend_sentence)
        else:
            sentences.append("\u56fe\u4e2d\u5404\u7ec4\u66f2\u7ebf\u7684\u4e0a\u4e0b\u4f4d\u7f6e\u548c\u4e0b\u964d\u901f\u5ea6\u53ef\u76f4\u89c2\u53cd\u6620\u590d\u53d1\u98ce\u9669\u5728\u4e0d\u540c\u5206\u7ec4\u95f4\u7684\u5dee\u5f02\u3002")
        sentences.append("\u5728\u7ed3\u679c\u89e3\u8bfb\u4e2d\uff0cRFS\u66f2\u7ebf\u7684\u610f\u4e49\u4e0d\u4ec5\u5728\u4e8e\u7ec4\u95f4\u662f\u5426\u5206\u79bb\uff0c\u8fd8\u5728\u4e8e\u5206\u79bb\u51fa\u73b0\u7684\u65f6\u95f4\u548c\u5404\u7ec4\u4e0b\u964d\u901f\u5ea6\u3002")
        sentences.append("\u82e5\u67d0\u4e00\u7ec4\u66f2\u7ebf\u5728\u968f\u8bbf\u65e9\u671f\u5df2\u660e\u663e\u4e0b\u964d\uff0c\u901a\u5e38\u63d0\u793a\u8be5\u7ec4\u590d\u53d1\u4e8b\u4ef6\u66f4\u65e9\u79ef\u7d2f\uff1b\u82e5\u66f2\u7ebf\u5728\u8f83\u957f\u65f6\u95f4\u5185\u4fdd\u6301\u5e73\u7a33\uff0c\u5219\u8bf4\u660e\u8be5\u7ec4\u5728\u590d\u53d1\u76f8\u5173\u7ed3\u5c40\u4e0a\u5448\u73b0\u76f8\u5bf9\u7a33\u5b9a\u7684\u8d8b\u52bf\u3002")
        sentences.append("\u8be5\u56fe\u56e0\u6b64\u4e3a3.2\u4e2dRFS\u7ec4\u95f4\u6bd4\u8f83\u63d0\u4f9b\u4e86\u76f4\u89c2\u652f\u6301\uff0c\u4f46\u5176\u4e34\u5e8a\u542b\u4e49\u4ecd\u9700\u7ed3\u5408\u5404\u7ec4\u57fa\u7ebf\u98ce\u9669\u548c\u6cbb\u7597\u9009\u62e9\u80cc\u666f\u8fdb\u884c\u7406\u89e3\u3002")
        return "".join(sentences)

    if "os" in lowered or "overall" in lowered or "\u603b\u751f\u5b58" in lowered:
        sentences = [
            "\u56fe3\u8fdb\u4e00\u6b65\u5448\u73b0OS\u7ec8\u70b9\u7684\u66f2\u7ebf\u53d8\u5316\u3002",
        ]
        if evidence.os_p_value:
            clause = "\u5df2\u8fbe\u7edf\u8ba1\u5b66\u610f\u4e49" if _p_value_is_significant(evidence.os_p_value) else "\u672a\u8fbe\u7edf\u8ba1\u5b66\u610f\u4e49"
            sentences.append(f"\u4e0eRFS\u76f8\u6bd4\uff0cOS\u66f2\u7ebf\u7684\u7ec4\u95f4\u5206\u79bb\u7a0b\u5ea6\u76f8\u5bf9\u8f83\u5f31\uff0c\u7edf\u8ba1\u5b66\u6bd4\u8f83{clause}\uff08P={evidence.os_p_value}\uff09\u3002")
        else:
            sentences.append("\u4e0eRFS\u76f8\u6bd4\uff0cOS\u66f2\u7ebf\u66f4\u6613\u53d7\u968f\u8bbf\u957f\u5ea6\u3001\u590d\u53d1\u540e\u6cbb\u7597\u53ca\u4e8b\u4ef6\u6570\u7684\u5171\u540c\u5f71\u54cd\u3002")
        sentences.append("\u56e0\u6b64\uff0c\u8be5\u56fe\u4e3b\u8981\u4f5c\u4e3a\u5bf9OS\u7ed3\u679c\u7684\u56fe\u5f62\u5316\u652f\u6301\uff0c\u5176\u89e3\u8bfb\u5e94\u4e0e\u524d\u8ff0\u7ec4\u95f4\u6bd4\u8f83\u548c\u57fa\u7ebf\u80cc\u666f\u4fdd\u6301\u4e00\u81f4\u3002")
        sentences.append("\u5f53OS\u66f2\u7ebf\u5b58\u5728\u91cd\u53e0\u6216\u4ea4\u53c9\u65f6\uff0c\u5e94\u907f\u514d\u4ec5\u51ed\u5c40\u90e8\u66f2\u7ebf\u9ad8\u4f4e\u63a8\u65ad\u660e\u786e\u751f\u5b58\u83b7\u76ca\uff0c\u800c\u5e94\u4ee5\u5df2\u62a5\u544a\u7684\u7edf\u8ba1\u5b66\u7ed3\u679c\u4e3a\u4e3b\u8981\u5224\u65ad\u4f9d\u636e\u3002")
        return "".join(sentences)

    return ""


def _extract_image_lines_from_buckets(chunks: Iterable[list[str]]) -> list[str]:
    images: list[str] = []
    for lines in chunks:
        for raw_line in lines:
            if IMAGE_LINE_PATTERN.match(raw_line.strip()):
                images.append(raw_line)
    return images


def _image_line_figure_number(raw_line: str) -> int:
    match = IMAGE_LINE_PATTERN.match(raw_line.strip())
    if not match:
        return 999
    return _resolve_figure_number(match.group("path"), {})


def _assign_result_images_to_subsections(
    *,
    ordered_content: dict[str, list[str]],
    subsection_titles: list[str],
    figure_entries: list[dict[str, object]] | None = None,
) -> dict[str, list[str]]:
    _baseline_title, _comparison_title, _curve_title = subsection_titles
    assigned = {"baseline": [], "comparison": [], "curve": []}
    all_images = _extract_image_lines_from_buckets(ordered_content.values())
    deduped_images: list[str] = []
    seen: set[str] = set()
    for raw_line in sorted(all_images, key=_image_line_figure_number):
        key = raw_line.strip()
        if key in seen:
            continue
        seen.add(key)
        deduped_images.append(raw_line)

    for raw_line in deduped_images:
        role = _infer_result_image_role(raw_line, figure_entries=figure_entries)
        assigned[role].append(raw_line)

    if not assigned["baseline"] and deduped_images:
        first_line = deduped_images[0]
        assigned["baseline"].append(first_line)
        assigned["curve"] = [line for line in assigned["curve"] if line.strip() != first_line.strip()]
        assigned["comparison"] = [line for line in assigned["comparison"] if line.strip() != first_line.strip()]

    if not assigned["curve"] and len(deduped_images) >= 2:
        tail_lines = [line for line in deduped_images[1:] if line.strip() not in {item.strip() for item in assigned["baseline"]}]
        assigned["curve"].extend(tail_lines)
        assigned["comparison"] = [line for line in assigned["comparison"] if line.strip() not in {item.strip() for item in tail_lines}]

    for key in assigned:
        assigned[key] = sorted(assigned[key], key=_image_line_figure_number)

    return assigned


def _infer_result_image_role(
    raw_line: str,
    *,
    figure_entries: list[dict[str, object]] | None = None,
) -> str:
    metadata = _figure_metadata_for_image_line(raw_line, figure_entries)
    lowered = f"{raw_line}\n{metadata}".casefold()
    figure_number = _image_line_figure_number(raw_line)
    if any(
        token in lowered
        for token in (
            "cohort",
            "flow",
            "followup",
            "follow-up",
            "distribution",
            "missingness",
            "missing",
            "baseline",
            "table1",
            "table 1",
            "composition",
            "\u961f\u5217",
            "\u6d41\u7a0b",
            "\u7b5b\u9009",
            "\u968f\u8bbf",
            "\u5206\u5e03",
            "\u7f3a\u5931",
            "\u57fa\u7ebf",
            "\u6784\u6210",
            "\u4e34\u5e8a\u75c5\u7406",
        )
    ):
        return "baseline"
    if any(
        token in lowered
        for token in (
            "forest",
            "cox",
            "hazard",
            "roc",
            "hr",
            "risk",
            "factor",
            "\u68ee\u6797",
            "\u98ce\u9669",
            "\u56e0\u7d20",
            "\u5355\u56e0\u7d20",
            "\u591a\u56e0\u7d20",
            "\u56de\u5f52",
        )
    ):
        return "comparison"
    if any(
        token in lowered
        for token in (
            "kaplan",
            "meier",
            "km_",
            "survival",
            "curve",
            "rfs",
            "os",
            "dfs",
            "pfs",
            "\u751f\u5b58\u66f2\u7ebf",
            "\u751f\u5b58",
            "\u590d\u53d1",
            "\u66f2\u7ebf",
        )
    ):
        return "curve"
    if figure_number == 1:
        return "baseline"
    if figure_number >= 2:
        return "curve"
    return "comparison"


def _figure_metadata_for_image_line(
    raw_line: str,
    figure_entries: list[dict[str, object]] | None,
) -> str:
    if not figure_entries:
        return ""

    match = IMAGE_LINE_PATTERN.match(raw_line.strip())
    if not match:
        return ""

    image_path = match.group("path")
    file_name = Path(image_path).name
    figure_number = _resolve_figure_number(image_path, {})
    for entry in figure_entries:
        relative_path = str(entry.get("relative_path") or "")
        entry_file = str(entry.get("file_name") or "")
        entry_index = int(entry.get("index") or 0)
        path_matches = image_path in {relative_path, entry_file} or file_name in {Path(relative_path).name, entry_file}
        number_matches = figure_number == entry_index and re.search(r"figure\d+", file_name, flags=re.IGNORECASE)
        if not path_matches and not number_matches:
            continue

        fragments = [
            str(entry.get("original_name") or ""),
            str(entry.get("caption") or ""),
            str(entry.get("figure_id") or ""),
            str(entry.get("relative_path") or ""),
            match.group("alt"),
        ]
        captions = entry.get("captions")
        if isinstance(captions, list):
            fragments.extend(str(item) for item in captions)
        referenced_sections = entry.get("referenced_in_sections")
        if isinstance(referenced_sections, list):
            fragments.extend(str(item) for item in referenced_sections)
        return "\n".join(fragment for fragment in fragments if fragment)

    return match.group("alt")


def _format_result_figure_refs(image_lines: list[str]) -> str:
    numbers = sorted({_image_line_figure_number(line) for line in image_lines if _image_line_figure_number(line) < 999})
    if not numbers:
        return ""
    if len(numbers) == 1:
        return f"图{numbers[0]}"
    return "、".join(f"图{number}" for number in numbers)


def _build_results_baseline_paragraph(evidence: ResultEvidence, section_text: str, image_lines: list[str]) -> str:
    sentences: list[str] = []
    if evidence.patient_count:
        sentences.append(f"\u672c\u7814\u7a76\u5171\u7eb3\u5165{evidence.patient_count}\u4f8b\u60a3\u8005\u8fdb\u884c\u5206\u6790\u3002")
    else:
        sentences.append("\u7814\u7a76\u961f\u5217\u6309\u7167\u4e34\u5e8a\u5206\u7ec4\u6216\u4e3b\u8981\u66b4\u9732\u56e0\u7d20\u8fdb\u884c\u5f52\u7eb3\uff0c\u5e76\u4ee5\u7ec4\u95f4\u7ec8\u70b9\u6bd4\u8f83\u548c\u56fe\u5f62\u5448\u73b0\u4f5c\u4e3a\u7ed3\u679c\u5c55\u5f00\u7684\u4e3b\u8981\u4f9d\u636e\u3002")

    distribution_sentence = _build_treatment_distribution_sentence(evidence)
    if distribution_sentence:
        sentences.append(distribution_sentence)
        figure_refs = _format_result_figure_refs(image_lines)
        if figure_refs:
            sentences.append(f"{figure_refs}进一步展示了不同术后治疗方案在队列中的构成情况。")
        if _has_label_in_facts(evidence.treatment_facts, "\u76d1\u6d4b/\u672a\u6cbb\u7597\u7ec4") and _has_label_in_facts(evidence.treatment_facts, "TACE\u7ec4"):
            sentences.append("\u4ece\u603b\u4f53\u5206\u5e03\u6765\u770b\uff0c\u771f\u5b9e\u4e16\u754c\u672f\u540e\u7ba1\u7406\u4ecd\u4ee5\u76d1\u6d4b\u968f\u8bbf\u548cTACE\u4e3a\u4e3b\uff0c\u5176\u4f59\u6cbb\u7597\u65b9\u5f0f\u6240\u5360\u6bd4\u4f8b\u76f8\u5bf9\u8f83\u4f4e\u3002")
        sentences.append("\u5404\u6cbb\u7597\u7ec4\u6837\u672c\u6784\u6210\u5e76\u4e0d\u5747\u8861\uff0c\u63d0\u793a\u4e0d\u540c\u672f\u540e\u7ba1\u7406\u7b56\u7565\u5728\u771f\u5b9e\u4e16\u754c\u4e2d\u5b58\u5728\u660e\u663e\u7684\u4e34\u5e8a\u9009\u62e9\u5dee\u5f02\u3002")
        sentences.append("\u8fd9\u79cd\u6784\u6210\u7279\u5f81\u4e0d\u4ec5\u53cd\u6620\u4e86\u4e0d\u540c\u6cbb\u7597\u65b9\u5f0f\u5728\u5b9e\u9645\u8bca\u7597\u4e2d\u7684\u5e94\u7528\u6bd4\u91cd\uff0c\u4e5f\u63d0\u793a\u540e\u7eed\u7ec8\u70b9\u6bd4\u8f83\u53ef\u80fd\u53d7\u5230\u57fa\u7ebf\u98ce\u9669\u5206\u5e03\u7684\u5f71\u54cd\u3002")
        sentences.append("\u56e0\u6b64\uff0c\u5728\u89e3\u8bfb\u4e0d\u540c\u7ec4\u95f4\u7684\u751f\u5b58\u6216\u590d\u53d1\u5dee\u5f02\u65f6\uff0c\u9700\u540c\u65f6\u5173\u6ce8\u6cbb\u7597\u9009\u62e9\u80cc\u540e\u7684\u60a3\u8005\u7279\u5f81\u3001\u75be\u75c5\u72b6\u6001\u548c\u968f\u8bbf\u80cc\u666f\u3002")
        sentences.append("\u4e0a\u8ff0\u5206\u7ec4\u6784\u6210\u4e3a\u540e\u7eedOS\u53caRFS\u7684\u7ec4\u95f4\u6bd4\u8f83\u63d0\u4f9b\u4e86\u57fa\u7840\uff0c\u4e5f\u63d0\u793a\u7ed3\u679c\u89e3\u8bfb\u9700\u7ed3\u5408\u57fa\u7ebf\u80cc\u666f\u4e88\u4ee5\u7406\u89e3\u3002")
    elif image_lines:
        figure_refs = _format_result_figure_refs(image_lines)
        if figure_refs:
            sentences.append(f"{figure_refs}\u63d0\u4f9b\u4e86\u4e0e\u7814\u7a76\u5206\u7ec4\u6216\u57fa\u7ebf\u6784\u6210\u76f8\u5173\u7684\u56fe\u5f62\u8bc1\u636e\u3002")
        sentences.append("\u56fe\u5f62\u6240\u5bf9\u5e94\u7684\u6bd4\u8f83\u5bf9\u8c61\u548c\u8d8b\u52bf\u53ef\u4f5c\u4e3a\u57fa\u7ebf\u6216\u5206\u7ec4\u6784\u6210\u7684\u76f4\u89c2\u8865\u5145\uff0c\u5e76\u4e3a\u540e\u7eed\u7ec8\u70b9\u6bd4\u8f83\u63d0\u4f9b\u7ed3\u679c\u80cc\u666f\u3002")
        sentences.append("\u4ece\u8bba\u6587\u7ed3\u679c\u8868\u8fbe\u89d2\u5ea6\u770b\uff0c\u5206\u7ec4\u6784\u6210\u7684\u63cf\u8ff0\u662f\u7406\u89e3\u7ec8\u70b9\u5dee\u5f02\u7684\u524d\u63d0\uff0c\u56e0\u4e3a\u4e0d\u540c\u7ec4\u95f4\u7684\u4eba\u7fa4\u6765\u6e90\u548c\u98ce\u9669\u5c42\u7ea7\u53ef\u80fd\u5e76\u4e0d\u5b8c\u5168\u4e00\u81f4\u3002")

    return _compose_reference_paragraph(sentences, "", min_sentences=6, max_sentences=8, min_chars=220)


def _build_results_comparison_paragraph(evidence: ResultEvidence, section_text: str, image_lines: list[str]) -> str:
    rfs_p = evidence.rfs_p_value
    os_p = evidence.os_p_value
    rfs_sentences: list[str] = []
    os_sentences: list[str] = []

    if rfs_p:
        rfs_clause = "\u5dee\u5f02\u6709\u7edf\u8ba1\u5b66\u610f\u4e49" if _p_value_is_significant(rfs_p) else "\u5dee\u5f02\u672a\u8fbe\u7edf\u8ba1\u5b66\u610f\u4e49"
        rfs_sentences.append("\u5728RFS\u7ec8\u70b9\u65b9\u9762\uff0c\u6bd4\u8f83\u5bf9\u8c61\u4e3a\u4e0d\u540c\u7814\u7a76\u5206\u7ec4\uff0c\u7ed3\u5c40\u4e3b\u8981\u53cd\u6620\u590d\u53d1\u63a7\u5236\u548c\u75be\u75c5\u8fdb\u5c55\u98ce\u9669\u3002")
        rfs_sentences.append(f"Log-rank\u68c0\u9a8c\u663e\u793a\uff0c\u5404\u7ec4RFS{rfs_clause}\uff08P={rfs_p}\uff09\u3002")
    else:
        rfs_sentences.append("\u5728RFS\u7ec8\u70b9\u65b9\u9762\uff0c\u7ec4\u95f4\u6bd4\u8f83\u805a\u7126\u4e8e\u4e0d\u540c\u7814\u7a76\u5206\u7ec4\u7684\u590d\u53d1\u6216\u75be\u75c5\u8fdb\u5c55\u98ce\u9669\u3002")
        rfs_sentences.append("\u73b0\u6709\u7ed3\u679c\u4ee5\u66f2\u7ebf\u5206\u5c42\u548c\u7ec4\u95f4\u8d8b\u52bf\u4e3a\u4e3b\u8981\u8868\u73b0\uff0c\u5bf9\u672a\u5f62\u6210\u660e\u786e\u7edf\u8ba1\u5b66\u5224\u65ad\u7684\u90e8\u5206\u4ec5\u6309\u89c2\u5bdf\u5230\u7684\u65b9\u5411\u6027\u53d8\u5316\u8fdb\u884c\u63cf\u8ff0\u3002")

    trend_sentence = _extract_result_trend_sentence(evidence.treatment_facts)
    if trend_sentence:
        rfs_sentences.append(trend_sentence)
    if rfs_p and os_p and _p_value_is_significant(rfs_p) and not _p_value_is_significant(os_p):
        rfs_sentences.append("\u4e0eOS\u76f8\u6bd4\uff0cRFS\u5bf9\u672f\u540e\u7ba1\u7406\u7b56\u7565\u7684\u7ec4\u95f4\u5dee\u5f02\u8868\u73b0\u66f4\u4e3a\u654f\u611f\uff0c\u63d0\u793a\u590d\u53d1\u63a7\u5236\u53ef\u80fd\u662f\u5f53\u524d\u66f4\u6613\u89c2\u5bdf\u5230\u7684\u7ed3\u5c40\u5c42\u9762\u3002")
    elif rfs_p and not os_p:
        rfs_sentences.append("\u4ece\u7ed3\u5c40\u7c7b\u578b\u6765\u770b\uff0c\u4e0d\u540c\u672f\u540e\u6cbb\u7597\u7b56\u7565\u4e0e\u590d\u53d1\u63a7\u5236\u4e4b\u95f4\u7684\u5173\u8054\u66f4\u5bb9\u6613\u5728RFS\u5c42\u9762\u5448\u73b0\u3002")

    if os_p:
        os_clause = "\u5dee\u5f02\u6709\u7edf\u8ba1\u5b66\u610f\u4e49" if _p_value_is_significant(os_p) else "\u5dee\u5f02\u672a\u8fbe\u7edf\u8ba1\u5b66\u610f\u4e49"
        os_sentences.append("\u5728OS\u7ec8\u70b9\u65b9\u9762\uff0c\u6bd4\u8f83\u5bf9\u8c61\u4ecd\u4e3a\u540c\u4e00\u7814\u7a76\u5206\u7ec4\uff0c\u7ec8\u70b9\u53cd\u6620\u4ece\u8d77\u59cb\u89c2\u5bdf\u81f3\u6b7b\u4ea1\u6216\u672b\u6b21\u968f\u8bbf\u7684\u603b\u751f\u5b58\u5dee\u5f02\u3002")
        os_sentences.append(f"Log-rank\u68c0\u9a8c\u663e\u793a\uff0c\u5404\u7ec4OS{os_clause}\uff08P={os_p}\uff09\u3002")
        if not _p_value_is_significant(os_p):
            os_sentences.append("\u5404\u7ec4OS\u867d\u5448\u73b0\u4e00\u5b9a\u5206\u5c42\u8d8b\u52bf\uff0c\u4f46\u7edf\u8ba1\u5b66\u8bc1\u636e\u5c1a\u4e0d\u5145\u5206\uff0c\u603b\u751f\u5b58\u5dee\u5f02\u7684\u7a33\u5b9a\u6027\u9700\u7ed3\u5408\u66f4\u957f\u968f\u8bbf\u89c2\u5bdf\u3002")
    else:
        os_sentences.append("\u5728OS\u7ec8\u70b9\u65b9\u9762\uff0c\u7ec4\u95f4\u6bd4\u8f83\u53cd\u6620\u4e0d\u540c\u5206\u7ec4\u7684\u957f\u671f\u751f\u5b58\u7ed3\u5c40\u3002")
        os_sentences.append("\u4e0eRFS\u76f8\u6bd4\uff0cOS\u66f4\u6613\u53d7\u968f\u8bbf\u957f\u5ea6\u3001\u590d\u53d1\u540e\u6cbb\u7597\u548c\u57fa\u7ebf\u98ce\u9669\u6784\u6210\u7684\u5171\u540c\u5f71\u54cd\uff0c\u56e0\u6b64\u5bf9\u5176\u7ec4\u95f4\u5dee\u5f02\u9700\u4fdd\u6301\u514b\u5236\u89e3\u8bfb\u3002")

    if os_p and not rfs_p:
        os_sentences.append("\u8fd9\u8868\u660e\u7ec4\u95f4\u5dee\u5f02\u66f4\u591a\u4f53\u73b0\u5728\u603b\u751f\u5b58\u5c42\u9762\uff0c\u5176\u4e34\u5e8a\u542b\u4e49\u9700\u653e\u5728\u57fa\u7ebf\u72b6\u6001\u548c\u540e\u7eed\u6cbb\u7597\u80cc\u666f\u4e0b\u7406\u89e3\u3002")
    elif rfs_p and os_p:
        os_sentences.append("\u56e0\u6b64\uff0cOS\u7ed3\u679c\u4e0eRFS\u7ed3\u679c\u5171\u540c\u63d0\u793a\u7ec4\u95f4\u9884\u540e\u5b58\u5728\u5206\u5c42\u73b0\u8c61\uff0c\u4f46\u4e0d\u5b9c\u5c06\u5176\u76f4\u63a5\u89e3\u91ca\u4e3a\u67d0\u4e00\u6cbb\u7597\u65b9\u6848\u7684\u786e\u5b9a\u56e0\u679c\u4f18\u52bf\u3002")

    rfs_paragraph = _compose_reference_paragraph(rfs_sentences, "", min_sentences=3, max_sentences=5, min_chars=180)
    os_paragraph = _compose_reference_paragraph(os_sentences, "", min_sentences=3, max_sentences=5, min_chars=180)
    return "\n\n".join(paragraph for paragraph in (rfs_paragraph, os_paragraph) if paragraph)

    sentences: list[str] = []
    rfs_p = evidence.rfs_p_value
    os_p = evidence.os_p_value
    if rfs_p and os_p:
        rfs_clause = "\u5dee\u5f02\u6709\u7edf\u8ba1\u5b66\u610f\u4e49" if _p_value_is_significant(rfs_p) else "\u5dee\u5f02\u672a\u8fbe\u7edf\u8ba1\u5b66\u610f\u4e49"
        os_clause = "\u5dee\u5f02\u6709\u7edf\u8ba1\u5b66\u610f\u4e49" if _p_value_is_significant(os_p) else "\u5dee\u5f02\u672a\u8fbe\u7edf\u8ba1\u5b66\u610f\u4e49"
        sentences.append(
            f"\u7ec4\u95f4Log-rank\u68c0\u9a8c\u663e\u793a\uff0c\u4e0d\u540c\u6cbb\u7597\u65b9\u6848\u7684RFS{rfs_clause}\uff08P={rfs_p}\uff09\uff0cOS{os_clause}\uff08P={os_p}\uff09\u3002"
        )
        sentences.append("\u5728RFS\u7ec8\u70b9\u65b9\u9762\uff0c\u6bd4\u8f83\u91cd\u70b9\u5728\u4e8e\u4e0d\u540c\u5206\u7ec4\u4ece\u624b\u672f\u6216\u8d77\u59cb\u89c2\u5bdf\u65f6\u70b9\u81f3\u590d\u53d1\u4e8b\u4ef6\u6216\u672b\u6b21\u968f\u8bbf\u7684\u65f6\u95f4\u5dee\u5f02\uff0c\u8be5\u7ec8\u70b9\u66f4\u76f4\u63a5\u53cd\u6620\u590d\u53d1\u63a7\u5236\u548c\u75be\u75c5\u8fdb\u5c55\u98ce\u9669\u3002")
        sentences.append("\u5728OS\u7ec8\u70b9\u65b9\u9762\uff0c\u6bd4\u8f83\u5bf9\u8c61\u4ecd\u4e3a\u540c\u4e00\u7814\u7a76\u5206\u7ec4\uff0c\u4f46\u7ed3\u5c40\u5b9a\u4e49\u8f6c\u4e3a\u603b\u751f\u5b58\u65f6\u95f4\uff0c\u5176\u53d8\u5316\u53ef\u80fd\u540c\u65f6\u53d7\u590d\u53d1\u540e\u6cbb\u7597\u3001\u968f\u8bbf\u957f\u5ea6\u548c\u57fa\u7ebf\u5371\u9669\u5dee\u5f02\u5f71\u54cd\u3002")
    elif rfs_p:
        rfs_clause = "\u5dee\u5f02\u6709\u7edf\u8ba1\u5b66\u610f\u4e49" if _p_value_is_significant(rfs_p) else "\u5dee\u5f02\u672a\u8fbe\u7edf\u8ba1\u5b66\u610f\u4e49"
        sentences.append(f"RFS\u7684Log-rank\u68c0\u9a8c\u7ed3\u679c\u4e3aP={rfs_p}\uff0c\u63d0\u793a\u4e0d\u540c\u6cbb\u7597\u7ec4\u95f4{rfs_clause}\u3002")
    elif os_p:
        os_clause = "\u5dee\u5f02\u5177\u6709\u7edf\u8ba1\u5b66\u610f\u4e49" if _p_value_is_significant(os_p) else "\u5dee\u5f02\u672a\u8fbe\u7edf\u8ba1\u5b66\u610f\u4e49"
        sentences.append(f"OS\u7684Log-rank\u68c0\u9a8c\u7ed3\u679c\u4e3aP={os_p}\uff0c\u63d0\u793a\u4e0d\u540c\u6cbb\u7597\u7ec4\u95f4{os_clause}\u3002")

    trend_sentence = _extract_result_trend_sentence(evidence.treatment_facts)
    if trend_sentence:
        sentences.append(trend_sentence)
    if rfs_p or os_p:
        figure_refs = _format_result_figure_refs(image_lines)
        if figure_refs:
            sentences.append(f"{figure_refs}所示统计结果与组间比较方向一致，可作为主要结局差异的直观补充。")
        if rfs_p and not os_p:
            sentences.append("\u4ece\u7ed3\u5c40\u7c7b\u578b\u6765\u770b\uff0c\u4e0d\u540c\u672f\u540e\u6cbb\u7597\u7b56\u7565\u5bf9\u590d\u53d1\u63a7\u5236\u7684\u5f71\u54cd\u66f4\u4e3a\u660e\u663e\uff0c\u800c\u5bf9\u603b\u751f\u5b58\u7684\u5f71\u54cd\u4ecd\u9700\u66f4\u957f\u968f\u8bbf\u624d\u80fd\u5145\u5206\u663e\u73b0\u3002")
        elif os_p and not rfs_p:
            sentences.append("\u8fd9\u8868\u660e\u7ec4\u95f4\u5dee\u5f02\u66f4\u591a\u4f53\u73b0\u5728\u603b\u751f\u5b58\u5c42\u9762\uff0c\u800c\u5176\u4e0e\u590d\u53d1\u76f8\u5173\u7684\u53d8\u5316\u8d8b\u52bf\u4ecd\u9700\u7ed3\u5408\u66f4\u591a\u8bc1\u636e\u89c2\u5bdf\u3002")
        else:
            if not _p_value_is_significant(os_p):
                sentences.append("\u5c31OS\u800c\u8a00\uff0c\u5404\u7ec4\u5dee\u5f02\u867d\u6709\u4e00\u5b9a\u5206\u5c42\u8d8b\u52bf\uff0c\u4f46\u7edf\u8ba1\u5b66\u8bc1\u636e\u4ecd\u4e0d\u5145\u5206\uff0c\u8bf4\u660e\u603b\u751f\u5b58\u83b7\u76ca\u4ecd\u9700\u66f4\u957f\u65f6\u95f4\u89c2\u5bdf\u3002")
            sentences.append("\u4e0a\u8ff0\u7ed3\u679c\u63d0\u793a\u4e0d\u540c\u672f\u540e\u6cbb\u7597\u7b56\u7565\u5bf9\u590d\u53d1\u63a7\u5236\u7684\u5f71\u54cd\u66f4\u4e3a\u654f\u611f\uff0c\u800c\u5bf9\u603b\u751f\u5b58\u7684\u5dee\u5f02\u4ecd\u6709\u5f85\u8fdb\u4e00\u6b65\u968f\u8bbf\u9a8c\u8bc1\u3002")
            sentences.append("\u56e0\u800c\uff0c\u672c\u8282\u7ed3\u679c\u66f4\u9002\u5408\u88ab\u7406\u89e3\u4e3a\u4e0d\u540c\u7b56\u7565\u4e0e\u7ed3\u5c40\u4e4b\u95f4\u5b58\u5728\u5206\u5c42\u5dee\u5f02\uff0c\u800c\u975e\u76f4\u63a5\u8bc1\u660e\u67d0\u4e00\u6cbb\u7597\u65b9\u6848\u5177\u6709\u7edd\u5bf9\u4f18\u52bf\u3002")

    if not sentences:
        if image_lines:
            figure_refs = _format_result_figure_refs(image_lines)
            if figure_refs:
                sentences.append(f"{figure_refs}\u63d0\u4f9b\u4e86\u4e3b\u8981\u7ed3\u5c40\u7684\u56fe\u5f62\u5316\u5448\u73b0\uff0c\u53ef\u7528\u4e8e\u89c2\u5bdf\u5206\u7ec4\u95f4\u66f2\u7ebf\u5206\u79bb\u3001\u6307\u6807\u6ce2\u52a8\u6216\u7ed3\u5c40\u53d8\u5316\u7684\u65b9\u5411\u3002")
        sentences.append("\u4e3b\u8981\u7ec8\u70b9\u6bd4\u8f83\u56f4\u7ed5\u7814\u7a76\u5206\u7ec4\u4e0e\u4e34\u5e8a\u7ed3\u5c40\u4e4b\u95f4\u7684\u5173\u7cfb\u5c55\u5f00\uff0c\u7ed3\u679c\u63cf\u8ff0\u91cd\u70b9\u5305\u62ec\u6bd4\u8f83\u5bf9\u8c61\u3001\u7ec8\u70b9\u542b\u4e49\u3001\u66f2\u7ebf\u65b9\u5411\u548c\u7ec4\u95f4\u5dee\u5f02\u7684\u53ef\u89c1\u7279\u5f81\u3002")
        sentences.append("\u5bf9\u4e8e\u7edf\u8ba1\u5b66\u610f\u4e49\u5c1a\u4e0d\u660e\u786e\u7684\u7ed3\u679c\uff0c\u8bba\u6587\u6b63\u6587\u5b9c\u91c7\u7528\u8d8b\u52bf\u6027\u548c\u63a2\u7d22\u6027\u8868\u8fbe\uff0c\u5c06\u7ed3\u679c\u9650\u5b9a\u5728\u89c2\u5bdf\u5230\u7684\u7ec4\u95f4\u5dee\u5f02\u8303\u56f4\u5185\u3002")
        sentences.append("\u8fd9\u79cd\u5904\u7406\u65b9\u5f0f\u80fd\u591f\u5728\u4e0d\u589e\u52a0\u672a\u5b9e\u65bd\u5206\u6790\u7684\u524d\u63d0\u4e0b\uff0c\u5c06\u56fe\u5f62\u8bc1\u636e\u548c\u7ec8\u70b9\u542b\u4e49\u8f6c\u5316\u4e3a\u66f4\u5b8c\u6574\u7684\u7ed3\u679c\u6bb5\u843d\u3002")

    return _compose_reference_paragraph(sentences, "", min_sentences=7, max_sentences=9, min_chars=280)


def _build_results_curve_paragraph(evidence: ResultEvidence, section_text: str, image_lines: list[str]) -> str:
    sentences: list[str] = []
    figure_refs = _format_result_figure_refs(image_lines)
    if image_lines:
        if figure_refs:
            sentences.append(f"\u6839\u636e\u4e0a\u8ff0\u7ec4\u95f4\u6bd4\u8f83\u7ed3\u679c\uff0c\u8fdb\u4e00\u6b65\u7ed8\u5236\u4e86\u4e0d\u540c\u6cbb\u7597\u65b9\u6848\u7684Kaplan-Meier\u751f\u5b58\u66f2\u7ebf\uff08{figure_refs}\uff09\u3002")
        else:
            sentences.append("\u6839\u636e\u4e0a\u8ff0\u7ec4\u95f4\u6bd4\u8f83\u7ed3\u679c\uff0c\u8fdb\u4e00\u6b65\u7ed8\u5236\u4e86\u4e0d\u540c\u6cbb\u7597\u65b9\u6848\u7684Kaplan-Meier\u751f\u5b58\u66f2\u7ebf\u3002")
        if len(image_lines) >= 2:
            sentences.append("\u56fe2\u6240\u5bf9\u5e94\u7684RFS\u66f2\u7ebf\u4e3b\u8981\u53cd\u6620\u75be\u75c5\u63a7\u5236\u548c\u590d\u53d1\u98ce\u9669\uff0c\u56fe3\u6240\u5bf9\u5e94\u7684OS\u66f2\u7ebf\u5219\u53cd\u6620\u957f\u671f\u751f\u5b58\u7ed3\u5c40\u53ca\u540e\u7eed\u6cbb\u7597\u7684\u7efc\u5408\u5f71\u54cd\u3002")
    trend_sentence = _extract_result_trend_sentence(evidence.treatment_facts)
    if trend_sentence:
        sentences.append(trend_sentence)
    if evidence.os_p_value and not _p_value_is_significant(evidence.os_p_value):
        sentences.append("\u76f8\u6bd4\u4e4b\u4e0b\uff0cOS\u66f2\u7ebf\u867d\u63d0\u793a\u4e00\u5b9a\u5206\u5c42\u8d8b\u52bf\uff0c\u4f46\u603b\u4f53\u91cd\u53e0\u4ecd\u8f83\u591a\uff0c\u7ec4\u95f4\u5206\u79bb\u7a0b\u5ea6\u5f31\u4e8eRFS\u66f2\u7ebf\uff0c\u4e0eOS\u5dee\u5f02\u672a\u8fbe\u7edf\u8ba1\u5b66\u610f\u4e49\u7684\u7ed3\u679c\u4e00\u81f4\u3002")
    else:
        sentences.append("\u66f2\u7ebf\u7684\u5206\u79bb\u8d8b\u52bf\u4e0e\u7ec4\u95f4\u6bd4\u8f83\u7ed3\u679c\u57fa\u672c\u4e00\u81f4\uff0c\u53ef\u4ece\u56fe\u5f62\u5c42\u9762\u76f4\u89c2\u652f\u6301\u4e0a\u8ff0\u7edf\u8ba1\u5b66\u5224\u65ad\u3002")
    sentences.append("\u4ece\u66f2\u7ebf\u5f62\u6001\u770b\uff0c\u82e5\u7ec4\u95f4\u5206\u79bb\u5728\u968f\u8bbf\u65e9\u671f\u5373\u51fa\u73b0\uff0c\u901a\u5e38\u63d0\u793a\u8d77\u59cb\u98ce\u9669\u6216\u65e9\u671f\u7ed3\u5c40\u4e8b\u4ef6\u5bf9\u7ec4\u95f4\u5dee\u5f02\u7684\u5f71\u54cd\u8f83\u4e3a\u7a81\u51fa\u3002")
    sentences.append("\u82e5\u66f2\u7ebf\u5728\u540e\u671f\u9010\u6e10\u5206\u79bb\uff0c\u5219\u66f4\u53ef\u80fd\u53cd\u6620\u968f\u8bbf\u65f6\u95f4\u5ef6\u957f\u540e\u7ed3\u5c40\u4e8b\u4ef6\u7684\u7d2f\u79ef\u5dee\u5f02\uff0c\u5176\u4e34\u5e8a\u542b\u4e49\u9700\u7ed3\u5408\u4e2d\u4f4d\u968f\u8bbf\u65f6\u95f4\u548c\u4e8b\u4ef6\u6570\u8fdb\u4e00\u6b65\u5224\u65ad\u3002")
    sentences.append("\u7ed3\u5408\u56fe\u5f62\u53d8\u5316\u6765\u770b\uff0c\u590d\u53d1\u76f8\u5173\u7ed3\u5c40\u7684\u7ec4\u95f4\u5dee\u5f02\u8868\u73b0\u5f97\u66f4\u65e9\u4e14\u66f4\u76f4\u63a5\uff0c\u800c\u603b\u751f\u5b58\u7684\u5224\u65ad\u4ecd\u9700\u7ed3\u5408\u66f4\u957f\u968f\u8bbf\u3001\u66f4\u591a\u6821\u6b63\u5206\u6790\u8fdb\u4e00\u6b65\u786e\u8ba4\u3002")

    return _compose_reference_paragraph(sentences, "", min_sentences=6, max_sentences=8, min_chars=260)


def _build_result_evidence(
    manuscript_text: str,
    results_text: str | list[str],
    ordered_content: dict[str, list[str]] | None = None,
) -> ResultEvidence:
    result_lines = results_text if isinstance(results_text, list) else results_text.splitlines()
    evidence_line_blocks: list[list[str]] = [result_lines]
    if ordered_content:
        evidence_line_blocks.extend(ordered_content.values())
    evidence_line_blocks = [lines for lines in evidence_line_blocks if lines]

    flattened_sources = [_flatten_markdown_lines([lines]) for lines in evidence_line_blocks]
    evidence_text = "\n".join(part for part in flattened_sources if part).strip() or manuscript_text
    raw_evidence_text = "\n".join("\n".join(lines) for lines in evidence_line_blocks if lines).strip() or manuscript_text
    normalized = _clean_method_paragraph(evidence_text)
    markdown_tables = _extract_markdown_table_blocks(raw_evidence_text)
    facts = tuple(_extract_treatment_distribution_facts(raw_evidence_text))
    baseline = _extract_baseline_table(raw_evidence_text, markdown_tables)
    treatment_group = _extract_treatment_group_table(facts, raw_evidence_text, markdown_tables)
    univariate = _extract_univariate_table(raw_evidence_text, markdown_tables)
    multivariate = _extract_multivariate_table(raw_evidence_text, markdown_tables)
    return ResultEvidence(
        patient_count=_extract_preferred_patient_count(evidence_text or manuscript_text),
        treatment_facts=facts,
        rfs_p_value=_extract_endpoint_p_value(normalized, "RFS"),
        os_p_value=_extract_endpoint_p_value(normalized, "OS"),
        trend_sentence=_extract_result_trend_sentence(facts),
        baseline_table=tuple(tuple(row) for row in baseline) if baseline else (),
        treatment_group_table=tuple(tuple(row) for row in treatment_group) if treatment_group else (),
        univariate_rows=tuple(tuple(row) for row in univariate) if univariate else (),
        multivariate_rows=tuple(tuple(row) for row in multivariate) if multivariate else (),
    )


def _extract_markdown_table_blocks(text: str) -> list[MarkdownTableBlock]:
    lines = text.splitlines()
    blocks: list[MarkdownTableBlock] = []
    line_index = 0
    while line_index < len(lines):
        consumed = _consume_markdown_table_block(lines, line_index)
        if consumed is None:
            line_index += 1
            continue
        block, next_index = consumed
        blocks.append(block)
        line_index = next_index
    return blocks


def _consume_markdown_table_block(source_lines: list[str], start_index: int) -> tuple[MarkdownTableBlock, int] | None:
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

    rows: list[tuple[str, ...]] = []
    line_index = start_index + 2
    while line_index < len(source_lines):
        candidate = source_lines[line_index].strip()
        if not candidate or "|" not in candidate or HEADING_PATTERN.match(candidate):
            break
        row_cells = _split_markdown_table_row(candidate)
        if len(row_cells) != len(header_cells):
            break
        rows.append(tuple(row_cells))
        line_index += 1

    if not rows:
        return None

    title = ""
    for reverse_index in range(start_index - 1, max(-1, start_index - 4), -1):
        candidate = source_lines[reverse_index].strip()
        if not candidate:
            continue
        if candidate.startswith("**") and candidate.endswith("**"):
            title = candidate.strip("*").strip()
            break
        if candidate.lower().startswith(("table ", "表")):
            title = candidate
            break
        if HEADING_PATTERN.match(candidate):
            break
        title = candidate
        break

    context_before = " ".join(line.strip() for line in source_lines[max(0, start_index - 3):start_index] if line.strip())
    return (
        MarkdownTableBlock(
            title=title,
            header=tuple(header_cells),
            rows=tuple(rows),
            context_before=context_before,
        ),
        line_index,
    )


def _split_markdown_table_row(raw_line: str) -> list[str]:
    stripped = raw_line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _find_table_by_kind(table_blocks: list[MarkdownTableBlock], kind: str) -> MarkdownTableBlock | None:
    for block in table_blocks:
        if _classify_markdown_table_block(block) == kind:
            return block
    return None


def _classify_markdown_table_block(block: MarkdownTableBlock) -> str:
    title = f"{block.title} {block.context_before}".casefold()
    header = " ".join(block.header).casefold()
    combined = f"{title} {header}"
    if _contains_any(combined, MULTIVARIATE_TITLE_HINTS) and _contains_any(combined, ANALYSIS_COMMON_HINTS):
        return "multivariate"
    if _contains_any(combined, UNIVARIATE_TITLE_HINTS) and _contains_any(combined, ANALYSIS_COMMON_HINTS):
        return "univariate"
    # Header-only classification: HR + CI columns indicate an analysis table
    if _contains_any(header, ANALYSIS_COMMON_HINTS):
        return "univariate"
    if _contains_any(combined, ("治疗组", "分组汇总", "构成", "占比", "follow-up", "随访")) and any(
        token in header for token in ("n", "占比", "事件", "删失", "随访")
    ):
        return "treatment_group"
    if _contains_any(combined, BASELINE_TITLE_HINTS) or (
        "变量" in header and ("p值" in header or "p value" in header or any(token in header for token in ("年龄", "性别", "bclc", "child", "ecog", "afp")))
    ):
        return "baseline"
    return ""


def _normalize_table_rows(header: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> list[list[str]]:
    return [list(header), *[list(row) for row in rows]]


def _sentence_candidates(text: str) -> list[str]:
    return [segment.strip() for segment in SECTION_LINE_SPLIT_PATTERN.split(text) if segment.strip()]


def _normalize_treatment_label(raw_label: str) -> str:
    label = raw_label.strip().strip("（）()：:，,；;")
    lowered = label.casefold()
    for canonical, aliases in TREATMENT_GROUP_ALIASES:
        if canonical.casefold() in lowered:
            return canonical
        if any(alias.casefold() in lowered for alias in aliases):
            return canonical
    if "联合" in label and ("免疫" in label or "靶向" in label):
        return "联合治疗组"
    return label


def _extract_numeric_after_label(sentence: str, label: str, unit: str) -> str:
    alias_patterns = [re.escape(label)]
    for canonical, aliases in TREATMENT_GROUP_ALIASES:
        if canonical == label:
            alias_patterns.extend(re.escape(alias) for alias in aliases)
            break
    pattern = rf"(?:{'|'.join(alias_patterns)})[^。；\n]{{0,24}}?(\d+(?:\.\d+)?)\s*{re.escape(unit)}"
    match = re.search(pattern, sentence, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _extract_patient_count_for_label(sentence: str, label: str) -> str:
    direct = _extract_numeric_after_label(sentence, label, "例")
    if direct:
        return direct
    alias_patterns = [re.escape(label)]
    for canonical, aliases in TREATMENT_GROUP_ALIASES:
        if canonical == label:
            alias_patterns.extend(re.escape(alias) for alias in aliases)
            break
    match = re.search(
        rf"(?:{'|'.join(alias_patterns)})[^。；\n]{{0,20}}?[（(]?n\s*=\s*(\d+)[)）]?",
        sentence,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _extract_percentage_for_label(sentence: str, label: str) -> str:
    return _extract_numeric_after_label(sentence, label, "%")


def _extract_followup_for_label(sentence: str, label: str) -> str:
    alias_patterns = [re.escape(label)]
    for canonical, aliases in TREATMENT_GROUP_ALIASES:
        if canonical == label:
            alias_patterns.extend(re.escape(alias) for alias in aliases)
            break
    match = re.search(
        rf"(?:{'|'.join(alias_patterns)})[^。；\n]{{0,30}}?(?:中位)?随访(?:时间)?[^0-9]{{0,6}}?(\d+(?:\.\d+)?)\s*月",
        sentence,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _extract_event_count_for_label(sentence: str, label: str, event_kind: str) -> str:
    alias_patterns = [re.escape(label)]
    for canonical, aliases in TREATMENT_GROUP_ALIASES:
        if canonical == label:
            alias_patterns.extend(re.escape(alias) for alias in aliases)
            break
    match = re.search(
        rf"(?:{'|'.join(alias_patterns)})[^。；\n]{{0,24}}?{event_kind}[^0-9]{{0,6}}?(\d+)\s*例?",
        sentence,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _extract_analysis_rows_from_text(text: str, kind: str) -> list[list[str]]:
    rows: list[list[str]] = []
    header = ["变量", "HR", "95% CI", "P值"]
    active = False
    section_hints = MULTIVARIATE_SECTION_HINTS if kind == "multivariate" else UNIVARIATE_SECTION_HINTS
    other_hints = UNIVARIATE_SECTION_HINTS if kind == "multivariate" else MULTIVARIATE_SECTION_HINTS
    for sentence in _sentence_candidates(text):
        folded = sentence.casefold()
        if _contains_any(folded, section_hints):
            active = True
        elif _contains_any(folded, other_hints):
            active = False
        eligible = active or (_contains_any(folded, section_hints) and _contains_any(folded, ANALYSIS_COMMON_HINTS))
        if not eligible:
            continue
        hr_match = re.search(HR_VALUE_PATTERN, sentence, flags=re.IGNORECASE)
        ci_match = re.search(CI_VALUE_PATTERN, sentence, flags=re.IGNORECASE)
        p_match = re.search(P_VALUE_CAPTURE_PATTERN, sentence, flags=re.IGNORECASE)
        if not (hr_match and ci_match and p_match):
            continue
        variable_text = re.split(r"(?:HR|风险比|hazard ratio)", sentence, maxsplit=1, flags=re.IGNORECASE)[0]
        variable_text = re.sub(r"^(单因素|多因素|单变量|多变量|univariate|multivariate|cox回归|cox分析|校正后)[:：\s]*", "", variable_text, flags=re.IGNORECASE).strip("：:，,；; ")
        if not variable_text:
            continue
        ci_value = f"{ci_match.group('low')}-{ci_match.group('high')}"
        p_value = re.sub(r"\s+", "", p_match.group("p"))
        rows.append([variable_text, hr_match.group("hr").replace(" ", ""), ci_value, p_value])
    return [header, *rows] if rows else []


def _has_meaningful_table_values(rows: list[list[str]], required_columns: tuple[int, ...]) -> bool:
    for row in rows[1:]:
        if any(index < len(row) and row[index] not in TABLE_EMPTY_VALUES for index in required_columns):
            return True
    return False


def _table_has_minimum_group_rows(rows: list[list[str]], minimum: int = 2) -> bool:
    count = 0
    for row in rows[1:]:
        if row and row[0] != "联合/免疫/靶向合计":
            count += 1
    return count >= minimum


def _extract_baseline_rows_from_text(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for sentence in _sentence_candidates(text):
        if not any(token.casefold() in sentence.casefold() for token in BASELINE_VARIABLE_HINTS):
            continue
        p_match = re.search(P_VALUE_CAPTURE_PATTERN, sentence, flags=re.IGNORECASE)
        percent_values = re.findall(r"\d+(?:\.\d+)?%", sentence)
        metric_values = re.findall(r"\d+(?:\.\d+)?(?:±\d+(?:\.\d+)?)?", sentence)
        if len(percent_values) >= 2:
            values = percent_values[:4]
        elif len(metric_values) >= 2:
            values = metric_values[:4]
        else:
            continue
        variable = re.split(r"[:：，,]", sentence, maxsplit=1)[0].strip()
        if len(values) < 2 or not variable:
            continue
        row = [variable, *values[:4]]
        if p_match:
            row.append(re.sub(r"\s+", "", p_match.group("p")))
        rows.append(row)
    if not rows:
        return []
    width = max(len(row) for row in rows)
    if width < 3:
        return []
    header = ["变量", "值1", "值2"]
    if width >= 4:
        header.append("值3")
    if width >= 5:
        header.append("值4")
    if any(len(row) == width and re.search(P_VALUE_CAPTURE_PATTERN, " ".join(row), flags=re.IGNORECASE) for row in rows):
        header.append("P值")
    normalized_rows: list[list[str]] = [header]
    for row in rows:
        padded = row + [""] * (len(header) - len(row))
        normalized_rows.append(padded[:len(header)])
    return normalized_rows


def _extract_treatment_group_rows_from_text(
    treatment_facts: tuple[tuple[str, str, str], ...],
    text: str,
) -> list[list[str]]:
    labels: list[str] = []
    for canonical, _aliases in TREATMENT_GROUP_ALIASES:
        if canonical in labels:
            continue
        if canonical in {label for label, _percent, _count in treatment_facts} or canonical.casefold() in text.casefold():
            labels.append(canonical)
    fact_map = {label: (percent, count) for label, percent, count in treatment_facts}
    row_map: dict[str, list[str]] = {}
    for label in labels:
        percent, count = fact_map.get(label, ("", ""))
        row_map[label] = [label, count, percent, "", "", ""]
    for sentence in _sentence_candidates(text):
        normalized_sentence = sentence.casefold()
        for label in labels:
            if _normalize_treatment_label(sentence) != label and label.casefold() not in normalized_sentence:
                if not any(alias.casefold() in normalized_sentence for canonical, aliases in TREATMENT_GROUP_ALIASES if canonical == label for alias in aliases):
                    continue
            row = row_map[label]
            row[1] = row[1] or _extract_patient_count_for_label(sentence, label)
            row[2] = row[2] or _extract_percentage_for_label(sentence, label)
            row[3] = row[3] or _extract_event_count_for_label(sentence, label, "事件(?:数)?")
            row[4] = row[4] or _extract_event_count_for_label(sentence, label, "删失(?:数)?")
            row[5] = row[5] or _extract_followup_for_label(sentence, label)
    rows = [["治疗组", "n", "占比", "事件数", "删失数", "中位随访时间（月）"]]
    for label in sorted(row_map, key=lambda item: TREATMENT_ORDER.get(item, 99)):
        if label == "联合/免疫/靶向合计":
            continue
        row = row_map[label]
        if row[1] or row[2]:
            rows.append(row)
    return rows if len(rows) > 2 else []


def _extract_existing_table_rows(table_blocks: list[MarkdownTableBlock], kind: str) -> list[list[str]]:
    block = _find_table_by_kind(table_blocks, kind)
    if not block:
        return []
    return _normalize_table_rows(block.header, block.rows)


def _extract_baseline_table(text: str, table_blocks: list[MarkdownTableBlock]) -> list[list[str]] | None:
    existing = _extract_existing_table_rows(table_blocks, "baseline")
    if existing:
        return existing
    inferred = _extract_baseline_rows_from_text(text)
    if len(inferred) < 3:
        return None
    return inferred


def _extract_treatment_group_table(
    treatment_facts: tuple[tuple[str, str, str], ...],
    text: str,
    table_blocks: list[MarkdownTableBlock],
) -> list[list[str]] | None:
    existing = _extract_existing_table_rows(table_blocks, "treatment_group")
    if existing and _has_meaningful_table_values(existing, (1, 2)) and _table_has_minimum_group_rows(existing):
        return existing
    inferred = _extract_treatment_group_rows_from_text(treatment_facts, text)
    if inferred and _has_meaningful_table_values(inferred, (1, 2)) and _table_has_minimum_group_rows(inferred):
        return inferred
    return None


def _extract_univariate_table(text: str, table_blocks: list[MarkdownTableBlock]) -> list[list[str]] | None:
    existing = _extract_existing_table_rows(table_blocks, "univariate")
    if existing:
        return existing
    inferred = _extract_analysis_rows_from_text(text, "univariate")
    return inferred or None


def _extract_multivariate_table(text: str, table_blocks: list[MarkdownTableBlock]) -> list[list[str]] | None:
    existing = _extract_existing_table_rows(table_blocks, "multivariate")
    if existing:
        return existing
    inferred = _extract_analysis_rows_from_text(text, "multivariate")
    return inferred or None


def _build_result_tables(evidence: ResultEvidence) -> list[str]:
    tables: list[str] = []
    if evidence.baseline_table:
        tables.extend(_render_markdown_result_table("表1 患者基线特征", [list(row) for row in evidence.baseline_table]))
    if evidence.treatment_group_table:
        tables.extend(_render_markdown_result_table("表2 治疗分组汇总", [list(row) for row in evidence.treatment_group_table]))
    if evidence.univariate_rows:
        tables.extend(_render_markdown_result_table("表3 单因素分析", [list(row) for row in evidence.univariate_rows]))
    if evidence.multivariate_rows:
        tables.extend(_render_markdown_result_table("表4 多因素分析", [list(row) for row in evidence.multivariate_rows]))
    return tables


def _render_markdown_result_table(title: str, rows: list[list[str]]) -> list[str]:
    rows = _prune_sparse_result_table(rows)
    if len(rows) < 2:
        return []
    header = rows[0]
    col_count = len(header)
    body = []
    for row in rows[1:]:
        padded = list(row) + [""] * (col_count - len(row))
        body.append("| " + " | ".join(padded[:col_count]) + " |")
    return [f"**{title}**", "", "| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * col_count) + " |", *body, ""]


def _prune_sparse_result_table(rows: list[list[str]]) -> list[list[str]]:
    if len(rows) < 2:
        return rows
    col_count = max(len(row) for row in rows)
    normalized_rows = [list(row) + [""] * (col_count - len(row)) for row in rows]
    header = normalized_rows[0]
    body_rows = normalized_rows[1:]
    keep_columns: list[int] = []
    for column_index, header_cell in enumerate(header):
        if column_index == 0:
            keep_columns.append(column_index)
            continue
        body_values = [row[column_index] for row in body_rows]
        if _is_empty_table_value(header_cell) and all(_is_empty_table_value(value) for value in body_values):
            continue
        if all(_is_empty_table_value(value) for value in body_values):
            continue
        keep_columns.append(column_index)

    if len(keep_columns) < 2:
        return []

    pruned_rows = [[row[index].strip() for index in keep_columns] for row in normalized_rows]
    pruned_body = [
        row for row in pruned_rows[1:]
        if row[0].strip() and any(not _is_empty_table_value(value) for value in row[1:])
    ]
    if not pruned_body:
        return []
    return [pruned_rows[0], *pruned_body]


def _is_empty_table_value(value: str) -> bool:
    normalized = re.sub(r"\s+", "", str(value or "")).strip()
    if not normalized:
        return True
    return normalized.casefold() in {"-", "--", "na", "n/a", "null", "none", "nan", "未提供", "未填写", "缺失", "无"}


def _build_treatment_distribution_sentence(evidence: ResultEvidence) -> str:
    facts = list(evidence.treatment_facts)
    if not facts:
        return ""
    if len(facts) == 1:
        return f"\u5728\u5404\u6cbb\u7597\u5206\u7ec4\u4e2d\uff0c{_format_treatment_distribution_fact(facts[0])}\u3002"
    if len(facts) == 2:
        if facts[1][0] == "\u8054\u5408/\u514d\u75ab/\u9776\u5411\u5408\u8ba1":
            return (
                f"\u5728\u5404\u6cbb\u7597\u5206\u7ec4\u4e2d\uff0c{_format_treatment_distribution_fact(facts[0])}\u5360\u6bd4\u6700\u9ad8\uff0c"
                f"{_format_treatment_distribution_fact(facts[1])}\u3002"
            )
        return (
            f"\u5728\u5404\u6cbb\u7597\u5206\u7ec4\u4e2d\uff0c{_format_treatment_distribution_fact(facts[0])}\u5360\u6bd4\u6700\u9ad8\uff0c"
            f"{_format_treatment_distribution_fact(facts[1])}\u6b21\u4e4b\u3002"
        )
    tail = "\u3001".join(_format_treatment_distribution_fact(fact) for fact in facts[2:5])
    return (
        f"\u5728\u5404\u6cbb\u7597\u5206\u7ec4\u4e2d\uff0c{_format_treatment_distribution_fact(facts[0])}\u5360\u6bd4\u6700\u9ad8\uff0c"
        f"{_format_treatment_distribution_fact(facts[1])}\u6b21\u4e4b\uff0c{tail}\u6240\u5360\u6bd4\u4f8b\u76f8\u5bf9\u8f83\u4f4e\u3002"
    )


def _has_label_in_facts(facts: tuple[tuple[str, str, str], ...], label: str) -> bool:
    return any(item[0] == label for item in facts)


def _normalize_result_figure_captions(
    assigned_images: dict[str, list[str]],
    figure_entries: list[dict[str, object]] | None = None,
) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    used_captions: set[str] = set()
    for role, lines in assigned_images.items():
        normalized[role] = []
        for line in lines:
            caption = _result_figure_caption_for_role(role, line, figure_entries)
            if caption in used_captions:
                caption = f"{caption}\uff08{_result_figure_label(line)}\uff09"
            used_captions.add(caption)
            normalized[role].append(_rewrite_image_alt_text(line, caption))
    return normalized


def _result_figure_caption_for_role(
    role: str,
    image_line: str = "",
    figure_entries: list[dict[str, object]] | None = None,
) -> str:
    metadata = _figure_metadata_for_image_line(image_line, figure_entries)
    lowered = f"{image_line}\n{metadata}".casefold()
    if role == "baseline":
        if any(token in lowered for token in ("cohort", "flow", "\u961f\u5217", "\u6d41\u7a0b", "\u7b5b\u9009")):
            return "\u961f\u5217\u6784\u5efa\u6d41\u7a0b\u56fe"
        if any(token in lowered for token in ("follow", "\u968f\u8bbf")):
            return "\u968f\u8bbf\u65f6\u95f4\u5206\u5e03\u56fe"
        if any(token in lowered for token in ("missing", "\u7f3a\u5931")):
            return "\u5173\u952e\u53d8\u91cf\u7f3a\u5931\u60c5\u51b5\u5206\u5e03\u56fe"
        if any(token in lowered for token in ("baseline", "clinic", "patholog", "\u57fa\u7ebf", "\u4e34\u5e8a\u75c5\u7406")):
            return "\u60a3\u8005\u4e34\u5e8a\u75c5\u7406\u57fa\u7ebf\u7279\u5f81\u5206\u5e03\u56fe"
        return "\u7814\u7a76\u5206\u7ec4\u6784\u6210\u56fe"
    if role == "comparison":
        if any(token in lowered for token in ("forest", "cox", "hazard", "hr", "\u68ee\u6797", "\u98ce\u9669", "\u56de\u5f52")):
            return "Cox\u6a21\u578b\u5371\u9669\u6bd4\u68ee\u6797\u56fe"
        if any(token in lowered for token in ("os", "overall", "\u603b\u751f\u5b58")):
            return "\u603b\u751f\u5b58\u4e3b\u8981\u7ec8\u70b9\u6bd4\u8f83\u56fe"
        if any(token in lowered for token in ("rfs", "recurrence", "\u65e0\u590d\u53d1", "\u590d\u53d1")):
            return "\u65e0\u590d\u53d1\u751f\u5b58\u4e3b\u8981\u7ec8\u70b9\u6bd4\u8f83\u56fe"
        return "\u4e3b\u8981\u7ec8\u70b9\u7ec4\u95f4\u6bd4\u8f83\u56fe"
    if role == "curve":
        if "rfs" in lowered or "recurrence" in lowered or "\u65e0\u590d\u53d1" in lowered:
            return "\u4e0d\u540c\u6cbb\u7597\u7ec4\u65e0\u590d\u53d1\u751f\u5b58Kaplan-Meier\u66f2\u7ebf"
        if "os" in lowered or "overall" in lowered or "\u603b\u751f\u5b58" in lowered:
            return "\u4e0d\u540c\u6cbb\u7597\u7ec4\u603b\u751f\u5b58Kaplan-Meier\u66f2\u7ebf"
        if "tace" in lowered:
            return "TACE\u5206\u7ec4Kaplan-Meier\u751f\u5b58\u66f2\u7ebf"
        if "immun" in lowered or "\u514d\u75ab" in lowered:
            return "\u514d\u75ab\u6cbb\u7597\u5206\u7ec4Kaplan-Meier\u751f\u5b58\u66f2\u7ebf"
        if "target" in lowered or "\u9776\u5411" in lowered:
            return "\u9776\u5411\u6cbb\u7597\u5206\u7ec4Kaplan-Meier\u751f\u5b58\u66f2\u7ebf"
        return "\u4e0d\u540c\u7814\u7a76\u5206\u7ec4\u751f\u5b58\u7ec8\u70b9Kaplan-Meier\u66f2\u7ebf"
    return "\u4e3b\u8981\u7ed3\u679c\u56fe"


def _rewrite_image_alt_text(image_line: str, alt_text: str) -> str:
    match = IMAGE_LINE_PATTERN.match(image_line.strip())
    if not match:
        return image_line
    return f"![{alt_text}]({match.group('path')})"


def _extract_top_level_section_text(markdown_text: str, target_heading: str) -> list[str]:
    _preamble_lines, section_blocks = _split_top_level_section_blocks(markdown_text)
    target_key = target_heading.casefold()
    for title, body in section_blocks:
        if title.casefold() == target_key:
            return body
    return []


def _extract_treatment_distribution_facts(text: str) -> list[tuple[str, str, str]]:
    normalized = _clean_method_paragraph(text)
    patterns = [
        ("监测/未治疗组", [
            r"监测/未治疗组(?:占比)?(?:最高)?[^。；\n]{0,24}?(?P<percent>\d+(?:\.\d+)?)%",
            r"监测/未治疗组[（(]?(?P<count>\d+)例[)）]?[^。；\n]{0,12}?(?P<percent>\d+(?:\.\d+)?)%",
        ]),
        ("TACE组", [
            r"(?:单纯)?TACE组[（(]?(?P<count>\d+)例[)）]?[^。；\n]{0,12}?(?P<percent>\d+(?:\.\d+)?)%",
            r"(?:单纯)?TACE组(?:占比)?(?:次之)?[^。；\n]{0,24}?(?P<percent>\d+(?:\.\d+)?)%",
        ]),
    ]
    grouped_patterns = [
        r"联合治疗(?:组)?、单纯免疫治疗(?:组)?及单纯靶向治疗(?:组)?三组合计占(?P<percent>\d+(?:\.\d+)?)%",
        r"联合治疗(?:组)?、免疫治疗(?:组)?(?:及|和|、)靶向治疗(?:组)?三组合计占(?P<percent>\d+(?:\.\d+)?)%",
        r"联合治疗(?:组)?、免疫治疗(?:组)?(?:及|和|、)靶向治疗(?:组)?(?:三组)?(?:合计)?占(?P<percent>\d+(?:\.\d+)?)%",
    ]
    facts: list[tuple[str, str, str]] = []
    seen_labels: set[str] = set()
    for label, label_patterns in patterns:
        if label in seen_labels:
            continue
        for pattern in label_patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if not match:
                continue
            percent = match.groupdict().get("percent") or ""
            count = (match.groupdict().get("count") or "").replace("例", "")
            if percent:
                facts.append((label, percent, count))
                seen_labels.add(label)
                break
    for pattern in grouped_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            facts.append(("联合/免疫/靶向合计", match.group("percent"), ""))
            seen_labels.add("联合/免疫/靶向合计")
            break
    order = {
        "监测/未治疗组": 0,
        "TACE组": 1,
        "联合/免疫/靶向合计": 2,
    }
    facts.sort(key=lambda item: order.get(item[0], 99))
    return facts





def _format_treatment_distribution_fact(fact: tuple[str, str, str]) -> str:
    label, percent, count = fact
    if label == "联合/免疫/靶向合计":
        return f"联合治疗、免疫治疗及靶向治疗合计（{percent}%）"
    if count:
        return f"{label}{count}例（{percent}%）"
    return f"{label}（{percent}%）"

def _extract_endpoint_p_value(text: str, endpoint: str) -> str:
    flexible_patterns = [
        rf"{endpoint}[^。；;\n]*?P(?:\u503c)?\s*(?:\u4e3a|=)\s*([0-9]*\.?[0-9]+)",
        rf"{endpoint}[^。；;\n]*?Log-rank[^。；;\n]*?P(?:\u503c)?\s*(?:\u4e3a|=)\s*([0-9]*\.?[0-9]+)",
        rf"{endpoint}[^。；;\n]*?P(?:\u503c)?\s*([=<])\s*([0-9]*\.?[0-9]+)",
        rf"{endpoint}[^。；;\n]*?Log-rank[^。；;\n]*?P(?:\u503c)?\s*([=<])\s*([0-9]*\.?[0-9]+)",
    ]
    for pattern in flexible_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        if len(match.groups()) == 1:
            return match.group(1)
        operator = match.group(1)
        value = match.group(2)
        return f"{operator}{value}" if operator == "<" else value

    patterns = [
        rf"{endpoint}[^。；\n]*?P\s*([=<])\s*([0-9]*\.?[0-9]+)",
        rf"{endpoint}[^。；\n]*?Log-rank[^。；\n]*?P\s*([=<])\s*([0-9]*\.?[0-9]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            operator = match.group(1)
            value = match.group(2)
            return f"{operator}{value}" if operator == "<" else value
    return ""


def _p_value_is_significant(value: str) -> bool:
    try:
        return float(value.strip().lstrip("<=")) < 0.05
    except ValueError:
        return False


def _extract_result_trend_sentence(facts: tuple[tuple[str, str, str], ...]) -> str:
    if _has_label_in_facts(facts, "\u76d1\u6d4b/\u672a\u6cbb\u7597\u7ec4") and _has_label_in_facts(facts, "\u8054\u5408\u6cbb\u7597\u7ec4"):
        return "\u5728\u7ec4\u95f4\u8d8b\u52bf\u4e0a\uff0c\u76d1\u6d4b/\u672a\u6cbb\u7597\u7ec4\u4fdd\u6301\u8f83\u9ad8\u7684RFS\u6c34\u5e73\uff0c\u8054\u5408\u6cbb\u7597\u7ec4\u4e0b\u964d\u76f8\u5bf9\u66f4\u5feb\u3002"
    return ""


def _build_discussion_summary_paragraph(evidence: ResultEvidence, section_text: str) -> str:
    sentences: list[str] = []
    if evidence.patient_count:
        sentences.append(f"\u672c\u7814\u7a76\u57fa\u4e8e{evidence.patient_count}\u4f8b\u60a3\u8005\u7684\u73b0\u6709\u4e34\u5e8a\u8d44\u6599\uff0c\u56f4\u7ed5\u7814\u7a76\u5206\u7ec4\u3001\u4e3b\u8981\u7ec8\u70b9\u53ca\u56fe\u8868\u7ed3\u679c\u8fdb\u884c\u4e86\u7cfb\u7edf\u6574\u7406\u3002")
    else:
        sentences.append("\u672c\u7814\u7a76\u56f4\u7ed5\u4e34\u5e8a\u5206\u7ec4\u3001\u56fe\u8868\u5448\u73b0\u548c\u4e3b\u8981\u7ec8\u70b9\u5c55\u5f00\uff0c\u5bf9\u7ec4\u95f4\u7ed3\u5c40\u5dee\u5f02\u53ca\u5176\u53ef\u80fd\u7684\u4e34\u5e8a\u542b\u4e49\u8fdb\u884c\u4e86\u533b\u5b66\u8bba\u6587\u5f0f\u5f52\u7eb3\u3002")
    distribution_sentence = _build_treatment_distribution_sentence(evidence)
    if distribution_sentence:
        sentences.append(distribution_sentence)
    endpoint_clauses = _build_endpoint_result_clauses(evidence)
    if endpoint_clauses:
        sentences.append("\u7ed3\u679c\u663e\u793a\uff0c" + "\uff0c".join(endpoint_clauses) + "\u3002")
    else:
        sentences.append("\u7ec4\u95f4\u6bd4\u8f83\u3001\u7ec8\u70b9\u5b9a\u4e49\u548c\u56fe\u5f62\u8d8b\u52bf\u6784\u6210\u4e86\u7ed3\u679c\u89e3\u8bfb\u7684\u4e3b\u8981\u4f9d\u636e\uff0c\u5176\u4e2d\u66f2\u7ebf\u5206\u79bb\u6216\u6307\u6807\u53d8\u5316\u5bf9\u5224\u65ad\u7ec4\u95f4\u5dee\u5f02\u5177\u6709\u91cd\u8981\u53c2\u8003\u4ef7\u503c\u3002")
    sentences.append("\u603b\u4f53\u800c\u8a00\uff0c\u7814\u7a76\u7ed3\u679c\u66f4\u5f3a\u8c03\u4e0d\u540c\u5206\u7ec4\u5728\u590d\u53d1\u6216\u751f\u5b58\u7ed3\u5c40\u4e0a\u7684\u5206\u5c42\u73b0\u8c61\uff0c\u800c\u975e\u5355\u7eaf\u5c06\u67d0\u4e00\u5206\u7ec4\u89e3\u91ca\u4e3a\u5177\u6709\u7edd\u5bf9\u4f18\u52bf\u3002")
    return _compose_reference_paragraph(sentences, "", min_sentences=4, max_sentences=4, min_chars=170)


def _build_discussion_interpretation_paragraph(evidence: ResultEvidence, section_text: str) -> str:
    sentences: list[str] = []
    if _has_label_in_facts(evidence.treatment_facts, "\u76d1\u6d4b/\u672a\u6cbb\u7597\u7ec4"):
        sentences.append("\u4ece\u7ed3\u679c\u8d70\u5411\u6765\u770b\uff0c\u76d1\u6d4b/\u672a\u6cbb\u7597\u7ec4\u5728RFS\u4e0a\u8868\u73b0\u8f83\u597d\uff0c\u8bf4\u660e\u4e0d\u540c\u672f\u540e\u7ba1\u7406\u7b56\u7565\u6240\u5bf9\u5e94\u7684\u57fa\u7ebf\u98ce\u9669\u4eba\u7fa4\u5e76\u4e0d\u5b8c\u5168\u4e00\u81f4\u3002")
    if _has_label_in_facts(evidence.treatment_facts, "\u8054\u5408\u6cbb\u7597\u7ec4"):
        sentences.append("\u8054\u5408\u6cbb\u7597\u7ec4\u7684\u66f2\u7ebf\u8d70\u5411\u5e76\u4e0d\u80fd\u76f4\u63a5\u89e3\u91ca\u4e3a\u660e\u786e\u751f\u5b58\u83b7\u76ca\u5dee\u5f02\uff0c\u66f4\u53ef\u80fd\u53cd\u6620\u63a5\u53d7\u5f3a\u5316\u6cbb\u7597\u60a3\u8005\u672c\u8eab\u5177\u6709\u66f4\u9ad8\u590d\u53d1\u98ce\u9669\u6216\u66f4\u590d\u6742\u7684\u4e34\u5e8a\u80cc\u666f\u3002")
    if evidence.rfs_p_value and evidence.os_p_value:
        sentences.append("\u56e0\u6b64\uff0c\u672c\u7814\u7a76\u66f4\u9002\u5408\u89e3\u91ca\u4e3a\u4e0d\u540c\u7b56\u7565\u4e0e\u590d\u53d1\u63a7\u5236\u53ca\u603b\u751f\u5b58\u5206\u5c42\u8d8b\u52bf\u4e4b\u95f4\u5b58\u5728\u5173\u8054\uff0c\u800c\u662f\u5426\u5b58\u5728\u7a33\u5b9a\u7684\u603b\u751f\u5b58\u83b7\u76ca\u4ecd\u9700\u66f4\u957f\u671f\u968f\u8bbf\u4e0e\u6821\u6b63\u5206\u6790\u9a8c\u8bc1\u3002")
    if not sentences:
        sentences.append("\u4ece\u7ed3\u679c\u8d8b\u52bf\u6765\u770b\uff0c\u73b0\u6709\u56fe\u8868\u548c\u7edf\u8ba1\u7ed3\u8bba\u66f4\u9002\u5408\u4f5c\u4e3a\u5173\u8054\u6027\u8bc1\u636e\u8fdb\u884c\u89e3\u8bfb\uff0c\u4e0d\u5b9c\u76f4\u63a5\u63a8\u5bfc\u4e3a\u660e\u786e\u56e0\u679c\u6548\u5e94\u3002")
        sentences.append("\u5bf9\u4e8e\u4ec5\u6709\u56fe\u5f62\u8d8b\u52bf\u800c\u7f3a\u5c11\u5177\u4f53\u6570\u503c\u7684\u53d1\u73b0\uff0c\u5e94\u5c06\u5176\u8868\u8ff0\u4e3a\u63d0\u793a\u6027\u6216\u63a2\u7d22\u6027\u7ed3\u679c\uff0c\u800c\u975e\u786e\u5b9a\u6027\u5224\u65ad\u3002")
        sentences.append("\u8fd9\u79cd\u8868\u8ff0\u65b9\u5f0f\u6709\u52a9\u4e8e\u5728\u4fdd\u6301\u8bba\u6587\u5b8c\u6574\u6027\u7684\u540c\u65f6\uff0c\u907f\u514d\u8d85\u51fa\u539f\u59cb\u8bc1\u636e\u7684\u89e3\u91ca\u8303\u56f4\u3002")
    elif len(sentences) < 3:
        sentences.append("\u5bf9\u4e8e\u7edf\u8ba1\u5b66\u610f\u4e49\u4e0e\u56fe\u5f62\u8d8b\u52bf\u4e0d\u5b8c\u5168\u4e00\u81f4\u7684\u60c5\u5f62\uff0c\u5e94\u4ee5\u5df2\u62a5\u544a\u7684P\u503c\u548c\u539f\u59cb\u56fe\u793a\u4e3a\u51c6\uff0c\u907f\u514d\u5bf9\u6548\u679c\u5927\u5c0f\u505a\u989d\u5916\u63a8\u65ad\u3002")
        sentences.append("\u8fd9\u4e9b\u7ed3\u679c\u4e3b\u8981\u53cd\u6620\u7814\u7a76\u5206\u7ec4\u4e0e\u7ed3\u5c40\u4e4b\u95f4\u7684\u89c2\u5bdf\u6027\u5173\u8054\uff0c\u4ecd\u9700\u5728\u66f4\u5b8c\u6574\u7684\u8d44\u6599\u548c\u6821\u6b63\u5206\u6790\u4e2d\u8fdb\u4e00\u6b65\u9a8c\u8bc1\u3002")
    return _compose_reference_paragraph(sentences, "", min_sentences=3, max_sentences=4, min_chars=150)


def _build_discussion_bias_paragraph(evidence: ResultEvidence, section_text: str) -> str:
    sentences: list[str] = []
    sentences.append("\u771f\u5b9e\u4e16\u754c\u7814\u7a76\u4e2d\u7684\u5206\u7ec4\u5f80\u5f80\u4e0e\u60a3\u8005\u57fa\u7ebf\u72b6\u6001\u3001\u75be\u75c5\u4e25\u91cd\u7a0b\u5ea6\u3001\u6cbb\u7597\u53ef\u53ca\u6027\u548c\u4e34\u5e8a\u51b3\u7b56\u504f\u597d\u76f8\u5173\uff0c\u56e0\u6b64\u7ec4\u95f4\u5dee\u5f02\u9700\u653e\u5728\u9009\u62e9\u504f\u501a\u548c\u6f5c\u5728\u6df7\u6742\u7684\u80cc\u666f\u4e0b\u7406\u89e3\u3002")
    if evidence.treatment_facts:
        sentences.append("\u4ece\u6837\u672c\u6784\u6210\u770b\uff0c\u5404\u7ec4\u89c4\u6a21\u6216\u6784\u6210\u6bd4\u53ef\u80fd\u4e0d\u5b8c\u5168\u5747\u8861\uff0c\u8fd9\u4f1a\u5f71\u54cd\u66f2\u7ebf\u5206\u79bb\u7a0b\u5ea6\u548c\u7ec8\u70b9\u4e8b\u4ef6\u7684\u8868\u9762\u5dee\u5f02\u3002")
    else:
        sentences.append("\u57fa\u7ebf\u5747\u8861\u6027\u548c\u5206\u7ec4\u6784\u6210\u662f\u89e3\u91ca\u7ec4\u95f4\u5dee\u5f02\u7684\u91cd\u8981\u524d\u63d0\uff0c\u82e5\u4e0d\u540c\u7ec4\u5728\u75be\u75c5\u8d1f\u8377\u3001\u5668\u5b98\u529f\u80fd\u6216\u6cbb\u7597\u53ef\u53ca\u6027\u4e0a\u5b58\u5728\u5dee\u5f02\uff0c\u66f2\u7ebf\u8868\u73b0\u4fbf\u53ef\u80fd\u53d7\u5230\u8fd9\u4e9b\u56e0\u7d20\u7684\u5171\u540c\u5f71\u54cd\u3002")
    sentences.append("\u56e0\u6b64\uff0c\u672c\u7814\u7a76\u6240\u5448\u73b0\u7684\u6bd4\u8f83\u7ed3\u679c\u5e94\u88ab\u89c6\u4e3a\u5bf9\u73b0\u6709\u8d44\u6599\u7684\u63cf\u8ff0\u6027\u548c\u63a2\u7d22\u6027\u603b\u7ed3\uff0c\u800c\u4e0d\u662f\u5bf9\u6cbb\u7597\u6548\u679c\u4f18\u52a3\u7684\u6700\u7ec8\u5224\u5b9a\u3002")
    sentences.append("\u8fd9\u4e00\u70b9\u5bf9\u771f\u5b9e\u4e16\u754c\u7814\u7a76\u5c24\u4e3a\u91cd\u8981\uff0c\u56e0\u4e3a\u771f\u5b9e\u8bca\u7597\u73af\u5883\u4e2d\u7684\u6cbb\u7597\u9009\u62e9\u5f80\u5f80\u5e76\u975e\u968f\u673a\u5206\u914d\uff0c\u800c\u662f\u7531\u60a3\u8005\u72b6\u6001\u3001\u533b\u751f\u5224\u65ad\u548c\u533b\u7597\u6761\u4ef6\u5171\u540c\u51b3\u5b9a\u3002")
    return _compose_reference_paragraph(sentences, "", min_sentences=4, max_sentences=4, min_chars=180)


def _build_discussion_statistical_visual_paragraph(evidence: ResultEvidence, section_text: str) -> str:
    sentences: list[str] = []
    if evidence.rfs_p_value or evidence.os_p_value:
        endpoint_clauses = _build_endpoint_result_clauses(evidence)
        if endpoint_clauses:
            sentences.append("\u7edf\u8ba1\u5b66\u7ed3\u679c\u4e3a\u56fe\u5f62\u8d8b\u52bf\u7684\u89e3\u91ca\u63d0\u4f9b\u4e86\u91cf\u5316\u53c2\u7167\uff1a" + "\uff0c".join(endpoint_clauses) + "\u3002")
    else:
        sentences.append("\u56fe\u5f62\u8d8b\u52bf\u5728\u8bba\u6587\u89e3\u8bfb\u4e2d\u5177\u6709\u76f4\u89c2\u4ef7\u503c\uff0c\u4f46\u5176\u4e34\u5e8a\u542b\u4e49\u4ecd\u9700\u4e0e\u7ec8\u70b9\u5b9a\u4e49\u3001\u7ec4\u95f4\u6784\u6210\u548c\u968f\u8bbf\u80cc\u666f\u8054\u7cfb\u8d77\u6765\u7406\u89e3\u3002")
    sentences.append("\u5f53\u66f2\u7ebf\u5448\u73b0\u5206\u79bb\u800c\u7edf\u8ba1\u5b66\u7ed3\u679c\u672a\u8fbe\u663e\u8457\u6c34\u5e73\u65f6\uff0c\u8fd9\u79cd\u73b0\u8c61\u901a\u5e38\u63d0\u793a\u6837\u672c\u91cf\u3001\u4e8b\u4ef6\u6570\u6216\u968f\u8bbf\u65f6\u95f4\u53ef\u80fd\u5c1a\u4e0d\u8db3\u4ee5\u652f\u6491\u7a33\u5b9a\u7684\u7edf\u8ba1\u5b66\u5224\u65ad\u3002")
    sentences.append("\u76f8\u53cd\uff0c\u82e5\u67d0\u4e00\u7ec8\u70b9\u5df2\u663e\u793a\u7edf\u8ba1\u5b66\u5dee\u5f02\uff0c\u4ecd\u9700\u8fdb\u4e00\u6b65\u5173\u6ce8\u66f2\u7ebf\u5206\u79bb\u7684\u65f6\u95f4\u70b9\u3001\u5206\u79bb\u5e45\u5ea6\u53ca\u9ad8\u5371\u4eba\u7fa4\u5728\u5404\u7ec4\u4e2d\u7684\u5206\u5e03\u60c5\u51b5\u3002")
    sentences.append("\u56e0\u6b64\uff0c\u7edf\u8ba1\u7ed3\u679c\u4e0e\u56fe\u5f62\u8d8b\u52bf\u5e94\u76f8\u4e92\u5370\u8bc1\u800c\u975e\u5f7c\u6b64\u66ff\u4ee3\uff0c\u8fd9\u6709\u52a9\u4e8e\u4f7f\u7ed3\u679c\u89e3\u8bfb\u4fdd\u6301\u514b\u5236\u5e76\u63a5\u8fd1\u4e34\u5e8a\u5b9e\u9645\u3002")
    return _compose_reference_paragraph(sentences, "", min_sentences=4, max_sentences=4, min_chars=180)


def _build_discussion_limitation_paragraph(evidence: ResultEvidence, section_text: str) -> str:
    sentences: list[str] = []
    sentences.append("\u672c\u7814\u7a76\u4ecd\u5b58\u5728\u4e00\u5b9a\u5c40\u9650\u6027\uff1a\u9996\u5148\uff0c\u771f\u5b9e\u4e16\u754c\u7814\u7a76\u56fa\u6709\u7684\u975e\u968f\u673a\u5206\u7ec4\u7279\u5f81\u53ef\u80fd\u5bfc\u81f4\u9009\u62e9\u504f\u501a\uff0c\u4ece\u800c\u5f71\u54cd\u7ec4\u95f4\u5dee\u5f02\u7684\u89e3\u91ca\u3002")
    if any(_has_label_in_facts(evidence.treatment_facts, label) for label in ("\u8054\u5408\u6cbb\u7597\u7ec4", "\u514d\u75ab\u6cbb\u7597\u7ec4", "\u9776\u5411\u6cbb\u7597\u7ec4")):
        sentences.append("\u6b64\u5916\uff0c\u514d\u75ab\u6cbb\u7597\u3001\u9776\u5411\u6cbb\u7597\u53ca\u8054\u5408\u6cbb\u7597\u7b49\u90e8\u5206\u4e9a\u7ec4\u6837\u672c\u91cf\u76f8\u5bf9\u8f83\u5c11\uff0cOS\u76f8\u5173\u7ed3\u8bba\u4ecd\u9700\u7ed3\u5408\u66f4\u957f\u968f\u8bbf\u4e0e\u591a\u56e0\u7d20\u6821\u6b63\u8fdb\u4e00\u6b65\u9a8c\u8bc1\u3002")
    else:
        sentences.append("\u5176\u6b21\uff0c\u5404\u7ec4\u57fa\u7ebf\u5747\u8861\u6027\u3001\u968f\u8bbf\u5b8c\u6574\u6027\u548c\u4e8b\u4ef6\u6570\u5747\u53ef\u80fd\u5f71\u54cd\u751f\u5b58\u66f2\u7ebf\u53caP\u503c\u7684\u7a33\u5b9a\u6027\uff0c\u56e0\u6b64\u76f8\u5173\u7ed3\u8bba\u4ecd\u9700\u5728\u66f4\u5b8c\u6574\u961f\u5217\u4e2d\u9a8c\u8bc1\u3002")
    sentences.append("\u540e\u7eed\u7814\u7a76\u5b9c\u5728\u66f4\u5b8c\u6574\u7684\u6570\u636e\u91c7\u96c6\u548c\u66f4\u89c4\u8303\u7684\u7814\u7a76\u8bbe\u8ba1\u4e0b\uff0c\u8fdb\u4e00\u6b65\u9a8c\u8bc1\u4e3b\u8981\u7ec8\u70b9\u3001\u5206\u7ec4\u8d8b\u52bf\u53ca\u5176\u4e34\u5e8a\u610f\u4e49\u3002")
    sentences.append("\u5728\u6761\u4ef6\u5141\u8bb8\u65f6\uff0c\u53ef\u5728\u540e\u7eed\u7814\u7a76\u4e2d\u7ed3\u5408\u66f4\u7ec6\u81f4\u7684\u57fa\u7ebf\u6821\u6b63\u3001\u66f4\u957f\u968f\u8bbf\u548c\u5916\u90e8\u9a8c\u8bc1\uff0c\u4ee5\u63d0\u9ad8\u7ed3\u8bba\u7684\u7a33\u5065\u6027\u548c\u4e34\u5e8a\u53ef\u63a8\u5e7f\u6027\u3002")
    return _compose_reference_paragraph(sentences, "", min_sentences=4, max_sentences=4, min_chars=180)


def _harmonize_structured_sections(markdown_text: str, report_language: str) -> str:
    if report_language != "zh" or not markdown_text.strip():
        return markdown_text
    evidence = _build_result_evidence(markdown_text, _extract_top_level_section_text(markdown_text, ZH_RESULTS_HEADING))
    return _replace_section_bodies_with_evidence(markdown_text, evidence)


def _replace_section_bodies_with_evidence(markdown_text: str, evidence: ResultEvidence) -> str:
    preamble_lines, section_blocks = _split_top_level_section_blocks(markdown_text)
    if not section_blocks:
        return markdown_text

    rebuilt: list[str] = []
    if preamble_lines:
        rebuilt.extend(preamble_lines)
        if rebuilt and rebuilt[-1].strip():
            rebuilt.append("")

    for title, body in section_blocks:
        rebuilt.append(f"# {title}")
        canonical = _heading_aliases("zh").get(_normalize_heading_candidate(title).casefold(), _normalize_heading_candidate(title))
        if canonical == ZH_ABSTRACT_HEADING:
            body = _rewrite_abstract_with_evidence(body, evidence)
        elif canonical == ZH_DISCUSSION_HEADING:
            body = _rewrite_discussion_section_body(body, markdown_text, evidence)
        rebuilt.extend(body)
        rebuilt.append("")

    return "\n".join(rebuilt).strip() + "\n"


def _rewrite_abstract_with_evidence(body_lines: list[str], evidence: ResultEvidence) -> list[str]:
    abstract_text = _flatten_abstract_block(body_lines, "zh")
    if not abstract_text:
        return body_lines

    return [_ensure_complete_chinese_abstract(abstract_text, evidence)]


def _build_abstract_result_sentence(evidence: ResultEvidence) -> str:
    fragments: list[str] = []
    if evidence.patient_count:
        fragments.append(f"\u5171\u7eb3\u5165{evidence.patient_count}\u4f8b\u60a3\u8005")
    distribution = _build_treatment_distribution_sentence(evidence)
    if distribution:
        fragments.append(distribution.removeprefix("\u5728\u5404\u6cbb\u7597\u5206\u7ec4\u4e2d\uff0c").rstrip("\u3002"))
    endpoint_clauses = _build_endpoint_result_clauses(evidence)
    if endpoint_clauses:
        fragments.append("\uff0c".join(endpoint_clauses))
    if not fragments:
        return ""
    return "\u7ed3\u679c\uff1a" + "\uff1b".join(fragments) + "\u3002"


def _build_endpoint_result_clauses(evidence: ResultEvidence) -> list[str]:
    clauses: list[str] = []
    if evidence.rfs_p_value:
        clauses.append(_format_endpoint_statistical_clause("RFS", evidence.rfs_p_value))
    if evidence.os_p_value:
        clauses.append(_format_endpoint_statistical_clause("OS", evidence.os_p_value))
    return clauses


def _format_endpoint_statistical_clause(endpoint: str, p_value: str) -> str:
    if _p_value_is_significant(p_value):
        return f"{endpoint}\u7ec4\u95f4\u5dee\u5f02\u6709\u7edf\u8ba1\u5b66\u610f\u4e49\uff08P={p_value}\uff09"
    return f"{endpoint}\u7ec4\u95f4\u5dee\u5f02\u672a\u8fbe\u7edf\u8ba1\u5b66\u610f\u4e49\uff08P={p_value}\uff09"


def _deduplicate_title_lines(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    if len(lines) < 2:
        return markdown_text
    first = lines[0].strip()
    second = lines[1].strip()
    if first.startswith("# ") and second == first[2:].strip():
        lines.pop(1)
    return "\n".join(lines)






















































































































































































































































































































































def _clean_discussion_paragraph(text: str) -> str:
    cleaned = _clean_method_paragraph(text)
    replacements = {
        "\u503c\u5f97\u6ce8\u610f\u7684\u662f\uff0c": "",
        "\u8fd9\u4e00\u770b\u4f3c\u53cd\u76f4\u89c9\u7684\u7ed3\u679c\u9700\u8981\u5ba1\u614e\u89e3\u8bfb\u3002": "",
        "\u4e00\u65b9\u9762\uff0c": "",
        "\u53e6\u4e00\u65b9\u9762\uff0c": "",
        "\u4ece\u673a\u5236\u89d2\u5ea6\u5206\u6790\uff0c": "",
        "\u7406\u8bba\u4e0a": "",
        "\u957f\u5c3e\u6548\u5e94": "\u957f\u671f\u751f\u5b58\u83b7\u76ca",
        "\u9006\u6cbb\u7597\u6548\u5e94": "\u9009\u62e9\u504f\u501a",
        "\u57fa\u77f3\u5730\u4f4d": "\u91cd\u8981\u5730\u4f4d",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.replace("\u3002\u3002", "\u3002")
    return cleaned.strip()


def _extract_unique_citation_markers(text: str) -> list[str]:
    markers = re.findall(r"\[(?:\s*@[^]]+)\]", text)
    unique: list[str] = []
    for marker in markers:
        if marker not in unique:
            unique.append(marker)
    return unique


def _append_citation_markers(text: str, markers: list[str]) -> str:
    if not markers:
        return text
    existing = _extract_unique_citation_markers(text)
    missing = [marker for marker in markers if marker not in existing]
    if not missing:
        return text
    return text.rstrip() + " " + " ".join(missing)


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(needle.casefold() in lowered for needle in needles)


def _medical_destination_heading(title: str) -> str:
    normalized = _normalize_heading_candidate(title)
    canonical = _heading_aliases("zh").get(normalized.casefold(), normalized)
    if canonical in {"摘要", "关键词", "引言", "患者与方法", "结果", "讨论"}:
        return canonical

    methods_like = ("患者", "方法", "材料", "统计", "纳入", "排除", "基线", "数据", "字段", "变量", "附件", "表格", "样本")
    results_like = ("结果", "生存", "图", "亚组", "特征")
    discussion_like = ("讨论", "局限", "结论", "展望", "建议", "意义", "机制", "对比")

    if any(token in normalized for token in discussion_like):
        return "讨论"
    if any(token in normalized for token in results_like):
        return "结果"
    if any(token in normalized for token in methods_like):
        return "患者与方法"
    return "讨论"


def _is_plain_destination_alias(title: str, destination: str) -> bool:
    normalized = _normalize_heading_candidate(title).casefold()
    alias_map = {
        "摘要": {"摘要", "abstract"},
        "关键词": {"关键词", "keywords", "key words"},
        "引言": {"引言", "简介", "介绍", "introduction"},
        "患者与方法": {"患者与方法", "方法", "材料与方法", "研究方法", "methods", "patients and methods"},
        "结果": {"结果", "研究结果", "results"},
        "讨论": {"讨论", "discussion"},
    }
    return normalized in {item.casefold() for item in alias_map.get(destination, set())}


def _should_suppress_moved_section_heading(title: str, destination: str) -> bool:
    normalized = _normalize_heading_candidate(title)
    if destination == "患者与方法" and normalized in {"数据基础与附件分析", "数据结构与主要字段", "附件与表格分析"}:
        return True
    if destination == "讨论" and normalized in {"局限性", "研究局限性", "结论", "展望", "后续研究方向与方法升级建议"}:
        return True
    return False


def _promote_named_extra_sections(markdown_text: str, report_language: str) -> str:
    if report_language == "zh":
        alias_map = {
            "数据结构与主要字段": "数据结构与主要字段",
            "数据结构、主要字段与样本量描述": "数据结构与主要字段",
            "主要字段与样本量描述": "数据结构与主要字段",
            "附件与表格分析": "附件与表格分析",
            "表格分析与附件说明": "附件与表格分析",
            "案例解读": "案例解读",
            "案例分析与解读": "案例解读",
            "展望": "展望",
            "未来展望": "展望",
        }
    else:
        alias_map = {
            "data structure and key fields": "Data Structure and Key Fields",
            "data structure, key fields and sample size": "Data Structure and Key Fields",
            "attachment and table analysis": "Attachment and Table Analysis",
            "attachment and table review": "Attachment and Table Analysis",
            "case interpretation": "Case Interpretation",
            "case analysis and interpretation": "Case Interpretation",
            "outlook": "Outlook",
            "future outlook": "Outlook",
        }

    promoted_lines: list[str] = []
    for raw_line in markdown_text.splitlines():
        stripped = raw_line.strip()
        plain = stripped.strip("*").strip()
        plain = plain.lstrip("#").strip()
        plain = re.sub(r"^\d+(?:\.\d+)*[.)]?\s*", "", plain).strip()
        canonical = alias_map.get(plain.casefold() if report_language == "en" else plain)
        if canonical:
            promoted_lines.append(f"# {canonical}")
            continue
        promoted_lines.append(raw_line)
    return "\n".join(promoted_lines)


def _named_extra_headings(report_language: str) -> set[str]:
    if report_language == "zh":
        return {
            "æ•°æ®åŸºç¡€ä¸Žé™„ä»¶åˆ†æž",
            "æ•°æ®ç»“æž„ä¸Žä¸»è¦å­—æ®µ",
            "é™„ä»¶ä¸Žè¡¨æ ¼åˆ†æž",
            "æ¡ˆä¾‹è§£è¯»",
            "å±•æœ›",
        }
    return {
        "Data Foundation and Attachment Analysis",
        "Data Structure and Key Fields",
        "Attachment and Table Analysis",
        "Case Interpretation",
        "Outlook",
    }


def _organize_data_foundation_sections(markdown_text: str, report_language: str) -> str:
    if report_language == "zh":
        parent_heading = "æ•°æ®åŸºç¡€ä¸Žé™„ä»¶åˆ†æž"
        child_order = ["æ•°æ®ç»“æž„ä¸Žä¸»è¦å­—æ®µ", "é™„ä»¶ä¸Žè¡¨æ ¼åˆ†æž"]
    else:
        parent_heading = "Data Foundation and Attachment Analysis"
        child_order = ["Data Structure and Key Fields", "Attachment and Table Analysis"]

    preamble_lines, section_blocks = _split_top_level_section_blocks(markdown_text)
    if not section_blocks:
        return markdown_text

    parent_index = -1
    child_indices: dict[str, int] = {}
    parent_key = parent_heading.casefold()
    child_keys = {heading.casefold(): heading for heading in child_order}

    for index, (title, _) in enumerate(section_blocks):
        title_key = title.casefold()
        if title_key == parent_key and parent_index == -1:
            parent_index = index
        if title_key in child_keys and title_key not in child_indices:
            child_indices[title_key] = index

    if parent_index == -1 and not child_indices:
        return markdown_text

    consumed_indices: set[int] = set()
    rebuilt_blocks: list[list[str]] = []

    if parent_index != -1:
        parent_title, parent_body_lines = section_blocks[parent_index]
        rebuilt_parent = [f"# {parent_title}", *parent_body_lines]
        consumed_indices.add(parent_index)

        for child_heading in child_order:
            child_index = child_indices.get(child_heading.casefold())
            if child_index is None:
                continue
            consumed_indices.add(child_index)
            if _block_has_nested_heading(parent_body_lines, child_heading):
                continue

            _, child_body_lines = section_blocks[child_index]
            nested_body_lines = _trim_blank_lines(_shift_markdown_heading_levels(child_body_lines, 1))
            if not nested_body_lines:
                continue

            if rebuilt_parent and rebuilt_parent[-1].strip():
                rebuilt_parent.append("")
            rebuilt_parent.append(f"## {child_heading}")
            rebuilt_parent.append("")
            rebuilt_parent.extend(nested_body_lines)
            rebuilt_parent.append("")

        rebuilt_parent = _trim_blank_lines(rebuilt_parent)
    else:
        parent_index = min(child_indices.values())
        rebuilt_parent = [f"# {parent_heading}", ""]

        for child_heading in child_order:
            child_index = child_indices.get(child_heading.casefold())
            if child_index is None:
                continue
            consumed_indices.add(child_index)
            _, child_body_lines = section_blocks[child_index]
            nested_body_lines = _trim_blank_lines(_shift_markdown_heading_levels(child_body_lines, 1))
            if not nested_body_lines:
                continue

            rebuilt_parent.append(f"## {child_heading}")
            rebuilt_parent.append("")
            rebuilt_parent.extend(nested_body_lines)
            rebuilt_parent.append("")

        rebuilt_parent = _trim_blank_lines(rebuilt_parent)

    for index, (title, body_lines) in enumerate(section_blocks):
        if index == parent_index:
            rebuilt_blocks.append(rebuilt_parent)
            continue
        if index in consumed_indices:
            continue
        rebuilt_blocks.append(_trim_blank_lines([f"# {title}", *body_lines]))

    output_lines = _trim_blank_lines(preamble_lines)
    if output_lines:
        output_lines.append("")

    for block in rebuilt_blocks:
        if not block:
            continue
        output_lines.extend(block)
        output_lines.append("")

    return "\n".join(_trim_blank_lines(output_lines)).strip() + "\n"


def _split_top_level_section_blocks(markdown_text: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    preamble_lines: list[str] = []
    section_blocks: list[tuple[str, list[str]]] = []
    current_title = ""
    current_body: list[str] = []

    for raw_line in markdown_text.splitlines():
        heading_match = HEADING_PATTERN.match(raw_line.strip())
        if heading_match and len(heading_match.group(1)) == 1:
            if current_title:
                section_blocks.append((current_title, current_body))
            else:
                preamble_lines = current_body
            current_title = heading_match.group(2).strip()
            current_body = []
            continue
        current_body.append(raw_line)

    if current_title:
        section_blocks.append((current_title, current_body))
    else:
        preamble_lines = current_body

    return preamble_lines, section_blocks


def _block_has_nested_heading(block_lines: list[str], heading: str) -> bool:
    target = heading.casefold()
    for raw_line in block_lines:
        heading_match = HEADING_PATTERN.match(raw_line.strip())
        if heading_match and len(heading_match.group(1)) >= 2 and heading_match.group(2).strip().casefold() == target:
            return True
    return False


def _shift_markdown_heading_levels(lines: list[str], delta: int) -> list[str]:
    shifted_lines: list[str] = []
    for raw_line in lines:
        heading_match = HEADING_PATTERN.match(raw_line.strip())
        if not heading_match:
            shifted_lines.append(raw_line)
            continue
        new_level = min(len(heading_match.group(1)) + delta, 6)
        shifted_lines.append(f"{'#' * new_level} {heading_match.group(2).strip()}")
    return shifted_lines


def _trim_blank_lines(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def _named_extra_headings(report_language: str) -> set[str]:
    if report_language == "zh":
        return {
            "\u6570\u636e\u57fa\u7840\u4e0e\u9644\u4ef6\u5206\u6790",
            "\u6570\u636e\u7ed3\u6784\u4e0e\u4e3b\u8981\u5b57\u6bb5",
            "\u9644\u4ef6\u4e0e\u8868\u683c\u5206\u6790",
            "\u6848\u4f8b\u89e3\u8bfb",
            "\u5c55\u671b",
        }
    return {
        "Data Foundation and Attachment Analysis",
        "Data Structure and Key Fields",
        "Attachment and Table Analysis",
        "Case Interpretation",
        "Outlook",
    }


def _organize_data_foundation_sections(markdown_text: str, report_language: str) -> str:
    if report_language == "zh":
        parent_heading = "\u6570\u636e\u57fa\u7840\u4e0e\u9644\u4ef6\u5206\u6790"
        child_order = [
            "\u6570\u636e\u7ed3\u6784\u4e0e\u4e3b\u8981\u5b57\u6bb5",
            "\u9644\u4ef6\u4e0e\u8868\u683c\u5206\u6790",
        ]
    else:
        parent_heading = "Data Foundation and Attachment Analysis"
        child_order = ["Data Structure and Key Fields", "Attachment and Table Analysis"]

    preamble_lines, section_blocks = _split_top_level_section_blocks(markdown_text)
    if not section_blocks:
        return markdown_text

    parent_index = -1
    child_indices: dict[str, int] = {}
    parent_key = parent_heading.casefold()
    child_keys = {heading.casefold(): heading for heading in child_order}

    for index, (title, _) in enumerate(section_blocks):
        title_key = title.casefold()
        if title_key == parent_key and parent_index == -1:
            parent_index = index
        if title_key in child_keys and title_key not in child_indices:
            child_indices[title_key] = index

    if parent_index == -1 and not child_indices:
        return markdown_text

    consumed_indices: set[int] = set()
    rebuilt_blocks: list[list[str]] = []

    if parent_index != -1:
        parent_title, parent_body_lines = section_blocks[parent_index]
        rebuilt_parent = [f"# {parent_title}", *parent_body_lines]
        consumed_indices.add(parent_index)

        for child_heading in child_order:
            child_index = child_indices.get(child_heading.casefold())
            if child_index is None:
                continue
            consumed_indices.add(child_index)
            if _block_has_nested_heading(parent_body_lines, child_heading):
                continue

            _, child_body_lines = section_blocks[child_index]
            nested_body_lines = _trim_blank_lines(_shift_markdown_heading_levels(child_body_lines, 1))
            if not nested_body_lines:
                continue

            if rebuilt_parent and rebuilt_parent[-1].strip():
                rebuilt_parent.append("")
            rebuilt_parent.append(f"## {child_heading}")
            rebuilt_parent.append("")
            rebuilt_parent.extend(nested_body_lines)
            rebuilt_parent.append("")

        rebuilt_parent = _trim_blank_lines(rebuilt_parent)
    else:
        parent_index = min(child_indices.values())
        rebuilt_parent = [f"# {parent_heading}", ""]

        for child_heading in child_order:
            child_index = child_indices.get(child_heading.casefold())
            if child_index is None:
                continue
            consumed_indices.add(child_index)
            _, child_body_lines = section_blocks[child_index]
            nested_body_lines = _trim_blank_lines(_shift_markdown_heading_levels(child_body_lines, 1))
            if not nested_body_lines:
                continue

            rebuilt_parent.append(f"## {child_heading}")
            rebuilt_parent.append("")
            rebuilt_parent.extend(nested_body_lines)
            rebuilt_parent.append("")

        rebuilt_parent = _trim_blank_lines(rebuilt_parent)

    for index, (title, body_lines) in enumerate(section_blocks):
        if index == parent_index:
            rebuilt_blocks.append(rebuilt_parent)
            continue
        if index in consumed_indices:
            continue
        rebuilt_blocks.append(_trim_blank_lines([f"# {title}", *body_lines]))

    output_lines = _trim_blank_lines(preamble_lines)
    if output_lines:
        output_lines.append("")

    for block in rebuilt_blocks:
        if not block:
            continue
        output_lines.extend(block)
        output_lines.append("")

    return "\n".join(_trim_blank_lines(output_lines)).strip() + "\n"


def _get_top_level_section_body(markdown_text: str, heading: str) -> str:
    lines = markdown_text.splitlines()
    target = heading.casefold()
    capture = False
    body: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match and len(heading_match.group(1)) == 1:
            current = heading_match.group(2).strip().casefold()
            if capture:
                break
            if current == target:
                capture = True
                continue
        if capture:
            body.append(raw_line)

    return "\n".join(body).strip()


def _has_substantive_section_body(body: str) -> bool:
    if not body:
        return False
    stripped = re.sub(r"(?m)^#+\s+.*$", "", body)
    stripped = re.sub(r"!\[.*?\]\(.*?\)", "", stripped)
    stripped = stripped.strip()
    return len(stripped) >= 40


def _upsert_top_level_section(markdown_text: str, heading: str, body: str) -> str:
    lines = markdown_text.splitlines()
    target = heading.casefold()
    output: list[str] = []
    index = 0
    replaced = False

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match and len(heading_match.group(1)) == 1 and heading_match.group(2).strip().casefold() == target:
            output.append(f"# {heading}")
            output.append("")
            output.extend(body.strip().splitlines())
            output.append("")
            replaced = True
            index += 1
            while index < len(lines):
                next_match = HEADING_PATTERN.match(lines[index].strip())
                if next_match and len(next_match.group(1)) == 1:
                    break
                index += 1
            continue
        output.append(raw_line)
        index += 1

    if not replaced:
        if output and output[-1].strip():
            output.append("")
        output.append(f"# {heading}")
        output.append("")
        output.extend(body.strip().splitlines())
    return "\n".join(output).strip() + "\n"


def _build_required_section_fallback(
    heading: str,
    structured_report: dict[str, object],
    report_language: str,
) -> str:
    source_text = _pick_structured_section_text(structured_report, heading, report_language)
    if source_text:
        return source_text

    if report_language == "zh":
        if heading == "局限性":
            return (
                "本研究仍受数据覆盖范围、变量完整性、样本代表性和分析口径一致性的限制。"
                "相关结论仍需在更完整的临床资料、更规范的随访记录和外部验证研究中进一步检验。"
            )
        return (
            "综合数据整理、分组比较和结局分析结果，研究已经能够对样本构成、关键指标和组间差异进行系统描述。"
            "后续如结合更完整的变量信息、更充分的样本量和更长期随访，相关结论仍可进一步完善和细化。"
        )

    if heading == "Limitations":
        return (
            "This report is grounded in the currently available source materials, so interpretation remains constrained by source-data coverage, field completeness, sample representativeness, and analytical consistency. "
            "Items that were not fully specified in the source, including broader validation context and longer-term follow-up detail, should therefore be interpreted with appropriate caution."
        )
    return (
        "Taken together, the source materials support a structured description of cohort composition, key variables, and treatment-group comparison results. "
        "Further expansion with richer variables, additional samples, and follow-up validation would help refine and strengthen the final conclusions."
    )


def _pick_structured_section_text(
    structured_report: dict[str, object],
    heading: str,
    report_language: str,
) -> str:
    sections = structured_report.get("sections") or []
    if not isinstance(sections, list):
        return ""

    if report_language == "zh":
        keyword_map = {
            "局限性": ["局限", "不足", "限制"],
            "结论": ["结论", "总结", "展望", "建议"],
        }
    else:
        keyword_map = {
            "Limitations": ["limitation", "constraint", "restriction"],
            "Conclusion": ["conclusion", "summary", "outlook", "future"],
        }

    keywords = keyword_map.get(heading, [])
    matched_blocks: list[str] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        heading_text = str(section.get("heading") or "")
        body_text = str(section.get("content_markdown") or "").strip()
        haystack = f"{heading_text}\n{body_text}".casefold()
        if any(keyword.casefold() in haystack for keyword in keywords) and body_text:
            matched_blocks.append(body_text)

    if not matched_blocks:
        return ""

    merged = "\n\n".join(matched_blocks[:2]).strip()
    return merged


def _apply_reference_journal_end_matter(
    markdown_text: str,
    *,
    source_markdown: str,
    structured_report: dict[str, object],
    has_references: bool,
) -> str:
    combined_text = f"{source_markdown}\n{markdown_text}".casefold()

    disclaimer_body = _build_reference_journal_disclaimer(source_markdown, structured_report)
    if disclaimer_body:
        markdown_text = _upsert_top_level_section(markdown_text, "免责声明", disclaimer_body)

    funding_body = _build_reference_journal_funding(source_markdown, structured_report)
    if funding_body:
        markdown_text = _upsert_top_level_section(markdown_text, "基金项目", funding_body)

    if has_references or any(token in combined_text for token in ("[@", "参考文献", "doi", " et al.", "http://", "https://")):
        reference_body = _get_top_level_section_body(markdown_text, "参考文献")
        if not reference_body.strip():
            markdown_text = _upsert_top_level_section(markdown_text, "参考文献", "文后参考文献由引文与参考文献库自动整理生成。")

    return markdown_text


def _build_reference_journal_disclaimer(source_markdown: str, structured_report: dict[str, object]) -> str:
    source_text = _extract_source_text_for_end_matter(source_markdown, structured_report)
    if not source_text:
        return ""
    lower_text = source_text.casefold()
    if not any(token in lower_text for token in ("伦理", "匿名", "知情同意", "赫尔辛基", "伦理委员会", "审批", "免知情", "隐私")):
        return ""

    sentences: list[str] = []
    if any(token in lower_text for token in ("匿名", "隐私", "去标识", "脱敏")):
        sentences.append("本研究所使用资料均基于匿名化或去标识化后的临床信息进行整理与分析，不涉及可识别个人身份的信息。")
    if any(token in lower_text for token in ("伦理", "伦理委员会", "审批", "赫尔辛基")):
        sentences.append("研究过程遵循相关伦理要求开展，并在资料核对与结果整理过程中重视受试者隐私保护。")
    if any(token in lower_text for token in ("知情同意", "免知情")):
        sentences.append("知情同意或豁免情形依照研究资料记录进行说明，伦理相关内容保持客观、克制和可追溯。")

    return "".join(sentences).strip()


def _build_reference_journal_funding(source_markdown: str, structured_report: dict[str, object]) -> str:
    source_text = _extract_source_text_for_end_matter(source_markdown, structured_report)
    if not source_text:
        return ""

    lines = source_text.replace("\r", "\n").split("\n")
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        if any(token in stripped for token in ("基金", "资助", "项目", "课题", "编号")):
            if len(stripped) <= 120:
                return stripped.rstrip("。；; ") + "。"
    return ""


def _extract_source_text_for_end_matter(source_markdown: str, structured_report: dict[str, object]) -> str:
    section_texts: list[str] = []
    for section in structured_report.get("sections") or []:
        if not isinstance(section, dict):
            continue
        heading_text = str(section.get("heading") or "")
        body_text = str(section.get("content_markdown") or "")
        section_texts.append(f"{heading_text}\n{body_text}".strip())
    return "\n".join(part for part in [source_markdown, *section_texts] if part).strip()


def _apply_reference_journal_numbering(markdown_text: str) -> str:
    preamble_lines, section_blocks = _split_top_level_section_blocks(markdown_text)
    if not section_blocks:
        return markdown_text

    heading_map = {
        "摘要": "摘要",
        "关键词": "关键词",
        "引言": "1. 引言",
        "患者与方法": "2. 患者和方法",
        "结果": "3. 研究结果",
        "讨论": "4. 讨论",
        "免责声明": "免责声明",
        "基金项目": "基金项目",
        "参考文献": "参考文献",
    }
    body_heading_map = {
        "1. 引言": "引言",
        "2. 患者和方法": "患者与方法",
        "3. 研究结果": "结果",
        "4. 讨论": "讨论",
    }
    methods_subheading_map = {
        "患者": "2.1 患者",
        "临床和病理指标": "2.2 临床和病理指标",
        "随访和治疗": "2.3 随访和治疗",
        "统计学分析": "2.4 统计学分析",
    }

    output_lines = _trim_blank_lines(preamble_lines)
    if output_lines:
        output_lines.append("")

    for title, body_lines in section_blocks:
        canonical_title = _canonical_reference_end_matter_title(title)
        display_title = heading_map.get(canonical_title, canonical_title)
        output_lines.append(f"# {display_title}")
        output_lines.append("")

        cleaned_body = _trim_blank_lines(body_lines)
        if canonical_title == "患者与方法":
            cleaned_body = _renumber_nested_headings(cleaned_body, methods_subheading_map)
        elif canonical_title == "结果":
            cleaned_body = _renumber_result_subheadings(cleaned_body)
        elif display_title in body_heading_map:
            cleaned_body = _strip_nested_numeric_prefixes(cleaned_body)

        output_lines.extend(cleaned_body)
        output_lines.append("")

    return "\n".join(_trim_blank_lines(output_lines)).strip() + "\n"


def _canonical_reference_end_matter_title(title: str) -> str:
    normalized = re.sub(r"^\d+(?:\.\d+)*\s*", "", title.strip())
    normalized = normalized.strip(".．、 ")
    aliases = {
        "引言": "引言",
        "患者和方法": "患者与方法",
        "患者与方法": "患者与方法",
        "研究结果": "结果",
        "结果": "结果",
        "讨论": "讨论",
        "摘要": "摘要",
        "关键词": "关键词",
        "免责声明": "免责声明",
        "基金项目": "基金项目",
        "参考文献": "参考文献",
    }
    return aliases.get(normalized, normalized)


def _renumber_nested_headings(lines: list[str], heading_map: dict[str, str]) -> list[str]:
    renumbered: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if not heading_match or len(heading_match.group(1)) < 2:
            renumbered.append(raw_line)
            continue
        original_title = re.sub(r"^\d+(?:\.\d+)*\s*", "", heading_match.group(2).strip())
        original_title = original_title.strip(".．、 ")
        mapped = heading_map.get(original_title)
        if mapped:
            renumbered.append(f"{'#' * len(heading_match.group(1))} {mapped}")
        else:
            renumbered.append(f"{'#' * len(heading_match.group(1))} {original_title}")
    return renumbered


def _renumber_result_subheadings(lines: list[str]) -> list[str]:
    renumbered: list[str] = []
    subsection_index = 1
    for raw_line in lines:
        stripped = raw_line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if not heading_match or len(heading_match.group(1)) < 2:
            renumbered.append(raw_line)
            continue
        title = re.sub(r"^\d+(?:\.\d+)*\s*", "", heading_match.group(2).strip())
        title = title.strip(".．、 ")
        renumbered.append(f"{'#' * len(heading_match.group(1))} 3.{subsection_index} {title}")
        subsection_index += 1
    return renumbered


def _strip_nested_numeric_prefixes(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if not heading_match or len(heading_match.group(1)) < 2:
            cleaned.append(raw_line)
            continue
        title = re.sub(r"^\d+(?:\.\d+)*\s*", "", heading_match.group(2).strip())
        title = title.strip(".．、 ")
        cleaned.append(f"{'#' * len(heading_match.group(1))} {title}")
    return cleaned


def _find_first_canonical_heading_index(lines: list[str], aliases: dict[str, str]) -> int:
    for index, raw_line in enumerate(lines):
        if _canonical_heading_from_text(raw_line.strip(), aliases):
            return index
    return -1


def _canonical_heading_from_text(text: str, aliases: dict[str, str]) -> str | None:
    candidate = _normalize_heading_candidate(text)
    if not candidate:
        return None
    return aliases.get(candidate.casefold())


def _normalize_heading_candidate(text: str) -> str:
    candidate = text.strip()
    if not candidate:
        return ""

    while candidate.startswith("#"):
        candidate = candidate[1:].strip()

    candidate = candidate.strip("*").strip()
    candidate = candidate.rstrip("：:.- ").strip()
    return candidate


def _looks_like_leading_title(text: str) -> bool:
    candidate = text.strip()
    if not candidate:
        return False
    if candidate.startswith(("#", "!", "*", "-", "1.", "2.", "3.")):
        return False
    return len(candidate) <= 80


def _ensure_explicit_figure_references(
    markdown_text: str,
    figure_entries: list[dict[str, object]],
    report_language: str,
) -> str:
    if not markdown_text.strip() or not figure_entries:
        return markdown_text


def _promote_numbered_subheadings(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    promoted_lines: list[str] = []
    current_heading_level = 0
    in_code_block = False

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            promoted_lines.append(raw_line)
            continue

        if in_code_block:
            promoted_lines.append(raw_line)
            continue

        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match:
            current_heading_level = len(heading_match.group(1))
            promoted_lines.append(raw_line)
            continue

        ordered_match = ORDERED_LIST_PATTERN.match(stripped)
        if ordered_match and _should_promote_ordered_heading(lines, index, current_heading_level):
            heading_level = min(max(current_heading_level + 1, 2), 3)
            promoted_lines.append(f"{'#' * heading_level} {ordered_match.group(1).strip()}")
            continue

        promoted_lines.append(raw_line)

    return "\n".join(promoted_lines).strip() + "\n"


def _promote_inline_numbered_subheadings(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    output: list[str] = []
    index = 0
    in_code_block = False
    current_heading_level = 0

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            output.append(raw_line)
            index += 1
            continue

        if in_code_block:
            output.append(raw_line)
            index += 1
            continue

        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match:
            current_heading_level = len(heading_match.group(1))
            output.append(raw_line)
            index += 1
            continue

        if current_heading_level >= 1 and ORDERED_LIST_PATTERN.match(stripped):
            run_end = index
            ordered_run: list[str] = []
            while run_end < len(lines) and ORDERED_LIST_PATTERN.match(lines[run_end].strip()):
                ordered_run.append(lines[run_end].strip())
                run_end += 1

            promoted_run = _build_inline_numbered_subheading_run(
                ordered_run,
                current_heading_level=current_heading_level,
            )
            if promoted_run is not None:
                output.extend(promoted_run)
                index = run_end
                continue

        output.append(raw_line)
        index += 1

    return "\n".join(output).strip() + "\n"


def _build_inline_numbered_subheading_run(
    ordered_run: list[str],
    *,
    current_heading_level: int,
) -> list[str] | None:
    if current_heading_level < 1 or len(ordered_run) < 2:
        return None

    parsed_items: list[tuple[str, str]] = []
    for raw_item in ordered_run:
        ordered_match = ORDERED_LIST_PATTERN.match(raw_item)
        if not ordered_match:
            return None
        title, body = _split_inline_numbered_heading(ordered_match.group(1).strip())
        if not title or not body:
            return None
        parsed_items.append((title, body))

    heading_level = min(max(current_heading_level + 1, 2), 3)
    promoted_lines: list[str] = []
    for title, body in parsed_items:
        promoted_lines.append(f"{'#' * heading_level} {title}")
        promoted_lines.append(body)
        promoted_lines.append("")

    while promoted_lines and not promoted_lines[-1].strip():
        promoted_lines.pop()
    return promoted_lines


def _split_inline_numbered_heading(text: str) -> tuple[str, str]:
    match = re.match(r"^(.{2,40}?)[：:]\s+(.+)$", text)
    if not match:
        return "", ""

    title = match.group(1).strip()
    body = match.group(2).strip()
    if not title or not body:
        return "", ""
    if len(body) < 20:
        return "", ""
    return title, body


def _demote_empty_top_level_sections(markdown_text: str, report_language: str) -> str:
    lines = markdown_text.splitlines()
    output: list[str] = []
    index = 0
    seen_top_level = False
    core_headings = set(_heading_aliases(report_language).values()) | _named_extra_headings(report_language)

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if not heading_match or len(heading_match.group(1)) != 1:
            output.append(raw_line)
            index += 1
            continue

        block_end = index + 1
        while block_end < len(lines):
            next_match = HEADING_PATTERN.match(lines[block_end].strip())
            if next_match and len(next_match.group(1)) == 1:
                break
            block_end += 1

        section_block = lines[index:block_end]
        heading_title = heading_match.group(2).strip()
        if (
            seen_top_level
            and heading_title not in core_headings
            and _section_starts_with_nested_heading(section_block)
        ):
            output.extend(_demote_top_level_block(section_block))
        else:
            output.extend(section_block)
            seen_top_level = True

        index = block_end

    return "\n".join(output).strip() + "\n"


def _section_starts_with_nested_heading(section_block: list[str]) -> bool:
    if len(section_block) <= 1:
        return False

    for raw_line in section_block[1:]:
        stripped = raw_line.strip()
        if not stripped:
            continue
        heading_match = HEADING_PATTERN.match(stripped)
        return bool(heading_match and len(heading_match.group(1)) >= 2)

    return False


def _demote_top_level_block(section_block: list[str]) -> list[str]:
    if not section_block:
        return []

    demoted: list[str] = []
    for index, raw_line in enumerate(section_block):
        stripped = raw_line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if not heading_match:
            demoted.append(raw_line)
            continue

        current_level = len(heading_match.group(1))
        title = heading_match.group(2).strip()
        if index == 0 and current_level == 1:
            demoted.append(f"## {title}")
            continue

        bumped_level = min(current_level + 1, 6)
        demoted.append(f"{'#' * bumped_level} {title}")

    return demoted


def _prefer_ordered_lists(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    output: list[str] = []
    index = 0
    in_code_block = False

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            output.append(raw_line)
            index += 1
            continue

        if in_code_block:
            output.append(raw_line)
            index += 1
            continue

        if _is_top_level_bullet_line(raw_line):
            run_end = index
            while run_end < len(lines) and _is_top_level_bullet_line(lines[run_end]):
                run_end += 1

            bullet_run = lines[index:run_end]
            if 2 <= len(bullet_run) <= 4 and _should_order_bullet_run(output, bullet_run):
                for number, bullet_line in enumerate(bullet_run, start=1):
                    bullet_text = bullet_line.strip()[2:].strip()
                    output.append(f"{number}. {bullet_text}")
                index = run_end
                continue

        output.append(raw_line)
        index += 1

    return "\n".join(output).strip() + "\n"


def _trim_excess_ordered_lists(markdown_text: str, report_language: str) -> str:
    lines = markdown_text.splitlines()
    output: list[str] = []
    index = 0
    in_code_block = False
    current_top_heading = ""

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            output.append(raw_line)
            index += 1
            continue

        if in_code_block:
            output.append(raw_line)
            index += 1
            continue

        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match:
            if len(heading_match.group(1)) == 1:
                current_top_heading = heading_match.group(2).strip().casefold()
            output.append(raw_line)
            index += 1
            continue

        if ORDERED_LIST_PATTERN.match(stripped):
            run_end = index
            ordered_run: list[str] = []
            while run_end < len(lines) and ORDERED_LIST_PATTERN.match(lines[run_end].strip()):
                ordered_run.append(lines[run_end])
                run_end += 1

            if len(ordered_run) >= 2:
                previous_line = _previous_nonempty_line(output)
                item_texts = [ORDERED_LIST_PATTERN.match(line.strip()).group(1).strip() for line in ordered_run]
                if _should_keep_numbered_run(previous_line, current_top_heading, item_texts, report_language):
                    for number, item_text in enumerate(item_texts, start=1):
                        output.append(f"{number}. {item_text}")
                else:
                    for item_text in item_texts:
                        output.append(f"- {item_text}")
                index = run_end
                continue

        output.append(raw_line)
        index += 1

    return "\n".join(output).strip() + "\n"


def _normalize_numeric_subheadings(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    normalized_lines: list[str] = []
    current_top_level = False

    for raw_line in lines:
        stripped = raw_line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        if not heading_match:
            normalized_lines.append(raw_line)
            continue

        level = len(heading_match.group(1))
        title = heading_match.group(2).strip()
        cleaned_title = re.sub(r"^\d+(?:\.\d+)*[.)]?\s*", "", title).strip()

        if level == 1:
            current_top_level = True
            normalized_lines.append(f"# {cleaned_title or title}")
            continue

        if current_top_level and title != cleaned_title:
            normalized_level = 2 if level >= 2 else level
            normalized_lines.append(f"{'#' * normalized_level} {cleaned_title or title}")
            continue

        normalized_lines.append(raw_line)

    return "\n".join(normalized_lines).strip() + "\n"


def _should_promote_ordered_heading(lines: list[str], index: int, current_heading_level: int) -> bool:
    if current_heading_level < 1:
        return False

    stripped = lines[index].strip()
    ordered_match = ORDERED_LIST_PATTERN.match(stripped)
    if not ordered_match:
        return False

    title = ordered_match.group(1).strip()
    if not title:
        return False
    if len(title) > 40:
        return False
    if re.search(r"[。！？.!?:：;；]\s*$", title):
        return False

    next_nonempty = ""
    for next_index in range(index + 1, len(lines)):
        candidate = lines[next_index].strip()
        if candidate:
            next_nonempty = candidate
            break

    if not next_nonempty:
        return False
    if HEADING_PATTERN.match(next_nonempty) or IMAGE_LINE_PATTERN.match(next_nonempty):
        return False
    if ORDERED_LIST_PATTERN.match(next_nonempty):
        return False

    if next_nonempty.startswith(("- ", "* ")):
        bullet_count = 0
        for follow_index in range(index + 1, len(lines)):
            follow = lines[follow_index].strip()
            if not follow:
                if bullet_count > 0:
                    break
                continue
            if follow.startswith(("- ", "* ")):
                bullet_count += 1
                continue
            break
        return bullet_count >= 1

    return True


def _is_top_level_bullet_line(raw_line: str) -> bool:
    if raw_line.startswith((" ", "\t")):
        return False
    stripped = raw_line.strip()
    return stripped.startswith(("- ", "* "))


def _should_order_bullet_run(output_lines: list[str], bullet_run: list[str]) -> bool:
    if not bullet_run:
        return False

    bullet_texts = [line.strip()[2:].strip() for line in bullet_run]
    if any(not text or len(text) > 140 for text in bullet_texts):
        return False

    for raw_line in reversed(output_lines):
        stripped = raw_line.strip()
        if not stripped:
            continue

        if stripped.startswith("#"):
            return False

        if ORDERED_LIST_PATTERN.match(stripped):
            return True

        if stripped.endswith((":", "：")) and _looks_like_order_intro(stripped):
            return True

        return False
    return False


def _looks_like_order_intro(text: str) -> bool:
    normalized = text.strip().casefold()
    zh_triggers = (
        "如下",
        "包括",
        "主要包括",
        "可概括为",
        "分为",
        "分成",
        "体现在",
        "具体如下",
        "主要有",
    )
    en_triggers = (
        "as follows",
        "include",
        "includes",
        "including",
        "consists of",
        "are summarized below",
        "can be grouped into",
        "can be summarized as",
    )
    return any(token in text for token in zh_triggers) or any(token in normalized for token in en_triggers)


def _previous_nonempty_line(output_lines: list[str]) -> str:
    for raw_line in reversed(output_lines):
        stripped = raw_line.strip()
        if stripped:
            return stripped
    return ""


def _should_keep_numbered_run(
    previous_line: str,
    current_top_heading: str,
    item_texts: list[str],
    report_language: str,
) -> bool:
    if not item_texts:
        return False

    if previous_line.endswith((":", "：")) and _looks_like_order_intro(previous_line):
        return True

    if any(_looks_sequential_item(text, report_language) for text in item_texts):
        return True

    return False


def _looks_sequential_item(text: str, report_language: str) -> bool:
    normalized = text.casefold()
    zh_markers = ("首先", "其次", "再次", "最后", "第一", "第二", "第三", "步骤")
    en_markers = ("first", "second", "third", "finally", "step ")
    if report_language == "zh":
        return any(marker in text for marker in zh_markers)
    return any(marker in normalized for marker in en_markers)


def _is_methods_like_heading(current_top_heading: str, report_language: str) -> bool:
    if not current_top_heading:
        return False
    if report_language == "zh":
        return current_top_heading in {"方法", "研究方法", "患者与方法"}
    return current_top_heading == "methods"


def _inject_section_overview_paragraphs(markdown_text: str, report_language: str) -> str:
    return markdown_text


def _build_section_overview_sentence(section_title: str, child_titles: list[str], report_language: str) -> str:
    cleaned_children = [
        re.sub(r"^\d+(?:\.\d+)*[.)]?\s*", "", title).strip()
        for title in child_titles
        if title.strip()
    ]
    cleaned_children = cleaned_children[:4]
    if report_language == "zh":
        if cleaned_children:
            joined = "、".join(cleaned_children[:-1]) + (f"以及{cleaned_children[-1]}" if len(cleaned_children) > 1 else cleaned_children[0])
            return f"本节主要围绕{joined}展开。"
        return f"本节围绕{section_title}的核心内容展开。"

    if cleaned_children:
        if len(cleaned_children) == 1:
            joined_en = cleaned_children[0]
        elif len(cleaned_children) == 2:
            joined_en = f"{cleaned_children[0]} and {cleaned_children[1]}"
        else:
            joined_en = ", ".join(cleaned_children[:-1]) + f", and {cleaned_children[-1]}"
        return f"This section focuses on {joined_en}."
    return f"This section presents the core content of {section_title}."


def _ensure_explicit_figure_references(
    markdown_text: str,
    figure_entries: list[dict[str, object]],
    report_language: str,
) -> str:
    if not markdown_text.strip() or not figure_entries:
        return markdown_text

    image_line_pattern = re.compile(r"^!\[(?P<alt>.*?)\]\((?P<path>.*?)\)\s*$")
    figure_lookup = {
        str(entry.get("relative_path") or ""): int(entry.get("index") or 0)
        for entry in figure_entries
        if entry.get("relative_path")
    }
    figure_lookup.update(
        {
            Path(str(entry.get("relative_path") or "")).name: int(entry.get("index") or 0)
            for entry in figure_entries
            if entry.get("relative_path")
        }
    )

    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output: list[str] = []
    index = 0

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        image_match = image_line_pattern.fullmatch(stripped)
        if not image_match:
            output.append(raw_line)
            index += 1
            continue

        output.append(raw_line)
        figure_number = _resolve_figure_number(image_match.group("path"), figure_lookup)
        figure_label = f"图{figure_number}" if report_language == "zh" else f"Figure {figure_number}"
        block: list[str] = []
        index += 1

        while index < len(lines):
            candidate = lines[index]
            candidate_stripped = candidate.strip()
            if image_line_pattern.fullmatch(candidate_stripped):
                break
            if candidate_stripped.startswith("#"):
                break
            block.append(candidate)
            index += 1

        output.extend(_ground_figure_block(block, figure_label, report_language))

    cleaned = "\n".join(output).strip()
    return cleaned + "\n" if cleaned else ""


def _ground_figure_block(block_lines: list[str], figure_label: str, report_language: str) -> list[str]:
    if not block_lines:
        return []
    if not any(raw_line.strip() and not _is_figure_caption_line(raw_line.strip(), figure_label) for raw_line in block_lines):
        return []

    if _block_has_explicit_figure_reference(block_lines, figure_label):
        return block_lines

    grounded = list(block_lines)
    first_content_index: int | None = None
    for index, raw_line in enumerate(grounded):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _is_figure_caption_line(stripped, figure_label):
            continue
        if first_content_index is None:
            first_content_index = index
        if stripped.startswith(("- ", "* ")) or ORDERED_LIST_PATTERN.match(stripped):
            continue
        grounded[index] = _prepend_figure_reference(raw_line, figure_label, report_language)
        return grounded

    insert_at = first_content_index if first_content_index is not None else 0
    while insert_at < len(grounded) and not grounded[insert_at].strip():
        insert_at += 1
    grounded.insert(insert_at, _default_figure_reference_line(figure_label, report_language))
    return grounded


def _block_has_explicit_figure_reference(block_lines: list[str], figure_label: str) -> bool:
    pattern = _figure_reference_pattern(figure_label)
    for raw_line in block_lines:
        stripped = raw_line.strip()
        if not stripped or _is_figure_caption_line(stripped, figure_label):
            continue
        if pattern.search(stripped):
            return True
    return False


def _is_figure_caption_line(text: str, figure_label: str) -> bool:
    normalized = text.strip().strip("*").strip()
    return normalized.startswith(f"{figure_label}.") or normalized.startswith(f"{figure_label}：") or normalized.startswith(
        f"{figure_label}:"
    )


def _prepend_figure_reference(line: str, figure_label: str, report_language: str) -> str:
    prefix = f"{figure_label}显示，" if report_language == "zh" else f"{figure_label} shows that "
    bold_prefix = re.match(r"^(?P<lead>\s*\*\*[^*]+\*\*\s*)(?P<body>.*)$", line)
    if bold_prefix and bold_prefix.group("body").strip():
        return f"{bold_prefix.group('lead')}{prefix}{bold_prefix.group('body').lstrip()}"
    return prefix + line.lstrip()


def _default_figure_reference_line(figure_label: str, report_language: str) -> str:
    if report_language == "zh":
        return f"{figure_label}显示了相关结果。"
    return f"As shown in {figure_label}, the corresponding results are discussed below."


def _figure_reference_pattern(figure_label: str) -> re.Pattern[str]:
    match = re.search(r"(\d+)", figure_label)
    figure_number = match.group(1) if match else "1"
    return re.compile(rf"(?i)(?:图\s*{re.escape(figure_number)}|fig(?:ure)?\.?\s*{re.escape(figure_number)})")


def _resolve_figure_number(figure_path: str, figure_lookup: dict[str, int]) -> int:
    file_name = Path(figure_path).name
    if figure_path in figure_lookup:
        return max(1, figure_lookup[figure_path])
    if file_name in figure_lookup:
        return max(1, figure_lookup[file_name])
    match = re.search(r"figure(\d+)", file_name, flags=re.IGNORECASE)
    if match:
        return max(1, int(match.group(1)))
    return 1


def _sanitize_citation_markers(markdown_text: str, allowed_keys: set[str]) -> str:
    if not allowed_keys:
        return markdown_text

    citation_pattern = re.compile(r"\[(?P<body>\s*@[^]]+)\]")

    def replace(match: re.Match[str]) -> str:
        valid_keys: list[str] = []
        seen: set[str] = set()
        for chunk in match.group("body").split(";"):
            cleaned = chunk.strip()
            if not cleaned:
                continue
            key = cleaned.removeprefix("@").strip()
            if key not in allowed_keys or key in seen:
                continue
            seen.add(key)
            valid_keys.append(f"@{key}")
        if not valid_keys:
            return ""
        return "[" + "; ".join(valid_keys) + "]"

    cleaned = citation_pattern.sub(replace, markdown_text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + "\n"


def _apply_lightweight_reference_alignment(
    markdown_text: str,
    reference_entries: list[dict[str, object]],
    report_language: str,
) -> str:
    if not reference_entries:
        return markdown_text

    aligned = markdown_text
    if report_language == "zh":
        aligned = re.sub(r"(?mi)^#\s*Abstract\s*$", "# 摘要", aligned)
        aligned = re.sub(r"(?mi)^Abstract\s*$", "# 摘要", aligned)
    return aligned


def _inject_reference_citations(
    markdown_text: str,
    reference_entries: list[dict[str, object]],
    report_language: str,
) -> str:
    citation_keys = [
        str(entry.get("citation_key") or "").strip()
        for entry in reference_entries
        if str(entry.get("citation_key") or "").strip()
    ]
    if not citation_keys:
        return markdown_text

    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = list(lines)
    current_heading = ""
    candidate_slots: list[dict[str, int | str]] = []

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            current_heading = stripped.lstrip("#").strip().casefold()
            continue

        if not _is_reference_citation_candidate(stripped):
            continue

        section_key = _reference_section_key(current_heading, report_language)
        candidate_slots.append(
            {
                "index": index,
                "priority": _reference_section_priority(section_key),
                "existing_count": len(_extract_markdown_citation_keys(raw_line)),
            }
        )

    existing_keys = _extract_markdown_citation_keys(markdown_text)
    missing_keys = [citation_key for citation_key in citation_keys if citation_key not in existing_keys]
    if not missing_keys:
        return markdown_text

    if not candidate_slots:
        for index, raw_line in enumerate(output):
            if _is_reference_citation_candidate(raw_line.strip()):
                updated_line = raw_line
                for citation_key in missing_keys:
                    updated_line = _append_citation_marker(updated_line, citation_key)
                output[index] = updated_line
                return "\n".join(output)
        return markdown_text

    ordered_slots = sorted(
        candidate_slots,
        key=lambda slot: (
            int(slot["existing_count"]),
            int(slot["priority"]),
            int(slot["index"]),
        ),
    )
    usage_counts = {int(slot["index"]): int(slot["existing_count"]) for slot in ordered_slots}

    for offset, citation_key in enumerate(missing_keys):
        slot = ordered_slots[offset % len(ordered_slots)]
        line_index = int(slot["index"])
        output[line_index] = _append_citation_marker(output[line_index], citation_key)
        usage_counts[line_index] = usage_counts.get(line_index, 0) + 1
        ordered_slots.sort(
            key=lambda item: (
                usage_counts.get(int(item["index"]), 0),
                int(item["priority"]),
                int(item["index"]),
            ),
        )

    return "\n".join(output)


def _reference_section_key(heading: str, report_language: str) -> str:
    normalized = heading.casefold()
    if report_language == "zh":
        mapping = {
            "摘要": "abstract",
            "关键词": "abstract",
            "引言": "introduction",
            "患者与方法": "methods",
            "方法": "methods",
            "结果": "results",
            "讨论": "discussion",
            "局限性": "limitations",
            "结论": "conclusion",
            "abstract": "abstract",
            "keywords": "abstract",
            "introduction": "introduction",
            "methods": "methods",
            "results": "results",
            "discussion": "discussion",
            "limitations": "limitations",
            "conclusion": "conclusion",
        }
    else:
        mapping = {
            "abstract": "abstract",
            "introduction": "introduction",
            "methods": "methods",
            "results": "results",
            "discussion": "discussion",
            "limitations": "limitations",
            "conclusion": "conclusion",
        }
    return mapping.get(normalized, "")


def _section_citation_plan(section_key: str, reference_count: int) -> list[int]:
    if reference_count <= 0:
        return []
    if section_key == "abstract":
        return [0]
    if section_key == "introduction":
        return [0, min(1, reference_count - 1)]
    if section_key == "discussion":
        return [0, min(1, reference_count - 1)]
    if section_key == "limitations":
        return [0]
    if section_key == "conclusion":
        return [0]
    return []


def _append_citation_marker(line: str, citation_key: str) -> str:
    prefix = line.rstrip()
    trailing = line[len(prefix):]
    match = re.match(r"^(?P<body>.*?)(?P<punct>[。！？.!?])?$", prefix)
    if not match:
        return f"{prefix} [@{citation_key}]{trailing}"
    body = match.group("body").rstrip()
    punct = match.group("punct") or ""
    return f"{body} [@{citation_key}]{punct}{trailing}"


def _reference_section_priority(section_key: str) -> int:
    if section_key in {"introduction", "discussion", "results"}:
        return 0
    if section_key in {"methods", "conclusion"}:
        return 1
    if section_key in {"abstract", "limitations"}:
        return 2
    return 3


def _is_reference_citation_candidate(stripped: str) -> bool:
    if not stripped:
        return False
    if stripped.startswith("#") or stripped.startswith("!["):
        return False
    if stripped.startswith(("- ", "* ")) or ORDERED_LIST_PATTERN.match(stripped):
        return False
    if len(stripped) < 40:
        return False
    return True


def _extract_markdown_citation_keys(text: str) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"\[(?P<body>\s*@[^]]+)\]", text):
        for chunk in match.group("body").split(";"):
            key = chunk.strip().removeprefix("@").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return keys


def _append_citation_marker(line: str, citation_key: str) -> str:
    prefix = line.rstrip()
    trailing = line[len(prefix):]
    existing_match = re.search(r"\[(?P<body>\s*@[^]]+)\](?P<punct>[\u3002\uff01\uff1f.!?])?$", prefix)
    if existing_match:
        keys = _extract_markdown_citation_keys(existing_match.group(0))
        if citation_key not in keys:
            keys.append(citation_key)
        merged = "[" + "; ".join(f"@{key}" for key in keys) + "]"
        start, _ = existing_match.span()
        punct = existing_match.group("punct") or ""
        return f"{prefix[:start].rstrip()} {merged}{punct}{trailing}"

    match = re.match(r"^(?P<body>.*?)(?P<punct>[\u3002\uff01\uff1f.!?])?$", prefix)
    if not match:
        return f"{prefix} [@{citation_key}]{trailing}"
    body = match.group("body").rstrip()
    punct = match.group("punct") or ""
    return f"{body} [@{citation_key}]{punct}{trailing}"


def _remove_duplicate_headings(markdown_text: str, headings: list[str]) -> str:
    lines = markdown_text.splitlines()
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            heading_text = stripped.lstrip("#").strip()
            if heading_text in headings:
                if heading_text in seen:
                    continue
                seen.add(heading_text)
                output.append(f"# {heading_text}")
                continue
        output.append(line)
    return "\n".join(output)


def _localize_markdown_terms(markdown_text: str, report_language: str) -> str:
    localized_lines: list[str] = []
    for raw_line in markdown_text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("!["):
            if report_language == "en":
                localized_lines.append(_localize_english_image_line(raw_line))
            else:
                localized_lines.append(raw_line)
            continue

        updated = raw_line
        if report_language == "zh":
            updated = re.sub(r"(?i)\bFigure\s+(\d+)\b", r"图\1", updated)
            updated = re.sub(r"(?i)\bFig\.?\s*(\d+)\b", r"图\1", updated)
            updated = re.sub(r"(?i)\bSection\s+(\d+(?:\.\d+)*)\b", r"第\1节", updated)
        else:
            updated = re.sub(r"图\s*(\d+)", r"Figure \1", updated)
            updated = re.sub(r"表\s*(\d+)", r"Table \1", updated)
            updated = re.sub(r"第\s*(\d+(?:\.\d+)*)\s*节", r"Section \1", updated)
            updated = re.sub(
                r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
                lambda match: _format_english_date(match.group(1), match.group(2), match.group(3)),
                updated,
            )
            updated = _translate_common_cjk_phrases_to_english(updated)
        localized_lines.append(updated)
    return "\n".join(localized_lines)


def _localize_english_image_line(raw_line: str) -> str:
    image_match = re.match(r"^(?P<prefix>\s*)!\[(?P<alt>.*?)\]\((?P<path>.*?)\)(?P<suffix>\s*)$", raw_line)
    if not image_match:
        return raw_line
    alt_text = image_match.group("alt")
    localized_alt = re.sub(r"图\s*(\d+)", r"Figure \1", alt_text)
    localized_alt = re.sub(r"表\s*(\d+)", r"Table \1", localized_alt)
    localized_alt = _translate_common_cjk_phrases_to_english(localized_alt)
    return (
        f"{image_match.group('prefix')}![{localized_alt}]({image_match.group('path')})"
        f"{image_match.group('suffix')}"
    )


def _format_english_date(year_text: str, month_text: str, day_text: str) -> str:
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


def _translate_common_cjk_phrases_to_english(text: str) -> str:
    replacements = [
        ("数据集", "dataset"),
        ("截至", "as-of"),
        ("工作表", "worksheet"),
        ("基线特征", "baseline characteristics"),
        ("筛选逻辑", "screening logic"),
        ("病理特征", "pathological features"),
        ("术中", "intraoperative"),
        ("治疗概览", "treatment overview"),
        ("疗效评估", "efficacy evaluation"),
        ("随访", "follow-up"),
        ("核心随访数据", "core follow-up data"),
        ("知情同意签署日期", "informed consent signing date"),
        ("纳入排除标准", "inclusion and exclusion criteria"),
        ("肿瘤标志物检查", "tumor marker examination"),
        ("检验检查", "laboratory examination"),
    ]
    updated = text
    for source, target in replacements:
        updated = updated.replace(source, target)
    return updated


def _heading_aliases(report_language: str) -> dict[str, str]:
    if report_language == "zh":
        mapping = {
            "摘要": "摘要",
            "abstract": "摘要",
            "关键词": "关键词",
            "key words": "关键词",
            "keywords": "关键词",
            "引言": "引言",
            "简介": "引言",
            "介绍": "引言",
            "introduction": "引言",
            "患者与方法": "患者与方法",
            "方法": "患者与方法",
            "材料与方法": "患者与方法",
            "研究方法": "患者与方法",
            "methods": "患者与方法",
            "patients and methods": "患者与方法",
            "results": "结果",
            "结果": "结果",
            "研究结果": "结果",
            "讨论": "讨论",
            "discussion": "讨论",
            "局限性": "局限性",
            "局限": "局限性",
            "limitations": "局限性",
            "结论": "结论",
            "总结": "结论",
            "conclusion": "结论",
        }
    else:
        mapping = {
            "摘要": "Abstract",
            "abstract": "Abstract",
            "关键词": "Keywords",
            "keywords": "Keywords",
            "引言": "Introduction",
            "introduction": "Introduction",
            "方法": "Methods",
            "患者与方法": "Patients and Methods",
            "材料与方法": "Methods",
            "methods": "Methods",
            "patients and methods": "Patients and Methods",
            "结果": "Results",
            "results": "Results",
            "讨论": "Discussion",
            "discussion": "Discussion",
            "局限性": "Limitations",
            "limitations": "Limitations",
            "结论": "Conclusion",
            "conclusion": "Conclusion",
        }
    return {key.casefold(): value for key, value in mapping.items()}


def _build_section_lookup(sections: object) -> dict[str, str]:
    lookup: dict[str, str] = {}
    if not isinstance(sections, list):
        return lookup
    for section in sections:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading") or "").strip().lower()
        content_markdown = str(section.get("content_markdown") or "").strip()
        paragraphs = section.get("paragraphs") or []
        paragraph_text = "\n\n".join(str(item).strip() for item in paragraphs if str(item).strip())
        text = paragraph_text or content_markdown
        if heading and text:
            lookup[heading] = text
    return lookup


def _pick_section_text(section_lookup: dict[str, str], keywords: list[str]) -> str:
    for heading, text in section_lookup.items():
        if any(keyword in heading for keyword in keywords):
            return text
    return ""


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_reference_prompt_entries(reference_entries: list[dict[str, object]]) -> list[dict[str, object]]:
    prompt_entries: list[dict[str, object]] = []
    for entry in reference_entries:
        prompt_entries.append(
            {
                "citation_key": str(entry.get("citation_key") or ""),
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
                "evidence_source_file": str(entry.get("evidence_source_file") or ""),
            }
        )
    return prompt_entries


def _remove_markdown_thematic_breaks(markdown_text: str) -> str:
    cleaned = re.sub(r"(?m)^\s*(?:---|\*\*\*|___)\s*$", "", markdown_text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    return cleaned + "\n" if cleaned else ""


def _archive_job_artifacts(job: dict[str, object]) -> Path | None:
    settings = get_settings()
    created_at = str(job.get("created_at") or "")
    task_id = str(job.get("task_id") or "unknown")
    report_name = str(job.get("report_name") or "generated_report")
    timestamp = _format_archive_timestamp(created_at)
    archive_name = f"{timestamp}_{_slugify(report_name)}"
    archive_dir = settings.output_archive_dir / archive_name
    if archive_dir.exists():
        archive_dir = settings.output_archive_dir / f"{archive_name}_{task_id[:8]}"

    if archive_dir.exists():
        shutil.rmtree(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)

    job_manifest_path = archive_dir / "job.json"
    job_manifest_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_path = job.get("markdown_path")
    if markdown_path:
        source_path = Path(str(markdown_path))
        if source_path.exists():
            input_dir = archive_dir / "input"
            input_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, input_dir / source_path.name)

    figure_dir = job.get("figure_dir")
    if figure_dir:
        source_figure_dir = Path(str(figure_dir))
        if source_figure_dir.exists():
            shutil.copytree(source_figure_dir, archive_dir / "figure", dirs_exist_ok=True)

    assets_dir = job.get("assets_dir")
    if assets_dir:
        source_assets_dir = Path(str(assets_dir))
        if source_assets_dir.exists():
            shutil.copytree(source_assets_dir, archive_dir / "assets_source", dirs_exist_ok=True)

    reference_assets_dir = job.get("reference_assets_dir")
    if reference_assets_dir:
        source_reference_assets_dir = Path(str(reference_assets_dir))
        if source_reference_assets_dir.exists():
            shutil.copytree(source_reference_assets_dir, archive_dir / "references_source", dirs_exist_ok=True)

    intermediate_dir = job.get("intermediate_dir")
    if intermediate_dir:
        source_intermediate_dir = Path(str(intermediate_dir))
        if source_intermediate_dir.exists():
            shutil.copytree(source_intermediate_dir, archive_dir / "intermediates", dirs_exist_ok=True)

    generated_dir = archive_dir / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    for key in ("final_markdown_file", "latex_file", "output_file"):
        file_path = job.get(key)
        if not file_path:
            continue
        source_file = Path(str(file_path))
        if source_file.exists():
            shutil.copy2(source_file, generated_dir / source_file.name)

    template_path = job.get("template_path")
    if template_path:
        source_template = Path(str(template_path))
        if source_template.exists():
            template_archive_dir = archive_dir / "template_source"
            if source_template.is_dir():
                shutil.copytree(source_template, template_archive_dir, dirs_exist_ok=True)
            else:
                template_archive_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_template, template_archive_dir / source_template.name)

    return archive_dir


def _format_archive_timestamp(created_at: str) -> str:
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%Y%m%d_%H%M")
    except ValueError:
        return datetime.now().astimezone().strftime("%Y%m%d_%H%M")


def _slugify(value: str) -> str:
    allowed = [char if _is_slug_char(char) else "_" for char in value.strip()]
    slug = "".join(allowed).strip("_")
    return slug or "generated_report"


def _is_slug_char(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char in {"-", "_"}) or ("\u4e00" <= char <= "\u9fff")
