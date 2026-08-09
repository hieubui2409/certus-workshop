/**
 * Panel 4 — grid heatmap (SDD 08 §5.4).
 *
 * Màu KHÔNG phải một thang liên tục. Nó là HÀM CỦA BAND, vì band là biến hạng
 * mục — tô thang liên tục lên biến hạng mục là mời người đọc nội suy giữa
 * `stub` và `N/A`.
 *
 * Yêu cầu quan trọng nhất: `N/A` (tím, gạch chéo) phải phân biệt được NGAY TỪ
 * XA với `unknown` (xám). `N/A` bị loại khỏi CẢ tử lẫn mẫu; `unknown` NẰM
 * TRONG mẫu và chấm 0. Hai ô cùng sắc xám thì mẫu số tụt 17 → 13 trở nên vô
 * hình — và đó đúng là thứ buổi học cần sinh viên nhìn thấy.
 */

import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Group,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Title,
  useComputedColorScheme,
} from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { ResponsiveHeatMap, type HeatMapDatum } from '@nivo/heatmap';
import type { Band, Cell } from '@/types/contracts';
import { BAND_LEGEND_ORDER, BAND_STYLES, bandColor, breakdownDenominator } from '@/lib/bands';
import { axisDomains, buildSlices, sliceCoverage, type Slice } from '@/lib/slices';
import { CellDetail } from './CellDetail';

interface Datum extends HeatMapDatum {
  x: string;
  y: number | null;
  cell: Cell | null;
}

interface Props {
  cells: Cell[];
  /**
   * Số ô THẬT của lưới (từ bước `project_grid`). Khác `cells.length` khi backend
   * chạm trần phát ô — và khác cả `rowAxis × colAxis` khi lưới có hơn hai trục,
   * vì bản đồ nhiệt chỉ vẽ được một LÁT CẮT hai chiều.
   */
  totalCells?: number;
}

/** Điểm chỉ dùng để nivo có một giá trị số; MÀU không đọc từ nó. */
const BAND_ORDINAL: Record<Band, number> = {
  high: 5,
  med: 4,
  low: 3,
  stub: 2,
  unknown: 1,
  'N/A': 0,
};

export function GridHeatmap({ cells, totalCells }: Props) {
  const scheme = useComputedColorScheme('light');
  const [selected, setSelected] = useState<Cell | null>(null);
  const [sliceKey, setSliceKey] = useState<string | null>(null);

  const domains = useMemo(() => axisDomains(cells), [cells]);
  const slices = useMemo(() => buildSlices(cells), [cells]);
  const coverage = useMemo(() => sliceCoverage(cells, slices), [cells, slices]);

  // Lát đang xem phải BÁM theo dữ liệu: chạy lượt phân tích khác thì tập trục
  // đổi, và một `sliceKey` còn sót lại từ lượt trước trỏ vào hư không — màn
  // hình trắng, không lời giải thích. Giữ lựa chọn khi nó vẫn còn hợp lệ.
  useEffect(() => {
    if (slices.length === 0) {
      if (sliceKey !== null) setSliceKey(null);
      return;
    }
    if (!slices.some((s) => s.key === sliceKey)) setSliceKey(slices[0].key);
  }, [slices, sliceKey]);

  const slice = slices.find((s) => s.key === sliceKey) ?? slices[0] ?? null;

  const byKey = useMemo(() => {
    const map = new Map<string, Cell>();
    if (!slice) return map;
    for (const c of slice.cells) {
      map.set(`${c.axes[slice.rowAxis]}|${c.axes[slice.colAxis]}`, c);
    }
    return map;
  }, [slice]);

  const data = useMemo(
    () =>
      (slice?.rowValues ?? []).map((row) => ({
        id: row,
        data: (slice?.colValues ?? []).map((col): Datum => {
          const cell = byKey.get(`${row}|${col}`) ?? null;
          return {
            x: col,
            y: cell ? BAND_ORDINAL[cell.band] : null,
            cell,
          };
        }),
      })),
    [byKey, slice],
  );

  const breakdown = breakdownDenominator(cells.map((c) => c.band));
  const naCells = cells.filter((c) => c.band === 'N/A');

  // Ba con số dễ bị nhầm là một:
  //   `enumerated` — số ô THẬT của lưới (mẫu số của grid_coverage)
  //   `cells.length` — số ô giao diện nhận được (có thể ít hơn: backend chặn trần)
  //   `drawn` — số ô bản đồ nhiệt vẽ ra (một LÁT CẮT hai trục của lưới n chiều)
  // Nói ra cả ba khi chúng lệch, thay vì để người xem đếm ô trên hình rồi tin.
  const enumerated = totalCells ?? breakdown.enumerated;
  const drawn = slice ? slice.rowValues.length * slice.colValues.length : 0;
  const axisCount = domains.length;

  if (cells.length === 0 || !slice) {
    return (
      <Alert color="gray" variant="light" title="Chưa có ô nào">
        Chạy một lượt phân tích để sinh lưới.
      </Alert>
    );
  }

  return (
    <Stack gap="sm">
      <Box>
        <Title order={3}>Lưới rủi ro</Title>
        <Text size="sm" c="dimmed">
          Trục dọc: {slice.rowAxis} · trục ngang: {slice.colAxis}. Bấm vào một ô để xem chi tiết.
        </Text>
      </Box>

      <DenominatorTable
        enumerated={enumerated}
        na={breakdown.na}
        scoreable={enumerated - breakdown.na}
        excluded={0}
      />

      <SlicePicker
        slices={slices}
        value={slice.key}
        onChange={setSliceKey}
        enumerated={enumerated}
        unplaced={coverage.unplaced}
      />

      {drawn < enumerated && (
        <Alert
          color="orange"
          variant="light"
          icon={<IconAlertTriangle size={18} />}
          title={`Bản đồ nhiệt vẽ ${drawn}/${enumerated} ô — nó là MỘT LÁT CẮT, không phải cả lưới`}
        >
          <Text size="xs">
            Lưới có {axisCount} trục nên mẫu số thật là {enumerated} ô t-wise, chia thành{' '}
            {slices.length} lát cắt. Màn hình phẳng chỉ bày được hai chiều, nên hình dưới là lát cắt{' '}
            <Text span ff="monospace" fw={600}>
              {slice.rowAxis} × {slice.colAxis}
            </Text>
            {cells.length < enumerated && (
              <>
                {' '}
                — và giao diện mới nhận {cells.length}/{enumerated} ô (backend chặn trần số ô gửi
                lên)
              </>
            )}
            . Đừng đếm ô trên hình để suy ra mẫu số: con số đúng nằm ở khối “Ô được liệt kê” ngay
            trên và ở tab “Ba tầng mẫu số”.
          </Text>
        </Alert>
      )}

      {naCells.length > 0 && (
        <Alert
          color="red"
          variant="light"
          icon={<IconAlertTriangle size={18} />}
          title={`${naCells.length} ô mang band N/A — chúng đã rời khỏi mẫu số`}
        >
          <Text size="xs">
            N/A bị loại khỏi cả tử lẫn mẫu, nên mọi tỉ lệ phía sau được tính trên phần còn lại. Hãy
            mở từng ô và đọc cờ: N/A chỉ được phép vào qua constraints.yaml đã qua
            admit_constraint(). Cờ{' '}
            <Text span ff="monospace" fw={600}>
              na_from_analysis
            </Text>{' '}
            nghĩa là nó vào qua đường khác.
          </Text>
        </Alert>
      )}

      <Paper withBorder radius="md" p="xs">
        <Box h={340}>
          <ResponsiveHeatMap<Datum, object>
            data={data}
            margin={{ top: 60, right: 24, bottom: 24, left: 110 }}
            xInnerPadding={0.06}
            yInnerPadding={0.06}
            axisTop={{ tickSize: 5, tickPadding: 6, tickRotation: -25, legend: '', legendOffset: 46 }}
            axisLeft={{ tickSize: 5, tickPadding: 6, tickRotation: 0 }}
            axisRight={null}
            axisBottom={null}
            colors={(cell) =>
              cell.data.cell ? bandColor(cell.data.cell.band, scheme) : 'transparent'
            }
            emptyColor={scheme === 'dark' ? '#25262b' : '#f1f3f5'}
            borderWidth={2}
            borderColor={scheme === 'dark' ? '#1a1b1e' : '#ffffff'}
            enableLabels
            label={(cell) => cell.data.cell?.band ?? '—'}
            labelTextColor={(cell) =>
              cell.data.cell ? BAND_STYLES[cell.data.cell.band].fg : '#868e96'
            }
            hoverTarget="cell"
            animate={false}
            onClick={(cell) => setSelected(cell.data.cell)}
            tooltip={({ cell }) => (
              <Paper withBorder shadow="md" p="xs" radius="sm">
                {cell.data.cell ? (
                  <>
                    <Text size="xs" ff="monospace" fw={600}>
                      {cell.data.cell.id}
                    </Text>
                    <Text size="xs">
                      band: {cell.data.cell.band} · zone: {cell.data.cell.zone_id} (w ={' '}
                      {cell.data.cell.zone_w})
                    </Text>
                    <Text size="xs" c="dimmed">
                      {BAND_STYLES[cell.data.cell.band].meaning}
                    </Text>
                  </>
                ) : (
                  <Text size="xs">
                    Ô này KHÔNG được liệt kê vào lưới (exclude) — nó chưa từng vào mẫu số.
                  </Text>
                )}
              </Paper>
            )}
          />
        </Box>
      </Paper>

      <BandLegend scheme={scheme} excluded={0} />

      <CellDetail cell={selected} domains={domains} onClose={() => setSelected(null)} />
    </Stack>
  );
}

/**
 * Chọn lát cắt để xem — mỗi mục nói ra HAI TRỤC và phân bố band của chính nó.
 *
 * Con số nằm ngay trong mục là có chủ ý: chọn lát mù rồi mới biết nó có gì thì
 * người đứng lớp phải bấm qua cả sáu lát mới tìm được lát đáng chỉ. Ở đây họ
 * đọc thẳng "8 unknown" rồi mới bấm.
 *
 * `Select` chứ không phải tab: số lát là C(n,2) — 4 trục ra 6 lát, 6 trục ra
 * 15. Một hàng tab 15 mục thì cuộn ngang, và cái đang chọn trôi khỏi màn hình.
 */
function SlicePicker({
  slices,
  value,
  onChange,
  enumerated,
  unplaced,
}: {
  slices: Slice[];
  value: string;
  onChange: (key: string) => void;
  enumerated: number;
  unplaced: number;
}) {
  const label = (s: Slice) => {
    const parts = BAND_LEGEND_ORDER.filter((b) => s.counts[b] > 0).map(
      (b) => `${s.counts[b]} ${b}`,
    );
    return `${s.rowAxis} × ${s.colAxis} — ${s.cells.length} ô · ${parts.join(' · ')}`;
  };
  const total = slices.reduce((sum, s) => sum + s.cells.length, 0);

  return (
    <Paper withBorder p="sm" radius="md">
      <Select
        label={`Lát cắt đang xem — lưới này có ${slices.length} lát`}
        description={
          `Mỗi lát khoá đúng hai trục; ${slices.length} lát cộng lại là ${total}/${enumerated} ô của mẫu số. ` +
          'Chọn lát nào thì bản đồ nhiệt dưới chuyển sang đúng lát đó.'
        }
        data={slices.map((s) => ({ value: s.key, label: label(s) }))}
        value={value}
        onChange={(v) => v && onChange(v)}
        allowDeselect={false}
        checkIconPosition="right"
        comboboxProps={{ withinPortal: true }}
      />
      {unplaced > 0 && (
        <Text size="xs" c="orange" mt={6}>
          {unplaced} ô KHÔNG rơi vào lát nào ở trên (chúng không mang đúng hai trục). Duyệt hết mọi
          lát vẫn không gặp chúng — con số mẫu số đúng vẫn là {enumerated}.
        </Text>
      )}
    </Paper>
  );
}

function DenominatorTable({
  enumerated,
  na,
  scoreable,
  excluded,
}: {
  enumerated: number;
  na: number;
  scoreable: number;
  excluded: number;
}) {
  const items: { label: string; value: number; note: string; color: string }[] = [
    {
      label: 'Ô được liệt kê',
      value: enumerated,
      note: 'enumerate_t_wise(t=2) sau khi trừ exclude',
      color: 'certus',
    },
    {
      label: 'Ô không liệt kê (exclude)',
      value: excluded,
      note: 'bất khả thi theo constraints.yaml — chưa từng vào lưới',
      color: 'gray',
    },
    {
      label: 'Ô N/A',
      value: na,
      note: 'bị loại khỏi CẢ tử lẫn mẫu',
      color: 'violet',
    },
    {
      label: 'Ô thực sự vào mẫu',
      value: scoreable,
      note: 'mọi tỉ lệ phía sau chia cho con số này',
      color: 'red',
    },
  ];

  return (
    <SimpleGrid cols={{ base: 2, md: 4 }} spacing="xs">
      {items.map((it) => (
        <Paper key={it.label} withBorder p="xs" radius="md">
          <Text size="xs" c="dimmed">
            {it.label}
          </Text>
          <Text fz={24} fw={700} ff="monospace" c={it.color} lh={1.1}>
            {it.value}
          </Text>
          <Text size="xs" c="dimmed">
            {it.note}
          </Text>
        </Paper>
      ))}
    </SimpleGrid>
  );
}

function BandLegend({ scheme, excluded }: { scheme: 'light' | 'dark'; excluded: number }) {
  return (
    <Paper withBorder p="sm" radius="md">
      <Text size="xs" fw={600} mb={6}>
        Chú giải — cột cuối là bài học
      </Text>
      <Stack gap={4}>
        {BAND_LEGEND_ORDER.map((band) => {
          const style = BAND_STYLES[band];
          return (
            <Group key={band} gap="xs" wrap="nowrap" align="center">
              <Box
                w={26}
                h={16}
                style={{
                  borderRadius: 3,
                  flexShrink: 0,
                  background: style.hatched
                    ? `repeating-linear-gradient(45deg, ${bandColor(band, scheme)}, ${bandColor(band, scheme)} 4px, rgba(255,255,255,0.55) 4px, rgba(255,255,255,0.55) 7px)`
                    : bandColor(band, scheme),
                }}
              />
              <Text size="xs" ff="monospace" w={44}>
                {band}
              </Text>
              <Text size="xs" style={{ flex: 1 }}>
                {style.meaning}
              </Text>
              <Badge size="xs" color={style.inDenominator ? 'blue' : 'violet'} variant="light">
                {style.inDenominator ? 'trong mẫu số' : 'ngoài mẫu số'}
              </Badge>
            </Group>
          );
        })}
        <Group gap="xs" wrap="nowrap" align="center">
          <Box
            w={26}
            h={16}
            style={{
              borderRadius: 3,
              flexShrink: 0,
              background: scheme === 'dark' ? '#25262b' : '#f1f3f5',
              border: '1px dashed var(--mantine-color-dimmed)',
            }}
          />
          <Text size="xs" ff="monospace" w={44}>
            exclude
          </Text>
          <Text size="xs" style={{ flex: 1 }}>
            {excluded} ô bất khả thi theo constraints.yaml — chưa từng được liệt kê.
          </Text>
          <Badge size="xs" color="gray" variant="light">
            ngoài mẫu số
          </Badge>
        </Group>
      </Stack>
    </Paper>
  );
}
