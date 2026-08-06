"""Lớp gọi model. Ba chế độ, một hợp đồng.

Vì sao có cassette: ràng buộc vận hành là 1000 sinh viên chạy đồng thời, nên
`mock` phải là mặc định. Nhưng cassette được thu từ `LLM_MODE=record` trên model
thật, nên triệu chứng ở `mock` LÀ triệu chứng ở `live` — không phải mô phỏng lại
bằng tay.

Vì sao `complete()` gọi lại `stream()` thay vì có đường code riêng: hai đường code
cho cùng một việc là cách chắc chắn nhất để hai chế độ trôi khỏi nhau mà không ai
thấy, và lúc đó cassette hết còn là bằng chứng về hành vi thật.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.contracts.errors import CassetteMissError, CertusError, ConfigError
from app.settings import Settings, settings as default_settings

__all__ = [
    "LLMResponse",
    "ToolLoopResult",
    "ToolLoopExhausted",
    "LLMClient",
    "cassette_key",
    "cassette_slug",
]


# ─────────────────────────── khoá cassette ───────────────────────────


def _canonical_request(
    *,
    model: str,
    system: str,
    messages: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]] | None,
) -> str:
    """Chuẩn hoá request thành MỘT chuỗi, để hash ra khoá cassette.

    `tools` nằm trong khoá vì cùng một prompt với hai tool set khác nhau là hai
    lời gọi khác nhau: model chọn hành động dựa trên tool đang có. Bỏ `tools` ra
    khỏi khoá sẽ khiến cassette báo hit cho một request mà nó chưa từng thấy.
    """
    payload = {
        "model": model,
        "system": system,
        "messages": list(messages),
        "tools": list(tools or []),
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def cassette_key(
    *,
    model: str,
    system: str,
    messages: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """sha256(model + system + messages + tools) — hợp đồng ở system-design §9."""
    canonical = _canonical_request(model=model, system=system, messages=messages, tools=tools)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def cassette_slug(key: str, hint: str | None = None) -> str:
    """Tên file cassette: có phần đọc được cho người, có phần khoá cho máy."""
    short = key[:12]
    if not hint:
        return f"{short}.json"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in hint).strip("_").lower()
    return f"{safe}__{short}.json"


# ─────────────────────────── kiểu trả về ───────────────────────────


@dataclass(frozen=True)
class LLMResponse:
    """Một lượt trả lời của model.

    `from_cassette` có mặt vì trace viewer phải phân biệt được "model nói thế"
    với "bản ghi nói thế". Gộp hai thứ đó là mất khả năng debug đúng chỗ đắt nhất.
    """

    text: str
    tool_uses: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str | None = None
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    from_cassette: bool = False
    chunks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolLoopResult:
    """Kết quả một lượt tool-loop nhiều vòng (tầng chat).

    `tool_calls` giữ đúng thứ tự model đã gọi (name/input/output) — UI dựa vào đây để
    hiện tool chạy LIVE, và để phơi bug "claim OBSERVED mà KHÔNG có tool call nào".
    """

    final: LLMResponse
    messages: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 0


class ToolLoopExhausted(CertusError):
    """Model vẫn đòi gọi tool sau `max_rounds` vòng.

    Dừng trung thực thay vì lặp vô hạn: một tool-loop không hội tụ là một lỗi cần
    đọc ra, không phải thứ nuốt im lặng bằng cách trả về câu trả lời dở dang.
    """

    def __init__(self, rounds: int) -> None:
        self.rounds = rounds
        super().__init__(
            f"tool-loop chưa dừng sau {rounds} vòng — model vẫn ở stop_reason=tool_use"
        )


# ─────────────────────────── client ───────────────────────────


class LLMClient:
    """Ba chế độ theo `settings.llm_mode`."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self._cassettes: dict[str, dict[str, Any]] | None = None
        self._anthropic: Any = None
        self._last_response: LLMResponse | None = None

    # --- cassette store -------------------------------------------------

    @property
    def cassette_dir(self) -> Path:
        return Path(self.settings.cassette_dir)

    def _index(self) -> dict[str, dict[str, Any]]:
        if self._cassettes is None:
            self._cassettes = self._load_cassettes()
        return self._cassettes

    def reload_cassettes(self) -> None:
        """Buộc đọc lại đĩa. Dùng sau khi `record` vừa ghi thêm bản ghi."""
        self._cassettes = None

    def _load_cassettes(self) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        directory = self.cassette_dir
        if not directory.is_dir():
            return index
        for path in sorted(directory.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            key = raw.get("key")
            if not key:
                # Cassette không có khoá thì không tra cứu được. Nêu đích danh
                # file thay vì bỏ qua im lặng.
                raise ConfigError("cassette.key", f"{path} thiếu trường 'key'")
            raw["_path"] = str(path)
            index[key] = raw
        return index

    # --- API chính ------------------------------------------------------

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] | None = None,
        max_tokens: int | None = None,
        cassette_hint: str | None = None,
    ) -> LLMResponse:
        """Gọi model và gom toàn bộ câu trả lời."""
        self._last_response = None
        async for _chunk in self.stream(
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            cassette_hint=cassette_hint,
        ):
            pass
        response = self._last_response
        if response is None:  # pragma: no cover - stream luôn set trước khi kết thúc
            raise RuntimeError("stream() kết thúc mà không sinh LLMResponse")
        return response

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] | None = None,
        max_tokens: int | None = None,
        cassette_hint: str | None = None,
    ) -> AsyncIterator[str]:
        """Phát ra từng mẩu chữ. API dùng SSE nên đây là dạng gốc, không phải tuỳ chọn."""
        mode = self.settings.llm_mode
        model = self.settings.model
        key = cassette_key(model=model, system=system, messages=messages, tools=tools)

        if mode == "mock":
            record = self._index().get(key)
            if record is None:
                raise CassetteMissError(self._miss_message(key, model, system))
            response = _response_from_record(record, model=model)
            self._last_response = response
            for chunk in response.chunks:
                yield chunk
            return

        chunks: list[str] = []
        final: Any = None
        async with self._stream_live(
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens or self.settings.max_tokens,
        ) as stream:
            async for text in stream.text_stream:
                chunks.append(text)
                yield text
            final = await stream.get_final_message()

        response = _response_from_message(final, chunks=chunks)
        self._last_response = response

        if mode == "record":
            self._write_cassette(
                key=key,
                model=model,
                system=system,
                messages=messages,
                tools=tools,
                response=response,
                hint=cassette_hint,
            )
            self.reload_cassettes()

    # --- tool-loop (tầng chat) ------------------------------------------

    async def complete_with_tools(
        self,
        *,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        registry: Any,
        max_rounds: int = 6,
        cassette_hint: str | None = "chat",
    ) -> "ToolLoopResult":
        """Vòng lặp tool-use: gọi model, thực thi tool nó đòi, gọi lại tới khi end_turn.

        Mỗi vòng là một `complete()` riêng — một cassette-key riêng theo `messages` lớn
        dần. Chuỗi tất định khi replay vì (1) tool chạy trên artifact cố định, (2)
        tool_result serialize canonical, (3) assistant turn dựng lại từ resp round-trip
        byte y hệt. Xem system-architecture §7.
        """
        convo: list[dict[str, Any]] = [dict(m) for m in messages]
        tools = registry.anthropic_schemas()
        tool_calls: list[dict[str, Any]] = []

        for round_no in range(1, max_rounds + 1):
            resp = await self.complete(
                system=system, messages=convo, tools=tools, cassette_hint=cassette_hint
            )
            if resp.stop_reason != "tool_use":
                return ToolLoopResult(
                    final=resp, messages=convo, tool_calls=tool_calls, rounds=round_no
                )

            # Dựng lại lượt assistant từ resp (KHÔNG cần raw block): text trước, rồi các
            # khối tool_use. Phải khớp byte với lúc thu để key vòng sau trúng cassette.
            assistant_content: list[dict[str, Any]] = []
            if resp.text:
                assistant_content.append({"type": "text", "text": resp.text})
            for tu in resp.tool_uses:
                assistant_content.append(
                    {"type": "tool_use", "id": tu["id"], "name": tu["name"], "input": tu["input"]}
                )
            convo.append({"role": "assistant", "content": assistant_content})

            # Thực thi tool THẬT (tất định) và nối tool_result canonical.
            results: list[dict[str, Any]] = []
            for tu in resp.tool_uses:
                output = registry.call(tu["name"], **tu["input"])
                tool_calls.append({"name": tu["name"], "input": tu["input"], "output": output})
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu["id"],
                        "content": json.dumps(output, sort_keys=True, ensure_ascii=False),
                    }
                )
            convo.append({"role": "user", "content": results})

        raise ToolLoopExhausted(max_rounds)

    # --- live -----------------------------------------------------------

    def _client(self) -> Any:
        """AsyncAnthropic. Dùng SDK chính chủ, không tự viết HTTP client."""
        if self._anthropic is None:
            from anthropic import AsyncAnthropic

            api_key = self.settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
            auth_token = self.settings.anthropic_auth_token or os.environ.get(
                "ANTHROPIC_AUTH_TOKEN"
            )
            if api_key:
                self._anthropic = AsyncAnthropic(api_key=api_key)
            elif auth_token:
                # OAuth bearer (subscription). SDK gửi Authorization: Bearer …
                self._anthropic = AsyncAnthropic(auth_token=auth_token)
            else:
                raise ConfigError(
                    "anthropic_api_key",
                    f"llm_mode={self.settings.llm_mode!r} cần khoá API "
                    "(CERTUS_ANTHROPIC_API_KEY / ANTHROPIC_API_KEY) hoặc OAuth "
                    "(CERTUS_ANTHROPIC_AUTH_TOKEN / ANTHROPIC_AUTH_TOKEN)",
                )
        return self._anthropic

    def _stream_live(
        self,
        *,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] | None,
        max_tokens: int,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": list(messages),
        }
        if tools:
            kwargs["tools"] = list(tools)
        return self._client().messages.stream(**kwargs)

    # --- ghi cassette ---------------------------------------------------

    def _write_cassette(
        self,
        *,
        key: str,
        model: str,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] | None,
        response: LLMResponse,
        hint: str | None,
    ) -> Path:
        directory = self.cassette_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / cassette_slug(key, hint)
        record = {
            "key": key,
            "model": model,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "request": {
                "system": system,
                "messages": list(messages),
                "tools": list(tools or []),
            },
            "response": {
                "text": response.text,
                "chunks": response.chunks,
                "tool_uses": response.tool_uses,
                "stop_reason": response.stop_reason,
                "usage": response.usage,
            },
        }
        path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    # --- thông điệp lỗi -------------------------------------------------

    def _miss_message(self, key: str, model: str, system: str) -> str:
        head = system[:200].replace("\n", " ")
        return (
            f"không có cassette khớp key={key}\n"
            f"  model      : {model}\n"
            f"  system[:200]: {head}\n"
            f"  thư mục    : {self.cassette_dir}\n"
            f"  đang có    : {len(self._index())} bản ghi\n"
            f"  cách sinh  : CERTUS_LLM_MODE=record chạy lại đúng bước này"
        )


# ─────────────────────────── ánh xạ dữ liệu ───────────────────────────


def _response_from_record(record: Mapping[str, Any], *, model: str) -> LLMResponse:
    body = record.get("response", {})
    text = body.get("text", "")
    chunks = list(body.get("chunks") or ([text] if text else []))
    return LLMResponse(
        text=text,
        tool_uses=list(body.get("tool_uses") or []),
        stop_reason=body.get("stop_reason"),
        model=record.get("model", model),
        usage=dict(body.get("usage") or {}),
        from_cassette=True,
        chunks=chunks,
    )


def _response_from_message(message: Any, *, chunks: Iterable[str]) -> LLMResponse:
    text_parts: list[str] = []
    tool_uses: list[dict[str, Any]] = []
    for block in getattr(message, "content", []) or []:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text_parts.append(getattr(block, "text", ""))
        elif block_type == "tool_use":
            tool_uses.append(
                {
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                    "input": getattr(block, "input", {}) or {},
                }
            )
    usage_obj = getattr(message, "usage", None)
    usage: dict[str, Any] = {}
    if usage_obj is not None:
        for name in ("input_tokens", "output_tokens"):
            value = getattr(usage_obj, name, None)
            if value is not None:
                usage[name] = value
    return LLMResponse(
        text="".join(text_parts),
        tool_uses=tool_uses,
        stop_reason=getattr(message, "stop_reason", None),
        model=getattr(message, "model", ""),
        usage=usage,
        from_cassette=False,
        chunks=list(chunks),
    )
