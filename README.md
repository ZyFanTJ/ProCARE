# ProCARE: A Cognitive Agent Framework for Real-World Studies

**ProCARE** (Profile-driven Cognitive Agent for RWS Evidence) is a cognitive agent framework designed for Real-World Studies (RWS). This project is the official reference implementation of the ProCARE framework, with the codebase named `HF_ai4research_v2`.

> This project is built based on the methodology described in [docs/techreport.txt](docs/techreport.txt).

---

## Core Concept (The ProCARE Framework)

ProCARE aims to address the high requirements for methodological rigor, causal assumption verification, and compliant reporting in the RWS process. The core mechanism is the **Profile-Driven Cognitive Loop**, formalized as:

$$ \Phi \;\xrightarrow{}\; \mathcal{M} \;\xrightarrow{}\; (P, C, R) $$

Where:
- $\Phi$: Structured Heterogeneous Data Profile.
- $\mathcal{M}$: Profile-Aligned Cognitive Memory system.
- $(P, C, R)$: Generated Research Plan (Plan), Verified Executable Code (Code), and Scientific Report (Report).

---

## System Modules and Methodology

The system mainly consists of the following five core modules, corresponding to the methodological design in the paper:

### 1. Heterogeneous Data Profiling ($\Phi$)
The system does not directly process raw data but compresses it into a structured metadata profile $\Phi$, which includes two dimensions:
- **Granularity**: Dataset-level (High) vs. Field-level (Low).
- **Abstraction**: Structural vs. Knowledge-driven.

| | High Granularity (Dataset/Task) | Low Granularity (Field/Instance) |
|---|---|---|
| **Structural ($\Phi^{\cdot,S}$)** | Table relationships, statistical summary, quality metrics | Field types, cardinality, distribution, missing mechanism |
| **Knowledge ($\Phi^{\cdot,K}$)** | Research design patterns, variable roles, compliance | Ontology mapping, validation status, plausibility checks |

*Code Reference: `backend/app/services/excel_analyzer.py` (ExcelAgent)*

### 2. Cognitive Memory Architecture ($\mathcal{M}$)
To support long-term reasoning and prevent hallucinations, the system maintains four types of profile-aligned memory banks:
- **Episodic Memory ($\mathcal{M}^{\mathrm{epi}}$)**: Dynamically records execution trajectories and runtime assumptions as a chain of evidence.
- **Working Memory ($\mathcal{M}^{\mathrm{work}}$)**: Maintains field-level dynamic context to ensure type consistency.
- **Semantic Memory ($\mathcal{M}^{\mathrm{sem}}$)**: Stores high-level research design principles (from $\Phi^{\mathrm{H,K}}$) as methodological guardrails.
- **Procedural Memory ($\mathcal{M}^{\mathrm{proc}}$)**: Stores operational strategies (e.g., confounding factor adjustment rules).

*Code Reference: `backend/app/core/memory.py`*

### 3. Hierarchical Planning
Adopts a two-stage planning mechanism, from coarse-grained feasibility assessment to field-level operationalization:
1.  **Preliminary Plan ($P_0$)**: Based on high-granularity profiles, formulates research design and analysis strategies compliant with STROBE standards.
2.  **Detailed Execution Plan ($P_d$)**: Combines field-level semantics (e.g., specific columns for exposure $X$, outcome $Y$) to generate an executable blueprint.

*Code Reference: `backend/app/agents/plan_agent.py`*

### 4. Constrained Code Synthesis
Generates executable code $C^*$ through a **Verifier-Repair** loop:
- **Verifier ($V$)**: Combines static analysis (Schema check) and runtime sandbox (Sandbox Execution) to detect if the code violates constraints $\mathcal{C}$.
- **Repair ($R$)**: Applies minimal edits to repair detected violations (e.g., Schema mismatch, methodological assumptions not met).

*Code Reference: `backend/app/agents/code_agent.py` and `backend/app/core/react_loop.py`*

### 5. DAG-Based Report Generation
Report generation is modeled as a dependency Directed Acyclic Graph (DAG). The system calculates the **Support Score** for each reporting task (based on variable availability, temporal validity, sample size, and methodological consistency) and dynamically generates report chapters through weighted topological sorting to ensure conclusions are evidence-based.

*Code Reference: `backend/app/services/report_builder.py`*

---

## System Architecture and Directory

```
backend/
├── app/
│   ├── agents/            # Agent Core (Implements Plan, Code, Report generation)
│   ├── core/              # Infrastructure (LLM Client, ReAct Loop, Memory $\mathcal{M}$)
│   ├── services/          # Business Services
│   │   ├── excel_analyzer.py  # Implements Heterogeneous Profiling $\Phi$
│   │   ├── executor.py        # Code Execution Sandbox
│   │   └── report_builder.py  # DAG-Based Reporting
│   ├── config/            # Configuration Files (Prompt Templates)
│   └── api/               # FastAPI Interfaces
└── output/                # Runtime Artifacts

frontend/                  # React + Vite Frontend Interface
```

---

## Quick Start

### Environment Requirements
- Python 3.10+
- Node.js 16+

### 1. Backend Startup

```bash
# Enter backend directory
cd backend

# Create and activate virtual environment
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start API service (default port 8000)
uvicorn app.main:app --reload
```

### 2. Frontend Startup

```bash
# Enter frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Access the browser address (usually `http://localhost:5173`) to start using it.

---

## Usage Workflow

1.  **Upload Data**: Upload an Excel file, and the system automatically generates the **Heterogeneous Data Profile ($\Phi$)**.
2.  **Define Goal**: Input the research topic ($T_{\text{goal}}$).
3.  **Cognitive Loop**:
    *   **Planning**: Generate Preliminary Plan $P_0$ and Detailed Plan $P_d$.
    *   **Coding**: Enter the ReAct loop and synthesize code $C^*$ through constraint guidance.
    *   **Reporting**: Generate an academic report $R$ with a complete chain of evidence based on DAG.
4.  **View Results**: View execution logs, statistical charts, and the Markdown report in the interface.

---

## Demo

![Demo](docs/AI4RWS.mp4)

---

## License

This project is for demonstration and research purposes only. Please use real-world data under the premise of compliance and privacy security.
