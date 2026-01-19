from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


try:
    from app.core.llm import LLMClient
except Exception:
    _backend_dir = Path(__file__).resolve().parent
    _app_dir = _backend_dir / "app"
    sys.path.append(str(_backend_dir))
    sys.path.append(str(_app_dir))
    try:
        from core.llm import LLMClient
    except Exception:
        from app.core.llm import LLMClient


@dataclass
class MetricResult:
    metric_id: str
    metric_name: str
    method: str
    status: str
    score_0_5: Optional[float] = None
    score_0_1: Optional[float] = None
    rationale: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _score_0_1(score_0_5: Optional[float]) -> Optional[float]:
    if score_0_5 is None:
        return None
    return _clamp(float(score_0_5) / 5.0, 0.0, 1.0)


def _read_text(path: Path, max_bytes: Optional[int] = None) -> str:
    if not path.exists():
        return ""
    data = path.read_bytes()
    if max_bytes is not None:
        data = data[:max_bytes]
    try:
        return data.decode("utf-8")
    except Exception:
        try:
            return data.decode("utf-8-sig")
        except Exception:
            return data.decode(errors="replace")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(_read_text(path))
    except Exception:
        return None


def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    for end in range(len(text) - 1, start, -1):
        if text[end] != "}":
            continue
        chunk = text[start : end + 1]
        try:
            obj = json.loads(chunk)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


class Judge:
    def is_available(self) -> bool:
        raise NotImplementedError

    def judge_text(self, prompt: str) -> Tuple[Optional[Dict[str, Any]], str]:
        raise NotImplementedError

    def judge_images(self, prompt: str, image_paths: Sequence[str]) -> Tuple[Optional[Dict[str, Any]], str]:
        raise NotImplementedError


class LLMJudge(Judge):
    def __init__(self, model: Optional[str] = None, timeout_sec: int = 30):
        self._client = LLMClient()
        preferred = (model or "").strip() or None
        env_model = (getattr(self._client, "model", None) or os.environ.get("OPENAI_API_MODEL") or "").strip() or None
        self._model = preferred or env_model or "gpt-4o-mini"
        self._timeout_sec = int(timeout_sec)

    def is_available(self) -> bool:
        try:
            api_key = getattr(self._client, "api_key", None)
            return bool(api_key)
        except Exception:
            return False

    def judge_text(self, prompt: str) -> Tuple[Optional[Dict[str, Any]], str]:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        def _call() -> str:
            return self._client.generate(prompt, model=self._model)

        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                raw = ex.submit(_call).result(timeout=self._timeout_sec)
        except FuturesTimeout:
            raw = "[LLM错误] timeout"
        except Exception as e:
            raw = f"[LLM错误] {e}"

        obj = _extract_first_json_object(raw)
        return obj, raw

    def judge_images(self, prompt: str, image_paths: Sequence[str]) -> Tuple[Optional[Dict[str, Any]], str]:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        images = list(image_paths)

        def _call() -> str:
            return self._client.generate_with_images(prompt, image_paths=images, model=self._model)

        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                raw = ex.submit(_call).result(timeout=self._timeout_sec)
        except FuturesTimeout:
            raw = "[LLM错误] timeout"
        except Exception as e:
            raw = f"[LLM错误] {e}"

        obj = _extract_first_json_object(raw)
        return obj, raw


class Metric:
    metric_id: str
    metric_name: str
    method: str

    def evaluate(self, job: "JobArtifacts", judge: Judge, opts: "EvalOptions") -> MetricResult:
        raise NotImplementedError


@dataclass
class EvalOptions:
    rerun_code: bool = False
    rerun_timeout_sec: int = 240
    max_report_chars: int = 60000
    max_code_chars: int = 50000


class JobArtifacts:
    def __init__(self, job_dir: str | Path):
        self.job_dir = Path(job_dir)

    @property
    def job_id(self) -> str:
        return self.job_dir.name

    def path(self, name: str) -> Path:
        return self.job_dir / name

    def plan(self) -> Dict[str, Any]:
        data = _read_json(self.path("plan_refined.json")) or _read_json(self.path("plan.json")) or {}
        return data if isinstance(data, dict) else {}

    def excel_info(self) -> Dict[str, Any]:
        data = _read_json(self.path("excel_info.json")) or {}
        return data if isinstance(data, dict) else {}

    def exec_status(self) -> Dict[str, Any]:
        data = _read_json(self.path("exec_status.json")) or {}
        return data if isinstance(data, dict) else {}

    def exec_logs(self) -> Dict[str, Any]:
        data = _read_json(self.path("exec_logs.json")) or {}
        return data if isinstance(data, dict) else {}

    def analysis_code(self) -> str:
        return _read_text(self.path("analysis.py"), max_bytes=300000)

    def report_md(self, max_chars: int) -> str:
        text = _read_text(self.path("report.md"))
        return text[:max_chars]

    def plots_dir(self) -> Path:
        return self.job_dir / "plots"

    def list_plots(self) -> List[Path]:
        d = self.plots_dir()
        if not d.exists():
            return []
        return sorted([p for p in d.glob("*.png") if p.is_file()])

    def list_csvs(self) -> List[Path]:
        d = self.plots_dir()
        if not d.exists():
            return []
        return sorted([p for p in d.glob("*.csv") if p.is_file()])


class PlanConsistencyMetric(Metric):
    metric_id = "plan_consistency"
    metric_name = "研究计划一致性"
    method = "LLM_JUDGE"

    def evaluate(self, job: JobArtifacts, judge: Judge, opts: EvalOptions) -> MetricResult:
        plan = job.plan()
        topic = (plan.get("topic") or "").strip()
        objective = (plan.get("objective") or "").strip()
        steps = plan.get("steps") or []
        evidence = {"topic": topic, "objective": objective, "steps_preview": steps[:6]}

        if not judge.is_available():
            return MetricResult(
                metric_id=self.metric_id,
                metric_name=self.metric_name,
                method=self.method,
                status="skipped",
                rationale="未检测到可用的LLM配置，跳过LLM评测。",
                evidence=evidence,
            )

        prompt = (
            "你是RWS研究方案评审员。请评估“研究计划”是否与“研究目标”一致，是否存在偏离。\n"
            "只输出JSON对象，不要输出其它文字。\n"
            "JSON字段：score_0_5（0-5数字，允许0.5步进），rationale（简短理由），strengths（数组），issues（数组），suggestions（数组），confidence_0_1（0-1数字）。\n"
            f"研究目标（topic）：{topic}\n"
            f"研究目标（objective）：{objective}\n"
            f"研究计划（steps）：{json.dumps(steps, ensure_ascii=False)[:20000]}\n"
        )
        obj, raw = judge.judge_text(prompt)
        if not obj:
            return MetricResult(
                metric_id=self.metric_id,
                metric_name=self.metric_name,
                method=self.method,
                status="error",
                rationale="LLM未返回可解析JSON。",
                evidence={**evidence, "llm_raw": raw[:2000]},
            )
        try:
            score_f = float(obj.get("score_0_5"))
        except Exception:
            score_f = None
        return MetricResult(
            metric_id=self.metric_id,
            metric_name=self.metric_name,
            method=self.method,
            status="ok",
            score_0_5=score_f,
            score_0_1=_score_0_1(score_f),
            rationale=str(obj.get("rationale") or ""),
            details={k: v for k, v in obj.items() if k not in {"score_0_5", "rationale"}},
            evidence={**evidence, "llm_raw": raw[:4000]},
        )


def _compute_missing_rates_from_csv(path: Path, max_rows: int = 50000) -> Dict[str, Any]:
    import csv

    try:
        f = path.open("r", encoding="utf-8-sig", errors="replace", newline="")
    except Exception as e:
        return {"error": f"open_failed: {e}"}

    with f:
        try:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return {"error": "empty_csv"}
            cols = [str(h) for h in header]
            miss = [0] * len(cols)
            total = [0] * len(cols)
            rows = 0
            missing_tokens = {"", "na", "nan", "none", "null", "n/a"}
            for row in reader:
                rows += 1
                if rows > max_rows:
                    break
                if row is None:
                    continue
                for i in range(len(cols)):
                    total[i] += 1
                    cell = row[i] if i < len(row) else ""
                    if str(cell).strip().lower() in missing_tokens:
                        miss[i] += 1
            missing_rate = {cols[i]: (miss[i] / total[i] if total[i] else 1.0) for i in range(len(cols))}
            return {
                "rows": rows,
                "cols": len(cols),
                "missing_rate": {str(k): float(v) for k, v in missing_rate.items()},
                "columns": cols,
            }
        except Exception as e:
            return {"error": f"csv_parse_failed: {e}"}


class DataCompletenessMetric(Metric):
    metric_id = "data_completeness"
    metric_name = "数据清洗数据完整性"
    method = "LLM_JUDGE"

    def evaluate(self, job: JobArtifacts, judge: Judge, opts: EvalOptions) -> MetricResult:
        plan = job.plan()
        excel_info = job.excel_info()
        required_fields = plan.get("required_fields") or {}
        target_sheets = plan.get("target_sheets") or []
        excel_sheets = excel_info.get("sheets") or []
        excel_columns = excel_info.get("columns") or {}
        csvs = job.list_csvs()
        csv_stats = {p.name: _compute_missing_rates_from_csv(p) for p in csvs}
        evidence = {
            "target_sheets": target_sheets,
            "required_fields": required_fields,
            "excel_sheets": excel_sheets[:80],
            "excel_columns_preview": {k: (excel_columns.get(k) or [])[:40] for k in list(excel_columns.keys())[:20]},
            "csv_stats": {k: v for k, v in csv_stats.items()},
            "artifacts_present": {
                "missing_data_matrix_png": (job.plots_dir() / "missing_data_matrix.png").exists(),
                "cleaned_baseline_cohort_csv": (job.plots_dir() / "cleaned_baseline_cohort.csv").exists(),
                "survival_analysis_dataset_csv": (job.plots_dir() / "survival_analysis_dataset.csv").exists(),
            },
        }

        if not judge.is_available():
            return MetricResult(
                metric_id=self.metric_id,
                metric_name=self.metric_name,
                method=self.method,
                status="skipped",
                rationale="未检测到可用的LLM配置，跳过LLM评测。",
                evidence=evidence,
            )

        prompt = (
            "你是RWS数据清洗与数据质量评审员。请评估“数据完整性”：是否覆盖了研究所需变量，是否识别并处理缺失/异常（可基于产物与缺失率线索）。\n"
            "只输出JSON对象，不要输出其它文字。\n"
            "JSON字段：score_0_5（0-5数字，允许0.5步进），rationale（简短理由），strengths（数组），issues（数组），suggestions（数组），confidence_0_1（0-1数字）。\n"
            f"研究计划required_fields：{json.dumps(required_fields, ensure_ascii=False)[:12000]}\n"
            f"研究计划target_sheets：{json.dumps(target_sheets, ensure_ascii=False)[:4000]}\n"
            f"Excel结构sheets：{json.dumps(excel_sheets, ensure_ascii=False)[:8000]}\n"
            f"Excel结构columns(截断)：{json.dumps(evidence['excel_columns_preview'], ensure_ascii=False)[:12000]}\n"
            f"输出CSV缺失率统计：{json.dumps(csv_stats, ensure_ascii=False)[:16000]}\n"
            f"关键产物存在性：{json.dumps(evidence['artifacts_present'], ensure_ascii=False)}\n"
        )
        obj, raw = judge.judge_text(prompt)
        if not obj:
            return MetricResult(
                metric_id=self.metric_id,
                metric_name=self.metric_name,
                method=self.method,
                status="error",
                rationale="LLM未返回可解析JSON。",
                evidence={**evidence, "llm_raw": raw[:2000]},
            )
        try:
            score_f = float(obj.get("score_0_5"))
        except Exception:
            score_f = None
        return MetricResult(
            metric_id=self.metric_id,
            metric_name=self.metric_name,
            method=self.method,
            status="ok",
            score_0_5=score_f,
            score_0_1=_score_0_1(score_f),
            rationale=str(obj.get("rationale") or ""),
            details={k: v for k, v in obj.items() if k not in {"score_0_5", "rationale"}},
            evidence={**evidence, "llm_raw": raw[:4000]},
        )


class CodeExecutabilityMetric(Metric):
    metric_id = "code_executability"
    metric_name = "代码生成可执行性"
    method = "CODE"

    def _rerun_analysis(self, job: JobArtifacts, opts: EvalOptions) -> Dict[str, Any]:
        analysis_path = job.path("analysis.py")
        if not analysis_path.exists():
            return {"ran": False, "error": "analysis.py_not_found"}
        t0 = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, str(analysis_path)],
                cwd=str(job.job_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=opts.rerun_timeout_sec,
            )
            return {
                "ran": True,
                "returncode": proc.returncode,
                "elapsed_sec": time.time() - t0,
                "stdout_head": (proc.stdout or "")[:2000],
                "stderr_head": (proc.stderr or "")[:2000],
            }
        except subprocess.TimeoutExpired:
            return {"ran": True, "timeout": True, "elapsed_sec": time.time() - t0}
        except Exception as e:
            return {"ran": True, "error": str(e), "elapsed_sec": time.time() - t0}

    def evaluate(self, job: JobArtifacts, judge: Judge, opts: EvalOptions) -> MetricResult:
        status = job.exec_status()
        exec_logs = status.get("logs") or []
        success = status.get("success")
        running = status.get("running")
        current_step = status.get("current_step")
        evidence: Dict[str, Any] = {
            "exec_status": {
                "running": running,
                "success": success,
                "current_step": current_step,
                "max_iters": status.get("max_iters"),
            },
            "last_log": (exec_logs[-1] if isinstance(exec_logs, list) and exec_logs else None),
            "analysis_py_exists": job.path("analysis.py").exists(),
        }

        rerun = self._rerun_analysis(job, opts) if opts.rerun_code else {"ran": False}
        if rerun.get("ran"):
            evidence["rerun"] = rerun
            if rerun.get("timeout"):
                success = False
            elif "returncode" in rerun:
                success = (rerun.get("returncode") == 0)

        if success is True:
            score = 5.0
            rationale = "执行状态显示成功。"
        elif success is False:
            score = 0.0
            rationale = "执行状态显示失败或重跑失败。"
        else:
            score = 2.5
            rationale = "执行状态未知。"

        return MetricResult(
            metric_id=self.metric_id,
            metric_name=self.metric_name,
            method=self.method,
            status="ok",
            score_0_5=score,
            score_0_1=_score_0_1(score),
            rationale=rationale,
            evidence=evidence,
        )


def _analyze_python_code_quality(code: str) -> Dict[str, Any]:
    if not code.strip():
        return {"error": "empty_code"}
    try:
        tree = ast.parse(code)
    except Exception as e:
        return {"error": f"parse_failed: {e}"}

    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    broad_excepts = 0
    for n in ast.walk(tree):
        if isinstance(n, ast.ExceptHandler):
            if n.type is None:
                broad_excepts += 1
            elif isinstance(n.type, ast.Name) and n.type.id in {"Exception", "BaseException"}:
                broad_excepts += 1

    hardcoded_paths = len(re.findall(r"[A-Za-z]:\\\\", code))
    global_assigns = 0
    for n in tree.body:
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            global_assigns += 1

    return {
        "num_lines": len(code.splitlines()),
        "num_functions": len(funcs),
        "num_classes": len(classes),
        "num_imports": len(imports),
        "num_broad_excepts": broad_excepts,
        "num_windows_abs_paths": hardcoded_paths,
        "num_global_assigns": global_assigns,
    }


def _heuristic_static_code_quality_score(stats: Dict[str, Any]) -> Tuple[float, str]:
    if "error" in stats:
        return 0.0, str(stats.get("error"))

    score = 5.0
    reasons: List[str] = []

    if stats.get("num_functions", 0) <= 1:
        score -= 1.0
        reasons.append("函数拆分较少")
    if stats.get("num_broad_excepts", 0) >= 5:
        score -= 1.0
        reasons.append("宽泛异常捕获较多")
    if stats.get("num_windows_abs_paths", 0) >= 2:
        score -= 1.0
        reasons.append("硬编码绝对路径较多")
    if stats.get("num_lines", 0) >= 500 and stats.get("num_functions", 0) < 6:
        score -= 0.5
        reasons.append("代码偏长且模块化不足")

    score = _clamp(score, 0.0, 5.0)
    rationale = "；".join(reasons) if reasons else "静态结构信号显示代码可维护性较好。"
    return score, rationale


class CodeQualityMetric(Metric):
    metric_id = "code_quality"
    metric_name = "代码生成代码质量"
    method = "STATIC_AND_LLM"

    def evaluate(self, job: JobArtifacts, judge: Judge, opts: EvalOptions) -> MetricResult:
        code = job.analysis_code()
        code_preview = code[: opts.max_code_chars]
        static_stats = _analyze_python_code_quality(code_preview)
        static_score, static_rationale = _heuristic_static_code_quality_score(static_stats)
        evidence: Dict[str, Any] = {"static_stats": static_stats}

        llm_part: Optional[Dict[str, Any]] = None
        llm_raw: Optional[str] = None
        llm_score: Optional[float] = None
        if judge.is_available():
            prompt = (
                "你是Python代码审阅员。请评估代码质量：命名、结构化、可维护性、鲁棒性、可复现性（路径/配置）、异常处理与日志等。\n"
                "只输出JSON对象，不要输出其它文字。\n"
                "JSON字段：score_0_5（0-5数字，允许0.5步进），rationale（简短理由），strengths（数组），issues（数组），suggestions（数组），confidence_0_1（0-1数字）。\n"
                f"代码：\n{code_preview}\n"
            )
            llm_part, llm_raw = judge.judge_text(prompt)
            if llm_part and "score_0_5" in llm_part:
                try:
                    llm_score = float(llm_part.get("score_0_5"))
                except Exception:
                    llm_score = None

        if llm_score is None:
            combined_score = static_score
            rationale = static_rationale
            details = {"static": {"score_0_5": static_score, "rationale": static_rationale}}
            if llm_raw is not None:
                evidence["llm_raw"] = (llm_raw or "")[:2000]
        else:
            combined_score = _clamp((static_score + llm_score) / 2.0, 0.0, 5.0)
            rationale = str((llm_part or {}).get("rationale") or static_rationale)
            details = {
                "static": {"score_0_5": static_score, "rationale": static_rationale},
                "llm": llm_part,
            }
            evidence["llm_raw"] = (llm_raw or "")[:3000]

        return MetricResult(
            metric_id=self.metric_id,
            metric_name=self.metric_name,
            method=self.method,
            status="ok",
            score_0_5=combined_score,
            score_0_1=_score_0_1(combined_score),
            rationale=rationale,
            details=details,
            evidence=evidence,
        )


class PlotsLLMMetric(Metric):
    def __init__(self, metric_id: str, metric_name: str, rubric: str):
        self.metric_id = metric_id
        self.metric_name = metric_name
        self.method = "LLM_JUDGE_VISION"
        self._rubric = rubric

    def evaluate(self, job: JobArtifacts, judge: Judge, opts: EvalOptions) -> MetricResult:
        plots = job.list_plots()
        evidence = {"plots": [str(p) for p in plots]}
        if not plots:
            return MetricResult(
                metric_id=self.metric_id,
                metric_name=self.metric_name,
                method=self.method,
                status="skipped",
                rationale="未找到PNG图表产物。",
                evidence=evidence,
            )
        if not judge.is_available():
            return MetricResult(
                metric_id=self.metric_id,
                metric_name=self.metric_name,
                method=self.method,
                status="skipped",
                rationale="未检测到可用的LLM配置，跳过图表视觉评测。",
                evidence=evidence,
            )

        per_plot: Dict[str, Any] = {}
        scores: List[float] = []
        for p in plots:
            prompt = (
                "你是学术图表评审员。请根据给定图像评估图表质量。\n"
                "只输出JSON对象，不要输出其它文字。\n"
                "JSON字段：score_0_5（0-5数字，允许0.5步进），rationale（简短理由），issues（数组），suggestions（数组），confidence_0_1（0-1数字）。\n"
                f"评估维度：{self.metric_name}\n"
                f"评分标准：{self._rubric}\n"
            )
            obj, raw = judge.judge_images(prompt, [str(p)])
            if not obj:
                per_plot[p.name] = {"status": "error", "llm_raw": raw[:1500]}
                continue
            try:
                s = float(obj.get("score_0_5"))
                scores.append(s)
            except Exception:
                s = None
            per_plot[p.name] = {"status": "ok", "result": obj, "llm_raw": raw[:1500]}

        if not scores:
            return MetricResult(
                metric_id=self.metric_id,
                metric_name=self.metric_name,
                method=self.method,
                status="error",
                rationale="所有图表的LLM输出均不可解析为分数。",
                details={"per_plot": per_plot},
                evidence=evidence,
            )

        agg = float(sum(scores) / max(1, len(scores)))
        agg = _clamp(agg, 0.0, 5.0)
        return MetricResult(
            metric_id=self.metric_id,
            metric_name=self.metric_name,
            method=self.method,
            status="ok",
            score_0_5=agg,
            score_0_1=_score_0_1(agg),
            rationale=f"对{len(scores)}张图表取平均。",
            details={"per_plot": per_plot},
            evidence=evidence,
        )


class ReportStructureMetric(Metric):
    metric_id = "report_structure"
    metric_name = "报告生成结构完整性"
    method = "JSON"

    def _extract_headings(self, md: str) -> List[str]:
        headings: List[str] = []
        for ln in md.splitlines():
            m = re.match(r"^\\s{0,3}#{1,6}\\s*(.+?)\\s*$", ln)
            if not m:
                continue
            headings.append(m.group(1).strip())
        return headings

    def evaluate(self, job: JobArtifacts, judge: Judge, opts: EvalOptions) -> MetricResult:
        md = job.report_md(opts.max_report_chars)
        if not md.strip():
            return MetricResult(
                metric_id=self.metric_id,
                metric_name=self.metric_name,
                method=self.method,
                status="error",
                rationale="未找到report.md或内容为空。",
                evidence={"report_md_exists": job.path("report.md").exists()},
            )

        headings = self._extract_headings(md)
        required = [
            ("摘要", ["摘要", "Abstract"]),
            ("引言/背景", ["引言", "背景", "背景与目标", "研究背景", "Background"]),
            ("方法", ["方法", "Methods", "研究方法"]),
            ("结果", ["结果", "Results"]),
            ("讨论", ["讨论", "Discussion"]),
        ]
        found: Dict[str, bool] = {}
        for key, aliases in required:
            found[key] = any(any(a in h for a in aliases) for h in headings)

        present = sum(1 for v in found.values() if v)
        total = len(found)
        score = 5.0 * (present / total if total else 0.0)
        missing = [k for k, v in found.items() if not v]
        rationale = "结构要素齐全。" if not missing else f"缺少要素：{', '.join(missing)}"
        details = {"headings": headings[:80], "required_found": found, "missing": missing}

        score = _clamp(score, 0.0, 5.0)
        return MetricResult(
            metric_id=self.metric_id,
            metric_name=self.metric_name,
            method=self.method,
            status="ok",
            score_0_5=score,
            score_0_1=_score_0_1(score),
            rationale=rationale,
            details=details,
            evidence={"report_md_len": len(md)},
        )


class ReportLLMMetric(Metric):
    def __init__(self, metric_id: str, metric_name: str, rubric: str):
        self.metric_id = metric_id
        self.metric_name = metric_name
        self.method = "LLM_JUDGE"
        self._rubric = rubric

    def evaluate(self, job: JobArtifacts, judge: Judge, opts: EvalOptions) -> MetricResult:
        md = job.report_md(opts.max_report_chars)
        evidence = {"report_md_len": len(md)}
        if not md.strip():
            return MetricResult(
                metric_id=self.metric_id,
                metric_name=self.metric_name,
                method=self.method,
                status="error",
                rationale="未找到report.md或内容为空。",
                evidence={**evidence, "report_md_exists": job.path("report.md").exists()},
            )
        if not judge.is_available():
            return MetricResult(
                metric_id=self.metric_id,
                metric_name=self.metric_name,
                method=self.method,
                status="skipped",
                rationale="未检测到可用的LLM配置，跳过LLM评测。",
                evidence=evidence,
            )

        prompt = (
            "你是学术写作评审员。请根据维度对报告文本进行评分。\n"
            "只输出JSON对象，不要输出其它文字。\n"
            "JSON字段：score_0_5（0-5数字，允许0.5步进），rationale（简短理由），issues（数组），suggestions（数组），confidence_0_1（0-1数字）。\n"
            f"评估维度：{self.metric_name}\n"
            f"评分标准：{self._rubric}\n"
            f"报告文本：\n{md}\n"
        )
        obj, raw = judge.judge_text(prompt)
        if not obj:
            return MetricResult(
                metric_id=self.metric_id,
                metric_name=self.metric_name,
                method=self.method,
                status="error",
                rationale="LLM未返回可解析JSON。",
                evidence={**evidence, "llm_raw": raw[:2000]},
            )
        try:
            score_f = float(obj.get("score_0_5"))
        except Exception:
            score_f = None
        return MetricResult(
            metric_id=self.metric_id,
            metric_name=self.metric_name,
            method=self.method,
            status="ok",
            score_0_5=score_f,
            score_0_1=_score_0_1(score_f),
            rationale=str(obj.get("rationale") or ""),
            details={k: v for k, v in obj.items() if k not in {"score_0_5", "rationale"}},
            evidence={**evidence, "llm_raw": raw[:3000]},
        )


class BenchmarkEvaluator:
    def __init__(self, metrics: Sequence[Metric], judge: Judge, opts: EvalOptions):
        self.metrics = list(metrics)
        self.judge = judge
        self.opts = opts

    def evaluate(self, job_dir: str | Path) -> Dict[str, Any]:
        job = JobArtifacts(job_dir)
        t0 = time.time()
        results: List[MetricResult] = []
        for m in self.metrics:
            try:
                r = m.evaluate(job, self.judge, self.opts)
            except Exception as e:
                r = MetricResult(
                    metric_id=getattr(m, "metric_id", type(m).__name__),
                    metric_name=getattr(m, "metric_name", type(m).__name__),
                    method=getattr(m, "method", "unknown"),
                    status="error",
                    rationale="评测执行异常。",
                    error=str(e),
                )
            if r.score_0_1 is None:
                r.score_0_1 = _score_0_1(r.score_0_5)
            results.append(r)

        scores = [r.score_0_5 for r in results if r.status == "ok" and isinstance(r.score_0_5, (int, float))]
        overall = float(sum(scores) / len(scores)) if scores else None
        out = {
            "job_id": job.job_id,
            "job_dir": str(job.job_dir),
            "timestamp": int(time.time()),
            "elapsed_sec": time.time() - t0,
            "overall_score_0_5": overall,
            "overall_score_0_1": _score_0_1(overall) if overall is not None else None,
            "llm_available": bool(self.judge.is_available()),
            "results": [asdict(r) for r in results],
        }
        return out


def default_metrics() -> List[Metric]:
    return [
        PlanConsistencyMetric(),
        DataCompletenessMetric(),
        CodeExecutabilityMetric(),
        CodeQualityMetric(),
        PlotsLLMMetric(
            metric_id="plot_clarity",
            metric_name="图表Clarity",
            rubric="关注标题/图例/坐标/单位/标注是否明确，能否快速理解图意，是否存在遮挡或难辨识元素。",
        ),
        PlotsLLMMetric(
            metric_id="plot_information",
            metric_name="图表信息量",
            rubric="关注是否包含关键统计量/样本量/置信区间/检验结果等必要信息，能否支持结论。",
        ),
        PlotsLLMMetric(
            metric_id="plot_style",
            metric_name="图表视觉风格",
            rubric="关注配色、字体、线型一致性与学术规范性；是否适合论文/报告呈现。",
        ),
        PlotsLLMMetric(
            metric_id="plot_interpretation_accuracy",
            metric_name="图表解释准确性",
            rubric="仅依据图表判断可支持的观察是否被准确描述，是否存在过度解读或将相关性当因果。",
        ),
        ReportStructureMetric(),
        ReportLLMMetric(
            metric_id="report_language",
            metric_name="报告语言表达",
            rubric="关注用语是否学术、客观、简洁；是否避免冗长与含混；段落是否清晰。",
        ),
        ReportLLMMetric(
            metric_id="report_format",
            metric_name="报告格式规范",
            rubric="关注结构层级、标题与图表引用、表格格式、编号与一致性、引用风格的规范性。",
        ),
    ]


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--job_dir", type=str, required=True)
    p.add_argument("--out", type=str, default="")
    p.add_argument("--rerun", action="store_true")
    p.add_argument("--timeout", type=int, default=240)
    p.add_argument("--llm_timeout", type=int, default=30)
    p.add_argument("--model", type=str, default="")
    args = p.parse_args(argv)

    job_dir = Path(args.job_dir)
    if not job_dir.exists():
        print(f"job_dir not found: {job_dir}")
        return 2

    opts = EvalOptions(rerun_code=bool(args.rerun), rerun_timeout_sec=int(args.timeout))
    judge = LLMJudge(model=(args.model or None), timeout_sec=int(args.llm_timeout))
    evaluator = BenchmarkEvaluator(default_metrics(), judge, opts)
    result = evaluator.evaluate(job_dir)

    out_path = Path(args.out) if args.out else (job_dir / "benchmark_eval.json")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
