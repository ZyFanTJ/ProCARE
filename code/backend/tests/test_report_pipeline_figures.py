import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR))

from app.services.report_pipeline import _assign_result_images_to_subsections, _enforce_result_figure_distribution


def _image_lines_are_separated_by_text(markdown: str) -> bool:
    lines = markdown.splitlines()
    image_indexes = [index for index, line in enumerate(lines) if line.strip().startswith("![")]
    for previous, current in zip(image_indexes, image_indexes[1:]):
        between = [line.strip() for line in lines[previous + 1 : current] if line.strip()]
        if not any(not line.startswith("![") and not line.startswith("#") for line in between):
            return False
    return True


def test_result_images_use_original_names_when_numbered_paths_are_generic():
    subsection_titles = [
        "baseline",
        "comparison",
        "curve",
    ]
    image_lines = [
        "![Figure 1](figure/figure1.png)",
        "![Figure 2](figure/figure2.png)",
        "![Figure 3](figure/figure3.png)",
        "![Figure 4](figure/figure4.png)",
        "![Figure 5](figure/figure5.png)",
        "![Figure 6](figure/figure6.png)",
        "![Figure 7](figure/figure7.png)",
        "![Figure 8](figure/figure8.png)",
    ]
    ordered_content = {
        subsection_titles[0]: [],
        subsection_titles[1]: [],
        subsection_titles[2]: image_lines,
    }
    figure_entries = [
        {"index": 1, "file_name": "figure1.png", "relative_path": "figure/figure1.png", "original_name": "cohort_flow.png"},
        {"index": 2, "file_name": "figure2.png", "relative_path": "figure/figure2.png", "original_name": "cox_forest.png"},
        {"index": 3, "file_name": "figure3.png", "relative_path": "figure/figure3.png", "original_name": "followup_distribution.png"},
        {"index": 4, "file_name": "figure4.png", "relative_path": "figure/figure4.png", "original_name": "km_has_immunotherapy.png"},
        {"index": 5, "file_name": "figure5.png", "relative_path": "figure/figure5.png", "original_name": "km_has_tace.png"},
        {"index": 6, "file_name": "figure6.png", "relative_path": "figure/figure6.png", "original_name": "km_has_targeted_therapy.png"},
        {"index": 7, "file_name": "figure7.png", "relative_path": "figure/figure7.png", "original_name": "km_overall.png"},
        {"index": 8, "file_name": "figure8.png", "relative_path": "figure/figure8.png", "original_name": "missingness_top20.png"},
    ]

    assigned = _assign_result_images_to_subsections(
        ordered_content=ordered_content,
        subsection_titles=subsection_titles,
        figure_entries=figure_entries,
    )

    assert [Path(line.split("(", 1)[1].rstrip(")")).name for line in assigned["baseline"]] == [
        "figure1.png",
        "figure3.png",
        "figure8.png",
    ]
    assert [Path(line.split("(", 1)[1].rstrip(")")).name for line in assigned["comparison"]] == ["figure2.png"]
    assert [Path(line.split("(", 1)[1].rstrip(")")).name for line in assigned["curve"]] == [
        "figure4.png",
        "figure5.png",
        "figure6.png",
        "figure7.png",
    ]


def test_final_result_section_hard_moves_stacked_figures_to_matching_subsections():
    markdown = """# 结果

## 基线特征

基线段落。

## 主要结局相关因素分析

比较段落。

## Kaplan-Meier生存曲线

曲线段落。

![Figure 1](figure/figure1.png)
![Figure 2](figure/figure2.png)
![Figure 3](figure/figure3.png)
![Figure 4](figure/figure4.png)
![Figure 5](figure/figure5.png)
![Figure 6](figure/figure6.png)
![Figure 7](figure/figure7.png)
![Figure 8](figure/figure8.png)
"""
    figure_entries = [
        {"index": 1, "file_name": "figure1.png", "relative_path": "figure/figure1.png", "original_name": "cohort_flow.png"},
        {"index": 2, "file_name": "figure2.png", "relative_path": "figure/figure2.png", "original_name": "cox_forest.png"},
        {"index": 3, "file_name": "figure3.png", "relative_path": "figure/figure3.png", "original_name": "followup_distribution.png"},
        {"index": 4, "file_name": "figure4.png", "relative_path": "figure/figure4.png", "original_name": "km_has_immunotherapy.png"},
        {"index": 5, "file_name": "figure5.png", "relative_path": "figure/figure5.png", "original_name": "km_has_tace.png"},
        {"index": 6, "file_name": "figure6.png", "relative_path": "figure/figure6.png", "original_name": "km_has_targeted_therapy.png"},
        {"index": 7, "file_name": "figure7.png", "relative_path": "figure/figure7.png", "original_name": "km_overall.png"},
        {"index": 8, "file_name": "figure8.png", "relative_path": "figure/figure8.png", "original_name": "missingness_top20.png"},
    ]

    rewritten = _enforce_result_figure_distribution(markdown, figure_entries)

    baseline_block = rewritten.split("## 基线特征", 1)[1].split("## 主要结局相关因素分析", 1)[0]
    comparison_block = rewritten.split("## 主要结局相关因素分析", 1)[1].split("## Kaplan-Meier生存曲线", 1)[0]
    curve_block = rewritten.split("## Kaplan-Meier生存曲线", 1)[1]

    assert "figure1.png" in baseline_block
    assert "figure3.png" in baseline_block
    assert "figure8.png" in baseline_block
    assert "figure2.png" in comparison_block
    assert "figure4.png" in curve_block
    assert "figure5.png" in curve_block
    assert "figure6.png" in curve_block
    assert "figure7.png" in curve_block
    assert "figure2.png" not in curve_block
    assert _image_lines_are_separated_by_text(rewritten)
    lines = rewritten.splitlines()
    for file_name in ["figure1.png", "figure2.png", "figure3.png", "figure4.png", "figure5.png", "figure6.png", "figure7.png", "figure8.png"]:
        image_line_index = next(index for index, line in enumerate(lines) if file_name in line)
        before = [line.strip() for line in lines[max(0, image_line_index - 3) : image_line_index] if line.strip()]
        after = [line.strip() for line in lines[image_line_index + 1 : image_line_index + 4] if line.strip()]
        assert any(not line.startswith("![") and not line.startswith("#") for line in before)
        assert any(not line.startswith("![") and not line.startswith("#") for line in after)
    assert "![队列构建流程图](figure/figure1.png)" in baseline_block
    assert "![Cox模型危险比森林图](figure/figure2.png)" in comparison_block
    assert "![随访时间分布图](figure/figure3.png)" in baseline_block
    assert "![关键变量缺失情况分布图](figure/figure8.png)" in baseline_block
