/**
 * Parser `text/event-stream` — SDD 08 §7.1.
 *
 * Tự viết thay vì dùng `EventSource` vì `EventSource` không gửi được header
 * `Authorization` (JWT bearer, system-design §3) và không POST được.
 *
 * Hai luật:
 *   1. Event lạ VẪN được phát ra dưới dạng warning `sse-unknown-event`.
 *   2. `data` hỏng KHÔNG bị bỏ qua — nó thành warning `sse-malformed-data`.
 * Nuốt im lặng ở cả hai chỗ là cách hợp đồng trôi khỏi nhau mà không ai thấy.
 */

import { isKnownEventName, type SseEvent } from '@/types/sse';

export type SseHandler = (event: SseEvent) => void;

function emitParseWarning(onEvent: SseHandler, code: string, msg: string): void {
  onEvent({ event: 'warning', data: { code, msg } });
}

/** Chuyển một frame thô (đã tách theo dòng trống) thành SseEvent. */
export function parseFrame(raw: string, onEvent: SseHandler): void {
  let name = 'message';
  const dataLines: string[] = [];

  for (const line of raw.split('\n')) {
    if (line.startsWith(':')) continue; // comment / keep-alive
    const sep = line.indexOf(':');
    const field = sep === -1 ? line : line.slice(0, sep);
    const value = sep === -1 ? '' : line.slice(sep + 1).replace(/^ /, '');
    if (field === 'event') name = value;
    else if (field === 'data') dataLines.push(value);
  }

  if (dataLines.length === 0) return;
  const payload = dataLines.join('\n');

  let parsed: unknown;
  try {
    parsed = JSON.parse(payload);
  } catch {
    emitParseWarning(
      onEvent,
      'sse-malformed-data',
      `event: ${name} — data không parse được: ${payload.slice(0, 200)}`,
    );
    return;
  }

  if (!isKnownEventName(name)) {
    emitParseWarning(
      onEvent,
      'sse-unknown-event',
      `event: ${name} không có trong hợp đồng SDD 00 §5 — data: ${payload.slice(0, 200)}`,
    );
    return;
  }

  onEvent({ event: name, data: parsed } as SseEvent);
}

/** Đọc một `ReadableStream` byte và phát từng frame ra `onEvent`. */
export async function consumeEventStream(
  body: ReadableStream<Uint8Array>,
  onEvent: SseHandler,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx = buffer.indexOf('\n\n');
    while (idx !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      if (frame.trim().length > 0) parseFrame(frame, onEvent);
      idx = buffer.indexOf('\n\n');
    }
  }

  if (buffer.trim().length > 0) parseFrame(buffer, onEvent);
}
