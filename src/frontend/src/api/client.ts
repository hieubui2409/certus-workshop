/**
 * REST thật — SDD 08 §4.3. Chỉ được gọi khi VITE_USE_MOCK=0.
 *
 * Cấu hình đọc từ biến môi trường Vite; `api/analyze.ts` giữ công tắc, file
 * này không tự quyết định gì.
 */

import type { AxisDiscoveryResponse, CoverageLayer, PromptPayload, RejectedFile, SampleRepo, UploadResult } from '@/types/api';
import { authHeaders, clearToken } from './auth';

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? '/api';

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: 'application/json', ...(await authHeaders()) },
    signal,
  });
  if (res.status === 401 || res.status === 403) {
    // Token hết hạn hoặc thiếu quyền. Xoá token đã lưu để lần sau xin lại —
    // giữ một token chết trong localStorage làm mọi request sau đó hỏng theo
    // cùng một cách, và triệu chứng đó chỉ đích danh sai chỗ.
    clearToken();
    throw new Error(`${path} bị từ chối (${res.status}) — kiểm tra quyền của vai đang dùng`);
  }
  if (!res.ok) {
    throw new Error(`${path} trả về ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export function fetchSamples(signal?: AbortSignal): Promise<SampleRepo[]> {
  return getJson<SampleRepo[]>('/samples', signal);
}

/**
 * Đề xuất tập trục (engine ToT) cho một repo — bước HITL trước khi phân tích.
 * POST vì đầu vào là `{target | upload_id}`, không phải một id trên URL.
 */
export async function discoverAxes(
  body: { target?: string; upload_id?: string; local_path?: string },
  signal?: AbortSignal,
): Promise<AxisDiscoveryResponse> {
  const res = await fetch(`${API_BASE}/axes/discover`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...(await authHeaders()) },
    body: JSON.stringify(body),
    signal,
  });
  if (res.status === 401 || res.status === 403) {
    clearToken();
    throw new Error(`/axes/discover bị từ chối (${res.status})`);
  }
  if (!res.ok) throw new Error(`/axes/discover trả về ${res.status} ${res.statusText}`);
  return (await res.json()) as AxisDiscoveryResponse;
}

/** Đúng 3 phần tử. Không có phần tử thứ tư nào gộp ba tầng lại. */
export function fetchCoverage(runId: string, signal?: AbortSignal): Promise<CoverageLayer[]> {
  return getJson<CoverageLayer[]>(`/coverage/${runId}`, signal);
}

export function fetchPromptPayload(runId: string, signal?: AbortSignal): Promise<PromptPayload> {
  return getJson<PromptPayload>(`/prompt-payload/${runId}`, signal);
}

/**
 * Chọn một repo mẫu — KHÔNG đi qua `/api/upload`. `/api/upload` chỉ nhận
 * `multipart/form-data` với field `file` (một `.zip`); nó không có khái niệm
 * "repo mẫu" và không có field `sample_id`. Danh sách repo mẫu tới từ
 * `/api/samples`, và việc "chọn" chỉ là giữ lại `sampleId` để đưa thẳng vào
 * `/api/analyze` dưới tên `target` — không có bước ingest nào ở giữa, nên
 * không có `accepted`/`rejected` thật để hiển thị ở đây.
 */
export async function uploadSample(sampleId: string): Promise<UploadResult> {
  return {
    run_id: sampleId,
    source: 'sample',
    label: sampleId,
    accepted: [],
    rejected: [],
    target: sampleId,
  };
}

/**
 * Hình dạng thật của phản hồi `/api/upload` (`UploadAck` —
 * `src/backend/app/api/schemas.py`). Cả hai chiều đều có danh sách per-file:
 * `accepted` cho tệp đã nhận (path + bytes + sha256 của byte thật ghi ra đĩa),
 * `rejected_reasons` cho tệp bị loại (path + lý do).
 *
 * `files_accepted` là số đếm dư thừa — backend đã khoá nó bằng validator để
 * luôn bằng `accepted.length`. Đọc danh sách, đừng đọc con số.
 */
interface UploadAck {
  upload_id: string;
  accepted: { path: string; bytes: number; sha256: string }[];
  files_accepted: number;
  files_rejected: number;
  rejected_reasons: Record<string, string>;
  bytes_total: number;
}

export async function uploadZip(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    headers: { ...(await authHeaders()) },
    body: form,
  });
  if (!res.ok) throw new Error(`upload thất bại: ${res.status}`);
  const ack = (await res.json()) as UploadAck;

  const rejected: RejectedFile[] = Object.entries(ack.rejected_reasons).map(([path, reason]) => ({
    path,
    reason,
  }));

  return {
    run_id: ack.upload_id,
    source: 'zip',
    label: file.name,
    // `?? []` phòng backend cũ chưa có trường này: bảng rỗng vẫn hơn màn
    // trắng, và badge bên cạnh nó đọc từ cùng một mảng nên không nói dối.
    accepted: ack.accepted ?? [],
    rejected,
    upload_id: ack.upload_id,
  };
}
