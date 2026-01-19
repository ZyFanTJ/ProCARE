from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

# Profile Components
class ProfileHighStructural(BaseModel):
    sheet_list: List[str] = Field(default_factory=list)
    stats: Dict[str, Any] = Field(default_factory=dict)
    quality_indicators: Dict[str, Any] = Field(default_factory=dict)

class ProfileHighKnowledge(BaseModel):
    study_design: str = ""
    variable_roles: Dict[str, str] = Field(default_factory=dict)
    feasibility: str = ""
    compliance: str = ""

class ProfileLowStructural(BaseModel):
    field_types: Dict[str, Dict[str, str]] = Field(default_factory=dict) # sheet -> col -> type
    cardinality: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    distributions: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    missingness: Dict[str, Dict[str, float]] = Field(default_factory=dict)

class ProfileLowKnowledge(BaseModel):
    ontology_mapping: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    validation_status: Dict[str, Dict[str, bool]] = Field(default_factory=dict)
    plausibility: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    confounder_coverage: Dict[str, Any] = Field(default_factory=dict)

class HeterogeneousProfile(BaseModel):
    high_structural: ProfileHighStructural = Field(default_factory=ProfileHighStructural)
    high_knowledge: ProfileHighKnowledge = Field(default_factory=ProfileHighKnowledge)
    low_structural: ProfileLowStructural = Field(default_factory=ProfileLowStructural)
    low_knowledge: ProfileLowKnowledge = Field(default_factory=ProfileLowKnowledge)

# Memory Components
class EpisodicMemory(BaseModel):
    """Dynamically logs execution traces and runtime assumptions."""
    traces: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)

class WorkingMemory(BaseModel):
    """Maintains dynamic field-level contexts grounded in low-granularity profile."""
    field_contexts: Dict[str, Any] = Field(default_factory=dict)

class SemanticMemory(BaseModel):
    """Stores high-level study-design principles."""
    design_principles: List[str] = Field(default_factory=list)
    reporting_semantics: Dict[str, Any] = Field(default_factory=dict)

class ProceduralMemory(BaseModel):
    """Stores operational policies."""
    policies: List[str] = Field(default_factory=list)

class CognitiveMemory(BaseModel):
    episodic: EpisodicMemory = Field(default_factory=EpisodicMemory)
    working: WorkingMemory = Field(default_factory=WorkingMemory)
    semantic: SemanticMemory = Field(default_factory=SemanticMemory)
    procedural: ProceduralMemory = Field(default_factory=ProceduralMemory)
    profile: Optional[HeterogeneousProfile] = None

    def update_profile(self, profile: HeterogeneousProfile):
        self.profile = profile
