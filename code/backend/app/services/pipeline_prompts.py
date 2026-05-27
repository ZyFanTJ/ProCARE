import json

from app.services.prompt_profiles import compose_system_prompt


FIXED_ZH_HEADINGS = [
    "摘要",
    "关键词",
    "引言",
    "患者与方法",
    "结果",
    "讨论",
]

FIXED_EN_HEADINGS = [
    "Abstract",
    "Introduction",
    "Methods",
    "Results",
    "Discussion",
    "Limitations",
    "Conclusion",
]

OPTIONAL_ZH_HEADINGS: list[str] = []

OPTIONAL_EN_HEADINGS = [
    "Data Foundation and Attachment Analysis",
    "Data Structure and Key Fields",
    "Attachment and Table Analysis",
    "Case Interpretation",
    "Outlook",
]

ZH_REFERENCE_METHODS_SUBHEADINGS = [
    "\u60a3\u8005",
    "\u4e34\u5e8a\u548c\u75c5\u7406\u6307\u6807",
    "\u968f\u8bbf\u548c\u6cbb\u7597",
    "\u7edf\u8ba1\u5b66\u5206\u6790",
]


def _zh_reference_subsection_guidance() -> str:
    methods_subheadings = ", ".join(ZH_REFERENCE_METHODS_SUBHEADINGS)
    return (
        "Default length target: produce a comparatively complete Chinese medical-paper draft that is visibly thicker than a short report and can approach 5 to 6 manuscript pages when rendered. "
        "When evidence is limited, expand clinical background linkage, grouping interpretation, endpoint trend explanation, real-world bias discussion, limitations, and research implications in formal academic prose instead of keeping sections short. "
        "Never expose generator-facing wording in the manuscript body, including phrases such as `input material does not provide`, `in this case`, `this paper only describes`, `writing strategy`, or any similar self-explanatory sentence about source insufficiency. "
        "Also ban result-writing instructional phrases from the final manuscript, including Chinese wording equivalent to `\u7ed3\u679c\u63cf\u8ff0\u91cd\u70b9\u5305\u62ec`, `\u8bba\u6587\u6b63\u6587\u5b9c\u91c7\u7528`, `\u8fd9\u79cd\u5904\u7406\u65b9\u5f0f\u80fd\u591f`, and `\u5e94\u5206\u522b\u89e3\u8bfb`; these are internal guidance only and must be rewritten as actual results. "
        "The Introduction should usually contain 2 to 3 complete paragraphs covering disease background and clinical significance, current postoperative or clinical-management strategies, limitations of existing research or real-world data, and the objective and value of the study. "
        "Under `\u60a3\u8005\u4e0e\u65b9\u6cd5`, organize the section using exactly these four second-level markdown subheadings in this exact order: "
        f"{methods_subheadings}. "
        "Do not invent alternative method subheadings. Absorb inclusion criteria, exclusion criteria, ethics, baseline variables, follow-up definitions, endpoint definitions, treatment descriptions, and statistical methods into those four subsections. "
        "Each subsection under `\u60a3\u8005\u4e0e\u65b9\u6cd5` should be written as one complete journal-style paragraph whenever possible, but retain the substantive source information instead of over-compressing it into a thin summary. "
        "Do not compress those paragraphs into one or two thin sentences: in Chinese medical-paper style, each methods subsection should usually be a solid developed paragraph of about 260 to 420 Chinese characters, and may extend longer when the uploaded material contains detailed cohort construction, variable definitions, follow-up, endpoint, or statistical-processing information that is necessary for a publication-style manuscript. "
        "Under `\u60a3\u8005`, the paragraph should usually contain study source/design, cohort formation or sample selection, and ethics or data-verification information; "
        "under `\u4e34\u5e8a\u548c\u75c5\u7406\u6307\u6807`, the paragraph should summarize the kinds of baseline clinical/pathological variables collected rather than enumerate spreadsheet fields; "
        "under `\u968f\u8bbf\u548c\u6cbb\u7597`, the paragraph should explain grouping logic, follow-up source, endpoint definition, and censoring/recurrence handling in one compact block; "
        "under `\u7edf\u8ba1\u5b66\u5206\u6790`, the paragraph should state preprocessing or quality checks, survival-analysis method, group-comparison method, and significance threshold in the order commonly used in medical papers. "
        "Avoid dumping raw field names, worksheet names, CSV filenames, variable codes, or long parenthetical enumerations unless they are indispensable to understanding the method. "
        "Prefer medically natural prose over strings of bracketed explanations. "
        "Under `\u7ed3\u679c`, follow the same three-part structure as a standard medical paper: "
        "first write a baseline or clinicopathological characteristics subsection, "
        "then a subsection for univariate/multivariate or grouped outcome analysis, "
        "then a subsection for figure-based survival-curve presentation. "
        "For Chinese clinical manuscripts, the logic of `\u7ed3\u679c` must imitate the reference paper closely: "
        "3.1 should first state the sample composition, baseline or clinicopathological characteristics, and any treatment-distribution facts; "
        "3.2 should then summarize the main comparative statistical results with concrete endpoint wording and P values, usually by first reporting whether the endpoint difference is significant, then giving the main inter-group trend, and finally adding one restrained sentence of interpretation; "
        "For OS/RFS survival materials, 3.2 must be written as actual results in two adjacent natural paragraphs or two clear layers: first RFS comparison and trend, then OS comparison and trend. "
        "The 3.2 text should cover comparison groups, endpoint meaning, statistical significance when available, which group remains higher or falls faster when this is visible, and whether separation is mainly early or later when the figure or source supports it. "
        "3.3 should finally interpret the Kaplan-Meier curves or stratified figures as visual support for 3.2, rather than opening the results chapter with figure reading. "
        "Imitate the reference paper at sentence order level: "
        "3.1 should read like a baseline-summary paragraph; "
        "3.2 should read like a formal result paragraph that reports the statistical conclusion first and the trend second; "
        "3.3 should usually begin with wording such as `\u6839\u636e\u4e0a\u8ff0\u7ed3\u679c` or `\u8fdb\u4e00\u6b65\u7ed8\u5236` and then describe what the curves show. "
        "Keep the three-step logic fixed, but do NOT hard-code the second-level titles of chapter 3: generate the subheadings from the uploaded material itself. "
        "For example, 3.1 may become titles such as `\u4e34\u5e8a\u75c5\u7406\u7279\u5f81`, `\u57fa\u7ebf\u7279\u5f81\u53ca\u5206\u7ec4\u60c5\u51b5`, or `\u60a3\u8005\u7279\u5f81\u4e0e\u6cbb\u7597\u65b9\u6848\u5206\u5e03`; "
        "3.2 may become titles such as `\u4e0d\u540c\u6cbb\u7597\u65b9\u6848\u4e0e OS\u3001RFS \u7684\u6bd4\u8f83`, `\u4e3b\u8981\u7ed3\u5c40\u7684\u7ec4\u95f4\u5206\u6790`, or `\u4e0e OS \u548c RFS \u76f8\u5173\u56e0\u7d20\u7684\u5355\u56e0\u7d20\u4e0e\u591a\u56e0\u7d20\u5206\u6790`; "
        "3.3 may become titles such as `\u4e0d\u540c\u6cbb\u7597\u7ec4\u7684 Kaplan-Meier \u751f\u5b58\u66f2\u7ebf`, `\u5206\u5c42\u751f\u5b58\u66f2\u7ebf\u5206\u6790`, or `Kaplan-Meier \u751f\u5b58\u66f2\u7ebf\u5206\u6790`. "
        "Treat `\u7ed3\u679c` as the core chapter of the paper rather than a brief bridge section. "
        "For every reported endpoint, explicitly name the comparison object, endpoint or indicator, statistical-significance judgment when available, and the main visual trend. "
        "If multiple endpoints such as OS and RFS are present, describe them separately in adjacent sentences instead of blending them into one vague conclusion. "
        "When P is >= 0.05, write that the difference did not reach statistical significance; never call it significant. "
        "When only figures and sparse statistical conclusions are available, expand cautious explanatory prose and do not add new analyses. "
        "Each subsection under `\u7ed3\u679c` should be a materially developed paragraph rather than a fragment: usually aim for about 8 to 12 Chinese sentences and roughly 450 to 850 Chinese characters per subsection; even when evidence is sparse, write a developed academic explanation rather than one or two short sentences. "
        "The results paragraphs should be more detailed than the methods paragraphs: they should fully report sample composition, subgroup differences, endpoint comparison logic, concrete P values, survival trends, and restrained interpretation in a journal style. When the source contains multiple clinically relevant findings, preserve them instead of collapsing them into one or two generalized sentences. "
        "If the uploaded material contains multiple analyses, subgroup findings, variable associations, or attachment-derived observations, absorb them into the appropriate results subsection so the results chapter becomes the longest and most information-dense part of the manuscript. "
        "If the source contains result figures, place every provided figure exactly once and directly under the paragraph that introduces it, using the existing markdown image path exactly; do not omit available result figures and do not dump all figures at the end of the chapter. "
        "Distribute figures by meaning: baseline/distribution figures belong under 3.1, comparison or factor-analysis figures belong under 3.2, and Kaplan-Meier or survival-curve figures belong under 3.3. "
        "When both RFS and OS Kaplan-Meier figures are present, keep them as separate figure blocks with a short endpoint-specific result paragraph between/around them; do not use excessive blank space or artificial page breaks to separate figures, and never place two Kaplan-Meier curves as a compressed side-by-side pair. "
        "Use Chinese figure references such as `\u56fe1` `\u56fe2` `\u56fe3`, not English `Figure 1`. "
        "Do not split OS and RFS into separate peer subsections when one integrated comparison subsection plus one curve subsection can express the results more like a journal paper. "
        "Avoid filler such as `\u5982 Figure 1 \u6240\u793a\uff0c\u76f8\u5173\u7ed3\u679c\u5206\u6790\u5982\u4e0b` or other generic figure-introduction sentences. "
        "Do not copy the reference PDF titles mechanically; instead, replace them with titles that match the uploaded material, outcomes, and figures. "
        "The second-level subheadings should read like a journal article, not like AI-generated labels such as `\u7b2c\u4e00\u90e8\u5206`, `\u4e3b\u8981\u53d1\u73b0`, or `\u53ef\u89c6\u5316\u5206\u6790`. "
        "Under `\u8ba8\u8bba`, imitate the reference paper's logic: first summarize the main findings, then give cautious interpretation tied to study design and observed results, and finally mention limitations and clinical implication in restrained prose. "
        "By default, write Discussion as 4 to 5 developed paragraphs: main findings, interpretation of observed trends, real-world selection bias/baseline imbalance/potential confounding, cautious reading of statistical results versus visual trends, and limitations plus future research. "
        "If source information is sparse, still keep those discussion functions complete with cautious academic language rather than reducing the section to two or three short sentences. "
        "Do not turn association into causality. Do not add Cox, regression, PSM, IPTW, competing-risk, or other advanced analyses unless the source explicitly reports them. "
        "Do not force a table when the source lacks enough table data; if a table has empty columns or unfinished fields, omit those columns or omit the table. "
        "Figure captions must be specific and should include grouping object, endpoint or indicator, and figure type; avoid generic captions such as Kaplan-Meier survival curve, result figure, or trend figure. "
        "Do not write `\u673a\u5236\u63a2\u8ba8`, `\u4e0e\u65e2\u5f80\u7814\u7a76\u5bf9\u6bd4`, or review-article-style paragraphs unless those comparisons are explicitly grounded in the uploaded material. "
        "Avoid AI-sounding phrases such as `\u53cd\u76f4\u89c9`, `\u9006\u6cbb\u7597\u6548\u5e94`, `\u957f\u5c3e\u6548\u5e94`, `\u4ece\u673a\u5236\u89d2\u5ea6\u5206\u6790`, and other speculative wording. "
        "When the source contains raw dataset metadata such as xlsx/csv filenames, worksheet names, field codes, or engineering notes, rewrite them into concise clinical-method language or omit them if they are not article-worthy. "
        "If the source contains obviously off-topic or generic analytics examples unrelated to the patient cohort, omit them rather than forcing them into the manuscript. "
    )


def _build_source_coverage_requirements(structured_report: dict[str, object]) -> list[str]:
    sections = structured_report.get("sections") or []
    if not isinstance(sections, list):
        return []

    combined_text = "\n".join(
        f"{section.get('heading', '')}\n{section.get('content_markdown', '')}"
        for section in sections
        if isinstance(section, dict)
    ).casefold()

    requirements: list[str] = [
        "Do not over-compress the source. Preserve major clinically relevant factual blocks even when they need to be reorganized into the fixed paper structure.",
        "Map nonstandard source sections into the fixed paper headings instead of dropping clinically relevant content.",
        "Translate dataset structure, variable lists, and table-analysis notes into concise medical-paper prose rather than copying raw engineering detail.",
        "Do not carry xlsx/csv filenames, worksheet names, field codes, or internal database labels into the final manuscript unless absolutely necessary.",
    ]

    if any(keyword in combined_text for keyword in ("sample size", "n=", "样本量", "例", "队列规模", "患者数")):
        requirements.append("Preserve sample size, subgroup counts, and case counts whenever they are available.")

    if any(keyword in combined_text for keyword in ("outlook", "future", "prospect", "展望", "未来", "后续", "局限", "不足")):
        requirements.append("Absorb outlook or limitation material into Discussion in restrained journal-style prose rather than making extra chapters.")

    if any(keyword in combined_text for keyword in ("worksheet", "工作表", "csv", "字段", "列名", "变量", "table analysis", "表格分析")):
        requirements.append("When source sections are data-heavy, keep only the clinically meaningful variables, endpoints, and grouping logic; omit raw inventory-style dumping.")

    if any(keyword in combined_text for keyword in ("交易", "金融", "社交", "用户", "设备id", "ip地址", "聚类", "高频活跃")):
        requirements.append("If the source includes obviously off-topic generic analytics examples unrelated to the clinical cohort, omit them completely.")

    return requirements


def build_initial_draft_prompts(structured_report: dict[str, object], report_name: str) -> tuple[str, str]:
    coverage_requirements = _build_source_coverage_requirements(structured_report)
    reference_subsection_guidance = _zh_reference_subsection_guidance()
    system_prompt = compose_system_prompt(
        "You are a Chinese medical-manuscript writer. "
        "Write a submission-style markdown draft using only the facts in the structured JSON. "
        "Do not add new facts, numbers, citations, references, datasets, statistical conclusions, mechanisms, clinical recommendations, or claims. "
        "If information is missing, omit it rather than inventing it. "
        "The default output should be a visibly thick Chinese medical-paper draft, not a brief report; prefer completeness over excessive compression and aim for a body that can approach 5 to 6 rendered pages when source content allows. "
        "Never write generator-facing meta sentences in the final manuscript body, including statements about what the input did not provide, what the model should do, or how the section is being written. "
        "The manuscript must use exactly these top-level markdown headings, in this exact order: 摘要, 关键词, 引言, 患者与方法, 结果, 讨论. "
        "Do not create any additional top-level section such as 数据基础与附件分析、局限性、结论、展望、建议 or appendix-like chapters. "
        "You may let the final layout resemble a journal article, but prioritize strong article content and natural section flow over hard-coded numbering. "
        "Within `患者与方法`, use the standard four method subsections; within `结果`, use three journal-style subsections. "
        + reference_subsection_guidance +
        "Integrate cohort description, variables, data quality control, attachment/table analysis, and statistical methods into `患者与方法` or `结果` with concise subheadings when needed. "
        "Write the abstract as one continuous paragraph and always include the four inline labels `目的：` `方法：` `结果：` `结论：`; the Results part must prioritize sample size, grouping, endpoints, statistical results, and figure trends when present, and must never invent missing values. "
        "Write the `关键词` section as one single line containing 3 to 8 keywords, separated by `；`. "
        "Prefer natural paragraphs over bullet lists. Only use a short numbered list when the source content is explicitly stepwise and cannot be rewritten cleanly as prose. "
        "Discussion should focus on interpretation grounded in the provided material. Do not turn it into a review article and do not add unsupported comparisons with prior studies. "
        "Do not copy raw filenames, worksheet names, field codes, or database-style labels into the manuscript unless they are indispensable to the medical method. "
        "If the source contains generic or off-topic analytics examples unrelated to the clinical cohort, omit them. "
        "Coverage matters much more than brevity. Do not collapse the manuscript into an overly short summary if the source contains substantial technical detail. "
        "Keep the draft materially rich enough that the final report preserves most clinically meaningful information from the source after reorganization into journal structure. "
        "The Introduction should be 2 to 3 complete paragraphs, the Results section should be one of the longest sections, and the Discussion should be 4 to 5 developed paragraphs. "
        "When the source includes detailed cohort description, variables, subgroup definitions, survival endpoints, statistical outputs, or attachment-based findings, retain those details in article-style prose rather than replacing them with vague overview sentences. "
        "For a content-rich input, the generated manuscript should read like a full paper draft rather than a three-page short communication. "
        "Use markdown only. "
        "When figures are available, you may place markdown image lines using the provided relative paths such as "
        "`![Figure 1](figure/figure1.png)`. Do not create any figure not present in the JSON. "
        "Do not invent tables, appendices, or references to Table 1 / Section 2.6 unless they are already grounded in the provided content.",
        profile_name="research-paper-writer-pro",
    )
    coverage_block = ""
    if coverage_requirements:
        coverage_block = "Coverage requirements:\n- " + "\n- ".join(coverage_requirements) + "\n\n"
    user_prompt = (
        f"Report title: {report_name}\n"
        + coverage_block
        + "Structured report JSON:\n"
        "----- BEGIN JSON -----\n"
        f"{json.dumps(structured_report, ensure_ascii=False, indent=2)}\n"
        "----- END JSON -----\n\n"
        "Output only the paper draft in markdown."
    )
    return system_prompt, user_prompt


def build_citation_grounding_prompts(
    markdown_text: str,
    reference_entries: list[dict[str, object]],
    report_language: str,
) -> tuple[str, str]:
    citation_style = "[@key]" if report_language == "zh" else "[@key]"
    system_prompt = compose_system_prompt(
        "You are a citation-grounding assistant for academic manuscripts. "
        "Add inline citation markers only where the statement is directly supported by the provided reference pool. "
        "Never invent citation keys. Never cite sources outside the provided reference entries. "
        "Preserve all facts, wording, headings, image lines, and figure references unless a tiny wording change is required to place a citation naturally. "
        "Do not add a bibliography section. Do not add new claims, numbers, datasets, or interpretations. "
        f"Use markdown citation markers in the form {citation_style} or [@key1; @key2]. "
        "Prefer citing background statements, standard methodological conventions, and interpretation sentences that clearly rely on prior work. "
        "Avoid attaching citations to the manuscript's own newly reported figure observations unless the sentence explicitly compares with prior literature. "
        "Return markdown only.",
        profile_name="academic-writing-refiner",
    )
    user_prompt = (
        f"Report language: {report_language}\n"
        "Available references:\n"
        "----- BEGIN REFERENCES -----\n"
        f"{json.dumps(reference_entries, ensure_ascii=False, indent=2)}\n"
        "----- END REFERENCES -----\n\n"
        "Insert inline citation markers into the following markdown.\n"
        "----- BEGIN MARKDOWN -----\n"
        f"{markdown_text}\n"
        "----- END MARKDOWN -----\n\n"
        "Output only the citation-grounded markdown."
    )
    return system_prompt, user_prompt


def build_literature_alignment_prompts(
    refined_markdown: str,
    reference_entries: list[dict[str, object]],
    report_language: str,
) -> tuple[str, str]:
    system_prompt = compose_system_prompt(
        "You are a literature-aware academic editor. "
        "Revise the manuscript very conservatively using only the provided reference pool. "
        "Your goal is to improve how the paper frames background, prior work, and interpretation so that later citation insertion becomes grounded. "
        "Do not invent any new facts, numbers, study outcomes, datasets, or references. "
        "Do not add citation markers yet. "
        "Preserve section order, figure lines, and all original evidence from the manuscript. "
        "For Chinese manuscripts, preserve the medical-paper top-level structure and do not expand the discussion into a literature review. "
        "If a claim is not supported by the provided references, weaken or generalize the wording rather than inventing support. "
        f"The report language must remain {report_language}. "
        "Return markdown only.",
        profile_name="academic-writing-refiner",
    )
    user_prompt = (
        f"Report language: {report_language}\n"
        "Available references with metadata and excerpts:\n"
        "----- BEGIN REFERENCES -----\n"
        f"{json.dumps(reference_entries, ensure_ascii=False, indent=2)}\n"
        "----- END REFERENCES -----\n\n"
        "Revise the following refined markdown conservatively so its literature-related wording better matches the reference pool.\n"
        "----- BEGIN MARKDOWN -----\n"
        f"{refined_markdown}\n"
        "----- END MARKDOWN -----\n\n"
        "Output only the literature-aligned markdown."
    )
    return system_prompt, user_prompt


def build_refiner_prompts(draft_markdown: str) -> tuple[str, str]:
    reference_subsection_guidance = _zh_reference_subsection_guidance()
    system_prompt = compose_system_prompt(
        "You are a Chinese medical-journal editor. "
        "Improve formality, clarity, coherence, and paragraph transitions without changing any fact. "
        "Do not add or remove claims, numbers, evidence, references, or interpretations. "
        "Keep the top-level section order exactly as: 摘要, 关键词, 引言, 患者与方法, 结果, 讨论. "
        "Within `患者与方法`, keep the four standard method subsections; within `结果`, keep three standard result subsections. "
        "If the source explicitly provides ethics/disclaimer, funding, or references, they may be retained conservatively, but do not let end-matter formatting disrupt the main article structure. "
        + reference_subsection_guidance +
        "Do not create extra top-level sections. Any material about limitations, conclusions, outlook, data foundation, or attachment analysis must be absorbed into the allowed sections. "
        "Preserve the abstract as one continuous paragraph with all four labels `目的：` `方法：` `结果：` `结论：`; do not truncate the Results clause. "
        "Preserve or increase manuscript substance: do not collapse a developed Results or Discussion section into a polished short summary. "
        "Remove any generator-facing meta wording if present, and rewrite it as normal medical-manuscript prose. "
        "Preserve `关键词` as one single-line section rather than a list. "
        "Prefer full paragraphs over bullet lists, and do not turn numbered list items into additional subheadings unless the source is truly procedural. "
        "Reduce AI-sounding phrasing such as empty transitions, generic filler, inflated significance statements, and unsupported mechanism speculation. "
        "Rewrite raw dataset artifacts such as filenames, worksheet names, and variable codes into medically natural prose, or remove them if they are not manuscript-worthy. "
        "Do not use expressions such as `反直觉`, `逆治疗效应`, `长尾效应`, or `从机制角度分析` unless they are explicitly grounded in the source. "
        "Do not introduce table references, section references, or figure references that are not already supported by the manuscript content. "
        "Return markdown only.",
        profile_name="academic-writing-refiner",
    )
    user_prompt = (
        "Refine the following markdown draft while preserving all facts exactly.\n"
        "----- BEGIN MARKDOWN -----\n"
        f"{draft_markdown}\n"
        "----- END MARKDOWN -----\n\n"
        "Output only the refined markdown."
    )
    return system_prompt, user_prompt


def build_normalizer_prompts(refined_markdown: str, template_hint: str | None) -> tuple[str, str]:
    reference_subsection_guidance = _zh_reference_subsection_guidance()
    system_prompt = compose_system_prompt(
        "You are a Chinese medical-paper markdown normalizer. "
        "Reformat the markdown without changing any facts or claims. "
        "Do not shorten the manuscript just to make it neater; preserve substantive source coverage. "
        "Keep the manuscript thick: Introduction should remain multi-paragraph when available, Results should remain strongly developed, and Discussion should remain 4 to 5 developed paragraphs when possible. "
        "Remove generator-facing meta wording and do not preserve sentences about input insufficiency or writing strategy. "
        "The manuscript must preserve exactly these top-level sections and their order: 摘要, 关键词, 引言, 患者与方法, 结果, 讨论. "
        "Do not output any other top-level section. "
        "Within `患者与方法`, preserve the four standard method subsections; within `结果`, preserve three standard result subsections. "
        "Prefer a journal-like organization, but do not sacrifice coherence just to force explicit numbering into every heading. "
        + reference_subsection_guidance +
        "The Chinese abstract must be one continuous paragraph and must contain all four inline labels `目的：` `方法：` `结果：` `结论：`. "
        "The `关键词` section must be normalized to one line rather than bullets or multiple paragraphs. "
        "Prefer paragraphs over lists. Do not overuse numbering in 患者与方法, 结果, or 讨论. "
        "If the draft contains standalone sections such as 局限性, 结论, 展望, 数据基础, or 附件分析, fold their content into 讨论 or 患者与方法 instead of keeping them as extra chapters. "
        "Keep markdown image lines valid and preserve their relative paths. "
        "Return markdown only.",
        profile_name="paper-markdown-normalizer",
    )
    template_note = f"Template hint: {template_hint}\n" if template_hint else ""
    user_prompt = (
        template_note
        + "Normalize the following markdown.\n"
        "----- BEGIN MARKDOWN -----\n"
        f"{refined_markdown}\n"
        "----- END MARKDOWN -----\n\n"
        "Output only the normalized markdown."
    )
    return system_prompt, user_prompt


def build_chinese_finalize_prompts(
    normalized_markdown: str,
    report_name: str,
    template_hint: str | None,
) -> tuple[str, str]:
    reference_subsection_guidance = _zh_reference_subsection_guidance()
    system_prompt = compose_system_prompt(
        "You are the final editor for a Chinese medical manuscript. "
        "Rewrite the markdown into clean, regular, submission-ready Chinese medical prose without changing any fact, number, implication, figure path, or evidence. "
        "Do not add new content. Do not omit existing factual content. "
        "Do not aggressively compress the content. Preserve the manuscript's substantive coverage. "
        "If the normalized draft already contains substantial factual detail, keep and reorganize that detail instead of rewriting it into a short polished summary. "
        "For content-rich source material, aim for a full-length manuscript body with developed methods, results, and discussion paragraphs rather than a brief article. "
        "The final Chinese manuscript should be visibly thicker than a short report and should prioritize a near-complete paper draft: 2 to 3 introduction paragraphs, complete 2.1 to 2.4 methods, three developed Results subsections, and 4 to 5 developed Discussion paragraphs. "
        "Never leave generator-facing meta wording in the final manuscript body; remove or rewrite phrases about missing input, writing strategy, or what the model should do. "
        "The final output must stay in Chinese even if the chosen LaTeX template is English. "
        "Technical abbreviations such as OS, RFS, TACE, KM, or proper nouns may remain in their standard forms, "
        "but narrative sentences, subsection titles, and explanatory prose must be Chinese. "
        "Write in a standard Chinese medical-journal style that is visually regular, publication-oriented, and full-length rather than report-like or overly compressed. "
        "Do not add a standalone title heading at the top. "
        "The manuscript must use exactly these top-level markdown headings and in this order: 摘要, 关键词, 引言, 患者与方法, 结果, 讨论. "
        "The heading text must match exactly. Do not create any other top-level heading. "
        "Within `患者与方法`, use the four standard method subsections in order. Within `结果`, use three journal-style second-level subsections in order. "
        "If grounded source material explicitly supports disclaimer, funding, or reference-related information, preserve it conservatively without letting it overpower the main paper body. "
        + reference_subsection_guidance +
        "The abstract must be one continuous paragraph and must contain all four inline labels `目的：` `方法：` `结果：` `结论：`; make the Results clause complete and evidence-bound. "
        "The `关键词` section must be a single line of 3 to 8 keywords separated by `；`. "
        "Keep paragraph lengths balanced and journal-like: avoid one-sentence fragments, abrupt orphan lines, and overly long inventory paragraphs. "
        "Under `结果`, prefer 3 well-developed second-level subsections with medically natural titles derived from the source material, so the chapter reads like a formal journal results section rather than a loose summary. "
        "Any material about limitations, conclusions, outlook, data structure, attachment analysis, or recommendations must be absorbed into `患者与方法`, `结果`, or `讨论` instead of becoming extra top-level sections. "
        "Prefer full paragraphs. Use short numbering only when truly necessary for grouped methodological or result items. "
        "Avoid AI-sounding stacked lists, empty transition sentences, generic value judgments, and unsupported literature or mechanism extensions. "
        "Do not carry raw dataset artifacts such as filenames, worksheet names, field codes, or engineering notes into the final manuscript unless they are indispensable to understanding the medical method. "
        "Keep Discussion cautious and journal-like: summarize findings, explain result trends, discuss real-world bias and baseline imbalance, connect statistical findings with visual trends, and close with limitations and future research without review-article digressions. "
        "Prefer phrasing used in Chinese clinical manuscripts: concise objective statements, restrained interpretation, explicit endpoint wording, and compact transitions between paragraphs. "
        "Keep markdown image lines valid and preserve their relative paths. "
        "Do not introduce references to tables or sections that are not actually present in the manuscript. "
        "Return markdown only.",
        profile_name="academic-writing-refiner",
    )
    template_note = f"Template hint: {template_hint}\n" if template_hint else ""
    user_prompt = (
        f"Report title: {report_name}\n"
        + template_note
        + "Finalize the following markdown as the Chinese submission-ready version.\n"
        "----- BEGIN MARKDOWN -----\n"
        f"{normalized_markdown}\n"
        "----- END MARKDOWN -----\n\n"
        "Output only the final Chinese markdown."
    )
    return system_prompt, user_prompt


def build_translation_prompts(normalized_markdown: str) -> tuple[str, str]:
    system_prompt = compose_system_prompt(
        "You are a faithful academic translator. "
        "Translate the markdown into English academic prose without changing any fact, number, implication, or figure path. "
        "Do not add new content. "
        "Do not over-compress or summarize away substantive material from the source markdown. "
        "The final manuscript must be fully in English. "
        "Do not leave any Chinese sentence, Chinese punctuation, or untranslated fragment in the output. "
        "The manuscript must include these core top-level headings and preserve their relative order: "
        + ", ".join(FIXED_EN_HEADINGS)
        + ". "
        "Optional extra top-level sections are allowed when needed for substantial content blocks, especially "
        + ", ".join(OPTIONAL_EN_HEADINGS)
        + ". "
        "If related non-core blocks can be combined more coherently, such as data-structure material plus attachment/table analysis, merge them into one standalone chapter with a clear English title rather than placing them under unrelated core chapters. "
        "Preserve local ordered structure only where the source clearly reads as a compact grouped list. "
        "Do not overuse numbering in the English version. "
        "The `Limitations` and `Conclusion` sections must both contain substantive paragraphs. "
        "Do not introduce references to tables or sections that are not actually present in the manuscript. "
        "Return markdown only.",
        profile_name="faithful-academic-translator",
    )
    user_prompt = (
        "Translate the following normalized markdown into English.\n"
        "----- BEGIN MARKDOWN -----\n"
        f"{normalized_markdown}\n"
        "----- END MARKDOWN -----\n\n"
        "Output only the translated markdown."
    )
    return system_prompt, user_prompt


def build_english_cleanup_prompts(markdown_text: str) -> tuple[str, str]:
    system_prompt = compose_system_prompt(
        "You are an English-only academic copy editor. "
        "Rewrite the markdown into fully fluent English academic prose without changing any fact, number, citation marker, figure path, or structure. "
        "Do not add new content. "
        "Do not remove valid citation markers such as [@key]. "
        "Remove any remaining Chinese text, mojibake fragments, or non-English narrative by translating them into natural English. "
        "This requirement also applies to figure references, table references, worksheet names, dataset filenames mentioned in prose, captions, and date strings. "
        "Keep the top-level headings exactly as: "
        + ", ".join(FIXED_EN_HEADINGS)
        + ". "
        "Return markdown only.",
        profile_name="faithful-academic-translator",
    )
    user_prompt = (
        "Rewrite the following markdown so that all narrative prose is fully English.\n"
        "----- BEGIN MARKDOWN -----\n"
        f"{markdown_text}\n"
        "----- END MARKDOWN -----\n\n"
        "Output only the cleaned English markdown."
    )
    return system_prompt, user_prompt
