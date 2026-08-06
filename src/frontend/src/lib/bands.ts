/**
 * Band → màu + nhãn tiếng Việt.
 *
 * YÊU CẦU QUAN TRỌNG NHẤT CỦA FILE NÀY: `N/A` và `unknown` phải phân biệt
 * được NGAY TỪ XA, ở CẢ light lẫn dark, không cần đọc chú giải.
 *
 * Đây là một bài học của buổi workshop chứ không phải một lựa chọn thẩm mỹ:
 *   - `N/A`     bị loại khỏi CẢ TỬ LẪN MẪU (config/grid.yaml: "N/A cố ý không
 *               có entry trong band_scores"). "not applicable" không phải
 *               "rủi ro trung bình bằng không".
 *   - `unknown` NẰM TRONG MẪU và chấm 0 — "chưa ai ghé".
 *
 * Hai ô cùng một sắc xám thì mẫu số tụt 17 → 13 của lỗi 3a trở nên vô hình,
 * và đó đúng là thứ buổi học cần sinh viên nhìn thấy.
 */

import type { Band } from '@/types/contracts';

export interface BandStyle {
  band: Band;
  /** nhãn tiếng Việt hiện trên chú giải */
  label: string;
  /** một câu giải thích band này nói gì */
  meaning: string;
  /** màu nền ở chế độ sáng / tối */
  light: string;
  dark: string;
  /** màu chữ chồng lên nền trên */
  fg: string;
  /** N/A được gạch chéo để phân biệt được cả khi in trắng đen */
  hatched: boolean;
  /** band có nằm trong mẫu số không — cột này là toàn bộ bài học */
  inDenominator: boolean;
}

export const BAND_STYLES: Record<Band, BandStyle> = {
  high: {
    band: 'high',
    label: 'high',
    meaning: 'đã chạm, đủ assert độc lập, có mutant bị giết',
    light: '#2f9e44',
    dark: '#40c057',
    fg: '#ffffff',
    hatched: false,
    inDenominator: true,
  },
  med: {
    band: 'med',
    label: 'med',
    meaning: 'đã chạm nhưng chưa đủ assert độc lập để xét high',
    light: '#94d82d',
    dark: '#a9e34b',
    fg: '#1a1b1e',
    hatched: false,
    inDenominator: true,
  },
  low: {
    band: 'low',
    label: 'low',
    meaning: 'chạm mờ — có đi qua nhưng gần như không kiểm gì',
    light: '#fab005',
    dark: '#fcc419',
    fg: '#1a1b1e',
    hatched: false,
    inDenominator: true,
  },
  stub: {
    band: 'stub',
    label: 'stub',
    meaning: 'có test nhưng rỗng — đọc như đã làm, thực chất chưa',
    light: '#e8590c',
    dark: '#fd7e14',
    fg: '#ffffff',
    hatched: false,
    inDenominator: true,
  },
  'N/A': {
    band: 'N/A',
    label: 'N/A — không áp dụng được',
    meaning: 'bị loại khỏi CẢ tử lẫn mẫu. Không phải "rủi ro bằng không".',
    light: '#7048e8',
    dark: '#9775fa',
    fg: '#ffffff',
    hatched: true,
    inDenominator: false,
  },
  unknown: {
    band: 'unknown',
    label: 'unknown — chưa ai ghé',
    meaning: 'NẰM TRONG mẫu số và chấm 0. Khác hẳn N/A.',
    light: '#adb5bd',
    dark: '#5c5f66',
    fg: '#ffffff',
    hatched: false,
    inDenominator: true,
  },
};

export function bandColor(band: Band, scheme: 'light' | 'dark'): string {
  return scheme === 'dark' ? BAND_STYLES[band].dark : BAND_STYLES[band].light;
}

export function bandFg(band: Band): string {
  return BAND_STYLES[band].fg;
}

/**
 * Thứ tự để vẽ chú giải: từ phủ tốt nhất tới chưa ghé, và `N/A` tách ra cuối
 * cùng vì nó không cùng một trục đo với năm cái kia.
 */
export const BAND_LEGEND_ORDER: readonly Band[] = [
  'high',
  'med',
  'low',
  'stub',
  'unknown',
  'N/A',
];

/** Đếm mẫu số thật: tổng cell, số N/A bị loại, số cell còn lại vào mẫu. */
export interface DenominatorBreakdown {
  enumerated: number;
  na: number;
  scoreable: number;
  byBand: Record<Band, number>;
}

export function breakdownDenominator(bands: readonly Band[]): DenominatorBreakdown {
  const byBand: Record<Band, number> = {
    high: 0,
    med: 0,
    low: 0,
    stub: 0,
    'N/A': 0,
    unknown: 0,
  };
  for (const b of bands) byBand[b] += 1;
  return {
    enumerated: bands.length,
    na: byBand['N/A'],
    scoreable: bands.length - byBand['N/A'],
    byBand,
  };
}
