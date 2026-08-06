/**
 * Lấy và giữ token cho phiên làm việc.
 *
 * Tài khoản demo mặc định là `demo-analyst` — chính vai đang BỊ CHẤM. Chọn nó
 * làm mặc định là có chủ đích: nếu vai đó làm được nhiều hơn mức nó nên làm,
 * điều đó phải lộ ra ngay trong lượt dùng đầu tiên, không phải sau khi ai đó
 * nghĩ ra việc đi đổi tài khoản.
 */

import { API_BASE } from './client';

const STORAGE_KEY = 'certus.token';

let inflight: Promise<string> | null = null;

export const DEFAULT_ACCOUNT = 'demo-analyst';

export function storedToken(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* localStorage bị chặn — phiên này chạy không có bộ nhớ, vẫn dùng được */
  }
}

export async function login(username: string = DEFAULT_ACCOUNT): Promise<string> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  });
  if (!res.ok) {
    throw new Error(`đăng nhập ${username} thất bại: ${res.status} ${res.statusText}`);
  }
  const data = (await res.json()) as { token: string };
  try {
    localStorage.setItem(STORAGE_KEY, data.token);
  } catch {
    /* không lưu được thì mỗi lần gọi lại xin token mới — chậm, không sai */
  }
  return data.token;
}

/** Token hiện có, hoặc xin mới. Gộp các lời gọi song song thành một. */
export async function ensureToken(): Promise<string> {
  const existing = storedToken();
  if (existing) return existing;
  if (!inflight) {
    inflight = login().finally(() => {
      inflight = null;
    });
  }
  return inflight;
}

/** Header Authorization, hoặc `{}` nếu không lấy được token. */
export async function authHeaders(): Promise<Record<string, string>> {
  try {
    return { Authorization: `Bearer ${await ensureToken()}` };
  } catch {
    // Trả rỗng thay vì ném: để request đi tiếp và nhận 403 THẬT từ backend.
    // Nuốt lỗi ở đây sẽ biến "chưa đăng nhập" thành "sản phẩm hỏng" trên UI.
    return {};
  }
}
