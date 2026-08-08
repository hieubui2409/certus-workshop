/**
 * Khám phá trục theo thời gian thực — dòng `/api/axes/discover/stream`.
 *
 * Bản REST (`discoverAxes` trong client.ts) vẫn còn và trả ĐÚNG cùng kết quả:
 * backend chạy chung một generator rồi lấy sự kiện `done`. Dùng bản stream khi
 * người dùng đang NHÌN — ở repo thật bước này quét hàng nghìn tệp rồi còn hỏi mô
 * hình, và một thanh chờ im lặng không phân biệt được "đang quét" với "đã treo".
 *
 * Vốn từ sự kiện RIÊNG, không phải 10-kind của `/analyze`: tái dùng parser của
 * analyze sẽ nuốt `axis`/`llm_delta` như "event lạ".
 */

import { authHeaders } from './auth';
import { API_BASE } from './client';
import type { AxisCandidate, AxisDiscoveryResponse } from '@/types/api';

export type AxisEventKind =
  | 'step'
  | 'axis'
  | 'axis_rationale'
  | 'llm_delta'
  | 'llm_skipped'
  | 'done'
  | 'error';

export interface AxisStepData {
  seq: number;
  name: string;
  status: 'running' | 'done';
  [k: string]: unknown;
}

export interface AxisEvent {
  event: AxisEventKind;
  data: Record<string, unknown> & { seq: number };
}

export type AxisHandler = (ev: AxisEvent) => void;

const AXIS_KINDS = new Set<AxisEventKind>([
  'step',
  'axis',
  'axis_rationale',
  'llm_delta',
  'llm_skipped',
  'done',
  'error',
]);

function parseAxisFrame(raw: string, onEvent: AxisHandler): void {
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
  if (!AXIS_KINDS.has(name as AxisEventKind)) return;
  try {
    const data = JSON.parse(dataLines.join('\n')) as AxisEvent['data'];
    onEvent({ event: name as AxisEventKind, data });
  } catch {
    /* data hỏng: bỏ frame, không dựng UI trên rác */
  }
}

export interface AxisStreamRequest {
  target?: string;
  uploadId?: string;
  localPath?: string;
}

export interface AxisStreamHandlers {
  onEvent: AxisHandler;
  signal?: AbortSignal;
}

/** Mở dòng khám phá trục và phát từng sự kiện khi nó đến. */
export async function openAxisStream(
  req: AxisStreamRequest,
  handlers: AxisStreamHandlers,
): Promise<void> {
  const res = await fetch(`${API_BASE}/axes/discover/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(await authHeaders()),
    },
    body: JSON.stringify({
      target: req.target ?? null,
      upload_id: req.uploadId ?? null,
      local_path: req.localPath ?? null,
    }),
    signal: handlers.signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`/axes/discover/stream trả về ${res.status} ${res.statusText}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    // sse-starlette đóng khung bằng CRLF; chuẩn hoá về `\n` TRƯỚC khi tách, nếu
    // không `indexOf('\n\n')` không bao giờ khớp và cả stream dồn thành một khối.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
    let idx = buffer.indexOf('\n\n');
    while (idx !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      if (frame.trim().length > 0) parseAxisFrame(frame, handlers.onEvent);
      idx = buffer.indexOf('\n\n');
    }
  }
  if (buffer.trim().length > 0) parseAxisFrame(buffer, handlers.onEvent);
}

/** Trạng thái tích luỹ từ dòng sự kiện — đủ để vẽ toàn bộ panel. */
export interface AxisStreamState {
  steps: AxisStepData[];
  candidates: AxisCandidate[];
  llmText: string;
  llmSkipped: string | null;
  result: AxisDiscoveryResponse | null;
  error: string | null;
}

export const EMPTY_AXIS_STREAM: AxisStreamState = {
  steps: [],
  candidates: [],
  llmText: '',
  llmSkipped: null,
  result: null,
  error: null,
};

/**
 * Gộp một sự kiện vào trạng thái. Hàm THUẦN để test được không cần mạng, và để
 * mọi luật "sự kiện này đổi gì trên màn hình" nằm đúng một chỗ.
 */
export function reduceAxisEvent(state: AxisStreamState, ev: AxisEvent): AxisStreamState {
  switch (ev.event) {
    case 'step': {
      const step = ev.data as unknown as AxisStepData;
      // Bước `done` thay bước `running` cùng tên thay vì chồng thêm dòng mới —
      // danh sách phải đọc ra tiến trình, không phải một sổ nhật ký hai dòng/bước.
      const i = state.steps.findIndex((s) => s.name === step.name);
      const steps = i === -1 ? [...state.steps, step] : state.steps.map((s, j) => (j === i ? step : s));
      return { ...state, steps };
    }
    case 'axis':
      return { ...state, candidates: [...state.candidates, ev.data as unknown as AxisCandidate] };
    case 'axis_rationale': {
      const axis = String(ev.data.axis);
      return {
        ...state,
        candidates: state.candidates.map((c) =>
          c.axis === axis ? { ...c, rationale: String(ev.data.rationale) } : c,
        ),
      };
    }
    case 'llm_delta':
      return { ...state, llmText: state.llmText + String(ev.data.text ?? '') };
    case 'llm_skipped':
      return { ...state, llmSkipped: String(ev.data.reason ?? 'không gọi mô hình') };
    case 'done':
      return { ...state, result: ev.data as unknown as AxisDiscoveryResponse };
    case 'error':
      return { ...state, error: `${ev.data.code}: ${ev.data.msg}` };
    default:
      return state;
  }
}
