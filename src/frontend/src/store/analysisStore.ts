/**
 * State của stream SSE — SDD 08 §6.
 *
 * Ba luật của store, cả ba đều là luật hiển thị chứ không phải tối ưu:
 *   1. KHÔNG khử trùng lặp, KHÔNG sắp xếp lại. Backend gửi hai lần cùng một
 *      claim.id thì UI hiện hai hàng. Gộp lại là che một triệu chứng.
 *   2. `answer` chỉ nối thêm — `event: token` là chuỗi tăng dần.
 *   3. `warnings` KHÔNG BAO GIỜ bị xoá trong vòng đời một lần chạy.
 */

import { create } from 'zustand';
import type { Cell, Claim, GateVerdict } from '@/types/contracts';
import type {
  DonePayload,
  ErrorPayload,
  LogPayload,
  SpanPayload,
  SseEvent,
  StepPayload,
  WarningPayload,
} from '@/types/sse';
import { isUnanchoredObserved } from '@/lib/labels';

export type RunStatus = 'idle' | 'running' | 'done' | 'error';

export interface AnalysisState {
  status: RunStatus;
  runId: string | null;
  question: string;
  steps: StepPayload[];
  logs: LogPayload[];
  claims: Claim[];
  cells: Cell[];
  gates: GateVerdict[];
  spans: SpanPayload[];
  warnings: WarningPayload[];
  answer: string;
  done: DonePayload | null;
  error: ErrorPayload | null;

  start: (runId: string, question: string) => void;
  apply: (event: SseEvent) => void;
  finish: () => void;
  reset: () => void;
}

const EMPTY = {
  status: 'idle' as RunStatus,
  runId: null,
  question: '',
  steps: [],
  logs: [],
  claims: [],
  cells: [],
  gates: [],
  spans: [],
  warnings: [],
  answer: '',
  done: null,
  error: null,
};

export const useAnalysisStore = create<AnalysisState>((set) => ({
  ...EMPTY,

  start: (runId, question) =>
    set({ ...EMPTY, status: 'running', runId, question }),

  finish: () =>
    set((s) => (s.status === 'running' ? { status: 'done' } : {})),

  reset: () => set({ ...EMPTY }),

  apply: (event) =>
    set((s) => {
      switch (event.event) {
        case 'step':
          return { steps: [...s.steps, event.data] };
        case 'log':
          return { logs: [...s.logs, event.data] };
        case 'claim':
          return { claims: [...s.claims, event.data] };
        case 'cell':
          return { cells: [...s.cells, event.data] };
        case 'gate':
          return { gates: [...s.gates, event.data] };
        case 'token':
          return { answer: s.answer + event.data.text };
        case 'span':
          return { spans: [...s.spans, event.data] };
        case 'warning':
          return { warnings: [...s.warnings, event.data] };
        case 'done':
          return { done: event.data, status: 'done' as RunStatus };
        case 'error':
          return { error: event.data, status: 'error' as RunStatus };
      }
    }),
}));

/* ─────────────────────────── Selector ─────────────────────────── */

/**
 * Đếm số trace_id phân biệt. Selector này tồn tại vì đúng lý do
 * `SpanStore.distinct_trace_count()` tồn tại ở backend (SDD 06 §5.1): kết quả
 * probe của lỗi 11 phải hỏi được bằng MỘT lời gọi, không phải bằng mắt.
 *
 * Span không mang `trace_id` được quy về `fallback` (trace_id của `event: done`)
 * và đánh dấu là suy ra — UI không bao giờ tự sinh một id mới, vì tự sinh id ở
 * phía UI đúng bằng việc xoá dấu vết của chính lỗi đang cần thấy.
 */
export function distinctTraceIds(spans: SpanPayload[], fallback?: string | null): string[] {
  const seen: string[] = [];
  for (const span of spans) {
    const id = span.trace_id ?? fallback ?? 'không rõ';
    if (!seen.includes(id)) seen.push(id);
  }
  return seen;
}

export function traceIdOf(span: SpanPayload, fallback?: string | null): string {
  return span.trace_id ?? fallback ?? 'không rõ';
}

/** Kết quả probe của lỗi 6, hỏi được bằng một lời gọi. */
export function unanchoredObservedClaims(claims: Claim[]): Claim[] {
  return claims.filter(isUnanchoredObserved);
}

/** Cổng có mẫu số 0 — sự cố cấu hình, không phải kết quả tốt. */
export function emptyDenominatorGates(gates: GateVerdict[]): GateVerdict[] {
  return gates.filter((g) => g.denominator === 0);
}
