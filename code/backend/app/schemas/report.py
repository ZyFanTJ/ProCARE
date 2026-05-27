from datetime import datetime

from pydantic import BaseModel, Field


class ReportSummary(BaseModel):
    title: str
    section_count: int
    image_reference_count: int
    asset_count: int
    reference_asset_count: int = 0
    reference_entry_count: int = 0
    headings: list[str] = Field(default_factory=list)
    referenced_assets: list[str] = Field(default_factory=list)


class ReportCreateResponse(BaseModel):
    task_id: str
    status: str
    message: str


class LastInputResponse(BaseModel):
    task_id: str
    report_name: str
    markdown_name: str
    report_language: str = "zh"
    template_path: str | None = None
    asset_names: list[str] = Field(default_factory=list)
    reference_asset_names: list[str] = Field(default_factory=list)
    llm_enabled: bool = True
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: int | None = None


class ArtifactFile(BaseModel):
    name: str
    path: str
    category: str


class ReportStatusResponse(BaseModel):
    task_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    report_name: str
    markdown_name: str
    report_language: str = "zh"
    asset_names: list[str] = Field(default_factory=list)
    reference_asset_names: list[str] = Field(default_factory=list)
    template_path: str | None = None
    output_file: str | None = None
    final_markdown_file: str | None = None
    latex_file: str | None = None
    archive_dir: str | None = None
    output_type: str | None = None
    compile_engine: str | None = None
    llm_enabled: bool = True
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: int | None = None
    intermediate_files: list[ArtifactFile] = Field(default_factory=list)
    summary: ReportSummary | None = None
    error: str | None = None
