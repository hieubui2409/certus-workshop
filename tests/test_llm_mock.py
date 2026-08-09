"""Kiểm tầng gọi model ở chế độ mock.

Khẳng định trung tâm: cassette miss PHẢI nổ. Một cassette miss im lặng đọc y hệt
một lời gọi LLM trả về rỗng, và hai thứ đó cần hai cách xử lý khác nhau.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agent.llm import LLMClient, cassette_key, cassette_slug  # noqa: E402
from app.contracts.errors import CassetteMissError  # noqa: E402
from app.settings import Settings  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SYSTEM = "Bạn là tầng diễn đạt của CERTUS."
MESSAGES = [{"role": "user", "content": "Bộ kiểm phủ tới đâu?"}]
TOOLS = [
    {
        "name": "count_grid_cells",
        "description": "Đếm ô của lưới t-wise.",
        "input_schema": {"type": "object", "properties": {}},
    }
]


def _settings(tmp_path: Path, mode: str = "mock") -> Settings:
    return Settings(llm_mode=mode, cassette_dir=tmp_path, model="claude-opus-5")


def _write_cassette(
    directory: Path, *, model: str, system: str, messages: list, tools: list | None, chunks: list[str]
) -> Path:
    key = cassette_key(model=model, system=system, messages=messages, tools=tools)
    path = directory / cassette_slug(key, "test")
    path.write_text(
        json.dumps(
            {
                "key": key,
                "model": model,
                "request": {"system": system, "messages": messages, "tools": tools or []},
                "response": {
                    "text": "".join(chunks),
                    "chunks": chunks,
                    "tool_uses": [],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


# ─────────────────────────── khoá cassette ───────────────────────────


def test_key_is_stable_across_calls():
    first = cassette_key(model="claude-opus-5", system=SYSTEM, messages=MESSAGES, tools=TOOLS)
    second = cassette_key(model="claude-opus-5", system=SYSTEM, messages=MESSAGES, tools=TOOLS)
    assert first == second
    assert len(first) == 64


def test_key_changes_with_each_of_the_four_components():
    base = cassette_key(model="claude-opus-5", system=SYSTEM, messages=MESSAGES, tools=TOOLS)

    other_model = cassette_key(model="claude-opus-4-8", system=SYSTEM, messages=MESSAGES, tools=TOOLS)
    other_system = cassette_key(model="claude-opus-5", system=SYSTEM + "!", messages=MESSAGES, tools=TOOLS)
    other_messages = cassette_key(
        model="claude-opus-5",
        system=SYSTEM,
        messages=[{"role": "user", "content": "câu khác"}],
        tools=TOOLS,
    )
    # Tool set khác nghĩa là model có bộ hành động khác, nên là một lời gọi khác.
    no_tools = cassette_key(model="claude-opus-5", system=SYSTEM, messages=MESSAGES, tools=None)

    assert len({base, other_model, other_system, other_messages, no_tools}) == 5


def test_key_ignores_dict_ordering():
    a = cassette_key(model="m", system="s", messages=[{"role": "user", "content": "x"}], tools=None)
    b = cassette_key(model="m", system="s", messages=[{"content": "x", "role": "user"}], tools=None)
    assert a == b


# ─────────────────────────── chế độ mock ───────────────────────────


def test_mock_replays_recorded_response(tmp_path):
    chunks = ["Ba tầng ", "mẫu số ", "lệch nhau."]
    _write_cassette(
        tmp_path,
        model="claude-opus-5",
        system=SYSTEM,
        messages=MESSAGES,
        tools=TOOLS,
        chunks=chunks,
    )
    client = LLMClient(_settings(tmp_path))

    response = asyncio.run(client.complete(system=SYSTEM, messages=MESSAGES, tools=TOOLS))

    assert response.text == "Ba tầng mẫu số lệch nhau."
    assert response.from_cassette is True
    assert response.stop_reason == "end_turn"
    assert response.usage["output_tokens"] == 5


def test_mock_streams_chunk_by_chunk(tmp_path):
    chunks = ["Coverage ", "94%", " · Wilson95"]
    _write_cassette(
        tmp_path,
        model="claude-opus-5",
        system=SYSTEM,
        messages=MESSAGES,
        tools=None,
        chunks=chunks,
    )
    client = LLMClient(_settings(tmp_path))

    async def drain() -> list[str]:
        return [chunk async for chunk in client.stream(system=SYSTEM, messages=MESSAGES)]

    received = asyncio.run(drain())

    assert received == chunks
    assert "".join(received) == "Coverage 94% · Wilson95"


def test_cassette_miss_raises_instead_of_returning_empty(tmp_path):
    _write_cassette(
        tmp_path,
        model="claude-opus-5",
        system=SYSTEM,
        messages=MESSAGES,
        tools=None,
        chunks=["đã ghi"],
    )
    client = LLMClient(_settings(tmp_path))

    with pytest.raises(CassetteMissError) as excinfo:
        asyncio.run(
            client.complete(
                system=SYSTEM,
                messages=[{"role": "user", "content": "câu chưa từng ghi"}],
            )
        )

    message = str(excinfo.value)
    assert "record" in message  # phải chỉ ra cách sinh cassette
    assert str(tmp_path) in message


def test_empty_cassette_dir_still_raises_not_returns_empty_text(tmp_path):
    client = LLMClient(_settings(tmp_path / "khong-ton-tai"))
    with pytest.raises(CassetteMissError):
        asyncio.run(client.complete(system=SYSTEM, messages=MESSAGES))


# ─────────────────────────── cassette đi kèm repo ───────────────────────────


def test_shipped_cassettes_are_loadable_and_keyed_by_their_own_request():
    """Mỗi cassette trong repo phải khớp với chính request nó ghi lại.

    Nếu khoá lệch khỏi phần `request`, cassette đó không bao giờ được dùng tới và
    không có gì báo — nó chỉ đơn giản là chết trong thư mục.
    """
    directory = REPO_ROOT / "fixtures" / "cassettes"
    files = sorted(directory.glob("*.json"))
    assert files, "repo phải đi kèm ít nhất một cassette"

    for path in files:
        record = json.loads(path.read_text(encoding="utf-8"))
        request = record["request"]
        recomputed = cassette_key(
            model=record["model"],
            system=request["system"],
            messages=request["messages"],
            tools=request.get("tools"),
        )
        assert recomputed == record["key"], f"{path.name}: khoá lệch khỏi request"
        assert "".join(record["response"]["chunks"]) == record["response"]["text"]


def test_cassette_analyze_deu_doc_ra_duoc_claim():
    """Cassette khớp khoá vẫn có thể VÔ DỤNG — phải đọc ra được claim.

    Ba tầng hỏng khác nhau, và chỉ tầng đầu được test ở trên bắt:
      1. khoá lệch  ⇒ không bao giờ replay tới (test trước lo)
      2. khoá đúng, `text` không parse được JSON  ⇒ replay xong, pipeline nuốt
         thành cảnh báo "không đọc được câu trả lời", giao diện trống
      3. khoá đúng, JSON hợp lệ, `claims` RỖNG  ⇒ trông y hệt một lượt chạy
         thành công mà mô hình không có gì để nói

    Hai tầng sau đọc giống nhau trên màn hình: một câu trả lời trống. Đó là lý
    do phải đo tận nội dung, không dừng ở "file tồn tại và khoá khớp".
    """
    directory = REPO_ROOT / "fixtures" / "cassettes"
    hong: list[str] = []
    files = sorted(directory.glob("analyze__*.json"))
    assert files, "phải có cassette cho bước diễn giải"

    for path in files:
        text = json.loads(path.read_text(encoding="utf-8"))["response"]["text"]
        try:
            payload = json.loads(text[text.find("{") : text.rfind("}") + 1])
        except (ValueError, json.JSONDecodeError) as exc:
            hong.append(f"{path.name}: không parse được JSON ({type(exc).__name__})")
            continue
        if not payload.get("claims"):
            hong.append(f"{path.name}: parse được nhưng 0 claim")

    assert not hong, "cassette replay ra câu trả lời rỗng:\n  " + "\n  ".join(hong)


# ── danh sách câu hỏi của UI và của script thu phải TRÙNG ────────────────────
#
# `App.tsx` khởi tạo `question` bằng một câu mặc định, và ba nút gợi ý ở
# `ChatPanel.SUGGESTIONS` gọi `onQuestionChange` — CÙNG một state mà nút "Chạy
# phân tích" đọc. Nên mỗi câu bấm được là một (repo, câu hỏi) chạy analyze thật,
# và mỗi tổ hợp đó cần một cassette.
#
# Đo được lúc viết test này: 9/9 tổ hợp có cassette cho ba câu trong
# `record_cassettes.QUESTIONS`, 0/9 cho ba câu gợi ý — trên CẢ cây gốc lẫn cây
# đã vá. Hai danh sách trôi khỏi nhau vì không có gì buộc chúng lại, và hậu quả
# chỉ hiện ra khi có người bấm nút: giữa buổi, trên máy 1000 sinh viên.
#
# Test đọc thẳng từ .tsx thay vì chép lại chuỗi sang Python: một bản chép là
# danh sách THỨ BA, và nó sẽ trôi y hệt hai cái kia.

import re as _re  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_REPO = _Path(__file__).resolve().parent.parent
_CHAT_PANEL = _REPO / "src" / "frontend" / "src" / "components" / "ChatPanel.tsx"
_APP_TSX = _REPO / "src" / "frontend" / "src" / "App.tsx"
_RECORDER = _REPO / "scripts" / "record_cassettes.py"


def _ui_questions() -> set[str]:
    """Mọi câu hỏi người dùng bấm được — mặc định + ba nút gợi ý."""
    chat = _CHAT_PANEL.read_text(encoding="utf-8")
    block = _re.search(r"const SUGGESTIONS = \[(.*?)\]", chat, _re.S)
    assert block, "không thấy SUGGESTIONS trong ChatPanel.tsx — test này đã lạc chỗ"
    found = set(_re.findall(r"'([^']+)'", block.group(1)))

    app = _APP_TSX.read_text(encoding="utf-8")
    default = _re.search(r"useState\('([^']*phủ tới đâu[^']*)'\)", app)
    assert default, "không thấy câu hỏi mặc định trong App.tsx"
    found.add(default.group(1))
    return found


def _recorder_questions() -> set[str]:
    src = _RECORDER.read_text(encoding="utf-8")
    block = _re.search(r"QUESTIONS = \[(.*?)^\]", src, _re.S | _re.M)
    assert block, "không thấy QUESTIONS trong record_cassettes.py"
    return set(_re.findall(r'"([^"]+)"', block.group(1)))


@pytest.mark.skipif(
    not _RECORDER.is_file(),
    reason=(
        "bản phát cho sinh viên không mang `scripts/` — không có danh sách thu "
        "để so. Test này canh sự đồng bộ giữa hai danh sách của repo INSTRUCTOR; "
        "ở bản phát thì cassette đã thu sẵn và đi kèm, không ai thu lại."
    ),
)
def test_cassette_phu_het_cau_hoi_ui() -> None:
    """Câu nào bấm được trên giao diện thì phải có trong danh sách thu cassette.

    Thiếu một câu ở đây KHÔNG làm sập gì lúc chạy test — nó nổ lúc có người bấm
    nút ở chế độ mock, và nổ thành một câu trả lời rỗng kèm cảnh báo, tức trông
    y như "mô hình không có gì để nói".
    """
    thieu = _ui_questions() - _recorder_questions()
    assert not thieu, (
        "câu hỏi bấm được trên UI mà chưa có trong record_cassettes.QUESTIONS "
        f"⇒ mock sẽ báo 'chưa có cassette': {sorted(thieu)}"
    )


def test_cassette_phu_cau_hoi_ui_khong_bi_skip_o_repo_instructor() -> None:
    """Chốt chống `skipif` nuốt mất chính test nó bảo vệ.

    `test_cassette_phu_het_cau_hoi_ui` bị skip ở bản phát cho sinh viên vì bản
    đó không mang `scripts/`. Hợp lý — nhưng một điều kiện skip là chỗ rất dễ
    biến thành "xanh ở mọi nơi vì không chạy ở đâu cả": đổi tên file, dời thư
    mục, hay một lần dọn dẹp là nó im lặng tắt luôn ở repo instructor, và không
    có gì kêu.

    Ở repo INSTRUCTOR (có `scripts/`, có `evals/golden/`) thì nó BẮT BUỘC chạy.

    Mốc nhận dạng là `evals/golden/cases.json`, KHÔNG phải `patches/`: bản phát
    SAU-LỚP (`build_student_repo.py --post-workshop`) có mang theo `patches/`
    làm tài liệu đối chiếu, nên `patches/` không còn phân biệt được hai cây.
    `evals/golden/` thì không bao giờ vào bản phát ở bất kỳ chế độ nào — nó
    chính là baseline chấm điểm.
    """
    la_instructor = (REPO_ROOT / "evals" / "golden" / "cases.json").is_file()
    if not la_instructor:
        pytest.skip("bản phát cho sinh viên — không có evals/golden/, không cần chốt này")
    assert _RECORDER.is_file(), (
        f"repo instructor phải có {_RECORDER.relative_to(REPO_ROOT)} — thiếu nó thì "
        "test đồng bộ hai danh sách câu hỏi bị skip im lặng, và cassette lại trôi"
    )
