from pathlib import Path
from typing import Dict, Optional, List
import json

from ..services.chapters import SectionContext, REGISTRY, SECTIONS_META


class ReportAgent:
    def build_report_modular(self, job_dir: str, topic: str, plan: Dict, exec_result: Dict, excel_info: Dict, job_id: Optional[str] = None) -> str:
        job = Path(job_dir)
        report_path = job / "report.md"
        status_path = job / "report_status.json"
        
        # 定义生成依赖 DAG (Generation Order)
        # 遵循 ProCARE: Abstract 依赖于其他所有内容
        dag = {
            "background": [],
            "data": [],
            "data_table": ["data"],
            "methods": ["data"],
            "results": ["methods"], 
            "discussion": ["results"],
            "limitations": ["results"],
            "outlook": ["results"],
            "conclusion": ["discussion", "limitations", "outlook"],
            "data_improvement": ["results"],
            "future_topics": ["results"],
            "appendix": ["results"],
            "abstract": ["conclusion", "background", "data", "methods", "results"] 
        }

        # 拓扑排序确定生成顺序
        generation_order = []
        visited = set()
        temp_visited = set()

        def visit(n):
            if n in visited:
                return
            if n in temp_visited:
                return # Cycle detected, skip
            temp_visited.add(n)
            for m in dag.get(n, []):
                visit(m)
            temp_visited.remove(n)
            visited.add(n)
            generation_order.append(n)

        # 确保所有注册的章节都在 DAG 中被访问
        all_sections = [s['id'] for s in SECTIONS_META if s.get('default')]
        for s in all_sections:
            visit(s)
        
        # 初始化上下文 (此时 context 尚未包含新生成的章节内容)
        ctx = SectionContext(job_dir=job_dir, topic=topic, plan=plan, exec_result=exec_result, excel_info=excel_info, job_id=job_id)
        
        total = len(all_sections)
        completed = 0
        
        # 存储生成的内容
        generated_content: Dict[str, str] = {}

        try:
            status_path.write_text(json.dumps({
                "state": "running",
                "step": "init",
                "progress": 0,
                "total": total,
                "completed": 0,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        # 按 DAG 顺序生成
        for sid in generation_order:
            if sid not in all_sections:
                continue
            
            # 每次生成前刷新上下文，确保能读取到之前生成并写入磁盘的章节
            # (Chapter.render 里虽然没直接读磁盘，但 Abstract 等依赖 ctx.sections_results)
            # 由于 ctx 是对象，我们需要更新它的状态。
            # 简单的做法是：每生成一个章节，写入 sections/ 目录，然后刷新 ctx
            
            try:
                # 生成章节
                content = REGISTRY.render(sid, ctx)
                generated_content[sid] = content
                
                # 写入分章节文件
                sections_dir = job / 'sections'
                sections_dir.mkdir(exist_ok=True)
                (sections_dir / f"{sid}.md").write_text(content, encoding='utf-8')
                
                # 刷新 Context (重新读取 sections)
                ctx = SectionContext(job_dir=job_dir, topic=topic, plan=plan, exec_result=exec_result, excel_info=excel_info, job_id=job_id)

            except Exception as e:
                print(f"Error generating section {sid}: {e}")
                generated_content[sid] = ""

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
            except Exception:
                pass

        # 按 Presentation Order (SECTIONS_META) 组装最终报告
        md_parts = []
        for s in SECTIONS_META:
            sid = s['id']
            if not s.get('default'):
                continue
            content = generated_content.get(sid, "")
            md_parts.append(content)

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