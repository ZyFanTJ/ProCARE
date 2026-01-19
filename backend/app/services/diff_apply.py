from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Tuple
import re


class PatchError(Exception):
    pass


def _strip_prefix(s: str, prefix: str) -> str:
    return s[len(prefix):] if s.startswith(prefix) else s


def is_apply_patch_text(text: str) -> bool:
    """Detect our simplified patch envelope more robustly.
    Accepts suggestions where headers are concatenated or have trailing characters.
    """
    if not text:
        return False
    # Find envelope markers anywhere in the text
    has_begin = re.search(r"\*\*\*\s*Begin\s*Patch", text) is not None
    has_end = re.search(r"\*\*\*\s*End\s*Patch", text) is not None
    return has_begin and has_end


import re

def _normalize_patch_text(raw: str) -> str:
    """
    Normalize loosely formatted patch text into our parser's expected layout.

    - Normalize newlines, strip BOM/NBSP
    - Extract content between the first *** Begin Patch and the last *** End Patch (tolerant match)
    - Canonicalize headers to the exact tokens our parser expects (with trailing ***)
    - Ensure headers/hunks live on their own lines (no glue)
    - Collapse vertical whitespace
    """
    if not raw:
        return ""

    # 0) 粗清洗：统一换行、去 BOM、NBSP -> 空格
    txt = raw.replace("\r\n", "\n").replace("\r", "\n")
    txt = txt.replace("\ufeff", "").replace("\u00A0", " ")

    # 1) 去除常见 Markdown 代码围栏（```diff / ```patch / ```text / ```）
    txt = re.sub(r"(?s)^\s*```(?:diff|patch|text)?\s*(.*?)\s*```\s*$", r"\1", txt)

    # 2) 若存在哨兵包裹（方案A），优先截取哨兵内部
    m = re.search(r"<<PATCH>>\n(?P<body>.*)\n<<END_PATCH>>", txt, flags=re.DOTALL)
    if m:
        txt = m.group("body").strip()

    # 3) 兼容“无 Markdown 含义”的替代头（方案B）
    txt = re.sub(r"(?mi)^\s*###\s*PATCH\s*BEGIN\s*###\s*$", "*** Begin Patch***", txt)
    txt = re.sub(r"(?mi)^\s*###\s*PATCH\s*END\s*###\s*$",   "*** End Patch***",   txt)
    txt = re.sub(r"(?mi)^\s*###\s*UPDATE\s+FILE:\s*(.+)\s*$", r"*** Update File: \1", txt)
    
    # 1) Text-level normalization first (统一换行 / 去BOM / NBSP->空格)
    txt = raw.replace("\r\n", "\n").replace("\r", "\n")
    txt = txt.replace("\ufeff", "")
    txt = txt.replace("\u00A0", " ")

    # 2) 宽松抓取 envelope（先把各种写法归一到不带***，再统一到带***）
    # 允许出现 *** Begin Patch、***   Begin    Patch 等
    m_begin = re.search(r"\*\*\*\s*Begin\s*Patch", txt, flags=re.IGNORECASE)
    m_end = None
    for m in re.finditer(r"\*\*\*\s*End\s*Patch", txt, flags=re.IGNORECASE):
        m_end = m
    if not m_begin or not m_end:
        # 没有补丁包裹，返回清洗后的原文
        return txt.strip()

    inner = txt[m_begin.start(): m_end.end()]

    # 3) 统一头部字面量 —— 统一为“带 ***”版本，与你的解析器对齐
    inner = re.sub(r"\*\*\*\s*Begin\s*Patch\**", "*** Begin Patch***", inner, flags=re.IGNORECASE)
    inner = re.sub(r"\*\*\*\s*End\s*Patch\**",   "*** End Patch***",   inner, flags=re.IGNORECASE)

    # 4) 归一化其他头部（允许用户写成 * Update File: ... 等）
    inner = re.sub(r"(?mi)^[\t ]*\**[\t ]*Update[\t ]*File:[\t ]*(.+)$", r"*** Update File: \1", inner)
    inner = re.sub(r"(?mi)^[\t ]*\**[\t ]*Add[\t ]*File:[\t ]*(.+)$",    r"*** Add File: \1",    inner)
    inner = re.sub(r"(?mi)^[\t ]*\**[\t ]*Delete[\t ]*File:[\t ]*(.+)$", r"*** Delete File: \1", inner)
    inner = re.sub(r"(?mi)^[\t ]*\**[\t ]*Move[\t ]*to:[\t ]*(.+)$",     r"*** Move to: \1",     inner)
    inner = re.sub(r"(?mi)^[\t ]*\**[\t ]*End[\t ]*of[\t ]*File[\t ]*$", r"*** End of File",     inner)

    # 5) Ensure headers/hunks are isolated on their own lines
    # 5.1 这些头部需要“前后都有换行”
    both_isolate = [
        r"\*\*\*\s*Begin\s*Patch\*{3}",
        r"\*\*\*\s*End\s*Patch\*{3}",
        r"\*\*\*\s*End\s*of\s*File",
        r"@@",
    ]
    for pat in both_isolate:
        inner = re.sub(rf"(?<!\n)({pat})", r"\n\1", inner)
        inner = re.sub(rf"({pat})(?!\n)", r"\1\n", inner)

    # 5.2 带路径的头部：既要前面有换行，也要“整行结束”后有换行（避免与下一行黏住）
    path_headers = [
        r"\*\*\*\s*Add\s*File:\s*.+",
        r"\*\*\*\s*Delete\s*File:\s*.+",
        r"\*\*\*\s*Update\s*File:\s*.+",
        r"\*\*\*\s*Move\s*to:\s*.+",
    ]
    for pat in path_headers:
        # 前面必须是换行
        inner = re.sub(rf"(?<!\n)({pat})", r"\n\1", inner)
        # 该行末尾必须换行（用 $ 来锚定这一行）
        inner = re.sub(rf"({pat})(?!\n)", r"\1\n", inner)

    # 6) 进一步保障 @@ 真正独占一行（双保险）
    inner = re.sub(r"(?m)^[\t ]*@@[\t ]*$", "@@", inner)  # 去除 @@ 行的两侧空白
    inner = re.sub(r"(?<!\n)@@", r"\n@@", inner)
    inner = re.sub(r"@@(?!\n)", r"@@\n", inner)

    # 7) 折叠多余空行
    inner = re.sub(r"\n{3,}", "\n\n", inner)

    # 8) 确保首尾（严格字面匹配解析器所需）
    inner = inner.strip()
    if not re.match(r"^\*\*\* Begin Patch\*{3}$", inner.splitlines()[0]):
        inner = "*** Begin Patch***\n" + inner
    if not re.search(r"\*\*\* End Patch\*{3}$", inner):
        # 清理 End Patch*** 之后的噪声
        inner = re.sub(r"(\*\*\* End Patch\*{3}).*", r"\1", inner, flags=re.DOTALL)
        if not inner.endswith("*** End Patch***"):
            inner = inner + "\n*** End Patch***"

    return inner



def apply_patch_text(patch_text: str, root_dir: str) -> Dict:
    """
    Apply a simplified diff/patch envelope to the filesystem under `root_dir`.

    Supported syntax (subset):
    - *** Begin Patch / *** End Patch
    - *** Add File: <path> followed by lines prefixed with '+' for file contents
    - *** Delete File: <path>
    - *** Update File: <path> [optional *** Move to: <new path>]
      - One or more hunks starting with '@@' and lines prefixed by ' ', '-' or '+'

    Returns a dict with keys: applied(bool), changes(list), errors(list).
    """
    changes: List[Dict] = []
    errors: List[str] = []
    # Normalize patch before parsing to be resilient to formatting glitches
    patch_text = _normalize_patch_text(patch_text)
    lines = patch_text.splitlines()

    def read_until_file_end(idx: int) -> int:
        # Helper: stop at next header or end
        while idx < len(lines):
            if lines[idx].startswith("*** ") and not lines[idx].startswith("*** End of File"):
                break
            if lines[idx].startswith("*** End Patch"):
                break
            idx += 1
        return idx

    if not (lines and lines[0].startswith("*** Begin Patch")):
        errors.append("Patch envelope missing Begin Patch header")
        return {"applied": False, "changes": changes, "errors": errors}

    i = 1
    root = Path(root_dir)
    root.mkdir(parents=True, exist_ok=True)

    while i < len(lines):
        line = lines[i]
        if line.startswith("*** End Patch"):
            break

        # Add File
        if line.startswith("*** Add File: "):
            rel_path = line.split(": ", 1)[1].strip()
            if not rel_path:
                errors.append("Add file header missing path")
                i += 1
                continue
            target = root / rel_path
            i += 1
            content: List[str] = []
            while i < len(lines):
                if lines[i].startswith("+"):
                    content.append(lines[i][1:])
                    i += 1
                else:
                    break
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("\n".join(content), encoding="utf-8")
                changes.append({"op": "add", "path": str(target)})
            except Exception as e:
                errors.append(f"Add file failed for {target}: {e}")
            continue

        # Delete File
        if line.startswith("*** Delete File: "):
            rel_path = line.split(": ", 1)[1].strip()
            if not rel_path:
                errors.append("Delete file header missing path")
                i += 1
                continue
            target = root / rel_path
            i += 1
            try:
                if target.exists():
                    target.unlink()
                    changes.append({"op": "delete", "path": str(target)})
                else:
                    errors.append(f"Delete file missing: {target}")
            except Exception as e:
                errors.append(f"Delete file failed for {target}: {e}")
            continue

        # Update File
        if line.startswith("*** Update File: "):
            rel_path = line.split(": ", 1)[1].strip()
            if not rel_path:
                errors.append("Update file header missing path")
                i += 1
                continue
            src_path = root / rel_path
            i += 1
            # Optional move
            new_path: Path | None = None
            if i < len(lines) and lines[i].startswith("*** Move to: "):
                rel_new = lines[i].split(": ", 1)[1].strip()
                new_path = root / rel_new
                i += 1

            # Read entire file content
            try:
                orig_text = src_path.read_text(encoding="utf-8")
                content = orig_text.splitlines()
            except Exception:
                orig_text = ""
                content = []

            # Apply hunks
            while i < len(lines):
                if lines[i].startswith("@@"):
                    i, content = _apply_hunk(lines, i, content)
                    continue
                if lines[i].startswith("*** End of File"):
                    i += 1
                    break
                if lines[i].startswith("*** "):
                    break
                # Skip stray lines
                i += 1

            # Write back to path (handle move) only if content or path changed
            try:
                target_path = new_path or src_path
                new_text = "\n".join(content)
                did_move = bool(new_path and src_path != new_path)
                did_modify = new_text != orig_text
                if did_move or did_modify:
                    if did_move:
                        new_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_text(new_text, encoding="utf-8")
                    if did_move and src_path.exists():
                        try:
                            src_path.unlink()
                        except Exception:
                            pass
                    changes.append({"op": "update", "path": str(target_path)})
                # else: no-op update; do not record change
            except Exception as e:
                errors.append(f"Update file failed for {src_path}: {e}")
            continue

        # Unknown header or noise: skip
        i += 1

    # Consider a patch successful only if it has no errors AND produced changes
    if len(errors) == 0 and len(changes) == 0:
        errors.append("No changes detected in patch")
    applied_ok = len(errors) == 0 and len(changes) > 0
    return {"applied": applied_ok, "changes": changes, "errors": errors}


def _apply_hunk(lines: List[str], idx: int, content: List[str]) -> Tuple[int, List[str]]:
    """Apply a single hunk starting at lines[idx] onto `content`.
    Strategy: treat the hunk as one contiguous change block with pre-context, +/- changes and post-context.
    More tolerant:
    - Use the '@@' header as a fuzzy location hint (e.g., function/class signature)
    - Treat non-prefixed lines before changes as pre-context (LLM often omits leading spaces)
    """
    # Capture hunk header line starting with '@@'
    header = lines[idx]
    i = idx + 1
    pre_ctx: List[str] = []
    minus: List[str] = []
    plus: List[str] = []
    post_ctx: List[str] = []

    # Phase: collect pre-context until first change
    while i < len(lines):
        l = lines[i]
        if l.startswith(" "):
            pre_ctx.append(l[1:])
            i += 1
            continue
        if l.startswith("-") or l.startswith("+"):
            break
        if l.startswith("@@") or l.startswith("*** "):
            break
        # Treat stray non-marker lines as context (LLM may omit leading space prefix)
        pre_ctx.append(l)
        i += 1

    # Phase: collect changes
    change_started = False
    while i < len(lines):
        l = lines[i]
        if l.startswith("-"):
            minus.append(l[1:])
            change_started = True
            i += 1
            continue
        if l.startswith("+"):
            plus.append(l[1:])
            change_started = True
            i += 1
            continue
        if l.startswith(" "):
            # If changes already collected, treat as post-context
            if change_started:
                post_ctx.append(l[1:])
                i += 1
                continue
            else:
                pre_ctx.append(l[1:])
                i += 1
                continue
        if l.startswith("@@") or l.startswith("*** "):
            break
        # stray line
        i += 1

    # Locate where to apply in `content`
    start_idx = _find_subsequence(content, pre_ctx)
    if start_idx is None:
        # If no pre-context match, try fuzzy by first minus line
        start_idx = _find_subsequence(content, minus) if minus else None
    if start_idx is None:
        # Try using header hint (e.g., @@ def analyze_data(...))
        hint = header[2:].strip() if header.startswith("@@") else ""
        fallback_pos: int | None = None
        if hint:
            # Search for a line containing the hint
            for j, line in enumerate(content):
                try:
                    if hint and hint in line:
                        fallback_pos = j + 1
                        break
                except Exception:
                    pass
        if fallback_pos is None:
            # Nothing matched; return without changes
            return i, content
        else:
            # If we only have additions, insert them at fallback position
            if plus and not minus:
                new_content = content[:fallback_pos] + plus + content[fallback_pos:]
                return i, new_content
            # Otherwise, proceed near fallback position with best-effort minus replacement
            start_idx = fallback_pos

    apply_pos = start_idx + len(pre_ctx)
    end_pos = apply_pos + len(minus)

    # Validate minus region
    if len(minus) and content[apply_pos:end_pos] != minus:
        # Try to search minus region near apply_pos
        alt = _find_subsequence(content[apply_pos:], minus)
        if alt is not None:
            apply_pos = apply_pos + alt
            end_pos = apply_pos + len(minus)

    # Apply replacement: remove minus, insert plus
    new_content = content[:apply_pos] + plus + content[end_pos:]

    # Optionally validate post-context
    if post_ctx:
        check_pos = apply_pos + len(plus)
        tail_slice = new_content[check_pos:check_pos + len(post_ctx)]
        # If post-context mismatch, we still keep changes.

    return i, new_content


def _find_subsequence(haystack: List[str], needle: List[str]) -> int | None:
    if not needle:
        return 0
    n = len(needle)
    for i in range(0, len(haystack) - n + 1):
        if haystack[i:i + n] == needle:
            return i
    return None


# --------------------
# replace_in_file 支持
# --------------------

def is_replace_in_file_text(text: str) -> bool:
    """检测是否为 <replace_in_file> 请求文本。"""
    if not text:
        return False
    return ("<replace_in_file" in text) and ("</replace_in_file>" in text)


def _extract_xml_tag(text: str, tag: str) -> str | None:
    """提取简单 XML 风格标签内容，忽略大小写与空白。"""
    m = re.search(rf"<\s*{tag}\s*>\s*(?P<body>.*?)\s*<\s*/\s*{tag}\s*>",
                  text, flags=re.IGNORECASE | re.DOTALL)
    return m.group("body") if m else None


def _parse_replace_blocks(diff_text: str) -> List[Tuple[str, str]]:
    """解析由 SEARCH/REPLACE 组成的区块。

    语法：
    ------- SEARCH\n
    [exact content]\n
    =======\n
    [new content]\n
    +++++++ REPLACE

    支持多个区块，按出现顺序解析。
    """
    blocks: List[Tuple[str, str]] = []
    lines = diff_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lines):
        # 寻找 SEARCH 头
        if re.match(r"^\s*-------\s*SEARCH\s*$", lines[i]):
            i += 1
            search_lines: List[str] = []
            # 收集 SEARCH 内容直到 =======
            while i < len(lines) and not re.match(r"^\s*=======" , lines[i]):
                search_lines.append(lines[i])
                i += 1
            # 跳过 =======
            if i < len(lines) and re.match(r"^\s*=======" , lines[i]):
                i += 1
            else:
                # 结构不完整，停止解析
                break

            replace_lines: List[str] = []
            # 收集 REPLACE 内容直到 +++++++ REPLACE
            while i < len(lines) and not re.match(r"^\s*\+{7}\s*REPLACE\s*$", lines[i]):
                replace_lines.append(lines[i])
                i += 1
            # 跳过 +++++++ REPLACE
            if i < len(lines) and re.match(r"^\s*\+{7}\s*REPLACE\s*$", lines[i]):
                i += 1
            else:
                # 结构不完整，停止解析
                break

            search = "\n".join(search_lines)
            replace = "\n".join(replace_lines)
            blocks.append((search, replace))
        else:
            i += 1
    return blocks


def _detect_newline_style(text: str) -> str:
    """检测文本中的换行风格；默认返回 '\n'。"""
    # 优先 CRLF
    if "\r\n" in text:
        return "\r\n"
    # 若存在单独 CR，较罕见，但兼容
    if "\r" in text and "\n" not in text:
        return "\r"
    return "\n"


def apply_replace_in_file_text(request_text: str, root_dir: str) -> Dict:
    """应用 <replace_in_file> 请求，执行基于 SEARCH/REPLACE 的精确替换。

    返回结构：
    { applied: bool, changes: list, errors: list }
    """
    changes: List[Dict] = []
    errors: List[str] = []

    # 提取 path 与 diff
    path_text = _extract_xml_tag(request_text, "path")
    diff_text = _extract_xml_tag(request_text, "diff")

    if not path_text:
        errors.append("Missing <path> in replace_in_file request")
        return {"applied": False, "changes": changes, "errors": errors}
    if not diff_text:
        errors.append("Missing <diff> in replace_in_file request")
        return {"applied": False, "changes": changes, "errors": errors}

    blocks = _parse_replace_blocks(diff_text)
    if not blocks:
        errors.append("No valid SEARCH/REPLACE blocks parsed")
        return {"applied": False, "changes": changes, "errors": errors}

    target = Path(root_dir) / _strip_prefix(path_text.strip(), "/")
    try:
        file_text = target.read_text(encoding="utf-8")
    except Exception as e:
        errors.append(f"Read target file failed: {target}: {e}")
        return {"applied": False, "changes": changes, "errors": errors}

    newline = _detect_newline_style(file_text)

    # 依次应用区块（仅替换首次出现）
    modified = False
    for idx, (search_raw, replace_raw) in enumerate(blocks, start=1):
        # 归一换行到文件风格
        search = (search_raw.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline))
        replace = (replace_raw.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline))

        pos = file_text.find(search)
        if pos == -1:
            # 为帮助诊断，提供少量上下文
            snippet = search_raw.splitlines()[:3]
            errors.append(
                f"SEARCH block #{idx} not found in {target}. First lines: "
                + (" | ".join(snippet) if snippet else "<empty>")
            )
            continue

        file_text = file_text[:pos] + replace + file_text[pos + len(search):]
        changes.append({
            "op": "replace",
            "path": str(target),
            "block_index": idx,
            "deleted_len": len(search),
            "inserted_len": len(replace),
        })
        modified = True

    if modified:
        try:
            target.write_text(file_text, encoding="utf-8")
        except Exception as e:
            errors.append(f"Write file failed: {target}: {e}")

    # 成功条件：至少一个区块成功替换，且没有写入错误
    applied_ok = modified and all("Write file failed" not in err for err in errors)
    if not modified and len(errors) == 0:
        errors.append("No changes applied: all SEARCH blocks not found")

    return {"applied": applied_ok, "changes": changes, "errors": errors}