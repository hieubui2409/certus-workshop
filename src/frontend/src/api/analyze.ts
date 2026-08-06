/**
 * Công tắc mock — SDD 08 §7. Đây là CHỖ Ở DUY NHẤT của quyết định
 * "gọi backend thật hay phát lại stream giả". Không component nào được tự hỏi
 * lại câu đó.
 *
 *   VITE_USE_MOCK=0  (MẶC ĐỊNH)  → api/client.ts + api/stream.ts (backend thật)
 *   VITE_USE_MOCK=1              → api/mock.ts
 *
 * Mặc định TẮT: một UI mặc định phát lại mock — tức phát lại đáp án đã đóng
 * sẵn — là một UI không ai kiểm được rằng nó có thật sự nói chuyện với backend
 * hay không. Bật mock phải là một lựa chọn TƯỜNG MINH (`VITE_USE_MOCK=1`).
 *
 * Hai nhánh phải CÙNG kiểu trả về và CÙNG thứ tự event; nếu không thì bật
 * VITE_USE_MOCK=1 sẽ lộ ra một UI khác, và lúc đó không ai biết triệu chứng
 * nào là của sản phẩm, triệu chứng nào là của mock.
 */

import type { AnalyzeRequest, CoverageLayer, PromptPayload, SampleRepo, UploadResult } from '@/types/api';
import type { SseEvent } from '@/types/sse';
import { authHeaders } from './auth';
import { API_BASE, fetchCoverage, fetchPromptPayload, fetchSamples, uploadSample, uploadZip } from './client';
import {
  mockAnalyzeStream,
  mockFetchCoverage,
  mockFetchPromptPayload,
  mockFetchSamples,
  mockUploadSample,
  mockUploadZip,
} from './mock';
import { consumeEventStream } from './stream';

/** Mặc định TẮT: chỉ bật mock khi khai tường minh `VITE_USE_MOCK=1`. */
export const USE_MOCK: boolean = (import.meta.env.VITE_USE_MOCK ?? '0') === '1';

export function listSamples(signal?: AbortSignal): Promise<SampleRepo[]> {
  return USE_MOCK ? mockFetchSamples() : fetchSamples(signal);
}

export function pickSample(sampleId: string): Promise<UploadResult> {
  return USE_MOCK ? mockUploadSample(sampleId) : uploadSample(sampleId);
}

export function sendZip(file: File): Promise<UploadResult> {
  return USE_MOCK ? mockUploadZip(file) : uploadZip(file);
}

export function getCoverage(runId: string, signal?: AbortSignal): Promise<CoverageLayer[]> {
  return USE_MOCK ? mockFetchCoverage() : fetchCoverage(runId, signal);
}

export function getPromptPayload(runId: string, signal?: AbortSignal): Promise<PromptPayload> {
  return USE_MOCK ? mockFetchPromptPayload() : fetchPromptPayload(runId, signal);
}

export interface StreamHandlers {
  onEvent: (event: SseEvent) => void;
  signal?: AbortSignal;
}

export async function openAnalyzeStream(
  req: AnalyzeRequest,
  handlers: StreamHandlers,
): Promise<void> {
  if (USE_MOCK) {
    await mockAnalyzeStream(handlers.onEvent, handlers.signal);
    return;
  }

  // `/analyze` trả JSON một lần; dòng sự kiện nằm ở `/analyze/stream`. Gọi
  // nhầm đường sẽ nhận về một object hợp lệ và parser SSE im lặng không ra
  // event nào — đúng loại hỏng khó nhìn nhất, nên đường dẫn ghi rõ ở đây.
  const res = await fetch(`${API_BASE}/analyze/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(await authHeaders()),
    },
    body: JSON.stringify(req),
    signal: handlers.signal,
  });

  if (!res.ok || !res.body) {
    handlers.onEvent({
      event: 'error',
      data: {
        code: 'http-error',
        msg: `POST /analyze/stream trả về ${res.status} ${res.statusText}`,
      },
    });
    return;
  }

  await consumeEventStream(res.body, handlers.onEvent);
}
