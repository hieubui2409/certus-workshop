/**
 * Định dạng số cho hiển thị.
 *
 * LUẬT CỦA FILE NÀY: nó ĐỊNH DẠNG, nó không CẤP SỐ. Không có phép chia nào ở
 * đây trừ hai chỗ tuyệt đối cần cho việc vẽ (`ratio` cho bề rộng thanh, và
 * `pct` cho phần trăm hiển thị) — và cả hai đều luôn đi kèm `k/n` nguyên bản
 * trên màn hình, không bao giờ thay thế nó.
 *
 * Mọi con số THỰC SỰ (coverage, interval, mẫu số) đều đến từ backend.
 */

import type { Interval } from '@/types/contracts';

/** `k/n` nguyên bản — thứ phải hiện ra TRƯỚC phần trăm. */
export function fraction(k: number, n: number): string {
  return `${k}/${n}`;
}

/** Tỉ lệ thô, chỉ dùng cho bề rộng thanh. `n === 0` ⇒ 0, không phải NaN. */
export function ratio(k: number, n: number): number {
  return n === 0 ? 0 : k / n;
}

export function pct(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** `Wilson95 [0.44, 1.00]` — method nằm trong chuỗi, không để ngầm. */
export function formatInterval(iv: Interval): string {
  const conf = Math.round(iv.conf * 100);
  const method = iv.method === 'wilson' ? 'Wilson' : iv.method;
  return `${method}${conf} [${iv.lower.toFixed(4)}, ${iv.upper.toFixed(4)}]`;
}

/**
 * Bên Python `width` là `@property`. Bên này nó là hàm chứ không phải trường
 * của kiểu: nếu là trường thì nó đi vào JSON và thành con số thứ hai nói cùng
 * một chuyện — mà hai con số nói cùng một chuyện thì sớm muộn sẽ lệch nhau.
 */
export function intervalWidth(iv: Interval): number {
  return iv.upper - iv.lower;
}

/** Rút gọn id dài (trace_id, sha256) nhưng KHÔNG bao giờ vứt bản đầy đủ đi. */
export function shortId(id: string, len = 8): string {
  return id.length <= len ? id : `${id.slice(0, len)}…`;
}

export function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
