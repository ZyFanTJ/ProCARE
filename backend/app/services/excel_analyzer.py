from typing import Dict, List, Optional
from openpyxl import load_workbook
import os as _os
import pandas as _pd
import json as _json
from ..core.llm import LLMClient


def _normalize_col(name: str) -> str:
    """将列名标准化：去空格、转小写、移除非字母数字和下划线。"""
    import re as _re
    s = (name or "").strip().lower()
    s = _re.sub(r"\s+", "_", s)
    s = _re.sub(r"[^a-z0-9_\u4e00-\u9fa5]", "", s)
    return s


def analyze_excel_structure(path: str, user_description: Optional[str] = None) -> Dict:
    """
    基础结构解析：只读取sheet列表与首行列名，并提供标准化列名与常见概念别名提示。
    画像(profile)不在此阶段进行，避免在上传后立刻对大量sheet采样带来性能问题。
    后续可调用 refine_excel_profile() 按计划针对性画像。
    """

    wb = load_workbook(filename=path, read_only=True)
    sheets = wb.sheetnames
    columns: Dict[str, List[str]] = {}
    normalized_columns: Dict[str, Dict[str, str]] = {}
    profile: Dict[str, Dict] = {}

    # 性能保护：大量sheet时仅画像前若干个sheet，其余只输出列名
    try:
        max_profile_sheets = int(_os.environ.get("PROFILE_MAX_SHEETS", "8"))
    except Exception:
        max_profile_sheets = 8
    try:
        nrows_sample = int(_os.environ.get("PROFILE_NROWS", "100"))
    except Exception:
        nrows_sample = 100

    for idx, s in enumerate(sheets):
        ws = wb[s]
        headers: List[str] = []
        first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if first_row:
            headers = [str(h).strip() for h in first_row if h is not None]
        columns[s] = headers
        if headers:
            normalized_columns[s] = dict(zip(headers, [*map(_normalize_col, headers)]))
        else:
            normalized_columns[s] = {}

        # 初始不做采样画像；留空，后续按计划细化。
        profile[s] = {
            "dtypes": {},
            "samples": {},
            "top_values": {},
            "missing_rate": {},
            "unique_rate": {},
            "candidate_keys": [],
        }

    # 提供常见概念的别名提示，供LLM匹配参考（不做强绑定，仅提示）
    synonyms_hint = {
        "id": ["id", "patient_id", "编号", "病历号", "患者id", "住院号"],
        "age": ["age", "年龄"],
        "sex": ["sex", "gender", "性别"],
        "date": ["date", "日期", "检测日期", "入院日期", "随访日期"],
        "group": ["group", "分组", "治疗组", "组别"],
        "treatment": ["treatment", "治疗", "用药", "方案"],
        "event": ["event", "事件", "结局", "死亡", "复发"],
        "time": ["time", "时间", "随访时间", "生存时间"],
    }

    info = {
        "path": path,
        "sheets": sheets,
        "columns": columns,
        "normalized_columns": normalized_columns,
        "profile": profile,
        "synonyms_hint": synonyms_hint,
    }
    if user_description:
        info["description"] = user_description
    else:
        info["description"] = ""
    return info


def refine_excel_profile(path: str, excel_info: Dict, plan: Dict) -> Dict:
    """
    按计划细化画像：优先对计划提及的sheet进行采样画像；若未显式提及，则选择前若干个sheet。
    画像包括：dtype_kind、示例值、缺失率、唯一率、Top值、候选主键。
    """
    sheets: List[str] = excel_info.get("sheets", []) or []
    normalized = excel_info.get("normalized_columns", {}) or {}
    profile = excel_info.get("profile", {}) or {}

    try:
        max_sheets = int(_os.environ.get("PROFILE_TARGET_SHEETS", "6"))
    except Exception:
        max_sheets = 6
    try:
        nrows = int(_os.environ.get("PROFILE_NROWS", "200"))
    except Exception:
        nrows = 200

    # 从plan中提取可能的sheet提及
    def _to_text(x):
        if isinstance(x, str):
            return x
        if isinstance(x, dict):
            return " ".join([str(v) for v in x.values() if v is not None])
        return str(x)

    steps = plan.get("steps", []) or []
    plan_text = " \n".join([_to_text(s) for s in steps]).lower()
    mentioned: List[str] = []
    for s in sheets:
        if s and s.lower() in plan_text:
            mentioned.append(s)

    target_sheets = mentioned[:max_sheets] if mentioned else sheets[:max_sheets]

    for s in target_sheets:
        try:
            df = _pd.read_excel(path, sheet_name=s, nrows=nrows)
        except Exception:
            continue

        total = len(df)
        miss_series = df.isna().sum()
        uniq_series = df.nunique(dropna=True)
        mr = (miss_series / total).round(4) if total else miss_series.astype(float) * 0
        ur = (uniq_series / total).round(4) if total else uniq_series.astype(float) * 0
        thr = max(20, int(total * 0.1))

        dtypes_map = {}
        for col, dtype in df.dtypes.items():
            if _pd.api.types.is_numeric_dtype(dtype):
                dtypes_map[str(col)] = "numeric"
            elif _pd.api.types.is_datetime64_any_dtype(dtype):
                dtypes_map[str(col)] = "datetime"
            else:
                nunique = int(uniq_series[col])
                dtypes_map[str(col)] = "categorical" if nunique <= thr else "text"

        samples_map = {str(c): df[c].dropna().astype(str).head(3).tolist() for c in df.columns}

        top_values_map = {}
        for c, k in dtypes_map.items():
            if k in ("categorical", "text"):
                top_values_map[c] = df[c].astype(str).value_counts(dropna=True).head(5).index.tolist()

        sheet_prof = {
            "dtypes": dtypes_map,
            "samples": samples_map,
            "top_values": top_values_map,
            "missing_rate": {str(k): float(v) for k, v in mr.items()},
            "unique_rate": {str(k): float(v) for k, v in ur.items()},
            "candidate_keys": [str(c) for c in df.columns if ur[c] >= 0.9 and mr[c] <= 0.05],
        }

        # 生成知识画像
        kp = _generate_knowledge_profile(s, sheet_prof, plan)
        sheet_prof["knowledge"] = kp

        profile[s] = sheet_prof

    excel_info["profile"] = profile
    excel_info["normalized_columns"] = normalized
    return excel_info

def _generate_knowledge_profile(sheet_name: str, sheet_prof: Dict, plan: Dict) -> Dict:
    """调用LLM生成知识层面的画像（High/Low Granularity Knowledge）。"""
    try:
        llm = LLMClient()
        objective = plan.get("objective", "") or plan.get("topic", "") or ""
        # 仅传递必要的元数据以节省token
        info_json = _json.dumps({
            "dtypes": sheet_prof.get("dtypes"),
            "samples": sheet_prof.get("samples"),
            "candidate_keys": sheet_prof.get("candidate_keys"),
        }, ensure_ascii=False)

        prompt = (
            "你是一名医学真实世界研究(RWS)专家。请根据以下Sheet数据画像和研究计划，生成数据的'知识画像'。\n"
            "请返回严格的JSON格式，包含以下字段：\n"
            "1. variable_roles (Dict[str, str]): 识别 Exposure, Outcome, Covariate, ID, Time 等角色。\n"
            "2. ontology_mapping (Dict[str, str]): 将列名映射到标准医学概念 (如 SNOMED/UMLS 对应的概念名)。\n"
            "3. plausibility (Dict[str, str]): 指出哪些字段的值域看起来合理/不合理，给出简短评价。\n"
            "4. study_design (str): 该Sheet在研究中可能扮演的角色 (如 Cohort Entry, Outcome Assessment, Covariate History)。\n\n"
            f"研究目标: {objective}\n"
            f"Sheet: {sheet_name}\n"
            f"画像: {info_json}\n\n"
            "仅输出JSON，不要解释。"
        )
        res = llm.generate(prompt)
        import re
        m = re.search(r"\{[\s\S]*\}", res)
        if m:
            return _json.loads(m.group(0))
    except Exception as e:
        print(f"[KnowledgeProfile] Error for {sheet_name}: {e}")
    return {
        "variable_roles": {},
        "ontology_mapping": {},
        "plausibility": {},
        "study_design": "Unknown"
    }

def refine_excel_profile_stream(path: str, excel_info: Dict, plan: Dict):
    sheets: List[str] = excel_info.get("sheets", []) or []
    normalized = excel_info.get("normalized_columns", {}) or {}
    profile = excel_info.get("profile", {}) or {}
    try:
        max_sheets = int(_os.environ.get("PROFILE_TARGET_SHEETS", "6"))
    except Exception:
        max_sheets = 6
    try:
        nrows = int(_os.environ.get("PROFILE_NROWS", "200"))
    except Exception:
        nrows = 200
    def _to_text(x):
        if isinstance(x, str):
            return x
        if isinstance(x, dict):
            return " ".join([str(v) for v in x.values() if v is not None])
        return str(x)
    steps = plan.get("steps", []) or []
    plan_text = " \n".join([_to_text(s) for s in steps]).lower()
    mentioned: List[str] = []
    for s in sheets:
        if s and s.lower() in plan_text:
            mentioned.append(s)
    target_sheets = mentioned[:max_sheets] if mentioned else sheets[:max_sheets]
    for s in target_sheets:
        try:
            df = _pd.read_excel(path, sheet_name=s, nrows=nrows)
        except Exception:
            yield f"PROFILE_ERROR:{s}"
            continue
        total = len(df)
        miss_series = df.isna().sum()
        uniq_series = df.nunique(dropna=True)
        mr = (miss_series / total).round(4) if total else miss_series.astype(float) * 0
        ur = (uniq_series / total).round(4) if total else uniq_series.astype(float) * 0
        thr = max(20, int(total * 0.1))
        dtypes_map = {}
        for col, dtype in df.dtypes.items():
            if _pd.api.types.is_numeric_dtype(dtype):
                dtypes_map[str(col)] = "numeric"
            elif _pd.api.types.is_datetime64_any_dtype(dtype):
                dtypes_map[str(col)] = "datetime"
            else:
                nunique = int(uniq_series[col])
                dtypes_map[str(col)] = "categorical" if nunique <= thr else "text"
        samples_map = {str(c): df[c].dropna().astype(str).head(3).tolist() for c in df.columns}
        top_values_map = {}
        for c, k in dtypes_map.items():
            if k in ("categorical", "text"):
                top_values_map[c] = df[c].astype(str).value_counts(dropna=True).head(5).index.tolist()
        sheet_prof = {
            "dtypes": dtypes_map,
            "samples": samples_map,
            "top_values": top_values_map,
            "missing_rate": {str(k): float(v) for k, v in mr.items()},
            "unique_rate": {str(k): float(v) for k, v in ur.items()},
            "candidate_keys": [str(c) for c in df.columns if ur[c] >= 0.9 and mr[c] <= 0.05],
        }
        
        # 生成知识画像
        yield f"正在生成知识画像（Sheet: {s}）……"
        kp = _generate_knowledge_profile(s, sheet_prof, plan)
        sheet_prof["knowledge"] = kp

        try:
            llm = LLMClient()
            objective = plan.get("objective", "") or plan.get("topic", "") or ""
            info_json = _json.dumps({
                "dtypes": dtypes_map,
                "missing_rate": sheet_prof["missing_rate"],
                "unique_rate": sheet_prof["unique_rate"],
                "candidate_keys": sheet_prof["candidate_keys"],
                "top_values": top_values_map,
            }, ensure_ascii=False)
            prompt = (
                "请根据以下Sheet数据画像信息生成不超过140字的中文摘要，"
                "描述数据类型分布、缺失与唯一性特点，并指出可能的主键及与研究目标的相关性。\n"
                f"研究目标: {objective}\n"
                f"Sheet: {s}\n"
                f"行数: {total}\n"
                "画像: " + info_json
            )
            summary = llm.generate(prompt).strip()
            sheet_prof["llm_summary"] = summary
        except Exception:
            sheet_prof["llm_summary"] = ""
        profile[s] = sheet_prof
        excel_info["profile"] = profile
        excel_info["normalized_columns"] = normalized
        yield f"正在对 Sheet: {s} 进行数据画像……"
        if sheet_prof.get("llm_summary"):
            yield f"LLM摘要（{s}）"
            yield sheet_prof["llm_summary"]