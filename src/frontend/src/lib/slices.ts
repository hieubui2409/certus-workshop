/**
 * Lưới n trục → danh sách LÁT CẮT hai trục, và tư cách của một ô trong đó.
 *
 * Vì sao tách khỏi `GridHeatmap.tsx`: đây là số học của MẪU SỐ, không phải
 * chuyện vẽ. Trước bản này bản đồ nhiệt suy hai trục bằng `Object.keys` của ô
 * ĐẦU TIÊN — nên nó vẽ đúng một lát cắt và năm lát còn lại không có đường nào
 * để xem. Với `shopcart` (4 trục) đo được 6 lát: C(4,2).
 *
 * ĐIỀU DỄ HIỂU SAI NHẤT, và là lý do file này viết dài:
 *
 *   Ở `t=2` một ô mang ĐÚNG HAI trục, không phải mọi trục của lưới.
 *   `cell:customer_tier=standard|shipping_zone=domestic` KHÔNG mang giá trị nào
 *   cho `payment_method`. Đó không phải dữ liệu thiếu — đó là toàn bộ ý nghĩa
 *   của phủ t-wise: ô ấy nói "cặp (standard, domestic) đã được chạm", và nó
 *   đúng như thế BẤT KỂ payment_method là gì.
 *
 * Nên khi người dùng bấm vào ô, thứ đúng đắn để hiện KHÔNG phải "giá trị của
 * các trục khác" (không tồn tại giá trị nào để hiện, và bịa ra một cái là đúng
 * loại lỗi sản phẩm này sinh ra để chống) mà là: trục nào ĐANG KHOÁ, trục nào
 * KHÔNG RÀNG BUỘC, và miền giá trị mà ô đang gộp qua.
 */

import type { Band, Cell } from '@/types/contracts';
import { BAND_LEGEND_ORDER } from './bands';

/** Một lát cắt hai trục của lưới — đơn vị mà bản đồ nhiệt vẽ được. */
export interface Slice {
  /** `<rowAxis>×<colAxis>` — ổn định, dùng làm khoá React và giá trị Select */
  key: string;
  rowAxis: string;
  colAxis: string;
  rowValues: string[];
  colValues: string[];
  /** ô thuộc chính lát này (mang đúng cặp trục này) */
  cells: Cell[];
  /** đếm theo band, đủ 6 khoá kể cả khi bằng 0 — bảng thưa đọc như bảng đầy */
  counts: Record<Band, number>;
}

/** Trục của lưới và miền giá trị của nó, gom qua TẤT CẢ các ô. */
export interface AxisDomain {
  name: string;
  values: string[];
}

/**
 * Miền giá trị từng trục, gom qua mọi ô.
 *
 * Phải quét hết chứ không đọc ô đầu: ở `t=2` ô đầu chỉ biết hai trục, nên đọc
 * mình nó thì một lưới 4 trục tự khai là lưới 2 trục.
 */
export function axisDomains(cells: readonly Cell[]): AxisDomain[] {
  const order: string[] = [];
  const seen = new Map<string, Set<string>>();
  for (const cell of cells) {
    for (const [axis, value] of Object.entries(cell?.axes ?? {})) {
      let bucket = seen.get(axis);
      if (!bucket) {
        bucket = new Set();
        seen.set(axis, bucket);
        order.push(axis);
      }
      if (value != null) bucket.add(value);
    }
  }
  return order.map((name) => ({ name, values: [...(seen.get(name) ?? [])] }));
}

function emptyCounts(): Record<Band, number> {
  const counts = {} as Record<Band, number>;
  for (const band of BAND_LEGEND_ORDER) counts[band] = 0;
  return counts;
}

/**
 * Nhóm ô thành các lát cắt hai trục.
 *
 * Lát cắt suy TỪ CHÍNH các ô đang có, không từ tích C(n,2) của danh sách trục:
 * một cặp trục không sinh ô nào thì cũng không có gì để vẽ, và bày một mục rỗng
 * trong hộp chọn chỉ dẫn người ta tới một màn hình trắng.
 *
 * Ô mang số trục khác 2 (lưới bậc khác, hoặc dữ liệu hỏng) bị bỏ qua ở ĐÂY và
 * được đếm lại ở `sliceCoverage()` — bỏ im lặng thì tổng số ô các lát cộng lại
 * ít hơn mẫu số thật mà không ai giải thích được vì sao.
 */
export function buildSlices(cells: readonly Cell[]): Slice[] {
  const groups = new Map<string, Cell[]>();
  for (const cell of cells) {
    const axes = Object.keys(cell?.axes ?? {});
    if (axes.length !== 2) continue;
    const key = `${axes[0]}×${axes[1]}`;
    const bucket = groups.get(key);
    if (bucket) bucket.push(cell);
    else groups.set(key, [cell]);
  }

  const slices: Slice[] = [];
  for (const [key, group] of groups) {
    const [rowAxis, colAxis] = key.split('×');
    const distinct = (axis: string) => {
      const out: string[] = [];
      for (const c of group) {
        const v = c.axes[axis];
        if (v != null && !out.includes(v)) out.push(v);
      }
      return out;
    };
    const counts = emptyCounts();
    for (const c of group) counts[c.band] += 1;
    slices.push({
      key,
      rowAxis,
      colAxis,
      rowValues: distinct(rowAxis),
      colValues: distinct(colAxis),
      cells: group,
      counts,
    });
  }
  return slices;
}

/**
 * Ô các lát cắt cộng lại có bằng số ô nhận được không.
 *
 * Tồn tại vì hộp chọn lát cắt là một chỗ mẫu số có thể co lại trong im lặng:
 * người dùng duyệt hết mọi lát mà vẫn không gặp một số ô, và màn hình không có
 * chỗ nào nói ra điều đó. `unplaced > 0` là câu nói ra.
 */
export function sliceCoverage(
  cells: readonly Cell[],
  slices: readonly Slice[],
): { placed: number; unplaced: number } {
  const placed = slices.reduce((sum, s) => sum + s.cells.length, 0);
  return { placed, unplaced: cells.length - placed };
}

/** Tư cách của một trục đối với MỘT ô cụ thể. */
export interface AxisRole {
  name: string;
  /** giá trị ô khoá ở trục này; `null` khi ô không ràng buộc trục này */
  value: string | null;
  locked: boolean;
  /** miền giá trị của trục trong cả lưới — ô không khoá thì gộp qua toàn miền */
  domain: string[];
}

/**
 * Xếp mọi trục của lưới thành KHOÁ / KHÔNG RÀNG BUỘC đối với một ô.
 *
 * Trục khoá đứng trước, đúng thứ tự `cell.axes` (thứ tự axis lock — cùng thứ tự
 * làm nên `cell.id`, nên bảng đọc khớp với chuỗi id ngay trên nó).
 */
export function axisRoles(cell: Cell, domains: readonly AxisDomain[]): AxisRole[] {
  const locked = Object.keys(cell?.axes ?? {});
  const domainOf = (name: string) => domains.find((d) => d.name === name)?.values ?? [];
  return [
    ...locked.map((name) => ({
      name,
      value: cell.axes[name],
      locked: true,
      domain: domainOf(name),
    })),
    ...domains
      .filter((d) => !locked.includes(d.name))
      .map((d) => ({ name: d.name, value: null, locked: false, domain: d.values })),
  ];
}
