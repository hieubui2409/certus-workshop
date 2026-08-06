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

import { useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Group,
  Paper,
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
import { MOCK_AXES, MOCK_EXCLUDED } from '@/api/mock';
import { CellDetail } from './CellDetail';

interface Datum extends HeatMapDatum {
  x: string;
  y: number | null;
  cell: Cell | null;
}

interface Props {
  cells: Cell[];
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

export function GridHeatmap({ cells }: Props) {
  const scheme = useComputedColorScheme('light');
  const [selected, setSelected] = useState<Cell | null>(null);

  const rowAxis = MOCK_AXES[0];
  const colAxis = MOCK_AXES[1];

  const byKey = useMemo(() => {
    const map = new Map<string, Cell>();
    for (const c of cells) {
      map.set(`${c.axes[rowAxis.name]}|${c.axes[colAxis.name]}`, c);
    }
    return map;
  }, [cells, rowAxis.name, colAxis.name]);

  const data = useMemo(
    () =>
      rowAxis.values.map((row) => ({
        id: row,
        data: colAxis.values.map((col): Datum => {
          const cell = byKey.get(`${row}|${col}`) ?? null;
          return {
            x: col,
            y: cell ? BAND_ORDINAL[cell.band] : null,
            cell,
          };
        }),
      })),
    [byKey, rowAxis.values, colAxis.values],
  );

  const breakdown = breakdownDenominator(cells.map((c) => c.band));
  const naCells = cells.filter((c) => c.band === 'N/A');

  if (cells.length === 0) {
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
          Trục dọc: {rowAxis.name} · trục ngang: {colAxis.name}. Bấm vào một ô để xem chi tiết.
        </Text>
      </Box>

      <DenominatorTable
        enumerated={breakdown.enumerated}
        na={breakdown.na}
        scoreable={breakdown.scoreable}
        excluded={MOCK_EXCLUDED.length}
      />

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

      <BandLegend scheme={scheme} excluded={MOCK_EXCLUDED.length} />

      <CellDetail cell={selected} onClose={() => setSelected(null)} />
    </Stack>
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
