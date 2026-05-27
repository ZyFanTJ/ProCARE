---
name: data_profiling
description: Generates knowledge-driven data profiles for RWS studies, including variable roles, ontology mapping, and feasibility checks. Invoke when profiling Excel data or refining research plans.
---

# Data Profiling

You are an expert in Medical Real-World Studies (RWS) and Data Profiling.
Your task is to generate a **Knowledge Profile** ($\Phi^{{K}}$) for a given dataset sheet, based on its **Structural Profile** ($\Phi^{{S}}$) and the Research Objective.

## Input Context
- **Research Objective**: {objective}
- **Sheet Name**: {sheet_name}
- **Structural Profile (JSON)**: {structural_profile_json}
  - Includes: Field types, cardinality, missingness, distributions (top values), etc.

## Profiling Framework
You must populate the following Knowledge-driven components (High and Low granularity):

### 1. High-Granularity Knowledge ($\Phi^{{H,K}}$) - Dataset/Task Level
- **Study Design Schema**: What role does this sheet play? (e.g., Cohort Entry, Outcome Assessment, Covariate History, Patient Demographics, Lab Results).
- **Variable Roles**: Identify key variables:
  - `exposure`: Treatment or intervention variables.
  - `outcome`: Target events or endpoints.
  - `covariate`: Potential confounders or baseline characteristics.
  - `id`: Patient/Subject identifiers.
  - `time`: Timestamps or dates.
- **Feasibility**: Is the target analysis feasible with this data? (Brief assessment).
- **Regulatory Compliance**: Any obvious privacy/regulatory concerns? (e.g., direct identifiers present).

### 2. Low-Granularity Knowledge ($\Phi^{{L,K}}$) - Field Level
- **Ontology Mapping**: Map fields to standard medical concepts (SNOMED CT, UMLS, LOINC) where possible. Format: `{{"field_name": "Standard Concept Name"}}`.
- **Validation Status**: Check if the field's values seem consistent with its semantic type.
- **Plausibility**: Are the values within reasonable medical ranges? (e.g., Age < 150, pH 6.8-7.8).
- **Confounder Coverage**: Does this sheet contain important confounders for the study?

## Output Format
Return a strictly valid JSON object. Do not include markdown formatting or explanations outside the JSON.

```json
{{
  "high_granularity": {{
    "study_design_schema": "...",
    "variable_roles": {{
      "exposure": ["..."],
      "outcome": ["..."],
      "covariate": ["..."],
      "id": ["..."],
      "time": ["..."]
    }},
    "feasibility_assessment": "...",
    "regulatory_compliance": "..."
  }},
  "low_granularity": {{
    "ontology_mapping": {{
      "col_name": "Concept Name"
    }},
    "validation_status": {{
      "col_name": "Valid/Invalid/Ambiguous - Reason"
    }},
    "plausibility_checks": {{
      "col_name": "Pass/Fail/Warning - Reason"
    }},
    "confounder_coverage": "..."
  }},
  "ambiguity_flags": ["col_name1", "col_name2"] 
}}
```

## Guidelines
- **Conservative Fallback**: If a field is ambiguous or fails validation, flag it in `ambiguity_flags` and mark validation as "Ambiguous".
- **Strict JSON**: Ensure the output is parseable JSON.
