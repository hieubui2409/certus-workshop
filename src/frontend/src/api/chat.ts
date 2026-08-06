/**
 * Hội thoại multiturn có tool-use — dòng `/api/chat/stream`.
 *
 * Chat có VỐN TỪ SỰ KIỆN RIÊNG (`tool_use`/`tool_result`/`message`/`done`/`error`),
 * KHÔNG phải 10-kind của `/analyze` (system-design §7). Vì thế phải có parser SSE
 * riêng: `consumeEventStream` của analyze gác theo hợp đồng analyze và sẽ NUỐT
 * `tool_use`/`tool_result` như "event lạ". Không tái dùng nó ở đây là cố ý.
 *
 * Luôn gọi backend thật: backend tự mock-default (phát lại cassette). Không có
 * nhánh mock riêng ở frontend cho chat.
 */

import { authHeaders } from './auth';
import { API_BASE } from './client';

export type ChatEventKind = 'message' | 'tool_use' | 'tool_result' | 'done' | 'error';

export interface ChatEvent {
  event: ChatEventKind;
  data: { seq: number; thread_id: string; payload: Record<string, unknown> };
}

export type ChatHandler = (ev: ChatEvent) => void;

const CHAT_KINDS = new Set<ChatEventKind>([
  'message',
  'tool_use',
  'tool_result',
  'done',
  'error',
]);

/** Một frame SSE thô → ChatEvent. Frame có event lạ hoặc data hỏng bị bỏ qua. */
function parseChatFrame(raw: string, onEvent: ChatHandler): void {
  let name = 'message';
  const dataLines: string[] = [];
  for (const line of raw.split('\n')) {
    if (line.startsWith(':')) continue; // keep-alive
    const sep = line.indexOf(':');
    const field = sep === -1 ? line : line.slice(0, sep);
    const value = sep === -1 ? '' : line.slice(sep + 1).replace(/^ /, '');
    if (field === 'event') name = value;
    else if (field === 'data') dataLines.push(value);
  }
  if (dataLines.length === 0) return;
  if (!CHAT_KINDS.has(name as ChatEventKind)) return;
  try {
    const data = JSON.parse(dataLines.join('\n')) as ChatEvent['data'];
    onEvent({ event: name as ChatEventKind, data });
  } catch {
    /* data hỏng: bỏ frame, không dựng UI trên rác */
  }
}

export interface ChatStreamHandlers {
  onEvent: ChatHandler;
  signal?: AbortSignal;
}

/** Gửi một lượt và stream các sự kiện của lượt đó. */
export async function openChatStream(
  threadId: string,
  message: string,
  handlers: ChatStreamHandlers,
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(await authHeaders()),
    },
    body: JSON.stringify({ thread_id: threadId, message }),
    signal: handlers.signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`/chat/stream trả về ${res.status} ${res.statusText}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    // sse-starlette đóng khung frame bằng CRLF (`\r\n\r\n`); chuẩn hoá về `\n`
    // TRƯỚC khi tách, nếu không `indexOf('\n\n')` không bao giờ khớp và cả stream
    // dồn thành một khối rác — đúng lỗi đã vá ở `stream.ts` của luồng analyze.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
    let idx = buffer.indexOf('\n\n');
    while (idx !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      if (frame.trim().length > 0) parseChatFrame(frame, handlers.onEvent);
      idx = buffer.indexOf('\n\n');
    }
  }
  if (buffer.trim().length > 0) parseChatFrame(buffer, handlers.onEvent);
}
