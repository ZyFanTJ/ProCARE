import os
import json
import pandas as pd
import numpy as np
import warnings
import concurrent.futures
import re
from typing import Dict, List, Optional, Generator
from ..core.llm import LLMClient
from ..core.skill_manager import SkillManager

# Suppress openpyxl warnings
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

class DataProfileAgent:
    """
    Independent agent for heterogeneous data profiling.
    Implements a 4-quadrant profiling strategy:
    - High-Granularity Structural (Dataset Stats)
    - Low-Granularity Structural (Field Stats)
    - High-Granularity Knowledge (Study Design, Roles)
    - Low-Granularity Knowledge (Ontology, Validation)
    """

    def __init__(self):
        self.skill_manager = SkillManager()
        self.llm = LLMClient()

    def refine_profile(self, path: str, excel_info: Dict, plan: Dict, use_llm: bool = True) -> Dict:
        """
        Refine the Excel profile based on the research plan.
        """
        # Collect generator results
        for _ in self.refine_profile_stream(path, excel_info, plan, use_llm=use_llm):
            pass
        return excel_info

    def refine_profile_stream(self, path: str, excel_info: Dict, plan: Dict, use_llm: bool = True) -> Generator[str, None, None]:
        """
        Stream the profiling process.
        Updates excel_info in-place.
        Parallelizes knowledge profiling for multiple sheets.
        """
        sheets: List[str] = excel_info.get("sheets", []) or []
        profile = excel_info.get("profile", {}) or {}
        
        # Determine target sheets based on plan
        # If not using LLM (structural only), we profile more sheets (up to 100)
        limit = 100 if not use_llm else int(os.environ.get("PROFILE_TARGET_SHEETS", "8"))
        target_sheets = self._get_target_sheets(sheets, plan, limit=limit)
        nrows = int(os.environ.get("PROFILE_NROWS", "200"))
        
        # Cleanup: Remove empty profiles (legacy placeholders) for non-target sheets
        # to reduce "useless info" in the output file.
        # We keep profiles that have actual data (dtypes not empty).
        keys_to_remove = []
        for k, v in profile.items():
            if k not in target_sheets and (not v.get("dtypes") and not v.get("heterogeneous_profile")):
                keys_to_remove.append(k)
        for k in keys_to_remove:
            del profile[k]
        excel_info["profile"] = profile
        
        # Helper function to process a single sheet
        def process_sheet(sheet_name: str, df: Optional[pd.DataFrame] = None, error: Optional[str] = None, total_rows: Optional[int] = None):
            try:
                if error:
                    return sheet_name, None, error
                
                # 2. Structural Profiling
                structural_profile = self._profile_structural(df, total_rows=total_rows)
                
                # 3. Knowledge Profiling (LLM)
                knowledge_profile = None
                if use_llm:
                    knowledge_profile = self._profile_knowledge(sheet_name, structural_profile, plan)
                
                return sheet_name, (structural_profile, knowledge_profile), None
            except Exception as e:
                return sheet_name, None, f"处理出错 {sheet_name}: {e}"

        # Submit tasks
        # Optimization: Pre-load dataframes to avoid file I/O contention in threads
        # and ensure thread safety (pd.read_excel/openpyxl might not be thread-safe for same file)
        loaded_sheets = {}
        sheet_rows = {}
        try:
            # Use ExcelFile to open once
            xls = pd.ExcelFile(path)
            # Try to get real row counts via openpyxl read-only mode (fast)
            try:
                from openpyxl import load_workbook
                wb = load_workbook(path, read_only=True, data_only=True)
                for s in target_sheets:
                    if s in wb.sheetnames:
                        # max_row includes header, and sometimes empty trailing rows
                        # It's an approximation but better than nrows=200
                        # We subtract 1 for header if > 0
                        mr = wb[s].max_row
                        sheet_rows[s] = max(0, mr - 1) if mr else 0
                wb.close()
            except Exception as e:
                print(f"Failed to get max_row: {e}")

            for s in target_sheets:
                try:
                    loaded_sheets[s] = pd.read_excel(xls, sheet_name=s, nrows=nrows)
                except Exception as e:
                    loaded_sheets[s] = e # Store exception to pass to thread
        except Exception as e:
            yield f"读取Excel文件失败: {e}"
            return

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_sheet = {}
            for s in target_sheets:
                val = loaded_sheets.get(s)
                total_rows = sheet_rows.get(s)
                if isinstance(val, Exception):
                    future_to_sheet[executor.submit(process_sheet, s, None, str(val))] = s
                else:
                    future_to_sheet[executor.submit(process_sheet, s, val, None, total_rows)] = s
            
            yield f"开始并行画像任务 (共 {len(target_sheets)} 个表)..."
            
            for future in concurrent.futures.as_completed(future_to_sheet):
                sheet_name = future_to_sheet[future]
                try:
                    s_name, result, error = future.result()
                    if error:
                        yield error
                        continue
                        
                    structural_profile, knowledge_profile = result
                    
                    if knowledge_profile is None:
                        knowledge_profile = {}

                    # Combine into the 4-quadrant structure
                    legacy_profile = self._map_to_legacy(structural_profile, knowledge_profile)
                    
                    full_profile = {
                        **legacy_profile,
                        "heterogeneous_profile": {
                            "high_structural": structural_profile["high"],
                            "low_structural": structural_profile["low"],
                            "high_knowledge": knowledge_profile.get("high_granularity", {}),
                            "low_knowledge": knowledge_profile.get("low_granularity", {}),
                            "ambiguity_flags": knowledge_profile.get("ambiguity_flags", [])
                        }
                    }
                    
                    profile[s_name] = full_profile
                    # Thread-safe dictionary update (GIL ensures this is atomic for single item assignment)
                    excel_info["profile"] = profile
                    yield f"完成画像: {s_name}"
                    
                except Exception as e:
                    yield f"任务异常 {sheet_name}: {e}"

    def _get_target_sheets(self, sheets: List[str], plan: Dict, limit: int = 8) -> List[str]:
        max_sheets = limit
        
        def _to_text(x):
            if isinstance(x, str): return x
            if isinstance(x, dict): return " ".join([str(v) for v in x.values() if v])
            return str(x)

        steps = plan.get("steps", []) or []
        plan_text = " \n".join([_to_text(s) for s in steps]).lower()
        mentioned = [s for s in sheets if s and s.lower() in plan_text]
        
        # Heuristic: Always include likely critical sheets if not already included
        priority_keywords = ["dm", "demographics", "co", "ds", "baseline", "outcome", "人口", "基线", "治疗"]
        priority_sheets = []
        for s in sheets:
            if any(k in s.lower() for k in priority_keywords):
                priority_sheets.append(s)
        
        # Combine
        final_list = []
        seen = set()
        
        # 1. Mentioned in plan
        for s in mentioned:
            if s not in seen:
                final_list.append(s)
                seen.add(s)
        
        # 2. Priority sheets
        for s in priority_sheets:
            if s not in seen and len(final_list) < max_sheets:
                final_list.append(s)
                seen.add(s)
                
        # 3. Fallback to first N
        if len(final_list) < max_sheets:
            for s in sheets:
                if s not in seen and len(final_list) < max_sheets:
                    final_list.append(s)
                    seen.add(s)
                    
        return final_list

    def _profile_structural(self, df: pd.DataFrame, total_rows: Optional[int] = None) -> Dict:
        """
        Generate High and Low Granularity Structural Profiles.
        """
        # If total_rows is provided (from openpyxl max_row), use it.
        # Otherwise fall back to len(df) (which might be truncated).
        # Note: df is the sample/subset.
        sample_rows = len(df)
        actual_rows = total_rows if total_rows is not None else sample_rows
        
        if sample_rows == 0:
            return {"high": {}, "low": {}}

        # Low Granularity (Field-level)
        dtypes_map = {}
        missing_rate = {}
        unique_rate = {}
        distributions = {}
        samples = {}
        
        # Heuristic for categorical vs text
        thr = max(20, int(sample_rows * 0.1))

        for col in df.columns:
            col_str = str(col)
            series = df[col]
            
            # Types
            dtype = series.dtype
            if pd.api.types.is_numeric_dtype(dtype):
                simple_type = "numeric"
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                simple_type = "datetime"
            else:
                nunique = series.nunique()
                simple_type = "categorical" if nunique <= thr else "text"
            dtypes_map[col_str] = simple_type

            # Missingness (Based on sample)
            n_missing = series.isna().sum()
            mr = round(n_missing / sample_rows, 4)
            missing_rate[col_str] = mr

            # Cardinality (Based on sample)
            n_unique = series.nunique()
            ur = round(n_unique / sample_rows, 4)
            unique_rate[col_str] = ur

            # Distribution / Samples
            valid_series = series.dropna()
            if simple_type == "numeric":
                if len(valid_series) > 0:
                    stats = {
                        "min": float(valid_series.min()),
                        "max": float(valid_series.max()),
                        "mean": float(valid_series.mean()),
                        "std": float(valid_series.std()) if len(valid_series) > 1 else 0.0
                    }
                else:
                    stats = {}
                distributions[col_str] = stats
            else:
                # Top values for categorical/text
                top_counts = valid_series.astype(str).value_counts().head(5)
                distributions[col_str] = top_counts.to_dict()

            # Samples (for LLM context)
            samples[col_str] = valid_series.astype(str).head(3).tolist()

        # High Granularity (Dataset-level)
        # Identify candidate keys
        candidate_keys = [
            c for c in df.columns 
            if unique_rate[str(c)] >= 0.95 and missing_rate[str(c)] <= 0.01
        ]

        high_struct = {
            "rows": actual_rows,
            "columns": len(df.columns),
            "candidate_keys": candidate_keys,
            "quality_indicators": {
                "empty_columns": [c for c, mr in missing_rate.items() if mr == 1.0],
                "constant_columns": [c for c, ur in unique_rate.items() if ur == 0 and missing_rate[c] < 1.0]
            }
        }

        low_struct = {
            "dtypes": dtypes_map,
            "missing_rate": missing_rate,
            "unique_rate": unique_rate,
            "distributions": distributions,
            "samples": samples  # Kept here for LLM usage, but maybe not shown in UI
        }

        return {"high": high_struct, "low": low_struct}

    def _profile_knowledge(self, sheet_name: str, structural_profile: Dict, plan: Dict) -> Dict:
        """
        Generate Knowledge Profile using LLM and DataProfiling skill.
        """
        skill = self.skill_manager.get_skill("data_profiling")
        
        # Prepare context for LLM
        low_struct = structural_profile["low"]
        context_profile = {
            "dtypes": low_struct["dtypes"],
            "missing_rate": low_struct["missing_rate"],
            "unique_rate": low_struct["unique_rate"],
            "distributions": low_struct["distributions"],
            "samples": low_struct["samples"],
            "candidate_keys": structural_profile["high"]["candidate_keys"]
        }
        
        objective = plan.get("objective", "") or plan.get("topic", "") or "General Analysis"

        prompt = skill.render(
            objective=objective,
            sheet_name=sheet_name,
            structural_profile_json=json.dumps(context_profile, ensure_ascii=False)
        )

        try:
            res = self.llm.generate(prompt)
            # Parse JSON from response
            m = re.search(r"\{[\s\S]*\}", res)
            if m:
                json_str = m.group(0)
                # Try standard parsing first
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    # Fallback: simple cleanup for common LLM JSON errors
                    # 1. Replace single quotes with double quotes for keys/strings
                    # Note: This is risky if content has single quotes, but common for 'lazy' LLMs
                    # A better way is using a robust parser if available, or just log error.
                    pass
                    
            # If standard parsing fails, return empty but log
            print(f"[DataProfileAgent] Failed to parse JSON for {sheet_name}. Response: {res[:100]}...")
            return {}
            
        except Exception as e:
            print(f"[DataProfileAgent] Error generating knowledge profile for {sheet_name}: {e}")
        
        return {}

    def _map_to_legacy(self, struct: Dict, knowledge: Dict) -> Dict:
        """
        Map new structure to legacy format for backward compatibility.
        """
        low = struct["high"]
        low_s = struct["low"]
        
        # Extract top values from distributions for categorical/text
        top_values = {}
        for col, dist in low_s["distributions"].items():
            if low_s["dtypes"].get(col) in ("categorical", "text"):
                top_values[col] = list(dist.keys())
        
        return {
            "dtypes": low_s["dtypes"],
            "samples": low_s["samples"],
            "top_values": top_values,
            "missing_rate": low_s["missing_rate"],
            "unique_rate": low_s["unique_rate"],
            "candidate_keys": struct["high"]["candidate_keys"],
            "knowledge": {
                "variable_roles": knowledge.get("high_granularity", {}).get("variable_roles", {}),
                "ontology_mapping": knowledge.get("low_granularity", {}).get("ontology_mapping", {}),
                "plausibility": knowledge.get("low_granularity", {}).get("plausibility_checks", {}),
                "study_design": knowledge.get("high_granularity", {}).get("study_design_schema", "Unknown")
            },
            "llm_summary": knowledge.get("high_granularity", {}).get("study_design_schema", "") 
        }
