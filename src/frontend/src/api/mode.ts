/**
 * Công tắc chế độ LLM của BACKEND — cassette (mock) ⇄ live (gọi model thật).
 *
 * KHÁC hẳn `USE_MOCK` (VITE_USE_MOCK) ở `api/analyze.ts`: cái đó là cờ build-time
 * của FRONTEND chọn "phát lại stream giả trong trình duyệt" vs "gọi backend".
 * Còn `llm_mode` ở đây là của BACKEND: khi đã gọi backend thật thì backend phát
 * lại cassette (mock) hay gọi Anthropic (live). Công tắc này chỉ có nghĩa khi
 * FE đang nói chuyện với backend (`USE_MOCK=false`).
 */

import { API_BASE } from './client';
import { authHeaders } from './auth';

export type LlmMode = 'mock' | 'live';

export interface ModeState {
  /** Chế độ hiện tại của process backend. Có thể là 'record' nếu ai đó bật qua CLI. */
  mode: string;
  /** live có creds để gọi model không (khoá API / auth token ccs). Sai ⇒ mở hướng dẫn. */
  live_available: boolean;
  model: string;
}

export async function getMode(signal?: AbortSignal): Promise<ModeState> {
  const res = await fetch(`${API_BASE}/mode`, {
    headers: { Accept: 'application/json', ...(await authHeaders()) },
    signal,
  });
  if (!res.ok) throw new Error(`/mode trả về ${res.status} ${res.statusText}`);
  return (await res.json()) as ModeState;
}

export async function setMode(mode: LlmMode): Promise<ModeState> {
  const res = await fetch(`${API_BASE}/mode`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...(await authHeaders()) },
    body: JSON.stringify({ mode }),
  });
  if (!res.ok) throw new Error(`/mode POST trả về ${res.status} ${res.statusText}`);
  return (await res.json()) as ModeState;
}
