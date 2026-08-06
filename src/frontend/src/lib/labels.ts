/**
 * Nhãn bằng chứng → màu + giải thích.
 *
 * Bốn màu khác nhau để mắt đếm được tỉ lệ `OBSERVED` mà không cần đọc từng
 * hàng. Ở repo mẫu nguyên bản, cột này gần như toàn xanh lá — và đó chính là
 * triệu chứng của lỗi 6: "Only a tool promotes a claim."
 */

import type { Label } from '@/types/contracts';

export interface LabelStyle {
  label: Label;
  /** tên màu của Mantine */
  color: string;
  meaning: string;
}

export const LABEL_STYLES: Record<Label, LabelStyle> = {
  OBSERVED: {
    label: 'OBSERVED',
    color: 'green',
    meaning: 'đã chạy/đọc/đo trực tiếp, và chưa có gì đổi từ đó',
  },
  DERIVED: {
    label: 'DERIVED',
    color: 'blue',
    meaning: 'suy ra từ OBSERVED bằng một cơ chế phát biểu được',
  },
  PRIOR: {
    label: 'PRIOR',
    color: 'yellow',
    meaning: 'kiến thức huấn luyện — có thể đã cũ, có thể sai',
  },
  ASSUMED: {
    label: 'ASSUMED',
    color: 'gray',
    meaning: 'chưa kiểm chứng nhưng kết luận đang cần tới',
  },
};

export function labelColor(label: Label): string {
  return LABEL_STYLES[label].color;
}

/**
 * Quy tắc phát hiện lỗi 6, đặt ở đây để cả bảng lẫn dòng đếm trên đầu bảng
 * dùng CHUNG một định nghĩa — hai chỗ định nghĩa "claim hỏng" theo hai kiểu là
 * cách con số trên đầu bảng lệch khỏi số hàng viền đỏ bên dưới.
 *
 * Nền: verification invariant #1 — OBSERVED phải có neo. Và:
 * "restating it more confidently does NOT promote a claim — that is a
 * hallucination wearing OBSERVED grammar."
 */
export function isUnanchoredObserved(claim: {
  label: Label;
  evidence_ids: string[];
  anchors: unknown[];
}): boolean {
  return (
    claim.label === 'OBSERVED' && claim.evidence_ids.length === 0 && claim.anchors.length === 0
  );
}

/**
 * Claim tỉ lệ mang nhãn OBSERVED mà thiếu k/n hoặc interval là CLAIM DỊ DẠNG
 * (note 01 §3). 3/3 và 300/300 mang cùng nhãn nhưng một cái đảm bảo 43.9%,
 * cái kia 98.9%.
 */
export function isMalformedRateClaim(claim: {
  label: Label;
  is_rate: boolean;
  k?: number | null;
  n?: number | null;
  interval?: unknown;
}): boolean {
  if (!claim.is_rate || claim.label !== 'OBSERVED') return false;
  return claim.k == null || claim.n == null || claim.interval == null;
}
