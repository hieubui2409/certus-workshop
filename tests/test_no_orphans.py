"""Đếm nơi gọi — luật `NNR-1`: code viết ra luôn được cắm vào, không mồ côi.

Đây là phép đo thứ hai trong định nghĩa "gate thật" (note 03 §1.4):

    Hàm chấm phải có ≥1 nơi gọi ngoài chính tệp định nghĩa và ngoài cây bài
    kiểm. 0 nơi gọi ⇒ ĐỎ. Phép đếm phải phát ra MẪU SỐ `symbols_scanned` cùng
    tử số `orphans`; `symbols_scanned == 0` ⇒ ĐỎ.

Ba điều tệp này cố ý làm khác cách quét ngây thơ:

1. **Chỉ đếm CẠNH GỌI THẬT (`ast.Call`).** Một cái tên nằm trong dict đăng ký
   không phải một nơi gọi — hệ tham chiếu có `registerGate` với 0 nơi đăng ký
   handler thật, và bảng ánh xạ của nó trông rất đầy đủ.
2. **Dùng AST, không dùng regex.** Đã đo được ba lần trong cùng một đợt: khảo
   sát bằng regex trên mã luôn trả tập NHỎ HƠN thật.
3. **Có đối chứng dương.** Một kết quả rỗng đọc y hệt nhau ở hai hoàn cảnh khác
   hẳn nhau — "quét sạch, không có hàm mồ côi" và "quét trượt, không bắt được
   gì". Không có đối chứng thì số 0 không được đọc thành phán quyết.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "src" / "backend"
APP_ROOT = BACKEND_ROOT / "app"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.contracts.errors import EmptyDenominatorError  # noqa: E402
from app.gates import registry  # noqa: E402

#: Tập CƯỠNG CHẾ — sáu hàm chấm. Mỗi hàm phải có nơi gọi sản phẩm.
ENFORCED_SYMBOLS: frozenset[str] = frozenset(
    {
        "check_requirements",
        "check_design",
        "check_grid",
        "check_execution",
        "check_outcome",
        "evaluate_stop_gate",
    }
)

#: Tập BIÊN — ổ cắm mà tầng 4 (`orchestrator/pipeline.py`) phải cắm vào.
#: Chúng chưa có nơi gọi sản phẩm vì tầng 4 thuộc lô build sau. Danh sách này
#: được ghim để chỗ hở SOÁT ĐƯỢC thay vì vô hình: thêm một hàm chưa đấu nối vào
#: đây làm bộ kiểm ĐỎ ngay.
EXPECTED_BOUNDARY: frozenset[str] = frozenset({"run_gate", "run_chain", "run_stop_gate"})


@dataclass(frozen=True)
class CallCensus:
    """Kết quả một lượt đếm. Mẫu số luôn đi cùng tử số."""

    symbols_scanned: int
    orphans: tuple[str, ...]
    files_parsed: int
    functions_indexed: int
    callers: dict[str, tuple[str, ...]]

    @property
    def orphan_count(self) -> int:
        return len(self.orphans)


def _is_test_path(path: Path) -> bool:
    return path.name.startswith("test_") or "tests" in path.parts


def census(root: Path, enforced: frozenset[str]) -> CallCensus:
    """Đếm nơi gọi của `enforced` trên cây `root`.

    Trả về mẫu số cùng tử số. Không tệp `.py` nào, hoặc không tên nào trong
    `enforced` tìm thấy định nghĩa ⇒ raise: mẫu số rỗng nghĩa là phép đếm trượt,
    và một phép đếm trượt không được phép trông giống một cây sạch.
    """
    files = sorted(p for p in root.rglob("*.py") if not _is_test_path(p))
    if not files:
        raise EmptyDenominatorError(f"không có tệp .py nào dưới {root} — phép quét trượt phạm vi")

    definitions: dict[str, set[Path]] = {}
    call_sites: dict[str, set[Path]] = {}
    functions_indexed = 0

    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions_indexed += 1
                definitions.setdefault(node.name, set()).add(path)
            elif isinstance(node, ast.Call):
                func = node.func
                name = (
                    func.id
                    if isinstance(func, ast.Name)
                    else func.attr
                    if isinstance(func, ast.Attribute)
                    else None
                )
                if name is not None:
                    call_sites.setdefault(name, set()).add(path)

    scanned = sorted(name for name in enforced if name in definitions)
    if not scanned:
        raise EmptyDenominatorError(
            f"symbols_scanned == 0 dưới {root}: không tìm thấy định nghĩa nào của "
            f"{sorted(enforced)} — ĐỎ, không phải 'không có hàm mồ côi'"
        )

    orphans: list[str] = []
    callers: dict[str, tuple[str, ...]] = {}
    for name in scanned:
        outside = {
            p for p in call_sites.get(name, set()) if p not in definitions[name]
        }
        callers[name] = tuple(sorted(str(p.relative_to(root)) for p in outside))
        if not outside:
            orphans.append(name)

    return CallCensus(
        symbols_scanned=len(scanned),
        orphans=tuple(orphans),
        files_parsed=len(files),
        functions_indexed=functions_indexed,
        callers=callers,
    )


# ───────────────────────── phép đo thật ─────────────────────────


def test_no_orphan_gate_functions() -> None:
    """0 nơi gọi ⇒ ĐỎ. Mẫu số phải khác 0 thì tử số mới có nghĩa."""
    result = census(APP_ROOT, ENFORCED_SYMBOLS)

    print(
        f"\n[census] files_parsed={result.files_parsed} "
        f"functions_indexed={result.functions_indexed} "
        f"symbols_scanned={result.symbols_scanned} "
        f"orphans={result.orphan_count} {result.orphans}"
    )
    for name, sites in sorted(result.callers.items()):
        print(f"[census]   {name}: {len(sites)} nơi gọi ngoài tệp định nghĩa -> {list(sites)}")

    assert result.symbols_scanned == len(ENFORCED_SYMBOLS), (
        f"symbols_scanned={result.symbols_scanned} nhưng tập cưỡng chế có "
        f"{len(ENFORCED_SYMBOLS)} tên — có hàm chấm bị đổi tên hoặc biến mất"
    )
    assert result.orphans == (), (
        f"{result.orphan_count}/{result.symbols_scanned} hàm chấm KHÔNG có nơi gọi nào "
        f"ngoài tệp định nghĩa: {result.orphans}. Một cái barie chỉ là barie nếu nó "
        f"từng hạ xuống."
    )


def test_boundary_set_is_exactly_the_three_declared_sockets() -> None:
    """Vùng biên phải đứng yên ở đúng ba tên đã khai trong SDD 05 §1.2."""
    assert frozenset(registry.PUBLIC_ENTRYPOINTS) == EXPECTED_BOUNDARY, (
        "registry.PUBLIC_ENTRYPOINTS đã đổi. Mỗi tên ở đây là một hàm CHƯA có nơi gọi "
        "sản phẩm; danh sách này chỉ được co lại khi orchestrator cắm vào, không được "
        "phình ra để miễn trừ một hàm mới."
    )


def test_no_scoring_function_hides_inside_the_boundary_set() -> None:
    """Không ai được miễn trừ một hàm chấm bằng cách khai nó là 'ổ cắm'."""
    overlap = ENFORCED_SYMBOLS & frozenset(registry.PUBLIC_ENTRYPOINTS)
    assert overlap == frozenset(), f"hàm chấm bị đưa vào vùng biên để né phép đếm: {overlap}"


# ───────────────────────── đối chứng dương ─────────────────────────


def test_positive_control_counter_actually_finds_a_planted_orphan(tmp_path: Path) -> None:
    """Đối chứng dương #1: cấy một hàm mồ côi, phép đếm PHẢI bắt được.

    Không có bước này thì kết quả "0 mồ côi" ở trên không phân biệt được với một
    bộ đếm hỏng luôn trả rỗng.
    """
    (tmp_path / "engine.py").write_text(
        "def wired():\n    return 1\n\n\ndef stranded():\n    return 2\n",
        encoding="utf-8",
    )
    (tmp_path / "caller.py").write_text(
        "from engine import wired\n\n\ndef main():\n    return wired()\n",
        encoding="utf-8",
    )

    result = census(tmp_path, frozenset({"wired", "stranded"}))

    assert result.symbols_scanned == 2
    assert result.orphans == ("stranded",)
    assert result.callers["wired"] == ("caller.py",)


def test_positive_control_registry_dict_entry_is_not_counted_as_a_call(tmp_path: Path) -> None:
    """Đối chứng dương #2: có tên trong sổ đăng ký KHÔNG phải có người thi hành.

    Đây là anti-pattern `B2` dựng lại nguyên hình: handler được đăng ký đầy đủ
    vào một bảng, và không dòng nào gọi nó.
    """
    (tmp_path / "engine.py").write_text(
        "def handler():\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "registry_like.py").write_text(
        "from engine import handler\n\nHANDLERS = {'x': handler}\n",
        encoding="utf-8",
    )

    result = census(tmp_path, frozenset({"handler"}))

    assert result.symbols_scanned == 1
    assert result.orphans == ("handler",), (
        "một cái tên nằm trong dict bị đếm thành nơi gọi — phép đếm này sẽ báo xanh "
        "cho đúng hình dạng nó phải bắt"
    )


def test_positive_control_scanner_sees_a_real_edge_in_the_real_tree() -> None:
    """Đối chứng dương #3: bộ quét không mù trên chính cây thật.

    Cạnh `registry.py → check_requirements` là cạnh phải tồn tại. Nếu bộ quét
    không thấy nó thì con số 0 mồ côi ở trên là "quét trượt", không phải "sạch".
    """
    result = census(APP_ROOT, ENFORCED_SYMBOLS)
    assert "gates/registry.py" in result.callers["check_requirements"]
    assert "gates/registry.py" in result.callers["evaluate_stop_gate"]


def test_negative_control_empty_denominator_is_red_not_green(tmp_path: Path) -> None:
    """Đối chứng âm: quét một cây rỗng phải NỔ, không được trả '0 mồ côi'.

    Đây là luật `L11` — "0 lỗi" trơ trọi không phân biệt được với "chưa soi cái
    nào"; và là bẫy đã đo: linter log "0 issues found" khi glob sai và quét 0 tệp.
    """
    (tmp_path / "notes.md").write_text("không có mã nguồn ở đây\n", encoding="utf-8")

    with pytest.raises(EmptyDenominatorError):
        census(tmp_path, ENFORCED_SYMBOLS)


def test_negative_control_missing_symbol_is_red_not_green(tmp_path: Path) -> None:
    """Quét đúng cây nhưng tìm một tên không tồn tại cũng phải NỔ."""
    (tmp_path / "engine.py").write_text("def something():\n    return 1\n", encoding="utf-8")

    with pytest.raises(EmptyDenominatorError):
        census(tmp_path, frozenset({"ten_khong_ton_tai"}))
