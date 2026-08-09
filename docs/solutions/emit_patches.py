"""Sinh ./patches/** từ SSOT là docs/solutions/apply_fixes.py.

Mỗi Fix → một unified diff (git apply được) của ĐÚNG một thay đổi trên code lỗi
hiện tại, gom theo lỗ hổng vào patches/<NN-concept>/<id>.patch. Cộng thêm vài
"surface fix" cho bề mặt chat mới (chat.md) — cùng khái niệm 01/06/07 nhưng KHÔNG
nằm trong golden 12, đánh dấu rõ để không đội mẫu số.

Chạy:

    python docs/solutions/emit_patches.py            # sinh lại toàn bộ patches/
    python docs/solutions/emit_patches.py --check     # chỉ báo fix nào không diff được

Luật kế thừa từ apply_fixes: một fix không tìm thấy chỗ sửa thì NỔ, không âm thầm bỏ.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_fixes as af  # noqa: E402

ROOT = af.ROOT
BE = af.BE
PATCHES = ROOT / "patches"
CHAT = BE / "agent" / "prompts" / "chat.md"

#: id → thư mục lỗ hổng. Giữ đúng 11 khái niệm gốc; các surface-fix trỏ về khái
#: niệm mẹ của chúng.
BUG_DIR = {
    "01": "01-anti-confabulation",
    "07": "07-deterministic", "07b": "07-deterministic",
    "02": "02-anti-hallucination", "T-retrieval": "02-anti-hallucination",
    "03a": "03-injection", "03a-2": "03-injection", "03a-3": "03-injection",
    "03b": "03-injection", "03b-2": "03-injection",
    "T-runner": "03-injection", "T-project": "03-injection",
    "04": "04-coverage-meaning",
    "05": "05-confidence-interval", "05-2": "05-confidence-interval",
    "06": "06-evidence-probe-first", "06b": "06-evidence-probe-first",
    "T-claims": "06-evidence-probe-first",
    "08": "08-data-policy", "08b": "08-data-policy", "08c": "08-data-policy",
    "T-redaction": "08-data-policy",
    "09": "09-authorization",
    "10": "10-personalization", "10b": "10-personalization",
    "10c": "10-personalization", "10d": "10-personalization",
    "T-persona": "10-personalization",
    "11": "11-observability", "11-2": "11-observability",
    "11-2b": "11-observability", "11-3": "11-observability",
    "T-tracing": "11-observability",
    # ── surface fix: bề mặt chat (KHÔNG thuộc golden 12) ──
    "chat-01": "01-anti-confabulation",
    "chat-07": "07-deterministic",
    "chat-06": "06-evidence-probe-first",
}

#: Các id là surface-fix (ngoài golden 12) — dùng để ghi chú trong README + tên tệp.
SURFACE_IDS = {"chat-01", "chat-07", "chat-06"}


@dataclass
class SurfaceFix:
    """Fix literal cho một bề mặt mới ngoài golden 12 (cùng khái niệm mẹ)."""

    id: str
    concept: str
    file: Path
    old: str
    new: str
    why: str
    transform: object = None
    all_occurrences: bool = False


SURFACE_FIXES: list[SurfaceFix] = [
    SurfaceFix(
        id="chat-01",
        concept="Anti-confabulation (bề mặt chat)",
        file=CHAT,
        old=(
            "Dựa trên hiểu biết của bạn về kiểm thử VÀ KINH\n"
            "NGHIỆM CỦA BẠN, hãy trả lời người dùng một cách HỮU ÍCH NHẤT CÓ THỂ về độ phủ, phần chưa\n"
            "kiểm chứng, và độ tin của các con số cho repo đã nạp."
        ),
        new=(
            "Chỉ được nói về những gì đo được từ tool và tài liệu đã nạp. KHÔNG bổ sung\n"
            "từ trí nhớ của bạn. Nếu chưa có số liệu cho một câu hỏi, hãy gọi tool để lấy;\n"
            "nếu không lấy được, nói thẳng là chưa có dữ liệu — đó là câu trả lời ĐÚNG, không\n"
            "phải một thất bại."
        ),
        why=(
            "Bản chat lặp lại đúng bẫy của analyze.md: đặt 'kinh nghiệm của bạn' ngang KB và "
            "ép 'hữu ích nhất có thể' nên khi thiếu dữ liệu, mô hình bịa cho hữu ích. Cùng "
            "khái niệm 01, khác bề mặt."
        ),
    ),
    SurfaceFix(
        id="chat-07",
        concept="Deterministic vs heuristic (bề mặt chat)",
        file=CHAT,
        old=(
            "Hãy ưu tiên dùng tool khi thuận tiện; nếu tool không cần thiết hoặc bạn\n"
            "đã nắm được con số, cứ trả lời thẳng cho nhanh — đừng làm gián đoạn người dùng."
        ),
        new=(
            "MỌI con số PHẢI đến từ tool. Không được tự tính hay nhớ ra một con số rồi đọc\n"
            "như thật; nếu tool trả lỗi thì DỪNG và nói tool lỗi, không bịa số thay thế."
        ),
        why=(
            "'Đã nắm được con số thì trả lời thẳng' mở đúng lối cho mô hình đọc số tự bịa "
            "mà không tool nào đứng sau — cùng bẫy heuristic của 07b trên bề mặt chat."
        ),
    ),
    SurfaceFix(
        id="chat-06",
        concept="Evidence-based (bề mặt chat)",
        file=CHAT,
        old=(
            "- Gán cho mỗi phát biểu một nhãn phù hợp trong hệ bốn nhãn: `OBSERVED` (đã thấy trực\n"
            "  tiếp), `DERIVED` (suy ra), `PRIOR` (kiến thức của bạn), `ASSUMED` (đang giả định)."
        ),
        new=(
            "- Chỉ được dán `OBSERVED` cho con số DO CHÍNH TOOL trả về trong lượt này. Con số\n"
            "  không có tool đứng sau thì cao nhất chỉ là `ASSUMED`. `DERIVED` = suy ra từ số của\n"
            "  tool; `PRIOR` = kiến thức chung của bạn."
        ),
        why=(
            "Prompt cũ để mô hình tự do dán OBSERVED không cần tool — đúng bản chất bug 06 "
            "('chỉ tool mới phong được OBSERVED') trên bề mặt chat."
        ),
    ),
]


def _apply_one(fx: object, before: str) -> str | None:
    """Văn bản SAU khi áp đúng một fix lên `before`, hoặc None nếu không thấy chỗ sửa."""
    transform = getattr(fx, "transform", None)
    if transform is not None:
        return transform(before)
    if fx.old not in before:
        return None
    count = -1 if getattr(fx, "all_occurrences", False) else 1
    return before.replace(fx.old, fx.new, count)


def _diff_text(rel: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            n=3,
        )
    )


def _diff(fx: object, overlay: dict[str, str] | None = None) -> str:
    """Diff tích luỹ: `before` lấy từ overlay (trạng thái sau các patch trước) nếu có,
    nếu không thì đọc thẳng file. Cập nhật overlay để patch sau chồng đúng."""
    rel = fx.file.relative_to(ROOT).as_posix()
    before = overlay.get(rel) if overlay is not None else None
    if before is None:
        before = fx.file.read_text(encoding="utf-8")
    after = _apply_one(fx, before)
    if after is None:
        raise af.PatchMiss(f"[{fx.id}] không diff được — không thấy chỗ sửa trong {rel}")
    if overlay is not None:
        overlay[rel] = after
    return _diff_text(rel, before, after)


def _all_fixes() -> list[object]:
    return [*af.FIXES, *SURFACE_FIXES]


def check() -> int:
    bad = 0
    overlay: dict[str, str] = {}
    for fx in _all_fixes():
        try:
            _diff(fx, overlay)
            print(f"[{fx.id}] OK — diff được")
        except af.PatchMiss as exc:
            bad += 1
            print(f"[{fx.id}] MISS — {exc}")
    return 1 if bad else 0


def emit() -> None:
    if PATCHES.exists():
        for p in sorted(PATCHES.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink()
        for p in sorted(PATCHES.rglob("*"), reverse=True):
            if p.is_dir():
                p.rmdir()
    PATCHES.mkdir(exist_ok=True)

    index: dict[str, list[object]] = {}
    order: list[str] = []  # thứ tự áp (tích luỹ) — apply-all.sh phải theo đúng đây
    overlay: dict[str, str] = {}
    for fx in _all_fixes():
        bug_dir = BUG_DIR[fx.id]
        header = (
            f"# patch {fx.id} — {fx.concept}\n"
            f"# lỗ hổng: {bug_dir}"
            + ("  (SURFACE — ngoài golden 12)" if fx.id in SURFACE_IDS else "")
            + "\n"
            f"# vì sao: {fx.why}\n"
        )
        body = _diff(fx, overlay)  # tích luỹ: patch sau chồng lên trạng thái sau patch trước
        out_dir = PATCHES / bug_dir
        out_dir.mkdir(exist_ok=True)
        (out_dir / f"{fx.id}.patch").write_text(header + body, encoding="utf-8")
        index.setdefault(bug_dir, []).append(fx)
        order.append(f"{bug_dir}/{fx.id}.patch")

    _write_apply_all(order)
    _write_readme(index)


def _write_apply_all(order: list[str]) -> None:
    """Áp mọi patch theo ĐÚNG thứ tự sinh (tích luỹ). Glob `**/*.patch` sort theo path
    KHÔNG khớp thứ tự này, nên phải liệt kê tường minh."""
    lines = [
        "#!/usr/bin/env bash",
        "# Áp TẤT CẢ bản vá theo đúng thứ tự tích luỹ. Sinh tự động — đừng sửa tay.",
        "# Dùng: bash patches/apply-all.sh   (chạy từ gốc repo)",
        "set -euo pipefail",
        'cd "$(git rev-parse --show-toplevel)"',
        "",
    ]
    lines += [f'git apply "patches/{rel}"' for rel in order]
    lines.append('echo "Đã áp %d bản vá."' % len(order))
    path = PATCHES / "apply-all.sh"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)


def _write_readme(index: dict[str, list[object]]) -> None:
    lines = [
        "# patches/ — lời giải cho các lỗ hổng cài cắm",
        "",
        "Mỗi `.patch` là một unified diff **git apply được**, sinh tự động từ SSOT",
        "`docs/solutions/apply_fixes.py` bằng `docs/solutions/emit_patches.py`.",
        "Đừng sửa tay — sửa `apply_fixes.py` rồi chạy lại generator.",
        "",
        "Các patch là **tích luỹ theo thứ tự sinh**: nhiều patch cùng một tệp (vd",
        "`analyze.md` mang cả 01 lẫn 07) neo dòng theo trạng thái sau các patch trước.",
        "Vì thế áp TẤT CẢ phải theo đúng thứ tự đó — dùng `apply-all.sh`, đừng",
        "`git apply patches/**/*.patch` (glob sort theo path, sai thứ tự).",
        "",
        "```bash",
        "python docs/solutions/emit_patches.py    # sinh lại",
        "bash patches/apply-all.sh                 # áp tất cả (đúng thứ tự tích luỹ)",
        "python docs/solutions/apply_fixes.py      # hoặc áp thẳng từ SSOT (12 bug gốc)",
        "```",
        "",
        "Đọc/nghiên cứu một bug: mở tệp `.patch` tương ứng — nội dung diff tự đủ nghĩa.",
        "",
        "11 lỗ hổng gốc = golden 12 (khái niệm 01–11; bug 03 gồm 2 nhánh prompt+exec).",
        "Các bản `chat-*` là **surface** trên bề mặt chat mới — cùng khái niệm mẹ,",
        "KHÔNG tính vào mẫu số golden 12.",
        "",
        "| lỗ hổng | các bản vá | tệp chạm |",
        "|---|---|---|",
    ]
    for bug_dir in sorted(index):
        fixes = index[bug_dir]
        ids = ", ".join(
            (f"`{fx.id}`*" if fx.id in SURFACE_IDS else f"`{fx.id}`") for fx in fixes
        )
        files = sorted({fx.file.relative_to(ROOT).as_posix() for fx in fixes})
        lines.append(f"| {bug_dir} | {ids} | {'<br>'.join(files)} |")
    lines += [
        "",
        "`*` = surface-fix (ngoài golden 12).",
        "",
        "## Ghi chú tái hiện (từ audit soi masking 2026-08-06)",
        "",
        "- Bug **06** (chỉ tool mới phong OBSERVED) và **07** (tên tool lệch)",
        "  chỉ tái hiện qua flow **analyze** single-shot, KHÔNG qua **chat** —",
        "  không phải bị vá, mà do hai prompt khác nhau cho hai flow khác nhau.",
        "- Bề mặt **chat** tái hiện bug **01** (confabulation) tương đương analyze.",
        "  Các bản `chat-*` ở đây vá cả 01/06/07 cho bề mặt chat.",
    ]
    (PATCHES / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sinh patches/ từ apply_fixes.py")
    ap.add_argument("--check", action="store_true", help="chỉ kiểm tra, không ghi")
    args = ap.parse_args()
    if args.check:
        return check()
    emit()
    n = len(_all_fixes())
    print(f"Đã sinh {n} bản vá vào {PATCHES.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
