"""Đề xuất trục ứng viên ĐA NGUỒN — enum + config-surface + branch-condition.

Proposer của tot-grid-coverage đọc code từ NHIỀU bề mặt, không chỉ Enum. Ba nguồn,
ba tier provenance khác nhau — và chính sự khác tier đó làm cổng `admit_axis` CẮN
thật thay vì kịch câm (khi mọi trục đều `retrieved` thì tầng provenance chẳng loại
được gì):

- **enum** → tier `retrieved`: một `class X(Enum)` là hằng số rời rạc ĐÃ khai báo,
  đọc thẳng từ source. Nguồn mạnh nhất.
- **config** → tier `derived`: `Literal["a", "b"]` trong annotation/Field là một bề
  mặt cấu hình rời rạc — SUY RA từ kiểu, không phải một enum runtime, nhưng vẫn neo
  vào một khai báo có thật.
- **branch** → tier `asserted`: một biến bị so `== "x"` rải rác trong nhánh điều
  kiện. Ta KHẲNG ĐỊNH nó là một trục vì thấy code rẽ theo nó, nhưng không có khai
  báo nào chứng thực tập giá trị đó đóng — nên `asserted`, và `admit_axis` loại nó
  khỏi đường default (chỉ HITL mới đưa vào được). Đây đúng là điểm dạy provenance.

Tất định tuyệt đối (AST, không LLM). Dedup theo tên: tier mạnh thắng — thứ tự phát
sinh enum→config→branch + first-wins cho ra đúng ưu tiên `retrieved>derived>asserted`.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from app.core.grid.axis_admit import AxisCandidate

__all__ = ["propose_candidates"]

# Biến một-ký-tự / dunder gần như luôn là loop var hoặc field nội bộ, không phải
# trục rủi ro — bỏ để branch-source không ngập rác.
_MIN_NAME_LEN = 2


def _iter_py(root: Path) -> Iterator[tuple[Path, ast.AST]]:
    for py in sorted(root.rglob("*.py")):
        if "test" in py.parts or py.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        yield py, tree


def _literal_members(sl: ast.expr) -> list[str]:
    """Chuỗi hằng trong `Literal[...]` — slice là Tuple (nhiều) hoặc một hằng đơn."""
    elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
    out: list[str] = []
    for e in elts:
        if isinstance(e, ast.Constant) and isinstance(e.value, str):
            out.append(e.value)
    return out


def _is_literal(value: ast.expr) -> bool:
    return (isinstance(value, ast.Name) and value.id == "Literal") or (
        isinstance(value, ast.Attribute) and value.attr == "Literal"
    )


def _annotation_literal(ann: ast.expr | None) -> list[str] | None:
    """Nếu annotation là `Literal[...]` trực tiếp, trả tập giá trị; ngược lại None."""
    if isinstance(ann, ast.Subscript) and _is_literal(ann.value):
        members = _literal_members(ann.slice)
        return members or None
    return None


def _config_candidates(root: Path) -> list[AxisCandidate]:
    """`name: Literal["a", "b"]` trong AnnAssign hoặc arg annotation → trục derived."""
    seen: dict[str, AxisCandidate] = {}
    for py, tree in _iter_py(root):
        rel = py.relative_to(root)
        for node in ast.walk(tree):
            target_name: str | None = None
            ann: ast.expr | None = None
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                target_name, ann = node.target.id, node.annotation
            elif isinstance(node, ast.arg) and node.annotation is not None:
                target_name, ann = node.arg, node.annotation
            if target_name is None or target_name.startswith("_") or len(target_name) < _MIN_NAME_LEN:
                continue
            members = _annotation_literal(ann)
            if not members or len(members) < 2:
                continue
            # first-wins: giữ lần gặp đầu (thứ tự file đã sort) cho ổn định.
            if target_name not in seen:
                seen[target_name] = AxisCandidate(
                    name=target_name, members=tuple(members),
                    ref=f"config:{rel}:{node.lineno}", tier="derived", origin="config",
                )
    return list(seen.values())


def _branch_candidates(root: Path) -> list[AxisCandidate]:
    """`var == "x"` / `var in ("x", "y")` gom theo biến → tập literal → trục asserted.

    Gom hợp (union) mọi literal đối chiếu với cùng một tên biến trong toàn repo. Đây
    là tín hiệu YẾU theo thiết kế (asserted) — mục đích là PHƠI cho HITL thấy, còn cổng
    default loại nó. Neo `ref` vào lần so đầu tiên.
    """
    members: dict[str, list[str]] = {}
    first_ref: dict[str, str] = {}
    for py, tree in _iter_py(root):
        rel = py.relative_to(root)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            left = node.left
            if not isinstance(left, ast.Name):
                continue
            var = left.id
            if var.startswith("_") or len(var) < _MIN_NAME_LEN:
                continue
            lits: list[str] = []
            for op, comp in zip(node.ops, node.comparators, strict=True):
                if isinstance(op, ast.Eq) and isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                    lits.append(comp.value)
                elif isinstance(op, (ast.In, ast.NotIn)) and isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
                    lits.extend(e.value for e in comp.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
            if not lits:
                continue
            bag = members.setdefault(var, [])
            for lit in lits:
                if lit not in bag:
                    bag.append(lit)
            first_ref.setdefault(var, f"branch:{rel}:{node.lineno}")
    out: list[AxisCandidate] = []
    for var in sorted(members):
        vals = members[var]
        if len(vals) < 2:
            continue
        out.append(AxisCandidate(
            name=var, members=tuple(vals), ref=first_ref[var], tier="asserted", origin="branch",
        ))
    return out


def propose_candidates(
    root: Path,
    discovered: Mapping[str, Sequence[str]],
    discovered_source: Mapping[str, str],
    *,
    sources: Sequence[str] = ("enum", "config", "branch"),
) -> list[AxisCandidate]:
    """Danh sách ứng viên đa nguồn, thứ tự enum→config→branch, dedup first-wins.

    `discovered`/`discovered_source` là kết quả `discover_axes` (Enum, tier retrieved) —
    truyền vào thay vì quét lại để giữ MỘT nguồn sự thật cho tập Enum. first-wins theo
    thứ tự nguồn cho ưu tiên tier: một tên vừa là Enum vừa là branch thì giữ bản Enum.
    """
    out: list[AxisCandidate] = []
    seen: set[str] = set()

    def _add(cands: list[AxisCandidate]) -> None:
        for c in cands:
            if c.name in seen:
                continue
            seen.add(c.name)
            out.append(c)

    if "enum" in sources:
        _add([
            AxisCandidate(name=n, members=tuple(v), ref=discovered_source.get(n, "?"),
                          tier="retrieved", origin="enum")
            for n, v in discovered.items()
        ])
    if "config" in sources:
        _add(_config_candidates(root))
    if "branch" in sources:
        _add(_branch_candidates(root))
    return out
