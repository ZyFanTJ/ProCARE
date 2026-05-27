from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import os

from ..core.llm import LLMClient
from ..core.skill_manager import SkillManager
from ..skills.report_generation.utils import load_snippet

try:
    import pandas as _pd
except Exception:
    _pd = None

_SKILL_MANAGER = None

def _get_skill_manager():
    global _SKILL_MANAGER
    if not _SKILL_MANAGER:
        _SKILL_MANAGER = SkillManager()
    return _SKILL_MANAGER

def _render_report_skill(instruction_name: str, context_str: str) -> str:
    """Helper to render report generation skill."""
    sm = _get_skill_manager()
    instruction = load_snippet(instruction_name)
    return sm.get_skill("report_generation").render(
        instruction=instruction,
        context=context_str
    )


class SectionContext:
    def __init__(self, job_dir: str, topic: str, plan: Dict, exec_result: Dict, excel_info: Dict, job_id: Optional[str] = None):
        self.job_dir = job_dir
        self.topic = topic
        self.plan = plan or {}
        self.exec_result = exec_result or {}
        self.excel_info = excel_info or {}
        self.job_id = job_id
        self.logs: List[Dict] = self.exec_result.get('logs', []) or []
        self.methods_detected = self._detect_methods(self.logs)
        steps_val = self.plan.get('steps', []) or []
        steps_str = ", ".join([self._step_to_text(s) for s in steps_val])
        self.plan_str = f"objective: {self.plan.get('objective', '')} steps: {steps_str}"
        self.log_summary = self._summarize_logs(self.logs)
        self.plots_dir = Path(self.job_dir) / 'plots' if self.job_id else None
        self.sections_text = ""
        self.sections_results = ""
        self.sections_others = ""
        try:
            sections_dir = Path(self.job_dir) / 'sections'
            if sections_dir.exists():
                texts_map = {}
                for p in sorted(sections_dir.glob('*.md')):
                    try:
                        texts_map[p.stem] = p.read_text(encoding='utf-8')
                    except Exception:
                        pass
                res = texts_map.get('results', '')
                self.sections_results = res or ''
                budget = 30000
                picked: List[str] = []
                for k in ['methods', 'discussion', 'conclusion']:
                    if k in texts_map and k != 'results':
                        picked.append(k)
                for k in sorted(texts_map.keys()):
                    if k not in picked and k != 'results':
                        picked.append(k)
                others: List[str] = []
                used = 0
                for k in picked:
                    t = texts_map.get(k) or ''
                    if not t:
                        continue
                    if used + len(t) <= budget:
                        others.append(t)
                        used += len(t)
                    else:
                        remain = max(0, budget - used)
                        if remain > 0:
                            others.append(t[:remain])
                            used += remain
                        break
                self.sections_others = "\n\n".join(others)
                self.sections_text = (self.sections_results or '') + ("\n\n" + self.sections_others if self.sections_others else '')
        except Exception:
            self.sections_text = ""
            self.sections_results = ""
            self.sections_others = ""

    def _step_to_text(self, s: Dict) -> str:
        name = s.get('name') or s.get('step') or 'step'
        target = s.get('target') or s.get('sheet') or ''
        extra = s.get('desc') or s.get('description') or ''
        return f"{name}{('->' + str(target)) if target else ''}{(':' + str(extra)) if extra else ''}"

    def _summarize_logs(self, logs: List[Dict]) -> str:
        parts = []
        for e in logs[:50]:
            lvl = e.get('level', 'INFO')
            msg = str(e.get('message', ''))
            parts.append(f"[{lvl}] {msg}")
        return "\n".join(parts) if parts else ""

    def _detect_methods(self, logs: List[Dict]) -> List[str]:
        text = "\n".join([str(e.get('message', '')) for e in logs])
        methods = []
        def has(k: str) -> bool:
            return k.lower() in text.lower()
        if has('kaplan') or has('km') or has('survival'):
            methods.append('Kaplan-Meier')
        if has('cox'):
            methods.append('Cox')
        if has('propensity') or has('psm'):
            methods.append('PSM')
        if has('logistic'):
            methods.append('Logistic')
        if has('anova') or has('ttest'):
            methods.append('Hypothesis Testing')
        if has('missing'):
            methods.append('Missing Data')
        if has('matching'):
            methods.append('Matching')
        if not methods:
            methods.append('EDA')
        return methods


STYLE_GUIDE = "" # Deprecated, now in snippets/style_guide.md

def _style_guide() -> str:
    """Deprecated: style guide is now included in SKILL.md via snippet"""
    return ""


class Chapter:
    id: str = ''
    title: str = ''
    parent: str = ''
    desc: str = ''
    default: bool = True

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        raise NotImplementedError

    def _style(self, guidelines: Optional[str]) -> str:
        g = guidelines.strip() if isinstance(guidelines, str) else ''
        return _style_guide() + ("\n" + g if g else '')

    def render_stream_iter(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None):
        content = self.render(ctx, human_note=human_note, guidelines=guidelines)
        step = max(32, len(content) // 200)
        for i in range(0, len(content), step):
            yield content[i:i+step]


class AbstractChapter(Chapter):
    id = 'abstract'
    title = '摘要'
    parent = '核心'
    desc = '研究目的、数据来源与主要结论'

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        llm = LLMClient()
        try:
            context_str = (
                f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}\n日志摘要: {ctx.log_summary}\n结果全文: {ctx.sections_results}\n其他章节: {ctx.sections_others}"
            )
            prompt = _render_report_skill('abstract', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
                
            abstract = llm.generate(prompt).strip()
        except Exception:
            abstract = f"针对{ctx.topic}的真实世界研究，采用{', '.join(ctx.methods_detected or ['EDA'])}方法，揭示了关键特征与趋势。"
        md = ["## 摘要\n", f"{abstract}\n"]
        if human_note:
            md.append(f"{human_note.strip()}\n")
        return "".join(md)

    def render_stream_iter(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None):
        llm = LLMClient()
        yield "## 摘要\n"
        try:
            context_str = (
                f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}\n日志摘要: {ctx.log_summary}\n结果全文: {ctx.sections_results}\n其他章节: {ctx.sections_others}"
            )
            prompt = _render_report_skill('abstract', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
                
            for chunk in llm.stream_iter(prompt):
                yield chunk
        except Exception:
            yield f"针对{ctx.topic}的真实世界研究，采用{', '.join(ctx.methods_detected or ['EDA'])}方法，揭示了关键特征与趋势。"
        if human_note:
            yield f"\n{human_note.strip()}\n"


class BackgroundChapter(Chapter):
    id = 'background'
    title = '背景与目标'
    parent = '核心'
    desc = '研究背景、动机与目标'

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        llm = LLMClient()
        try:
            context_str = f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}"
            prompt = _render_report_skill('background', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            background = llm.generate(prompt).strip()
        except Exception:
            background = f"{ctx.topic}是真实世界研究的重要领域，本研究旨在揭示其关键特征与关联。"
        md = ["## 背景与目标\n", f"{background}\n"]
        if human_note:
            md.append(f"{human_note.strip()}\n")
        return "".join(md)

    def render_stream_iter(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None):
        llm = LLMClient()
        yield "## 背景与目标\n"
        try:
            context_str = f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}"
            prompt = _render_report_skill('background', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            for chunk in llm.stream_iter(prompt):
                yield chunk
        except Exception:
            yield f"{ctx.topic}是真实世界研究的重要领域，本研究旨在揭示其关键特征与关联。"
        if human_note:
            yield f"\n{human_note.strip()}\n"


class DataChapter(Chapter):
    id = 'data'
    title = '数据说明'
    parent = '核心'
    desc = '数据结构与字段画像'

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        llm = LLMClient()
        try:
            context_str = f"计划摘要: {ctx.plan_str}\nExcel结构: {str(ctx.excel_info)[:800]}"
            prompt = _render_report_skill('data', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            data = llm.generate(prompt).strip()
        except Exception:
            data = "数据包含若干表与关键字段，样本量满足基本分析需求。"
        md = ["## 数据说明\n", f"{data}\n"]
        if human_note:
            md.append(f"{human_note.strip()}\n")
        return "".join(md)

    def render_stream_iter(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None):
        llm = LLMClient()
        yield "## 数据说明\n"
        try:
            context_str = f"计划摘要: {ctx.plan_str}\nExcel结构: {str(ctx.excel_info)[:800]}"
            prompt = _render_report_skill('data', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            for chunk in llm.stream_iter(prompt):
                yield chunk
        except Exception:
            yield "数据包含若干表与关键字段，样本量满足基本分析需求。"
        if human_note:
            yield f"\n{human_note.strip()}\n"


class DataTableChapter(Chapter):
    id = 'data_table'
    title = '数据表分析与案例解读'
    parent = '核心'
    desc = '画像与代表性样本'

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        llm = LLMClient()
        md = ["## 数据表分析与案例解读\n"]
        try:
            context_str = f"excel信息: {ctx.excel_info}"
            prompt = _render_report_skill('data_table', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            chunk = llm.generate(prompt).strip()
        except Exception:
            chunk = "字段分布与样本特征显示出多样性，需结合研究目标理解其意义。"
        md.append(f"{chunk}\n")
        if human_note:
            md.append(f"{human_note.strip()}\n")
        return "".join(md)

    def render_stream_iter(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None):
        llm = LLMClient()
        yield "## 数据表分析与案例解读\n"
        try:
            context_str = f"excel信息: {ctx.excel_info}"
            prompt = _render_report_skill('data_table', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            for chunk in llm.stream_iter(prompt):
                yield chunk
        except Exception:
            yield "字段分布与样本特征显示出多样性，需结合研究目标理解其意义。"
        if human_note:
            yield f"\n{human_note.strip()}\n"


class MethodsChapter(Chapter):
    id = 'methods'
    title = '方法'
    parent = '核心'
    desc = '清洗、匹配、统计与可视化方法'

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        llm = LLMClient()
        try:
            context_str = (
                f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}\n日志摘要: {ctx.log_summary}\n检测方法: {', '.join(ctx.methods_detected)}"
            )
            prompt = _render_report_skill('methods', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            methods = llm.generate(prompt).strip()
        except Exception:
            methods = f"本研究采用{', '.join(ctx.methods_detected or ['EDA'])}等方法，对数据进行清洗、转换与分析，使用Python与相关库实现。"
        md = ["## 方法\n", f"{methods}\n"]
        if human_note:
            md.append(f"{human_note.strip()}\n")
        return "".join(md)

    def render_stream_iter(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None):
        llm = LLMClient()
        yield "## 方法\n"
        try:
            context_str = (
                f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}\n日志摘要: {ctx.log_summary}\n检测方法: {', '.join(ctx.methods_detected)}"
            )
            prompt = _render_report_skill('methods', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            for chunk in llm.stream_iter(prompt):
                yield chunk
        except Exception:
            yield f"本研究采用{', '.join(ctx.methods_detected or ['EDA'])}等方法，对数据进行清洗、转换与分析，使用Python与相关库实现。"
        if human_note:
            yield f"\n{human_note.strip()}\n"


class ResultsChapter(Chapter):
    id = 'results'
    title = '结果'
    parent = '核心'
    desc = '图表描述与解读'

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        llm = LLMClient()
        md = ["## 结果\n"]
        img_files: List[Path] = []
        other_files: List[Path] = []
        if ctx.plots_dir and ctx.plots_dir.exists():
            for p in sorted(ctx.plots_dir.glob('*')):
                if p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif'}:
                    img_files.append(p)
                else:
                    other_files.append(p)
        for p in img_files[:12]:
            fname = p.name
            try:
                context_str = f"图表: {fname}\n日志摘要: {ctx.log_summary}"
                prompt = _render_report_skill('results_image', context_str)
                if guidelines:
                    prompt += f"\n额外指导: {guidelines}"
                text = llm.generate_with_images(prompt, image_paths=[str(p)]).strip()
            except Exception:
                text = f"图表 {fname} 展示了数据的主要趋势。"
            md.append(f"![{p.stem}](/static/jobs/{ctx.job_id}/plots/{fname})\n{text}\n")
        if other_files:
            md.append("\n### 附件与表格分析\n")
            for p in other_files[:8]:
                fname = p.name
                if p.suffix.lower() in {'.csv', '.tsv'} and _pd is not None:
                    try:
                        sep = ',' if p.suffix.lower() == '.csv' else '\t'
                        df = _pd.read_csv(str(p), sep=sep)
                        n_rows, n_cols = df.shape
                        cols = [str(c) for c in list(df.columns)[:10]]
                        miss = df.isna().sum() / max(n_rows, 1)
                        top_missing = sorted([(str(k), float(v)) for k, v in miss.items()], key=lambda x: x[1], reverse=True)[:3]
                        sample = df.head(5).to_dict(orient='records')
                        payload = {
                            "file": fname,
                            "dims": {"rows": int(n_rows), "cols": int(n_cols)},
                            "columns": cols,
                            "missing_top": top_missing,
                            "samples": sample,
                        }
                        context_str = (
                            f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}\n表格画像: {json.dumps(payload, ensure_ascii=False)}"
                        )
                        prompt = _render_report_skill('results_table', context_str)
                        if guidelines:
                            prompt += f"\n额外指导: {guidelines}"
                        text = llm.generate(prompt).strip()
                        md.append(f"- `{fname}`\n")
                        md.append(text + "\n")
                    except Exception:
                        md.append(f"- `{fname}`\n")
                else:
                    md.append(f"- `{fname}`\n")
        if not img_files and not other_files:
            md.append("无可展示图表。\n")
        if human_note:
            md.append(f"{human_note.strip()}\n")
        return "".join(md)

    def render_stream_iter(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None):
        llm = LLMClient()
        yield "## 结果\n"
        img_files: List[Path] = []
        other_files: List[Path] = []
        if ctx.plots_dir and ctx.plots_dir.exists():
            for p in sorted(ctx.plots_dir.glob('*')):
                if p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif'}:
                    img_files.append(p)
                else:
                    other_files.append(p)
        for p in img_files[:12]:
            fname = p.name
            yield f"![{p.stem}](/static/jobs/{ctx.job_id}/plots/{fname})\n"
            try:
                context_str = f"图表: {fname}\n日志摘要: {ctx.log_summary}"
                prompt = _render_report_skill('results_image', context_str)
                if guidelines:
                    prompt += f"\n额外指导: {guidelines}"
                text = llm.generate_with_images(prompt, image_paths=[str(p)]).strip()
                yield text + "\n"
            except Exception:
                yield f"图表 {fname} 展示了数据的主要趋势。\n"
        if other_files:
            yield "\n### 附件与表格分析\n"
            for p in other_files[:8]:
                fname = p.name
                if p.suffix.lower() in {'.csv', '.tsv'} and _pd is not None:
                    try:
                        sep = ',' if p.suffix.lower() == '.csv' else '\t'
                        df = _pd.read_csv(str(p), sep=sep)
                        n_rows, n_cols = df.shape
                        cols = [str(c) for c in list(df.columns)[:10]]
                        miss = df.isna().sum() / max(n_rows, 1)
                        top_missing = sorted([(str(k), float(v)) for k, v in miss.items()], key=lambda x: x[1], reverse=True)[:3]
                        sample = df.head(5).to_dict(orient='records')
                        payload = {
                            "file": fname,
                            "dims": {"rows": int(n_rows), "cols": int(n_cols)},
                            "columns": cols,
                            "missing_top": top_missing,
                            "samples": sample,
                        }
                        context_str = (
                            f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}\n表格画像: {json.dumps(payload, ensure_ascii=False)}"
                        )
                        prompt = _render_report_skill('results_table', context_str)
                        if guidelines:
                            prompt += f"\n额外指导: {guidelines}"
                        yield f"- `{fname}`\n"
                        for chunk in llm.stream_iter(prompt):
                            yield chunk
                        yield "\n"
                    except Exception:
                        yield f"- `{fname}`\n"
                else:
                    yield f"- `{fname}`\n"
        if not img_files and not other_files:
            yield "无可展示图表。\n"
        if human_note:
            yield f"{human_note.strip()}\n"


class DiscussionChapter(Chapter):
    id = 'discussion'
    title = '讨论'
    parent = '核心'
    desc = '解释现象与机制，比较既往研究'

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        llm = LLMClient()
        try:
            context_str = f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}\n日志摘要: {ctx.log_summary}"
            prompt = _render_report_skill('discussion', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            discussion = llm.generate(prompt).strip()
        except Exception:
            discussion = "结果提示了数据中的若干趋势与差异，这与真实世界数据的多样性相符。需要结合临床背景进一步验证与解释。"
        md = ["## 讨论\n", f"{discussion}\n"]
        if human_note:
            md.append(f"{human_note.strip()}\n")
        return "".join(md)

    def render_stream_iter(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None):
        llm = LLMClient()
        yield "## 讨论\n"
        try:
            context_str = f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}\n日志摘要: {ctx.log_summary}"
            prompt = _render_report_skill('discussion', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            for chunk in llm.stream_iter(prompt):
                yield chunk
        except Exception:
            yield "结果提示了数据中的若干趋势与差异，这与真实世界数据的多样性相符。需要结合临床背景进一步验证与解释。"
        if human_note:
            yield f"\n{human_note.strip()}\n"


class LimitationsChapter(Chapter):
    id = 'limitations'
    title = '局限性'
    parent = '核心'
    desc = '数据质量、偏倚与方法约束'

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        llm = LLMClient()
        try:
            context_str = f"日志摘要: {ctx.log_summary}"
            prompt = _render_report_skill('limitations', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            limits = llm.generate(prompt).strip()
        except Exception:
            limits = "数据来源与质量存在限制，潜在偏倚与方法约束需谨慎解读。"
        md = ["## 局限性\n", f"{limits}\n"]
        if human_note:
            md.append(f"{human_note.strip()}\n")
        return "".join(md)

    def render_stream_iter(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None):
        llm = LLMClient()
        yield "## 局限性\n"
        try:
            context_str = f"日志摘要: {ctx.log_summary}"
            prompt = _render_report_skill('limitations', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            for chunk in llm.stream_iter(prompt):
                yield chunk
        except Exception:
            yield "数据来源与质量存在限制，潜在偏倚与方法约束需谨慎解读。"
        if human_note:
            yield f"\n{human_note.strip()}\n"


class OutlookChapter(Chapter):
    id = 'outlook'
    title = '展望'
    parent = '核心'
    desc = '后续研究方向与方法升级'

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        llm = LLMClient()
        try:
            context_str = f"主题: {ctx.topic}"
            prompt = _render_report_skill('outlook', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            outlook = llm.generate(prompt).strip()
        except Exception:
            outlook = "未来可整合多模态数据与高级模型，进一步深化洞见。"
        md = ["## 展望\n", f"{outlook}\n"]
        if human_note:
            md.append(f"{human_note.strip()}\n")
        return "".join(md)

    def render_stream_iter(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None):
        llm = LLMClient()
        yield "## 展望\n"
        try:
            context_str = f"主题: {ctx.topic}"
            prompt = _render_report_skill('outlook', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            for chunk in llm.stream_iter(prompt):
                yield chunk
        except Exception:
            yield "未来可整合多模态数据与高级模型，进一步深化洞见。"
        if human_note:
            yield f"\n{human_note.strip()}\n"


class ConclusionChapter(Chapter):
    id = 'conclusion'
    title = '结论'
    parent = '核心'
    desc = '主要发现与意义'

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        llm = LLMClient()
        try:
            context_str = f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}"
            prompt = _render_report_skill('conclusion', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            conclusion = llm.generate(prompt).strip()
        except Exception:
            conclusion = "本次真实世界研究初步揭示了目标主题相关的关键特征与趋势，为后续深入研究提供依据。"
        md = ["## 结论\n", f"{conclusion}\n"]
        if human_note:
            md.append(f"{human_note.strip()}\n")
        return "".join(md)

    def render_stream_iter(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None):
        llm = LLMClient()
        yield "## 结论\n"
        try:
            context_str = f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}"
            prompt = _render_report_skill('conclusion', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            for chunk in llm.stream_iter(prompt):
                yield chunk
        except Exception:
            yield "本次真实世界研究初步揭示了目标主题相关的关键特征与趋势，为后续深入研究提供依据。"
        if human_note:
            yield f"\n{human_note.strip()}\n"


class AppendixChapter(Chapter):
    id = 'appendix'
    title = '附录'
    parent = '核心'
    desc = '代码、图表列表与日志摘要'
    default = False

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        md = ["## 附录（可复现性）\n"]
        md.append(f"- 代码文件：`{ctx.job_dir}/analysis.py`\n")
        if ctx.plots_dir and ctx.job_id:
            files = [p.name for p in sorted(ctx.plots_dir.glob('*.png'))]
            if files:
                md.append(f"- 图表文件共 {len(files)} 张：{', '.join(files[:10])}{' 等' if len(files) > 10 else ''}\n")
                md.append(f"- 静态目录：`/static/jobs/{ctx.job_id}/plots/`\n")
        md.append(f"- 执行日志摘要：\n\n```")
        md.append(ctx.log_summary)
        md.append("```\n")
        try:
            with open(Path(ctx.job_dir) / 'analysis.py', 'r', encoding='utf-8') as f:
                md.append("- 分析代码：\n\n```")
                md.append(f.read())
                md.append("```\n")
        except Exception:
            pass
        if human_note:
            md.append(f"{human_note.strip()}\n")
        return "".join(md)


class DataImprovementChapter(Chapter):
    id = 'data_improvement'
    title = '数据完善与优化建议'
    parent = '扩展'
    desc = '面向缺失与质量的改进建议及影响评估'

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        llm = LLMClient()
        sheets = ctx.excel_info.get('sheets', []) or []
        profile = ctx.excel_info.get('profile', {}) or {}
        overall_missing = []
        try:
            for s in sheets:
                miss = (profile.get(s, {}) or {}).get('missing_rate', {}) or {}
                for k, v in miss.items():
                    overall_missing.append((s, k, float(v)))
        except Exception:
            overall_missing = []
        top_missing = sorted(overall_missing, key=lambda x: x[2], reverse=True)[:12]
        keys_map = {}
        try:
            for s in sheets:
                keys_map[s] = (profile.get(s, {}) or {}).get('candidate_keys', []) or []
        except Exception:
            keys_map = {}
        payload = {
            'objective': ctx.plan_str,
            'top_missing': [(str(a), str(b), float(c)) for a, b, c in top_missing],
            'candidate_keys': keys_map,
            'results': ctx.sections_results,
            'others': ctx.sections_others[:30000],
        }
        try:
            payload = {
                'objective': ctx.plan_str,
                'top_missing': [(str(a), str(b), float(c)) for a, b, c in top_missing],
                'candidate_keys': keys_map,
                'results': ctx.sections_results,
                'others': ctx.sections_others[:30000],
            }
            context_str = (
                f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}\n画像摘要: {json.dumps(payload, ensure_ascii=False)}"
            )
            prompt = _render_report_skill('data_improvement', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            text = llm.generate(prompt).strip()
        except Exception:
            lines = []
            if top_missing:
                for s, k, v in top_missing[:6]:
                    lines.append(f"- {s}.{k} 缺失率≈{int(v*100)}%，建议统一编码字典并补录关键值")
            else:
                lines.append("- 关键字段缺失情况待画像补充，建议完善采集字典与校验")
            lines.append("- 对结局相关字段进行严格校验与补录，提升因果推断力度")
            lines.append("- 清洗文本型字段（如影像描述）并结构化，增强统计可用性")
            text = "\n".join(lines)
        md = ["## 数据完善与优化建议\n", f"{text}\n"]
        if human_note:
            md.append(f"{human_note.strip()}\n")
        return "".join(md)

    def render_stream_iter(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None):
        llm = LLMClient()
        yield "## 数据完善与优化建议\n"
        sheets = ctx.excel_info.get('sheets', []) or []
        profile = ctx.excel_info.get('profile', {}) or {}
        overall_missing = []
        try:
            for s in sheets:
                miss = (profile.get(s, {}) or {}).get('missing_rate', {}) or {}
                for k, v in miss.items():
                    overall_missing.append((s, k, float(v)))
        except Exception:
            overall_missing = []
        top_missing = sorted(overall_missing, key=lambda x: x[2], reverse=True)[:12]
        keys_map = {}
        try:
            for s in sheets:
                keys_map[s] = (profile.get(s, {}) or {}).get('candidate_keys', []) or []
        except Exception:
            keys_map = {}
        payload = {
            'objective': ctx.plan_str,
            'top_missing': [(str(a), str(b), float(c)) for a, b, c in top_missing],
            'candidate_keys': keys_map,
            'results': ctx.sections_results,
            'others': ctx.sections_others[:30000],
        }
        try:
            payload = {
                'objective': ctx.plan_str,
                'top_missing': [(str(a), str(b), float(c)) for a, b, c in top_missing],
                'candidate_keys': keys_map,
                'results': ctx.sections_results,
                'others': ctx.sections_others[:30000],
            }
            context_str = (
                f"主题: {ctx.topic}\n计划摘要: {ctx.plan_str}\n画像摘要: {json.dumps(payload, ensure_ascii=False)}"
            )
            prompt = _render_report_skill('data_improvement', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            for chunk in llm.stream_iter(prompt):
                yield chunk
        except Exception:
            yield "- 关键字段缺失情况待画像补充，建议完善采集字典与校验\n"
        if human_note:
            yield f"\n{human_note.strip()}\n"


class FutureTopicsChapter(Chapter):
    id = 'future_topics'
    title = '潜在研究主题建议'
    parent = '扩展'
    desc = '基于结果与画像提出新主题与假设'

    def render(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        llm = LLMClient()
        payload = {
            'objective': ctx.plan_str,
            'results': ctx.sections_results,
            'others': ctx.sections_others[:30000],
            'profile_hint': (ctx.excel_info or {}).get('profile', {}),
        }
        try:
            context_str = (
                f"主题: {ctx.topic}\n参考: {json.dumps(payload, ensure_ascii=False)}"
            )
            prompt = _render_report_skill('future_topics', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            text = llm.generate(prompt).strip()
        except Exception:
            text = (
                "- 按治疗方案与基线协变量分层的生存差异探究\n"
                "- 生物标志物阈值与复发风险的非线性关系\n"
                "- 随访方式与结局记录完整性对OS/RFS的影响\n"
                "- 影像文本结构化后对预后评估的增益\n"
            )
        md = ["## 潜在研究主题建议\n", f"{text}\n"]
        if human_note:
            md.append(f"{human_note.strip()}\n")
        return "".join(md)

    def render_stream_iter(self, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None):
        llm = LLMClient()
        yield "## 潜在研究主题建议\n"
        payload = {
            'objective': ctx.plan_str,
            'results': ctx.sections_results,
            'others': ctx.sections_others[:30000],
            'profile_hint': (ctx.excel_info or {}).get('profile', {}),
        }
        try:
            context_str = (
                f"主题: {ctx.topic}\n参考: {json.dumps(payload, ensure_ascii=False)}"
            )
            prompt = _render_report_skill('future_topics', context_str)
            if guidelines:
                prompt += f"\n额外指导: {guidelines}"
            for chunk in llm.stream_iter(prompt):
                yield chunk
        except Exception:
            yield (
                "- 按治疗方案与基线协变量分层的生存差异探究\n"
                "- 生物标志物阈值与复发风险的非线性关系\n"
            )
        if human_note:
            yield f"\n{human_note.strip()}\n"


class ChapterRegistry:
    def __init__(self):
        self._items: Dict[str, Chapter] = {}
        self._order: List[str] = []
        self._register(
            AbstractChapter(),
            BackgroundChapter(),
            DataChapter(),
            DataTableChapter(),
            MethodsChapter(),
            ResultsChapter(),
            DiscussionChapter(),
            LimitationsChapter(),
            OutlookChapter(),
            ConclusionChapter(),
            AppendixChapter(),
            DataImprovementChapter(),
            FutureTopicsChapter(),
        )

    def _register(self, *chapters: Chapter):
        for c in chapters:
            self._items[c.id] = c
            self._order.append(c.id)

    def render(self, section_id: str, ctx: SectionContext, human_note: Optional[str] = None, guidelines: Optional[str] = None) -> str:
        c = self._items.get(section_id)
        if not c:
            raise ValueError(f"Unknown section: {section_id}")
        return c.render(ctx, human_note=human_note, guidelines=guidelines)

    def meta(self) -> List[Dict]:
        items = []
        for sid in self._order:
            c = self._items[sid]
            items.append({
                'id': c.id,
                'title': c.title,
                'desc': c.desc,
                'default': getattr(c, 'default', True),
                'parent': c.parent or '其他',
            })
        return items


REGISTRY = ChapterRegistry()
SECTIONS_META = REGISTRY.meta()