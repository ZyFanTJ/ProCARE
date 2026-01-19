#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
apply_unified_patch.py

从包含 <<PATCH>> ... <<END_PATCH>> 的文本中提取 git unified diff 并应用到指定根目录。
特性：
- 支持新增/修改/删除文件（/dev/null）
- 兼容 CRLF/LF
- dry-run 预演
- 自动备份 .bak
- 路径裁剪 --strip/-p（类似 git apply -pN）
- 优先使用 `unidiff` 解析；若不可用或解析失败，回退内置解析
"""

import argparse
import io
import os
import re
import shutil
import sys
from typing import List, Tuple, Optional

# --------------- 工具函数 ---------------

PATCH_START = r"<<PATCH>>"
PATCH_END = r"<<END_PATCH>>"


def extract_patch_block(text: str) -> str:
    """从带边界的文本中提取 diff 内容；若找不到边界，则假定 text 本身即为统一 diff。"""
    m_start = re.search(r"(?m)^\s*<<PATCH>>\s*$", text)
    m_end = re.search(r"(?m)^\s*<<END_PATCH>>\s*$", text)
    if m_start and m_end and m_end.start() > m_start.end():
        patch = text[m_start.end():m_end.start()]
    else:
        patch = text
    # 防御性：去除误粘的 Markdown 围栏
    patch = re.sub(r"(?m)^\s*```.*$", "", patch)
    # 不做 strip；交由解析阶段统一换行与尾部清理
    return patch


def _contains_nonprefixed_hunk_lines(patch_text: str) -> bool:
    """检测补丁是否包含未带前缀的 hunk 行（既不是 ' ', '+', '-' 开头）。
    若存在，则说明该补丁更适合宽松解析而不是严格 unidiff。
    """
    in_hunk = False
    for ln in normalize_newlines(patch_text).split("\n"):
        if ln.startswith("diff --git "):
            in_hunk = False
            continue
        if ln.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if not ln:
            # 空行视作上下文
            continue
        if ln.startswith(" ") or ln.startswith("+") or ln.startswith("-"):
            continue
        # 不是头部且在 hunk 内的裸行
        return True
    return False


def detect_encoding(path: str) -> str:
    """简单编码探测：优先 utf-8，失败回退 gbk，再回退 latin-1。"""
    for enc in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                _ = f.read()
            return enc
        except Exception:
            continue
    return "utf-8"


def normalize_newlines(s: str) -> str:
    """统一换行符为 LF，避免 CRLF 影响 hunk 匹配。"""
    return s.replace("\r\n", "\n").replace("\r", "\n")


def ensure_parent_dir(path: str):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def strip_path(p: str, strip: int) -> str:
    """模拟 git apply -pN：裁剪前 N 个路径段。"""
    if strip <= 0:
        return p
    parts = p.split("/")
    if len(parts) <= strip:
        return ""
    return "/".join(parts[strip:])


# --------------- 基于 unidiff 的实现 ---------------

def _apply_with_unidiff(patch_text: str, root_dir: str, strip: int, dry_run: bool) -> Tuple[bool, List[str]]:
    try:
        from unidiff import PatchSet  # type: ignore
        from unidiff.errors import UnidiffParseError  # type: ignore
    except Exception as e:
        return False, [f"[WARN] unidiff 不可用（{e}），准备回退到内置解析器。"]

    msgs: List[str] = []

    # 统一换行并压缩末尾多余空行，避免 Unexpected trailing newline character
    patch_text = normalize_newlines(patch_text)
    patch_text = re.sub(r"\n+$", "\n", patch_text)  # 保留至多一个末尾换行

    try:
        ps = PatchSet(io.StringIO(patch_text))
    except UnidiffParseError as ue:
        return False, [f"[WARN] unidiff 解析失败（{ue}）。将回退到内置解析器。"]
    except Exception as e:
        return False, [f"[WARN] unidiff 解析异常（{e}）。将回退到内置解析器。"]

    if not ps:
        return False, ["[ERROR] 未解析到任何文件补丁"]

    for pf in ps:
        # 解析目标路径：优先使用原始 target/source，保留 a/、b/ 前缀供 -p 处理；若都为空，退回 pf.path
        raw_target = (pf.target_file or "")
        raw_source = (pf.source_file or "")
        rel_raw = (raw_target or raw_source or (pf.path or "")).replace("\\", "/").lstrip("/")

        # 路径裁剪（类似 git apply -pN）
        rel_path = strip_path(rel_raw, strip)
        if rel_path == "":
            orig = raw_target or raw_source or (pf.path or "")
            msgs.append(f"[INFO] 跳过：路径在 -p{strip} 裁剪后为空（原始：{orig}）")
            continue

        abs_path = os.path.join(root_dir, rel_path)

        # 新增/删除判断
        is_new = pf.is_added_file or pf.source_file == "/dev/null"
        is_delete = pf.is_removed_file or pf.target_file == "/dev/null"

        if is_delete:
            if dry_run:
                msgs.append(f"[DRY-RUN] 删除文件：{rel_path}")
            else:
                if os.path.exists(abs_path):
                    os.remove(abs_path)
                    msgs.append(f"[OK] 已删除：{rel_path}")
                else:
                    msgs.append(f"[INFO] 要删除的文件不存在：{rel_path}")
            continue

        if is_new:
            # 新增文件：尽可能收集所有非删除的行（兼容不规范上下文）
            new_lines: List[str] = []
            for h in pf:
                for l in h:
                    v = l.value.replace("\r\n", "\n").replace("\r", "\n")
                    # 标准：新增或上下文
                    if l.is_added or l.is_context:
                        new_lines.append(v)
                    # 兼容：未知类型但不是删除，视作内容行
                    elif not l.is_removed:
                        # 跳过“无换行结尾”标记等空白提示
                        if v.strip() in ("", "\\ No newline at end of file"):
                            continue
                        new_lines.append(v)
            content = "".join(new_lines)
            if dry_run:
                msgs.append(f"[DRY-RUN] 新增文件：{rel_path}（{len(new_lines)} 行）")
            else:
                ensure_parent_dir(abs_path)
                with open(abs_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(content)
                msgs.append(f"[OK] 已新增：{rel_path}（{len(new_lines)} 行）")
            continue

        # 修改已有文件：基于 hunk 应用
        if not os.path.exists(abs_path):
            msgs.append(f"[WARN] 目标文件不存在，尝试按新增处理：{rel_path}")
            ensure_parent_dir(abs_path)
            base = ""
        else:
            enc = detect_encoding(abs_path)
            with open(abs_path, "r", encoding=enc, newline="") as f:
                base = f.read()

        base_norm = normalize_newlines(base)
        base_lines = base_norm.split("\n")

        cursor = 0
        out_lines: List[str] = []
        ok = True

        for h in pf:
            target_start_idx = h.source_start - 1  # 在原文件中的预期起点（1-based -> 0-based）
            out_lines.extend(base_lines[cursor:target_start_idx])
            cursor = target_start_idx

            for l in h:
                v = l.value.replace("\r\n", "\n").replace("\r", "\n")
                if v.endswith("\n"):
                    v = v[:-1]
                if l.is_context:
                    if cursor >= len(base_lines) or base_lines[cursor] != v:
                        msgs.append(f"[ERROR] hunk 上下文不匹配：{rel_path} @ 原始行 {cursor+1}")
                        ok = False
                        break
                    out_lines.append(v)
                    cursor += 1
                elif l.is_removed:
                    if cursor >= len(base_lines) or base_lines[cursor] != v:
                        msgs.append(f"[ERROR] hunk 删除不匹配：{rel_path} @ 原始行 {cursor+1}")
                        ok = False
                        break
                    cursor += 1  # 跳过（删除）
                elif l.is_added:
                    out_lines.append(v)
                else:
                    # 兼容处理：将未知类型行宽松视作上下文或新增，避免报错中断
                    # 常见情况：unidiff 将某些提示行标记为特殊类型，或补丁上下文缺少前缀
                    if v.strip() in ("", "\\ No newline at end of file"):
                        # 忽略空白或 EOF 提示
                        continue
                    # 若与原文件当前位置匹配，当作上下文
                    if cursor < len(base_lines) and base_lines[cursor] == v:
                        out_lines.append(v)
                        cursor += 1
                    else:
                        # 否则宽松当作新增行插入
                        out_lines.append(v)
            if not ok:
                break

        if not ok:
            return False, msgs

        out_lines.extend(base_lines[cursor:])

        if dry_run:
            msgs.append(f"[DRY-RUN] 修改文件：{rel_path}（输出 {len(out_lines)} 行）")
        else:
            if os.path.exists(abs_path):
                shutil.copyfile(abs_path, abs_path + ".bak")
            ensure_parent_dir(abs_path)
            with open(abs_path, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(out_lines))
            msgs.append(f"[OK] 已修改：{rel_path}（{len(out_lines)} 行）")

    return True, msgs


# --------------- 内置简易解析回退 ---------------

def _split_file_diffs(patch_text: str) -> List[str]:
    """把统一 diff 按 'diff --git' 切分为若干文件块（保留头部）。
    仅在遇到 'diff --git' 后开始记录，避免前导空块。
    """
    blocks: List[str] = []
    cur: List[str] = []
    started = False
    for line in normalize_newlines(patch_text).split("\n"):
        if line.startswith("diff --git "):
            if started and cur:
                blocks.append("\n".join(cur))
                cur = []
            started = True
            cur.append(line)
        else:
            if started:
                cur.append(line)
    if started and cur:
        blocks.append("\n".join(cur))
    return blocks


def _parse_headers(block: str) -> Tuple[str, str]:
    """解析 --- 与 +++ 行，返回 (source, target)。若不存在则返回空串。
    保留 a/ 与 b/ 前缀，交由 strip 参数处理。
    """
    src = ""
    tgt = ""
    for line in block.split("\n"):
        if line.startswith("--- "):
            src = line[4:].strip()
        elif line.startswith("+++ "):
            tgt = line[4:].strip()
    return src, tgt


# --------------- LLM 风格 hunk 支持（无行号，仅上下文） ---------------

def _is_llm_style_hunk_header(line: str) -> bool:
    """判断是否为 LLM 风格的 hunk 头（例如: '@@ def func(...)'，而非 '@@ -a,b +c,d @@'）。"""
    if not line.startswith("@@"):
        return False
    # 标准头部通常形如: @@ -12,5 +12,7 @@ 可选附带函数名
    return re.match(r"^@@\s*-?\d+,\d+\s+\+?\d+,\d+\s+@@", line) is None


def _parse_diff_git_header(block: str) -> Tuple[str, str]:
    """从 'diff --git a/X b/Y' 解析 a/b 路径（若存在）。返回 (a, b)。保留前缀。"""
    lines = block.splitlines()
    first = lines[0] if lines else ""
    if first.startswith("diff --git "):
        parts = first.split()
        if len(parts) >= 4:
            a = parts[2]
            b = parts[3]
            return a, b
    return "", ""


def _detect_new_or_delete(block: str, src: str, tgt: str) -> Tuple[bool, bool]:
    """根据头部与 mode 行判断新增/删除。"""
    is_new = (src.strip() == "/dev/null") or any(
        ln.strip().startswith("new file mode") for ln in block.splitlines()
    )
    is_delete = (tgt.strip() == "/dev/null") or any(
        ln.strip().startswith("deleted file mode") for ln in block.splitlines()
    )
    return is_new, is_delete


def _collect_llm_hunks(lines: List[str]) -> List[Tuple[Optional[str], List[str]]]:
    """按 LLM 风格收集每个 hunk：返回 [(anchor, hunk_lines)]。"""
    hunks: List[Tuple[Optional[str], List[str]]] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("@@"):
            if _is_llm_style_hunk_header(ln):
                anchor = ln[2:].strip() or None
                i += 1
                buf: List[str] = []
                while i < len(lines) and not lines[i].startswith("@@"):
                    buf.append(lines[i])
                    i += 1
                hunks.append((anchor, buf))
                continue
        i += 1
    return hunks


def _apply_hunk_by_search(base_lines: List[str], anchor: Optional[str], hunk_lines: List[str]) -> List[str]:
    """将一个 hunk 应用到 base_lines 上：通过锚点与删除块搜索替换。返回新的 base_lines。"""
    # 解析 hunk 内的加减/上下文
    added: List[str] = []
    removed: List[str] = []
    context: List[str] = []
    for raw in hunk_lines:
        if raw.startswith("+") and not raw.startswith("+++"):
            added.append(raw[1:])
        elif raw.startswith("-") and not raw.startswith("---"):
            removed.append(raw[1:])
        elif raw.startswith(" "):
            context.append(raw[1:])
        else:
            # 其他行当作上下文（例如空行或普通文本）
            context.append(raw)

    # 若提供锚点，尝试定位
    start_idx = 0
    if anchor:
        # 在全文中寻找包含 anchor 的行（宽松匹配）
        norm_anchor = anchor.strip()
        for idx, line in enumerate(base_lines):
            if norm_anchor and norm_anchor in line:
                start_idx = idx
                break

    # 搜索要删除的块（连续匹配）。若没有删除块，则按锚点插入。
    def find_sequence(seq: List[str], begin: int, window: int = 300) -> Tuple[int, int]:
        if not seq:
            return -1, -1
        end_bound = min(len(base_lines), begin + window) if begin < len(base_lines) else len(base_lines)
        # 允许在全局扫描
        candidates = range(begin, end_bound) if begin < len(base_lines) else range(0, len(base_lines))
        for i in candidates:
            ok = True
            for j, s in enumerate(seq):
                if i + j >= len(base_lines) or base_lines[i + j].strip() != s.strip():
                    ok = False
                    break
            if ok:
                return i, i + len(seq)
        # 尝试全量扫描
        for i in range(0, len(base_lines)):
            ok = True
            for j, s in enumerate(seq):
                if i + j >= len(base_lines) or base_lines[i + j].strip() != s.strip():
                    ok = False
                    break
            if ok:
                return i, i + len(seq)
        return -1, -1

    left, right = find_sequence(removed, start_idx)

    new_lines = base_lines[:]
    if left != -1:
        # 替换删除块为新增块
        new_lines = new_lines[:left] + added + new_lines[right:]
    else:
        # 未找到删除块：若有上下文，尝试在锚点后查找上下文再插入
        ctx_left, ctx_right = find_sequence(context, start_idx)
        if ctx_left != -1:
            new_lines = new_lines[:ctx_right] + added + new_lines[ctx_right:]
        else:
            # 退化：若有锚点，在其后插入；否则追加到文件末尾
            insert_pos = start_idx + 1 if start_idx < len(base_lines) else len(base_lines)
            new_lines = new_lines[:insert_pos] + added + new_lines[insert_pos:]

    return new_lines


def _apply_llm_style(block: str, root_dir: str, strip: int, dry_run: bool) -> Tuple[bool, List[str]]:
    """对单个文件块应用 LLM 风格补丁。"""
    msgs: List[str] = []
    src, tgt = _parse_headers(block)
    a_path, b_path = _parse_diff_git_header(block)
    # 选择目标路径：优先 b_path 或 tgt
    rel = (b_path or tgt or a_path or src).replace("\\", "/")
    rel = strip_path(rel, strip)
    if not rel:
        first = block.splitlines()[0] if block.splitlines() else "(EMPTY BLOCK)"
        return False, [f"[ERROR] 无法解析目标路径，首行：{first}"]

    abs_path = os.path.join(root_dir, rel)
    is_new, is_delete = _detect_new_or_delete(block, src, tgt)

    lines = normalize_newlines(block).split("\n")
    hunks = _collect_llm_hunks(lines)

    if is_delete:
        if dry_run:
            msgs.append(f"[DRY-RUN] 删除文件：{rel}")
            return True, msgs
        if os.path.exists(abs_path):
            os.remove(abs_path)
            msgs.append(f"[OK] 已删除：{rel}")
        else:
            msgs.append(f"[INFO] 要删除的文件不存在：{rel}")
        return True, msgs

    if is_new:
        # 将所有 hunk 的新增与上下文行拼接为新文件内容
        new_lines: List[str] = []
        for anchor, hunk_lines in hunks:
            for raw in hunk_lines:
                if raw.startswith("+") and not raw.startswith("+++"):
                    new_lines.append(raw[1:])
                elif raw.startswith(" "):
                    new_lines.append(raw[1:])
                elif raw and raw[0] not in "+-@":
                    new_lines.append(raw)
        content = "\n".join(new_lines)
        if dry_run:
            msgs.append(f"[DRY-RUN] 新增文件：{rel}（{len(new_lines)} 行）")
            return True, msgs
        ensure_parent_dir(abs_path)
        with open(abs_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        msgs.append(f"[OK] 已新增：{rel}（{len(new_lines)} 行）")
        return True, msgs

    # 修改已有文件
    if not os.path.exists(abs_path):
        ensure_parent_dir(abs_path)
        base_text = ""
        msgs.append(f"[WARN] 目标文件不存在，按空文件尝试：{rel}")
    else:
        enc = detect_encoding(abs_path)
        with open(abs_path, "r", encoding=enc, newline="") as f:
            base_text = normalize_newlines(f.read())

    base_lines = base_text.split("\n")
    out_lines = base_lines[:]
    for anchor, hunk_lines in hunks:
        out_lines = _apply_hunk_by_search(out_lines, anchor, hunk_lines)

    if dry_run:
        msgs.append(f"[DRY-RUN] 修改文件：{rel}（输出 {len(out_lines)} 行）")
        return True, msgs

    if os.path.exists(abs_path):
        shutil.copyfile(abs_path, abs_path + ".bak")
    ensure_parent_dir(abs_path)
    with open(abs_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out_lines))
    msgs.append(f"[OK] 已修改：{rel}（{len(out_lines)} 行）")
    return True, msgs


def _apply_with_llm_style(patch_text: str, root_dir: str, strip: int, dry_run: bool) -> Tuple[bool, List[str]]:
    """尝试以 LLM 风格（无行号 hunk）应用补丁。"""
    msgs: List[str] = []
    text = normalize_newlines(patch_text)
    blocks = _split_file_diffs(text)
    if not blocks:
        return False, ["[ERROR] 未检测到 'diff --git' 头部，无法解析。"]

    any_llm = any(any(_is_llm_style_hunk_header(ln) for ln in b.splitlines()) for b in blocks)
    if not any_llm:
        return False, ["[INFO] 未检测到 LLM 风格 hunk，跳过该解析器"]

    ok_all = True
    for block in blocks:
        ok, mm = _apply_llm_style(block, root_dir, strip, dry_run)
        msgs.extend(mm)
        ok_all = ok_all and ok
    return ok_all, msgs


def _apply_with_builtin(patch_text: str, root_dir: str, strip: int, dry_run: bool) -> Tuple[bool, List[str]]:
    msgs: List[str] = []
    # 同步预处理，尽量与 unidiff 行为一致
    patch_text = normalize_newlines(patch_text)
    patch_text = re.sub(r"\n+$", "\n", patch_text)

    blocks = _split_file_diffs(patch_text)
    if not blocks:
        return False, ["[ERROR] 未检测到 'diff --git' 头部，无法解析。"]

    ok_all = True
    for block in blocks:
        src, tgt = _parse_headers(block)
        rel = (tgt or src).replace("\\", "/")
        if rel == "/dev/null":
            # 需要与头部联合判断新增/删除；为简化，这里跳过，让上层更严格的解析去处理
            first = block.splitlines()[0] if block.splitlines() else "(EMPTY BLOCK)"
            msgs.append(f"[INFO] 跳过 /dev/null 块（弱解析器不处理新增/删除判定）：\n{first}")
            continue

        rel = strip_path(rel, strip)
        if not rel or rel == "/dev/null":
            first = block.splitlines()[0] if block.splitlines() else "(EMPTY BLOCK)"
            msgs.append(f"[INFO] 跳过无法确定路径的块：\n{first}")
            continue

        abs_path = os.path.join(root_dir, rel)

        # 简化策略：取所有 hunk 之后的 + 与 context 行覆盖写入（弱匹配）
        lines = block.split("\n")
        hunks_started = False
        new_lines: List[str] = []
        for ln in lines:
            if ln.startswith("@@"):
                hunks_started = True
                continue
            if not hunks_started:
                continue
            if ln.startswith("+") and not ln.startswith("+++"):
                new_lines.append(ln[1:])
            elif ln.startswith(" ") or (ln and ln[0] not in "+-@"):
                new_lines.append(ln[1:] if ln.startswith(" ") else ln)

        if dry_run:
            msgs.append(f"[DRY-RUN][WEAK] 覆盖写入：{rel}（{len(new_lines)} 行）")
            continue

        ensure_parent_dir(abs_path)
        if os.path.exists(abs_path):
            shutil.copyfile(abs_path, abs_path + ".bak")
        with open(abs_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(new_lines))
        msgs.append(f"[OK][WEAK] 已覆盖写入：{rel}（{len(new_lines)} 行）")

    return ok_all, msgs


# --------------- 对外 API ---------------

def apply_unified_diff(patch_text: str, root_dir: str, strip: int = 0, dry_run: bool = False) -> Tuple[bool, List[str]]:
    """
    直接应用纯 git 统一 diff（不带 <<PATCH>>）。
    优先 unidiff，失败时回退内置解析（弱匹配）。
    """
    # 若检测到未带前缀的 hunk 行，跳过严格的 unidiff 解析，直接走宽松路径
    if _contains_nonprefixed_hunk_lines(patch_text):
        ok_llm, msgs_llm = _apply_with_llm_style(patch_text, root_dir, strip, dry_run)
        if ok_llm:
            return ok_llm, msgs_llm
        ok2, msgs2 = _apply_with_builtin(patch_text, root_dir, strip, dry_run)
        return ok2, msgs_llm + msgs2

    # 先尝试 unidiff
    ok, msgs = _apply_with_unidiff(patch_text, root_dir, strip, dry_run)
    if ok:
        return ok, msgs
    # 若 unidiff 失败，尝试 LLM 风格解析
    ok_llm, msgs_llm = _apply_with_llm_style(patch_text, root_dir, strip, dry_run)
    if ok_llm:
        return ok_llm, msgs + msgs_llm
    # 最后回退到内置弱解析
    ok2, msgs2 = _apply_with_builtin(patch_text, root_dir, strip, dry_run)
    return ok2, msgs + msgs_llm + msgs2


def apply_from_marked_text(marked_text: str, root_dir: str, strip: int = 0, dry_run: bool = False) -> Tuple[bool, List[str]]:
    """从带 <<PATCH>> 包裹的文本中提取 diff 并应用。"""
    patch = extract_patch_block(marked_text)
    if not patch or not patch.strip():
        return False, ["[ERROR] 未提取到任何补丁内容"]
    return apply_unified_diff(patch, root_dir, strip=strip, dry_run=dry_run)


# --------------- CLI ---------------

def main():
    p = argparse.ArgumentParser(description="Apply git unified diff to a directory.")
    p.add_argument("--patch", type=str, required=False, help="包含补丁内容的文件路径（可含 <<PATCH>> 包裹）。若省略，则从 stdin 读取。")
    p.add_argument("--root", type=str, required=True, help="应用补丁的根目录（相当于仓库根）。")
    p.add_argument("-p", "--strip", type=int, default=0, help="路径裁剪段数（类似 git apply -pN）。")
    p.add_argument("--dry-run", action="store_true", help="预演，不写入文件。")
    args = p.parse_args()

    if args.patch:
        with open(args.patch, "r", encoding="utf-8", newline="") as f:
            marked = f.read()
    else:
        marked = sys.stdin.read()

    ok, logs = apply_from_marked_text(marked_text=marked, root_dir=args.root, strip=args.strip, dry_run=args.dry_run)

    for m in logs:
        print(m)
    if not ok:
        sys.exit(2)


if __name__ == "__main__":
    main()
