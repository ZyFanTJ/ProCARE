import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Generator, Optional

from .settings_manager import SettingsManager


JOURNAL_FIGURES_SKILL = """---
name: journal-figures
description: Build publication-grade statistical figures for biomedical and clinical research reports.
---

# Journal Figures

Use this skill whenever the task generates charts, plots, diagrams, or figures for a research report.

## Required workflow

1. Read `implementation_plan.md` and `excel_info.json` before writing code.
2. Inspect actual columns and sample values before choosing figure types.
3. Use `publication_plotting.py` for all figure styling and saving.
4. Prefer a small number of high-information figures over many generic EDA plots.
5. Save every final figure to `plots/` as PNG, PDF, and SVG.
6. Write `plots/figure_manifest.json` describing every final figure.

## Figure selection

- Survival outcome: Kaplan-Meier curve with CI, censor marks when available, log-rank p-value, number-at-risk table, and clear time units.
- Effect estimates: forest plot with point estimate, 95% CI, null reference line, subgroup labels, and p-values where available.
- Group comparison: box/violin plus raw jittered observations, sample size, central tendency, interval, and statistical comparison if appropriate.
- Categorical comparison: grouped bar or dot plot with CI/error bars and sample size labels.
- Correlation: scatter plot with regression/smoother, confidence band, correlation coefficient, p-value, and notable outlier annotation if justified.
- Cohort construction: flow diagram with counts at each inclusion/exclusion step.
- Heatmap: only for dense matrix-style data; include clustering or meaningful ordering, scale label, and readable labels.

## Quality rules

- Do not create pie charts, 3D charts, rainbow palettes, decorative gradients, or chart junk.
- Do not leave figures as bare pandas `.plot()` output.
- Do not rely on chart titles for scientific meaning; use precise axis labels, legends, annotations, and manifest captions.
- Use color-blind-safe palettes and consistent group colors across figures.
- Use journal column sizes: single column about 85 mm, double column about 178 mm.
- Keep text legible at final print size.
- Include units in axis labels whenever the data supports them.
- If a required statistical element cannot be computed from available data, state that in `figure_manifest.json` and use the most informative valid alternative.

## Manifest schema

Write `plots/figure_manifest.json` as a list of objects:

```json
[
  {
    "figure_id": "figure1",
    "file_stem": "figure1_km_rfs",
    "figure_type": "kaplan_meier",
    "caption": "Kaplan-Meier recurrence-free survival by treatment group.",
    "variables": ["time_months", "event", "treatment_group"],
    "statistics": ["log-rank p=0.032", "number at risk shown"],
    "notes": []
  }
]
```

## Completion gate

Only print `TASK_DONE` after:

- final code runs without error;
- at least one final journal-grade figure exists in `plots/`;
- each final figure has PNG, PDF, and SVG versions;
- `plots/figure_manifest.json` exists and matches the generated figures.
"""


PUBLICATION_PLOTTING_HELPER = r'''"""Publication-grade plotting helpers for OpenCode-generated analysis scripts."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns


MM_TO_INCH = 1 / 25.4
SINGLE_COLUMN_IN = 85 * MM_TO_INCH
DOUBLE_COLUMN_IN = 178 * MM_TO_INCH


PALETTES = {
    "nature": ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F", "#8491B4", "#91D1C2", "#DC0000"],
    "nejm": ["#BC3C29", "#0072B5", "#E18727", "#20854E", "#7876B1", "#6F99AD", "#FFDC91", "#EE4C97"],
    "lancet": ["#00468B", "#ED0000", "#42B540", "#0099B4", "#925E9F", "#FDAF91", "#AD002A", "#ADB6B6"],
    "colorblind": ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#F0E442", "#56B4E9", "#E69F00", "#000000"],
}


def set_publication_style() -> None:
    """Apply restrained journal-style Matplotlib defaults."""
    sns.set_theme(style="ticks", context="paper")
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 8.5,
            "axes.labelsize": 9,
            "axes.titlesize": 9.5,
            "axes.titleweight": "bold",
            "xtick.labelsize": 7.8,
            "ytick.labelsize": 7.8,
            "legend.fontsize": 7.8,
            "legend.title_fontsize": 8.2,
            "figure.dpi": 150,
            "savefig.dpi": 600,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.8,
            "xtick.major.width": 0.7,
            "ytick.major.width": 0.7,
            "xtick.major.size": 3.0,
            "ytick.major.size": 3.0,
            "lines.linewidth": 1.4,
            "patch.linewidth": 0.8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "axes.grid": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def get_palette(n_colors: int = 8, palette_name: str = "nature") -> list[str]:
    colors = PALETTES.get(palette_name, PALETTES["nature"])
    if n_colors <= len(colors):
        return colors[:n_colors]
    repeats = math.ceil(n_colors / len(colors))
    return (colors * repeats)[:n_colors]


def journal_size(width: str = "single", height_ratio: float = 0.72) -> tuple[float, float]:
    base = DOUBLE_COLUMN_IN if width == "double" else SINGLE_COLUMN_IN
    return base, max(1.9, base * height_ratio)


def new_figure(width: str = "single", height_ratio: float = 0.72):
    set_publication_style()
    fig, ax = plt.subplots(figsize=journal_size(width, height_ratio), constrained_layout=True)
    return fig, ax


def clean_axis(ax, *, light_y_grid: bool = False) -> None:
    sns.despine(ax=ax)
    ax.tick_params(axis="both", which="major", direction="out")
    if light_y_grid:
        ax.grid(axis="y", color="#E5E7EB", linewidth=0.55)
        ax.set_axisbelow(True)


def format_p_value(p_value: float | None) -> str:
    if p_value is None or not np.isfinite(p_value):
        return "p not available"
    if p_value < 0.001:
        return "p<0.001"
    return f"p={p_value:.3f}"


def save_publication_figure(
    fig,
    output_dir: str | Path,
    file_stem: str,
    *,
    close: bool = True,
    pad_inches: float = 0.04,
) -> dict[str, str]:
    """Save PNG, PDF, and SVG variants. Returns absolute paths as strings."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in file_stem).strip("_") or "figure"
    paths = {
        "png": out_dir / f"{safe_stem}.png",
        "pdf": out_dir / f"{safe_stem}.pdf",
        "svg": out_dir / f"{safe_stem}.svg",
    }
    fig.savefig(paths["png"], dpi=600, bbox_inches="tight", pad_inches=pad_inches, facecolor="white")
    fig.savefig(paths["pdf"], bbox_inches="tight", pad_inches=pad_inches, facecolor="white")
    fig.savefig(paths["svg"], bbox_inches="tight", pad_inches=pad_inches, facecolor="white")
    print(f"[INFO] Saved plot: {paths['png']}")
    if close:
        plt.close(fig)
    return {key: str(path.resolve()) for key, path in paths.items()}


def write_figure_manifest(output_dir: str | Path, figures: Iterable[dict[str, Any]]) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "figure_manifest.json"
    payload = list(figures)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def validate_publication_outputs(output_dir: str | Path) -> tuple[bool, list[str]]:
    out_dir = Path(output_dir)
    errors: list[str] = []
    manifest_path = out_dir / "figure_manifest.json"
    if not manifest_path.exists():
        errors.append("Missing plots/figure_manifest.json")
        return False, errors
    try:
        figures = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"Invalid figure_manifest.json: {exc}"]
    if not isinstance(figures, list) or not figures:
        errors.append("figure_manifest.json must contain at least one figure")
        return False, errors
    for item in figures:
        stem = str(item.get("file_stem") or "").strip()
        if not stem:
            errors.append("A manifest item is missing file_stem")
            continue
        for ext in ("png", "pdf", "svg"):
            path = out_dir / f"{stem}.{ext}"
            if not path.exists():
                errors.append(f"Missing {path.name}")
            elif path.stat().st_size < 2048:
                errors.append(f"{path.name} is too small to be a valid publication figure")
    return not errors, errors
'''


def _get_configured_api_key() -> str:
    try:
        settings = SettingsManager().get_settings()
    except Exception:
        return ""

    api_keys = settings.get("api_keys") or {}
    if isinstance(api_keys, dict):
        for provider in ("openai", "google", "deepseek", "minimax"):
            key = str(api_keys.get(provider) or "").strip()
            if key:
                return key
    return str(settings.get("api_key") or "").strip()


class OpenCodeRunner:
    """
    Runner that integrates with the external `opencode` CLI.
    Expects opencode to be available in the system PATH.
    """

    def __init__(self, work_dir: str, attach_url: Optional[str] = None):
        self.work_dir = Path(work_dir)
        self.attach_url = attach_url

    def prepare_workspace(self, plan: Dict, excel_info: Dict) -> Dict[str, Any]:
        """Prepare OpenCode config, local skills, helper files, and instructions."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        (self.work_dir / ".git").mkdir(exist_ok=True)
        (self.work_dir / "plots").mkdir(exist_ok=True)
        excel_info_path = self.work_dir / "excel_info.json"
        if not excel_info_path.exists():
            excel_info_path.write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")
        plan_path = self.work_dir / "plan.json"
        if not plan_path.exists():
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_opencode_config()
        self._write_journal_figures_skill()
        self._write_publication_plotting_helper()
        instruction_path = self.generate_instruction_markdown(plan, excel_info)
        return {
            "instruction_path": str(instruction_path),
            "attach_files": [
                "implementation_plan.md",
                "excel_info.json",
                "publication_plotting.py",
                ".opencode/skills/journal-figures/SKILL.md",
            ],
            "prompt": self.build_analysis_prompt(),
        }

    def _write_opencode_config(self) -> Path:
        config = {
            "$schema": "https://opencode.ai/config.json",
            "permission": {
                "edit": "allow",
                "bash": "allow",
                "skill": {
                    "journal-figures": "allow",
                },
            },
        }
        config_path = self.work_dir / "opencode.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return config_path

    def _write_journal_figures_skill(self) -> Path:
        skill_dir = self.work_dir / ".opencode" / "skills" / "journal-figures"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(JOURNAL_FIGURES_SKILL, encoding="utf-8")
        return skill_path

    def _write_publication_plotting_helper(self) -> Path:
        helper_path = self.work_dir / "publication_plotting.py"
        helper_path.write_text(PUBLICATION_PLOTTING_HELPER, encoding="utf-8")
        return helper_path

    def generate_instruction_markdown(self, plan: Dict, excel_info: Dict) -> Path:
        """
        Generates implementation_plan.md in the workspace.
        """
        md_lines = [
            "# Implementation Plan",
            "",
            "## Objective",
            str(plan.get("objective") or "No objective provided"),
            "",
            "## Steps",
        ]
        for i, step in enumerate(plan.get("steps", []) or [], start=1):
            md_lines.append(f"{i}. {step}")

        md_lines.extend(
            [
                "",
                "## Data Context",
                f"Original Data Path: {excel_info.get('path', 'unknown')}",
                "Use `excel_info.json` for exact sheet names, columns, inferred types, sample values, and profile notes.",
                "",
                "## OpenCode Skills",
                "- Use the `journal-figures` skill for all visualization work.",
                "- The skill is installed locally at `.opencode/skills/journal-figures/SKILL.md`.",
                "- Use `publication_plotting.py` for style, sizing, palettes, saving, and figure output validation.",
                "",
                "## Requirements",
                "- Work only inside the current job directory.",
                "- Write the final runnable entry point to `analysis.py` unless a modular `main.py` is more appropriate.",
                "- Create modular helpers when the analysis is complex, but keep `analysis.py` or `main.py` as the executable entry point.",
                "- Save generated final figures to the `plots/` directory.",
                "- Save each final figure as `.png`, `.pdf`, and `.svg`.",
                "- Write `plots/figure_manifest.json` using the schema from the `journal-figures` skill.",
                "- Avoid generic EDA-only outputs such as bare histograms or non-null-count bars unless they directly answer the research objective.",
                "- Print `TASK_DONE` only after the script runs successfully and publication-grade figure outputs validate.",
                "- Print `TASK_FAILED` and a concise reason if the data cannot support a valid analysis figure.",
                "- Preserve useful intermediate statistical summaries as JSON/CSV/TXT files.",
                "",
                "## Figure Quality Gate",
                "- Prefer high-information clinical or statistical figures over decorative charts.",
                "- Include sample sizes, units, p-values/effect sizes/intervals when computable.",
                "- Use consistent group ordering and colors across figures.",
                "- Do not use pie charts, 3D charts, rainbow palettes, gradient backgrounds, or chart junk.",
                "",
                "## Plan Context",
                "```json",
                json.dumps(plan.get("context", {}), ensure_ascii=False, indent=2),
                "```",
            ]
        )

        md_path = self.work_dir / "implementation_plan.md"
        md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        return md_path

    def build_analysis_prompt(self) -> str:
        return (
            "Read `implementation_plan.md`, `excel_info.json`, and `publication_plotting.py`. "
            "Use the `journal-figures` skill before implementing visualization code. "
            "Create complete, runnable analysis code in `analysis.py` or `main.py`. "
            "Generate only research-relevant publication-grade figures in `plots/`, "
            "with PNG, PDF, SVG, and `plots/figure_manifest.json`. "
            "Run the code yourself, fix errors, and stop only when the quality gate passes."
        )

    def stream_run(
        self,
        prompt: str,
        model: Optional[str] = None,
        attach_files: Optional[list[str]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Executes opencode CLI as a subprocess and streams its output.
        """
        import codecs
        import logging
        import os
        import shutil
        import sys

        opencode_bin = shutil.which("opencode")
        if not opencode_bin:
            yield {"type": "log", "content": "[Error] `opencode` command not found. Please install OpenCode CLI.\n"}
            yield {"type": "done", "success": False}
            return

        cmd = [opencode_bin, "run"]

        # In opencode CLI, the positional argument must come before options.
        cmd.append(prompt)

        if self.attach_url:
            cmd.extend(["--attach", self.attach_url])

        # opencode/node can be sensitive to backslashes in --dir.
        work_dir_str = str(self.work_dir).replace("\\", "/")
        cmd.extend(["--dir", work_dir_str])

        if model:
            cmd.extend(["--model", model])

        if str(os.environ.get("OPENCODE_PRINT_LOGS", "1")).lower() not in {"0", "false", "no"}:
            cmd.extend(["--print-logs", "--log-level", os.environ.get("OPENCODE_LOG_LEVEL", "INFO")])

        if attach_files:
            for file_name in attach_files:
                file_path = self.work_dir / file_name
                if file_path.exists():
                    cmd.extend(["--file", str(file_path).replace("\\", "/")])
                else:
                    print(f"[Warning] Context file {file_name} not found in {self.work_dir}")

        logging.info("Executing OpenCode command: %s", " ".join(cmd))
        print(f"Executing OpenCode command: {' '.join(cmd)}")
        live_log_path = self.work_dir / "opencode_live.log"
        live_log_path.write_text(f"Executing OpenCode command: {' '.join(cmd)}\n", encoding="utf-8")

        yield {"type": "phase", "phase": "opencode_init"}
        yield {"type": "step_start", "step": 0, "code_len": 0}

        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["FORCE_COLOR"] = "1"
            if not env.get("OPENAI_API_KEY"):
                configured_api_key = _get_configured_api_key()
                if configured_api_key:
                    env["OPENAI_API_KEY"] = configured_api_key

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(self.work_dir),
                env=env,
                shell=False,
            )

            if process.stdout:
                fd = process.stdout.fileno()
                decoder = codecs.getincrementaldecoder("utf-8")("replace")
                while True:
                    chunk = os.read(fd, 1024)
                    if not chunk:
                        text_chunk = decoder.decode(b"", final=True)
                        if text_chunk:
                            yield {"type": "log", "content": text_chunk}
                        break
                    text_chunk = decoder.decode(chunk, final=False)
                    if text_chunk:
                        try:
                            print(text_chunk, end="", flush=True)
                        except UnicodeEncodeError:
                            stdout_encoding = sys.stdout.encoding or "utf-8"
                            safe_chunk = text_chunk.encode(stdout_encoding, errors="replace").decode(stdout_encoding)
                            print(safe_chunk, end="", flush=True)
                        with live_log_path.open("a", encoding="utf-8", errors="replace") as log_file:
                            log_file.write(text_chunk)
                        yield {"type": "log", "content": text_chunk}

            process.wait()
            success = process.returncode == 0

            if not success:
                error_msg = f"\n[Error] opencode process exited with code {process.returncode}"
                print(error_msg)
                with live_log_path.open("a", encoding="utf-8", errors="replace") as log_file:
                    log_file.write(error_msg + "\n")
                yield {"type": "log", "content": error_msg}

            analysis_exists = (self.work_dir / "analysis.py").exists()
            main_exists = (self.work_dir / "main.py").exists()
            if success and not (analysis_exists or main_exists):
                yield {
                    "type": "log",
                    "content": "\n[Warning] opencode finished, but neither analysis.py nor main.py was found.",
                }
                with live_log_path.open("a", encoding="utf-8", errors="replace") as log_file:
                    log_file.write("\n[Warning] opencode finished, but neither analysis.py nor main.py was found.\n")
                success = False

            with live_log_path.open("a", encoding="utf-8", errors="replace") as log_file:
                log_file.write(f"\nOpenCode done. success={success}\n")
            yield {"type": "done", "success": success}

        except FileNotFoundError:
            message = "[Error] `opencode` command not found. Please install OpenCode CLI.\n"
            with live_log_path.open("a", encoding="utf-8", errors="replace") as log_file:
                log_file.write(message)
            yield {"type": "log", "content": message}
            yield {"type": "done", "success": False}
        except Exception as exc:
            message = f"[Error] OpenCode execution failed: {exc}\n"
            with live_log_path.open("a", encoding="utf-8", errors="replace") as log_file:
                log_file.write(message)
            yield {"type": "log", "content": message}
            yield {"type": "done", "success": False}
