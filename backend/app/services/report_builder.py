from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import json
try:
    import pandas as _pd
except Exception:
    _pd = None
from ..core.llm import LLMClient
from .chapters import SectionContext, REGISTRY, SECTIONS_META


class ReportBuilder:
    STYLE_GUIDE = (
        "写作要求（必须遵守）：\n"
        "- 使用简体中文，学术、客观、中立、精炼。\n"
        "- 只输出内容本身；不回应或引用任何指令、问题或提示语。\n"
        "- 不出现“好的”“以下是”“根据您的”等客服式语句。\n"
        "- 不出现“AI”“模型”“提示词”“用户”等字样或自我说明。\n"
        "- 结构清晰、逻辑严谨；严格遵守字数要求。\n"
        "- 如需列点，使用短句要点；不加英文翻译或括注。\n"
    )

    def _step_to_text(self, s):
        if s is None:
            return ""
        if isinstance(s, str):
            return s
        if isinstance(s, dict):
            candidate = (
                s.get('title')
                or s.get('name')
                or s.get('desc')
                or s.get('step')
                or s.get('summary')
            )
            return str(candidate) if candidate is not None else str(s)
        if isinstance(s, (list, tuple, set)):
            try:
                return ", ".join([str(x) for x in s])
            except Exception:
                return str(s)
        return str(s)

    def _summarize_logs(self, logs: List[Dict]) -> str:
        pieces = []
        for l in logs or []:
            s = l.get("step")
            rc = l.get("returncode")
            out = (l.get("stdout") or "").strip()
            err = (l.get("stderr") or "").strip()
            if out:
                pieces.append(f"Step {s} rc={rc} stdout: {out[:600]}")
            if err:
                pieces.append(f"Step {s} stderr: {err[:300]}")
        return "\n".join(pieces)[:2000]

    def _detect_methods(self, logs: List[Dict]) -> List[str]:
        text = "\n".join([(l.get("stdout") or "") for l in logs or []])
        keys = {
            "EDA": ["Describe", "describe(", "非空计数", "直方图", "value_counts"],
            "生存分析": ["Kaplan", "K-M", "KM", "lifelines", "cox"],
            "相关性/回归": ["回归", "correlation", "pearson", "spearman", "线性回归"],
            "分组对比": ["分组", "groupby", "t检验", "anova"],
        }
        found = []
        for k, kws in keys.items():
            for w in kws:
                if w.lower() in text.lower():
                    found.append(k)
                    break
        return sorted(set(found))

    def _profile_df(self, df):
        prof = {
            "dtypes": {},
            "missing_rate": {},
            "unique_rate": {},
            "candidate_keys": [],
        }
        try:
            for col in df.columns:
                ser = df[col]
                kind = "text"
                if _pd is not None and _pd.api.types.is_numeric_dtype(ser):
                    kind = "numeric"
                elif _pd is not None and _pd.api.types.is_datetime64_any_dtype(ser):
                    kind = "datetime"
                elif _pd is not None and (_pd.api.types.is_categorical_dtype(ser) or _pd.api.types.is_object_dtype(ser)):
                    nunique = ser.nunique(dropna=True)
                    kind = "categorical" if nunique <= max(20, int(len(ser) * 0.1)) else "text"
                prof["dtypes"][str(col)] = kind

                total = len(ser)
                missing = int(ser.isna().sum()) if hasattr(ser, "isna") else 0
                unique = int(ser.nunique(dropna=True)) if hasattr(ser, "nunique") else 0
                prof["missing_rate"][str(col)] = round(missing / total, 4) if total else 0.0
                prof["unique_rate"][str(col)] = round(unique / total, 4) if total else 0.0

            candidates = [
                c for c, ur in prof["unique_rate"].items()
                if ur >= 0.9 and prof["missing_rate"].get(c, 1.0) <= 0.05
            ]
            prof["candidate_keys"] = candidates
        except Exception:
            pass
        return prof

    def _select_cases(self, df, prof, max_cases: int = 2):
        cases = []
        try:
            numeric_cols = [c for c, k in prof.get("dtypes", {}).items() if k == "numeric"]
            if numeric_cols:
                col = numeric_cols[0]
                ser = _pd.to_numeric(df[col], errors="coerce") if _pd is not None else df[col]
                idx_max = None
                try:
                    idx_max = int(ser.idxmax()) if getattr(ser, "notna", lambda: [])().any() else None
                except Exception:
                    try:
                        idx_max = int(ser.reset_index(drop=True).argmax())
                    except Exception:
                        idx_max = None
                if idx_max is not None:
                    row = df.iloc[idx_max].to_dict()
                    cases.append({"type": "数值极大值", "column": col, "row": row})

            if len(cases) < max_cases:
                cat_cols = [c for c, k in prof.get("dtypes", {}).items() if k in ("categorical", "text")]
                if cat_cols:
                    c = cat_cols[0]
                    try:
                        vc = df[c].astype(str).value_counts(dropna=True)
                        if len(vc) > 0:
                            rare_cat = vc.index[-1]
                            row = df[df[c].astype(str) == rare_cat].head(1).to_dict("records")
                            if row:
                                cases.append({"type": "稀有类别示例", "column": c, "value": str(rare_cat), "row": row[0]})
                    except Exception:
                        pass
        except Exception:
            pass
        return cases[:max_cases]

    def _update_status(self, job_dir: str, update: Dict):
        try:
            path = Path(job_dir) / "report_status.json"
            data = {}
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            data.update(update)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    def build_report_modular(self, job_dir: str, topic: str, plan: Dict, exec_result: Dict, excel_info: Dict, job_id: Optional[str] = None) -> str:
        job = Path(job_dir)
        report_path = job / "report.md"
        status_path = job / "report_status.json"
        ctx = SectionContext(job_dir=job_dir, topic=topic, plan=plan, exec_result=exec_result, excel_info=excel_info, job_id=job_id)
        md_parts: List[str] = []
        try:
            status_path.write_text(json.dumps({
                "state": "running",
                "step": "init",
                "progress": 0,
                "total": len([s for s in SECTIONS_META if s.get('default')]),
                "completed": 0,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        total = len([s for s in SECTIONS_META if s.get('default')]) or 1
        completed = 0
        for s in SECTIONS_META:
            if not s.get('default'):
                continue
            sid = s['id']
            try:
                content = REGISTRY.render(sid, ctx)
            except Exception:
                content = ""
            md_parts.append(content)
            completed += 1
            try:
                st = {
                    "state": "running",
                    "step": sid,
                    "completed": completed,
                    "total": total,
                    "progress": int(100 * completed / total),
                }
                status_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
                report_path.write_text("\n".join(md_parts), encoding="utf-8")
            except Exception:
                pass
        final_md = "\n".join(md_parts)
        report_path.write_text(final_md, encoding="utf-8")
        try:
            st = {
                "state": "done",
                "step": "done",
                "progress": 100,
                "completed": total,
                "total": total,
                "report_path": str(report_path),
            }
            status_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return str(report_path)

    def generate_section_modular(
        self,
        job_dir: str,
        topic: str,
        plan: dict,
        exec_result: dict,
        excel_info: dict,
        section_id: str,
        job_id: Optional[str] = None,
        human_note: Optional[str] = None,
        guidelines: Optional[str] = None,
    ) -> str:
        ctx = SectionContext(job_dir=job_dir, topic=topic, plan=plan, exec_result=exec_result, excel_info=excel_info, job_id=job_id)
        content = REGISTRY.render(section_id, ctx, human_note=human_note, guidelines=guidelines)
        try:
            sections_dir = Path(job_dir) / 'sections'
            sections_dir.mkdir(exist_ok=True)
            (sections_dir / f"{section_id}.md").write_text(content, encoding='utf-8')
        except Exception:
            pass
        return content
    def build_report(self, job_dir: str, topic: str, plan: Dict, exec_result: Dict, excel_info: Dict, job_id: Optional[str] = None) -> str:
        job = Path(job_dir)
        report_path = job / "report.md"
        preview_path = job / "report_preview.md"

        success = exec_result.get("success", False)
        logs = exec_result.get("logs", [])
        plots_dir = exec_result.get("plots_dir")

        llm = LLMClient()

        # 统一写作约束（所有章节提示词都会附加该要求）
        STYLE_GUIDE = (
            "写作要求（必须遵守）：\n"
            "- 使用简体中文，学术、客观、中立、精炼。\n"
            "- 只输出内容本身；不回应或引用任何指令、问题或提示语。\n"
            "- 不出现“好的”“以下是”“根据您的”等客服式语句。\n"
            "- 不出现“AI”“模型”“提示词”“用户”等字样或自我说明。\n"
            "- 结构清晰、逻辑严谨；严格遵守字数要求。\n"
            "- 如需列点，使用短句要点；不加英文翻译或括注。\n"
        )

        # 辅助：安全字符串化步骤
        def _step_to_text(s):
            if s is None:
                return ""
            if isinstance(s, str):
                return s
            if isinstance(s, dict):
                candidate = (
                    s.get('title')
                    or s.get('name')
                    or s.get('desc')
                    or s.get('step')
                    or s.get('summary')
                )
                return str(candidate) if candidate is not None else str(s)
            if isinstance(s, (list, tuple, set)):
                try:
                    return ", ".join([str(x) for x in s])
                except Exception:
                    return str(s)
            return str(s)

        steps_val = plan.get('steps', []) or []
        steps_str = ", ".join([str(_step_to_text(s)) for s in steps_val])
        plan_str = f"objective: {plan.get('objective', '')} steps: {steps_str}"

        # 辅助：精简日志为LLM摘要上下文
        def _summarize_logs(logs: List[Dict]) -> str:
            pieces = []
            for l in logs:
                s = l.get("step")
                rc = l.get("returncode")
                out = (l.get("stdout") or "").strip()
                err = (l.get("stderr") or "").strip()
                if out:
                    pieces.append(f"Step {s} rc={rc} stdout: {out[:600]}")
                if err:
                    pieces.append(f"Step {s} stderr: {err[:300]}")
            return "\n".join(pieces)[:2000]

        log_summary = _summarize_logs(logs)

        # 检测方法学关键词（用于方法段落提示）
        def _detect_methods(logs: List[Dict]) -> List[str]:
            text = "\n".join([(l.get("stdout") or "") for l in logs])
            keys = {
                "EDA": ["Describe", "describe(", "非空计数", "直方图", "value_counts"],
                "生存分析": ["Kaplan", "K-M", "KM", "lifelines", "cox"],
                "相关性/回归": ["回归", "correlation", "pearson", "spearman", "线性回归"],
                "分组对比": ["分组", "groupby", "t检验", "anova"],
            }
            found = []
            for k, kws in keys.items():
                for w in kws:
                    if w.lower() in text.lower():
                        found.append(k)
                        break
            return sorted(set(found))

        methods_detected = _detect_methods(logs)

        # 生成结构化RWS报告
        md: List[str] = []
        md.append(f"# RWS深度研究报告\n")
        md.append(f"**主题**: {topic}\n")
        md.append(f"**任务ID**: {job_id or job.name}\n")
        md.append(f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        md.append(f"**数据路径**: `{excel_info.get('path')}`\n")
        md.append(f"**执行成功**: {success}\n")

        # 摘要
        try:
            abstract_prompt = (
                f"{self.STYLE_GUIDE}\n"
                "任务：撰写不超过200字的RWS研究摘要，基于研究主题、计划摘要与数据特征，描述研究目的、数据来源与主要结论。\n"
                f"主题: {topic}\n计划摘要: {plan_str}\n数据Sheets: {excel_info.get('sheets')}\n用户描述: {excel_info.get('description', '')}"
            )
            abstract = llm.generate(abstract_prompt).strip()
        except Exception:
            abstract = "本次RWS研究围绕主题展开，基于Excel多Sheet数据进行分析，报告包含方法与结果的完整呈现。"
        md.append("\n## 摘要\n")
        md.append(f"{abstract}\n")
        self._update_status(job_dir, {"state": "running", "step": "abstract", "progress": 10})
        try:
            preview_path.write_text("\n".join(md), encoding="utf-8")
        except Exception:
            pass

        # 背景与目标
        try:
            background_prompt = (
                f"{self.STYLE_GUIDE}\n"
                "任务：撰写RWS研究的背景与目标。背景包含真实世界研究的动机、数据的生态环境、研究对象；目标从 plan.objective 中提炼。\n"
                f"主题: {topic}\n目标: {plan.get('objective','')}\n用户描述: {excel_info.get('description','')}"
            )
            background = llm.generate(background_prompt).strip()
        except Exception:
            background = f"研究目标：{plan.get('objective','') or '未明确'}。本研究在真实世界数据条件下开展，以期获得更贴近临床实际的证据。"
        md.append("\n## 背景与目标\n")
        md.append(f"{background}\n")
        self._update_status(job_dir, {"state": "running", "step": "background", "progress": 20})
        try:
            preview_path.write_text("\n".join(md), encoding="utf-8")
        except Exception:
            pass

        # 数据说明
        md.append("\n## 数据说明\n")
        md.append(f"- Sheets：{excel_info.get('sheets')}\n")
        # 列举每个sheet的字段类型摘要（若有画像）
        profile = excel_info.get("profile", {}) or {}
        if profile:
            for s in excel_info.get("sheets", []) or []:
                prof = profile.get(s) or {}
                dtypes = prof.get("dtypes", {})
                if dtypes:
                    kinds = {k: v for k, v in list(dtypes.items())[:10]}
                    md.append(f"  - {s} 字段类型示例：{kinds}\n")
        md.append(f"- 字段匹配策略：精确匹配 > 标准化匹配 > 概念别名提示；无法匹配即跳过，并在日志打印可用列。\n")

        # 数据表分析与代表性案例解读
        md.append("\n## 数据表分析与案例解读\n")
        self._update_status(job_dir, {"state": "running", "step": "data", "progress": 30})
        try:
            preview_path.write_text("\n".join(md), encoding="utf-8")
        except Exception:
            pass

        # 辅助：DataFrame画像与代表性样本选择
        def _profile_df(df):
            prof = {
                "dtypes": {},
                "missing_rate": {},
                "unique_rate": {},
                "candidate_keys": [],
            }
            try:
                for col in df.columns:
                    ser = df[col]
                    kind = "text"
                    if _pd is not None and _pd.api.types.is_numeric_dtype(ser):
                        kind = "numeric"
                    elif _pd is not None and _pd.api.types.is_datetime64_any_dtype(ser):
                        kind = "datetime"
                    elif _pd is not None and (_pd.api.types.is_categorical_dtype(ser) or _pd.api.types.is_object_dtype(ser)):
                        nunique = ser.nunique(dropna=True)
                        kind = "categorical" if nunique <= max(20, int(len(ser) * 0.1)) else "text"
                    prof["dtypes"][str(col)] = kind

                    total = len(ser)
                    missing = int(ser.isna().sum()) if hasattr(ser, "isna") else 0
                    unique = int(ser.nunique(dropna=True)) if hasattr(ser, "nunique") else 0
                    prof["missing_rate"][str(col)] = round(missing / total, 4) if total else 0.0
                    prof["unique_rate"][str(col)] = round(unique / total, 4) if total else 0.0

                candidates = [
                    c for c, ur in prof["unique_rate"].items()
                    if ur >= 0.9 and prof["missing_rate"].get(c, 1.0) <= 0.05
                ]
                prof["candidate_keys"] = candidates
            except Exception:
                pass
            return prof

        def _select_cases(df, prof, max_cases: int = 2):
            cases = []
            try:
                # 数值极值样本
                numeric_cols = [c for c, k in prof.get("dtypes", {}).items() if k == "numeric"]
                if numeric_cols:
                    col = numeric_cols[0]
                    ser = _pd.to_numeric(df[col], errors="coerce") if _pd is not None else df[col]
                    idx_max = None
                    try:
                        idx_max = int(ser.idxmax()) if getattr(ser, "notna", lambda: [])().any() else None
                    except Exception:
                        # 退化策略：取最大值所在行
                        try:
                            idx_max = int(ser.reset_index(drop=True).argmax())
                        except Exception:
                            idx_max = None
                    if idx_max is not None:
                        row = df.iloc[idx_max].to_dict()
                        cases.append({"type": "数值极大值", "column": col, "row": row})

                # 稀有类别样本
                if len(cases) < max_cases:
                    cat_cols = [c for c, k in prof.get("dtypes", {}).items() if k in ("categorical", "text")]
                    if cat_cols:
                        c = cat_cols[0]
                        try:
                            vc = df[c].astype(str).value_counts(dropna=True)
                            if len(vc) > 0:
                                rare_cat = vc.index[-1]
                                row = df[df[c].astype(str) == rare_cat].head(1).to_dict("records")
                                if row:
                                    cases.append({"type": "稀有类别示例", "column": c, "value": str(rare_cat), "row": row[0]})
                        except Exception:
                            pass
            except Exception:
                pass
            return cases[:max_cases]

        # 1) 源Excel各Sheet分析（优先使用已画像信息，必要时小样本读取）
        excel_path = excel_info.get("path")
        sheets = excel_info.get("sheets", []) or []
        columns_map = excel_info.get("columns", {}) or {}
        profile = excel_info.get("profile", {}) or {}
        if excel_path:
            md.append(f"- 源数据文件：`{excel_path}`\n")
        for s in sheets:
            prof = profile.get(s, {}) or {}
            dtypes = prof.get("dtypes", {}) or {}
            miss = prof.get("missing_rate", {}) or {}
            cand = prof.get("candidate_keys", []) or []
            n_fields = len(dtypes) if dtypes else len(columns_map.get(s, []) or [])
            md.append(f"  - Sheet：{s} | 字段数：{n_fields} | 候选主键：{cand[:3]}\n")
            if miss:
                top_missing = sorted(miss.items(), key=lambda x: x[1], reverse=True)[:3]
                md.append(f"    - 缺失率最高字段：{[k for k, _ in top_missing]}\n")
            # 代表性案例（若可读取且环境支持pandas）
            if _pd is not None and excel_path:
                try:
                    df = _pd.read_excel(excel_path, sheet_name=s, nrows=300)
                    df_prof = self._profile_df(df)
                    cases = self._select_cases(df, df_prof)
                    for c in cases:
                        try:
                            case_prompt = (
                                f"{self.STYLE_GUIDE}\n"
                                "任务：结合研究主题与计划，对下述代表性样本进行简洁的专业解读（80-120字），突出其在数据分布、异常及机制上的意义。\n"
                                f"主题：{topic}\n计划摘要：{plan_str}\nSheet：{s}\n类型：{c.get('type')}\n列：{c.get('column')}\n样本：{json.dumps(c.get('row', {}), ensure_ascii=False)}"
                            )
                            case_text = llm.generate(case_prompt).strip()
                        except Exception:
                            case_text = "该样本体现了数据的典型或异常特征，具有分析价值。"
                        md.append(f"    - 案例（{c.get('type')}）：{case_text}\n")
                except Exception:
                    # 读取失败则跳过案例解读，仅保留结构摘要
                    pass
        self._update_status(job_dir, {"state": "running", "step": "data_table", "progress": 45})
        try:
            preview_path.write_text("\n".join(md), encoding="utf-8")
        except Exception:
            pass

        # 2) Job目录下其他表格文件分析（CSV/XLSX/Parquet）
        job = Path(job_dir)
        tabular_suffixes = {".csv", ".xlsx", ".xls", ".parquet"}
        other_tables: List[Path] = []
        try:
            for p in sorted(job.glob("*")):
                if p.is_file() and p.suffix.lower() in tabular_suffixes and p.name not in {"report.md"}:
                    # 排除源Excel（若在同目录）避免重复
                    if excel_path and Path(excel_path).resolve() == p.resolve():
                        continue
                    other_tables.append(p)
        except Exception:
            other_tables = []

        if other_tables:
            md.append("\n### 衍生表格分析\n")
        for p in other_tables:
            md.append(f"- 文件：`{p.name}`\n")
            if _pd is None:
                md.append("  - 环境未安装pandas，仅提供文件信息。\n")
                continue
            # 小样本读取与画像
            df = None
            try:
                if p.suffix.lower() == ".csv":
                    df = _pd.read_csv(str(p), nrows=300)
                elif p.suffix.lower() in {".xlsx", ".xls"}:
                    df = _pd.read_excel(str(p), nrows=300)
                elif p.suffix.lower() == ".parquet":
                    df = _pd.read_parquet(str(p))
                    if len(df) > 300:
                        df = df.head(300)
            except Exception:
                df = None
            if df is None:
                md.append("  - 读取失败或不支持该格式。\n")
                continue

            df_prof = _profile_df(df)
            n_fields = len(df.columns)
            md.append(f"  - 维度：rows≈{len(df)}，cols={n_fields}\n")
            if df_prof.get("candidate_keys"):
                md.append(f"  - 候选主键：{df_prof['candidate_keys'][:3]}\n")
            miss = df_prof.get("missing_rate", {})
            if miss:
                top_missing = sorted(miss.items(), key=lambda x: x[1], reverse=True)[:3]
                md.append(f"  - 缺失率最高字段：{[k for k, _ in top_missing]}\n")

            cases = _select_cases(df, df_prof)
            for c in cases:
                try:
                    case_prompt = (
                        f"{STYLE_GUIDE}\n"
                        "任务：对下述衍生表的代表性样本进行专业解读，结合真实世界数据的复杂性说明其意义。\n"
                        f"主题：{topic}\n计划摘要：{plan_str}\n表：{p.name}\n类型：{c.get('type')}\n列：{c.get('column')}\n样本：{json.dumps(c.get('row', {}), ensure_ascii=False)}"
                    )
                    case_text = llm.generate(case_prompt).strip()
                except Exception:
                    case_text = "样本体现了分布或异常的代表性特征，值得进一步分析。"
                md.append(f"  - 案例（{c.get('type')}）：{case_text}\n")

        # 方法
        md.append("\n## 方法\n")
        method_intro = (
            "遵循真实世界研究规范，基于计划步骤执行分析；"
            f"本次检测到的方法学：{methods_detected or ['EDA']}。"
        )
        md.append(f"- {method_intro}\n")
        try:
            method_prompt = (
                f"{self.STYLE_GUIDE}\n"
                "任务：撰写方法学详细说明，包含数据清洗策略、字段匹配、统计方法与可视化方法。\n"
                f"计划摘要: {plan_str}\n日志摘要: {log_summary}"
            )
            method_body = llm.generate(method_prompt).strip()
        except Exception:
            method_body = "数据清洗采用缺失值识别与基本类型判断；字段匹配通过精确/标准化/别名三级策略；可视化包含直方图与分布图，若包含生存分析则绘制K-M曲线。"
        md.append(f"{method_body}\n")
        self._update_status(job_dir, {"state": "running", "step": "methods", "progress": 60})
        try:
            preview_path.write_text("\n".join(md), encoding="utf-8")
        except Exception:
            pass

        md.append("\n## 字段支撑与数据改进\n")
        try:
            support_payload = {
                "sheets": sheets,
                "profile": profile,
                "synonyms_hint": excel_info.get("synonyms_hint", {}),
            }
            support_prompt = (
                f"{self.STYLE_GUIDE}\n"
                "任务：评估当前数据字段是否足以支撑研究主题，并提出数据改进建议。\n"
                "请从以下维度进行要点式评估：缺失率、类型一致性、取值标准化、时间字段完整性、主键与关联字段、样本量。\n"
                "随后给出可操作的数据改进建议：需补充/新增的字段、提高填报与标准化的方法、补齐缺失的策略与采集流程优化。\n"
                "输出为两段要点列表：\n"
                "- 字段支撑性评估\n"
                "- 数据改进建议\n"
                f"主题: {topic}\n计划摘要: {plan_str}\n字段画像: {json.dumps(support_payload, ensure_ascii=False)}"
            )
            support_text = llm.generate(support_prompt).strip()
        except Exception:
            support_lines = []
            overall_missing = []
            try:
                for s in sheets:
                    miss = (profile.get(s, {}) or {}).get("missing_rate", {}) or {}
                    for k, v in miss.items():
                        overall_missing.append((s, k, v))
            except Exception:
                pass
            risky = [f"{s}.{k}" for s, k, v in overall_missing if v >= 0.3][:6]
            ok_fields = []
            try:
                for s in sheets:
                    d = (profile.get(s, {}) or {}).get("dtypes", {}) or {}
                    miss = (profile.get(s, {}) or {}).get("missing_rate", {}) or {}
                    ok = [c for c, kind in d.items() if miss.get(c, 1.0) <= 0.2]
                    if ok:
                        ok_fields.append(f"{s}: {ok[:6]}")
            except Exception:
                pass
            section_a = [
                "- 多个关键字段存在较高缺失率，可能削弱结论稳健性",
                f"- 可支撑分析的低缺失字段：{'; '.join(ok_fields) if ok_fields else '待补充'}",
                f"- 风险字段（缺失率≥30%）：{risky if risky else '暂无画像或需采样'}",
            ]
            section_b = [
                "- 建议在采集流程中强制关键字段为必填并增加校验",
                "- 补充时间相关字段（入院/出院/随访）以完善事件与序列分析",
                "- 对分类字段统一编码字典并开展历史数据清洗与映射",
                "- 针对缺失严重字段开展回溯补录或引入外部数据源",
            ]
            support_text = "\n".join(["- 字段支撑性评估", *section_a, "\n- 数据改进建议", *section_b])
        md.append(f"{support_text}\n")
        self._update_status(job_dir, {"state": "running", "step": "support", "progress": 70})
        try:
            preview_path.write_text("\n".join(md), encoding="utf-8")
        except Exception:
            pass

        # 结果
        md.append("\n## 结果\n")
        if plots_dir and job_id:
            plots_path = Path(plots_dir)
            for plot_file in sorted(plots_path.glob("*.png")):
                filename = plot_file.name
                image_url = f"/static/jobs/{job_id}/plots/{filename}"
                md.append(f"### {filename}\n")
                md.append(f"![{filename}]({image_url})\n")
                try:
                    desc_prompt = (
                        f"{self.STYLE_GUIDE}\n"
                        f"任务：基于研究主题‘{topic}’和计划‘{plan_str}’，完整描述图表‘{filename}’的内容，包括数据分布、趋势、异常值等。"
                    )
                    # 使用多模态：将本地图片以data URI传入
                    description = llm.generate_with_images(
                        desc_prompt,
                        image_paths=[str(plot_file)],
                    ).strip()
                except Exception:
                    description = "图表展示了数据的主要分布或趋势。"
                try:
                    analysis_prompt = (
                        f"{STYLE_GUIDE}\n"
                        f"任务：基于执行日志摘要与计划，对图表‘{filename}’进行结果解读，包括数据趋势、异常值、差异对比等。并且对数据中体现的结论、特殊情况提出合理的解释和说明。\n"
                        f"计划：{plan_str}\n执行日志摘要：{log_summary}"
                    )
                    analysis = llm.generate_with_images(
                        analysis_prompt,
                        image_paths=[str(plot_file)],
                    ).strip()
                except Exception:
                    analysis = "图表结果体现了样本的基本特征与差异。"
                md.append(f"**描述：** {description}\n")
                md.append(f"**解读：** {analysis}\n\n")
                self._update_status(job_dir, {"state": "running", "step": "results", "progress": 85})
                try:
                    preview_path.write_text("\n".join(md), encoding="utf-8")
                except Exception:
                    pass
        else:
            md.append("无可展示图表。\n")

        # 讨论
        try:
            discussion_prompt = (
                f"{self.STYLE_GUIDE}\n"
                "任务：撰写结果讨论。结合真实世界数据的复杂性，解释可能的现象与机制，指出与既往研究的一致与差异。\n"
                f"主题: {topic}\n计划摘要: {plan_str}\n日志摘要: {log_summary}"
            )
            discussion = llm.generate(discussion_prompt).strip()
        except Exception:
            discussion = "结果提示了数据中的若干趋势与差异，这与真实世界数据的多样性相符。需要结合临床背景进一步验证与解释。"
        md.append("\n## 讨论\n")
        md.append(f"{discussion}\n")
        self._update_status(job_dir, {"state": "running", "step": "discussion", "progress": 90})
        try:
            preview_path.write_text("\n".join(md), encoding="utf-8")
        except Exception:
            pass

        # 局限性
        try:
            limits_prompt = (
                f"{self.STYLE_GUIDE}\n"
                "任务：列出本研究的局限性（3-5条要点），聚焦数据质量、偏倚与方法约束。\n"
                "输出格式：仅为要点式列表，每行以‘- ’开头，不添加引言语句或英文括注。\n"
                f"日志摘要: {log_summary}"
            )
            limits = llm.generate(limits_prompt).strip()
        except Exception:
            limits = "- 数据缺失与测量误差可能影响结论\n- 非随机分组引入选择偏倚\n- 统计方法未覆盖所有混杂因素\n- 结果需要在更大样本中验证"
        md.append("\n## 局限性\n")
        md.append(f"{limits}\n")
        self._update_status(job_dir, {"state": "running", "step": "limitations", "progress": 95})
        try:
            preview_path.write_text("\n".join(md), encoding="utf-8")
        except Exception:
            pass

        # 展望
        try:
            outlook_prompt = (
                f"{self.STYLE_GUIDE}\n"
                "任务：撰写后续研究展望，包含数据补充、方法升级与外部验证。\n"
                f"主题: {topic}"
            )
            outlook = llm.generate(outlook_prompt).strip()
        except Exception:
            outlook = "后续可补充更多中心的数据、引入更严格的匹配与因果推断方法，并进行多队列外部验证以提升证据强度。"
        md.append("\n## 展望\n")
        md.append(f"{outlook}\n")
        self._update_status(job_dir, {"state": "running", "step": "outlook", "progress": 97})
        try:
            preview_path.write_text("\n".join(md), encoding="utf-8")
        except Exception:
            pass

        # 结论
        try:
            conclusion_prompt = (
                f"{self.STYLE_GUIDE}\n"
                "任务：撰写简洁结论，聚焦主题与主要发现。\n"
                f"主题: {topic}\n计划摘要: {plan_str}"
            )
            conclusion = llm.generate(conclusion_prompt).strip()
        except Exception:
            conclusion = "本次真实世界研究初步揭示了目标主题相关的关键特征与趋势，为后续深入研究提供依据。"
        md.append("\n## 结论\n")
        md.append(f"{conclusion}\n")
        self._update_status(job_dir, {"state": "running", "step": "conclusion", "progress": 99})
        try:
            preview_path.write_text("\n".join(md), encoding="utf-8")
        except Exception:
            pass

        # 附录与可复现性
        md.append("\n## 附录（可复现性）\n")
        md.append(f"- 代码文件：`{job_dir}/analysis.py`\n")
        if plots_dir and job_id:
            plots_path = Path(plots_dir)
            files = [p.name for p in sorted(plots_path.glob("*.png"))]
            if files:
                md.append(f"- 图表文件共 {len(files)} 张：{', '.join(files[:10])}{' 等' if len(files) > 10 else ''}\n")
                md.append(f"- 静态目录：`/static/jobs/{job_id}/plots/`\n")
        md.append(f"- 执行日志摘要：\n\n```")
        md.append(log_summary)
        md.append("```\n")

        # 附上代码
        md.append(f"- 分析代码：\n\n```")
        with open(Path(job_dir) / 'analysis.py', 'r', encoding='utf-8') as f:
            md.append(f.read())
        md.append("```\n")

        report_path.write_text("\n".join(md), encoding="utf-8")
        self._update_status(job_dir, {"state": "done", "step": "done", "progress": 100, "report_path": str(report_path)})
        return str(report_path)

    def generate_section(
        self,
        job_dir: str,
        topic: str,
        plan: dict,
        exec_result: dict,
        excel_info: dict,
        section_id: str,
        job_id: Optional[str] = None,
        human_note: Optional[str] = None,
        guidelines: Optional[str] = None,
    ) -> str:
        md = []
        llm = LLMClient()
        steps_val = plan.get('steps', []) or []
        steps_str = ", ".join([str(self._step_to_text(s)) for s in steps_val])
        plan_str = f"objective: {plan.get('objective', '')} steps: {steps_str}"
        logs_list = exec_result.get('logs', []) or []
        log_summary = self._summarize_logs(logs_list)
        methods_detected = self._detect_methods(logs_list)
        plots_dir = Path(job_dir) / 'plots' if job_id else None
        style = self.STYLE_GUIDE + ("\n" + guidelines.strip() if isinstance(guidelines, str) and guidelines.strip() else "")

        if section_id == 'abstract':
            try:
                abstract_prompt = (
                    f"{style}\n"
                    "任务：撰写摘要（不超过200字），包含背景、方法、主要发现与结论。"
                    f"主题: {topic}\n计划摘要: {plan_str}\n日志摘要: {log_summary}"
                )
                abstract = llm.generate(abstract_prompt).strip()
            except Exception:
                abstract = f"针对{topic}的真实世界研究，采用{', '.join(methods_detected or ['EDA'])}方法，揭示了关键特征与趋势。"
            md.append("## 摘要\n")
            md.append(f"{abstract}\n")
            if human_note:
                md.append(f"{human_note.strip()}\n")

        elif section_id == 'background':
            try:
                background_prompt = (
                    f"{style}\n"
                    "任务：撰写背景与目标（200-300字），包含文献综述、研究空白与具体目标。"
                    f"主题: {topic}\n计划摘要: {plan_str}"
                )
                background = llm.generate(background_prompt).strip()
            except Exception:
                background = f"{topic}是真实世界研究的重要领域，本研究旨在揭示其关键特征与关联。"
            md.append("## 背景与目标\n")
            md.append(f"{background}\n")
            if human_note:
                md.append(f"{human_note.strip()}\n")

        elif section_id == 'data':
            md.append('## 数据说明\n')
            excel_path = excel_info.get('path')
            if excel_path:
                md.append(f'- 源数据文件：`{excel_path}`\n')
            md.append(f"- Sheets：{excel_info.get('sheets')}\n")
            prof = excel_info.get('profile', {}) or {}
            if prof:
                for s in excel_info.get('sheets', []) or []:
                    p = prof.get(s) or {}
                    dtypes = p.get('dtypes', {})
                    if dtypes:
                        kinds = {k: v for k, v in list(dtypes.items())[:10]}
                        md.append(f"  - {s} 字段类型示例：{kinds}\n")
            md.append(f"- 字段匹配策略：精确匹配 > 标准化匹配 > 概念别名提示；无法匹配即跳过，并在日志打印可用列。\n")
            if human_note:
                md.append(f"{human_note.strip()}\n")
        elif section_id == 'data_table':
            md.append('## 数据表分析与案例解读\n')
            excel_path = excel_info.get('path')
            sheets = excel_info.get('sheets', []) or []
            columns_map = excel_info.get('columns', {}) or {}
            profile = excel_info.get('profile', {}) or {}
            for s in sheets:
                p = profile.get(s, {}) or {}
                dtypes = p.get('dtypes', {}) or {}
                miss = p.get('missing_rate', {}) or {}
                cand = p.get('candidate_keys', []) or []
                n_fields = len(dtypes) if dtypes else len(columns_map.get(s, []) or [])
                md.append(f"- Sheet：{s} | 字段数：{n_fields} | 候选主键：{cand[:3]}\n")
                if miss:
                    top_missing = sorted(miss.items(), key=lambda x: x[1], reverse=True)[:3]
                    md.append(f"  - 缺失率最高字段：{[k for k, _ in top_missing]}\n")
                if _pd is not None and excel_path:
                    try:
                        df = _pd.read_excel(excel_path, sheet_name=s, nrows=300)
                        df_prof = self._profile_df(df)
                        cases = self._select_cases(df, df_prof)
                        for c in cases:
                            try:
                                case_prompt = (
                                    f"{style}\n"
                                    "任务：结合研究主题与计划，对下述代表性样本进行简洁的专业解读（80-120字），突出其在数据分布、异常及机制上的意义。\n"
                                    f"主题：{topic}\n计划摘要：{plan_str}\nSheet：{s}\n类型：{c.get('type')}\n列：{c.get('column')}\n样本：{json.dumps(c.get('row', {}), ensure_ascii=False)}"
                                )
                                case_text = llm.generate(case_prompt).strip()
                            except Exception:
                                case_text = "该样本体现了数据的典型或异常特征，具有分析价值。"
                            md.append(f"  - 案例（{c.get('type')}）：{case_text}\n")
                    except Exception:
                        pass
            if human_note:
                md.append(f"{human_note.strip()}\n")
        elif section_id == 'methods':
            try:
                methods_prompt = (
                    f"{style}\n"
                    "任务：撰写方法学（200-300字），涵盖数据来源、处理步骤、分析方法与工具。"
                    f"主题: {topic}\n计划摘要: {plan_str}\n日志摘要: {log_summary}\n检测方法: {', '.join(methods_detected)}"
                )
                methods = llm.generate(methods_prompt).strip()
            except Exception:
                methods = f"本研究采用{', '.join(methods_detected or ['EDA'])}等方法，对数据进行清洗、转换与分析，使用Python与相关库实现。"
            md.append('## 方法\n')
            md.append(f'{methods}\n')
            if human_note:
                md.append(f"{human_note.strip()}\n")
        elif section_id == 'results':
            md.append('## 结果\n')
            md.append(f'{log_summary}\n')
            if plots_dir and plots_dir.exists():
                for plot in sorted(plots_dir.glob('*.png')):
                    rel_path = f'plots/{plot.name}'
                    try:
                        desc_prompt = f"{style}\n任务：描述此图（不超过100字），聚焦关键发现与含义。主题: {topic}\n[假设这是{plot.stem}相关的图]"
                        desc = llm.generate(desc_prompt).strip()
                    except Exception:
                        desc = f"{plot.stem}的可视化结果。"
                    md.append(f'![{plot.stem}]({rel_path})\n{desc}\n')
            if human_note:
                md.append(f"{human_note.strip()}\n")
        elif section_id == 'discussion':
            try:
                discussion_prompt = (
                    f"{style}\n"
                    "任务：撰写讨论（200-300字），解释结果含义、与文献比较及实际意义。"
                    f"主题: {topic}\n计划摘要: {plan_str}\n日志摘要: {log_summary}"
                )
                discussion = llm.generate(discussion_prompt).strip()
            except Exception:
                discussion = "结果揭示了关键关联，与现有文献一致，具有潜在临床/政策含义。"
            md.append('## 讨论\n')
            md.append(f'{discussion}\n')
            if human_note:
                md.append(f"{human_note.strip()}\n")
        elif section_id == 'limitations':
            try:
                limitations_prompt = (
                    f"{style}\n"
                    "任务：撰写局限性（100-200字），讨论数据/方法限制及潜在偏差。"
                    f"主题: {topic}\n计划摘要: {plan_str}\n日志摘要: {log_summary}"
                )
                limitations = llm.generate(limitations_prompt).strip()
            except Exception:
                limitations = "本研究受限于数据规模与完整性，未来可扩展更多来源。"
            md.append('## 局限性\n')
            md.append(f'{limitations}\n')
            if human_note:
                md.append(f"{human_note.strip()}\n")
        elif section_id == 'outlook':
            try:
                outlook_prompt = (
                    f"{style}\n"
                    "任务：撰写展望（100-200字），提出未来研究方向与改进建议。"
                    f"主题: {topic}\n计划摘要: {plan_str}\n日志摘要: {log_summary}"
                )
                outlook = llm.generate(outlook_prompt).strip()
            except Exception:
                outlook = "未来可整合多模态数据与高级模型，进一步深化洞见。"
            md.append('## 展望\n')
            md.append(f'{outlook}\n')
            if human_note:
                md.append(f"{human_note.strip()}\n")
        elif section_id == 'conclusion':
            try:
                conclusion_prompt = (
                    f"{style}\n"
                    "任务：撰写简洁结论（不超过120字），聚焦主题与主要发现。"
                    f"主题: {topic}\n计划摘要: {plan_str}"
                )
                conclusion = llm.generate(conclusion_prompt).strip()
            except Exception:
                conclusion = "本次真实世界研究初步揭示了目标主题相关的关键特征与趋势，为后续深入研究提供依据。"
            md.append('## 结论\n')
            md.append(f'{conclusion}\n')
            if human_note:
                md.append(f"{human_note.strip()}\n")
        elif section_id == 'appendix':
            md.append('## 附录\n')
            md.append('### 研究计划\n')
            md.append(f'{plan_str}\n')
            md.append('### 执行日志摘要\n')
            md.append(f'{log_summary}\n')
        else:
            raise ValueError(f"Unknown section: {section_id}")

        content = '\n'.join(md)
        try:
            sections_dir = Path(job_dir) / 'sections'
            sections_dir.mkdir(exist_ok=True)
            sec_path = sections_dir / f"{section_id}.md"
            sec_path.write_text(content, encoding='utf-8')
            manifest_path = Path(job_dir) / 'report_manifest.json'
            manifest = {}
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                except Exception:
                    manifest = {}
            manifest[section_id] = {
                'path': f'sections/{section_id}.md',
                'updated_at': datetime.utcnow().isoformat() + 'Z'
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass
        return content