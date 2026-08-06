"""Repo mẫu đi kèm, và bảng dữ liệu đã gửi cho mô hình.

Endpoint thứ hai (`/prompt-payload`) là chỗ lỗi chính sách dữ liệu lộ ra. Nó
tồn tại vì một lý do: **thứ đã gửi cho mô hình phải xem lại được.** Nếu không
có màn hình nào cho thấy payload thật, thì câu "chúng tôi không gửi bí mật đi"
là một lời hứa không ai kiểm được — kể cả người viết ra nó.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import needs
from app.policy.data_policy import load_policy
from app.settings import settings

router = APIRouter(prefix="/api", tags=["samples"])


@router.get("/samples")
def samples(principal=Depends(needs("repo:read"))) -> list[dict]:
    """Ba repo mẫu lành mạnh. Không repo nào chứa lỗi — lỗi nằm trong CERTUS."""
    described = {
        "shopcart": "Giỏ hàng: hạng khách, vùng giao, hình thức trả, loại mã giảm",
        "ledger": "Sổ kế toán kép: bút toán, tài khoản, ghi đồng thời",
        "payments": "Cổng thanh toán: có một module đời cũ chưa chuyển API mới",
    }
    out = []
    for path in sorted(settings.targets_dir.iterdir()):
        if not path.is_dir():
            continue
        py = len(list(path.rglob("*.py")))
        tests = len(list(path.rglob("test_*.py")))
        out.append(
            {
                "id": path.name,
                "name": path.name,
                "description": described.get(path.name, ""),
                "files": py,
                "test_files": tests,
            }
        )
    return out


@router.get("/prompt-payload/{run_id}")
def prompt_payload(
    run_id: str, principal=Depends(needs("repo:read"))
) -> dict:
    """Chính xác những gì đã đi vào prompt, và những gì bị giữ lại kèm lý do.

    Trả về CẢ HAI danh sách. Chỉ hiện danh sách đã gửi thì người đọc không có
    cách nào biết bộ lọc có chạy hay không — một bộ lọc hỏng và một bộ lọc
    không tồn tại cho ra cùng một màn hình.
    """
    from app.api.routes.analyze import _RUNS

    resp = _RUNS.get(run_id)
    policy = load_policy()
    sent = list(resp.files_sent_to_model) if resp else []

    held: list[dict] = []
    if resp:
        root = settings.targets_dir / resp.target
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                rel = str(path.relative_to(root))
                if rel in sent:
                    continue
                decision = policy.decide(rel)
                held.append({"path": rel, "reason": decision.reason})

    return {
        "run_id": run_id,
        "files_sent": sent,
        "files_held": held,
        "blocklist": policy.blocklist,
        "note": (
            "Danh sách này là payload THẬT đã gửi cho mô hình. "
            "Nếu có tệp bạn không mong đợi ở đây, đó là một phát hiện."
        ),
    }
