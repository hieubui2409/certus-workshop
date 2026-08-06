"""`python -m certus` — dùng CERTUS mà không cần mở trình duyệt.

Có mặt vì bước đầu tiên của sinh viên là `doctor`, và bắt họ dựng cả frontend
chỉ để biết mình thiếu `scipy` là cách chắc chắn nhất làm họ bỏ cuộc ở phút 20.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cmd_doctor(_args) -> int:
    from app.api.routes.health import doctor

    report = doctor()
    print(f"{'mục':<22} {'kết quả':<8} chi tiết")
    print("-" * 78)
    for c in report["checks"]:
        print(f"{c['name']:<22} {'OK' if c['ok'] else 'THIẾU':<8} {c['detail']}")
    print(f"\n{report['denominator'] - len(report['failed'])}/{report['denominator']} mục đạt")
    if report["failed"]:
        print("thiếu:", ", ".join(report["failed"]))
        print("\nDán nguyên văn phần trên vào Form 2 câu A5.")
    return 0 if report["ok"] else 1


def cmd_analyze(args) -> int:
    from app.api.schemas import AnalyzeRequest
    from app.orchestrator.pipeline import analyze

    from app.contracts.errors import CertusError

    target = Path(args.path).resolve()
    req = AnalyzeRequest(target=target.name, question=args.question)
    try:
        result = asyncio.run(analyze(req))
    except CertusError as exc:
        # Từ chối có lý do là một KẾT QUẢ, không phải một sự cố. Đổ traceback ra
        # đây biến một phán quyết đọc được thành một thứ trông như sản phẩm hỏng,
        # và người dùng sẽ thử lại thay vì đọc.
        print(f"\n  CERTUS · {target.name}   TỪ CHỐI PHÂN TÍCH")
        print("  " + "─" * 62)
        print(f"  {exc}")
        print("  " + "─" * 62)
        print("  Đây là fail-closed, không phải lỗi: không có mẫu số thì không có")
        print("  tỉ lệ nào đáng tin ở phía sau.\n")
        return 2
    resp = result.response
    cov = resp.coverage

    if args.json:
        print(resp.model_dump_json(indent=2))
        return 0

    print(f"\n  CERTUS · {resp.target}   (trace {resp.trace_id[:12]})")
    print("  " + "─" * 62)
    for r in (cov.line, cov.mutation, cov.grid):
        if r is None:
            continue
        iv = r.interval
        flags = f"  [{', '.join(r.flags)}]" if r.flags else ""
        print(
            f"  {r.name:<18} {r.k:>4}/{r.n:<5} = {r.point*100:5.1f}%"
            f"   {iv.method} {iv.conf*100:.0f}%: [{iv.lower*100:.1f}%, {iv.upper*100:.1f}%]{flags}"
        )
    print("  " + "─" * 62)
    print(f"  ô: {cov.cells_total} tổng · {cov.cells_na} N/A · {cov.cells_unknown} chưa ai canh")
    print(f"  zone: {len(cov.per_zone)}")
    for w in resp.warnings:
        print(f"  ! {w}")
    print()
    return 0


def cmd_evals(args) -> int:
    import subprocess

    root = Path(__file__).resolve().parents[3]
    return subprocess.call([sys.executable, str(root / "evals" / "run.py")])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="certus", description="CERTUS — chúng tôi không đoán.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="kiểm tra môi trường, nói rõ thiếu gì")
    d.set_defaults(fn=cmd_doctor)

    a = sub.add_parser("analyze", help="phân tích một repo")
    a.add_argument("path")
    a.add_argument("--question", default="Bộ kiểm thử của repo này phủ tới đâu?")
    a.add_argument("--json", action="store_true", help="in JSON thô")
    a.set_defaults(fn=cmd_analyze)

    e = sub.add_parser("evals", help="chạy golden eval")
    e.set_defaults(fn=cmd_evals)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
