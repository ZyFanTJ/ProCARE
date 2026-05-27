from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    topic: str = Field(..., description="研究主题或研究需求")
    excel_path: str = Field(..., description="已上传的Excel文件路径")
    excel_description: Optional[str] = Field(None, description="用户对Excel的补充描述")


class ResearchResponse(BaseModel):
    job_id: str
    success: bool
    report_path: str


class ExcelInfo(BaseModel):
    path: str
    sheets: List[str]
    columns: Dict[str, List[str]]
    description: Optional[str] = None
    md5: Optional[str] = None


class PlanRequest(BaseModel):
    topic: str
    excel_path: str
    excel_description: Optional[str] = None
    job_id: Optional[str] = None
    mode: str = "instruction"  # instruction / discovery


class PlanResponse(BaseModel):
    job_id: str
    plan: Dict


class PlanRefineRequest(BaseModel):
    job_id: str


class PlanRefineResponse(BaseModel):
    job_id: str
    plan_initial: Optional[Dict] = None
    plan_refined: Dict


class PlanUpdateRequest(BaseModel):
    job_id: str
    plan: Dict


class PlanUpdateResponse(BaseModel):
    ok: bool
    job_id: str


class ExecuteRequest(BaseModel):
    job_id: str


class ExecuteResponse(BaseModel):
    success: bool
    report_path: str
    logs: List[Dict] | None = None
    plots: List[str] | None = None


class SavePlanRequest(BaseModel):
    job_id: str
    plan: Dict


class SavePlanResponse(BaseModel):
    job_id: str
    plan: Dict


# 重新生成报告
class ReportRegenRequest(BaseModel):
    job_id: str

class ReportRegenResponse(BaseModel):
    ok: bool
    report_path: str


class BrainstormRequest(BaseModel):
    job_id: str
    topic: Optional[str] = None


class BrainstormResponse(BaseModel):
    hypotheses: List[str]
