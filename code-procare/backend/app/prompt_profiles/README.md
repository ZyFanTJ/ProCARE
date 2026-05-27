# Prompt Profiles

This directory stores project-local prompt profiles used by the FastAPI report pipeline.

They are lightweight, runtime-loaded equivalents inspired by Copaw's academic-writer stack:

- `research-paper-writer-pro`
- `academic-writing-refiner`
- `paper-markdown-normalizer`
- `faithful-academic-translator`

Current scope:

- The FastAPI app ingests `markdown + uploaded figures/assets`, so the active profiles focus on drafting, refining, normalizing, and translating paper text.
- `MinerU PDF Parser` and `PLS Office Docs` style ingestion are not wired into this project yet because the current upload flow does not accept PDF, Word, or Office parsing tasks.

These files are read by `app/services/pipeline_prompts.py` through `app/services/prompt_profiles.py`.
