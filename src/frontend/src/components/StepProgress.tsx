/**
 * Tiến trình 8 bước của `analyze_pipeline` (system-design §4).
 *
 * Mỗi bước phát một SSE event nên UI thấy được tiến trình. Bước bị `skipped`
 * hiện khác hẳn bước `ok`: một bước bị bỏ qua mà đọc như một bước đã chạy là
 * cách nửa pipeline biến mất trong im lặng.
 */

import { Badge, Group, Paper, Stack, Text } from '@mantine/core';
import type { StepPayload } from '@/types/sse';

/** Tên bước theo system-design §4 — 8 bước, thứ tự là hợp đồng. */
const STEP_NAMES: Record<number, string> = {
  1: 'Ingest — giải nén, lọc theo data policy',
  2: 'Đóng băng axes',
  3: 'Sinh cell (t-wise)',
  4: 'Chạy bộ kiểm + coverage',
  5: 'Mutation',
  6: 'Project band (0 lời gọi LLM)',
  7: 'Gate chain — 5 cổng',
  8: 'Tổng hợp & trả lời',
};

interface Props {
  steps: StepPayload[];
}

export function StepProgress({ steps }: Props) {
  /** Trạng thái CUỐI CÙNG của mỗi bước; danh sách event gốc không bị sửa. */
  const latest = new Map<number, StepPayload>();
  for (const s of steps) latest.set(s.step, s);

  return (
    <Paper withBorder p="sm" radius="md">
      <Text size="xs" fw={600} mb={6}>
        Pipeline — 8 bước
      </Text>
      <Stack gap={4}>
        {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => {
          const step = latest.get(n);
          const status = step?.status ?? 'chưa chạy';
          const color =
            status === 'ok'
              ? 'green'
              : status === 'running'
                ? 'blue'
                : status === 'failed'
                  ? 'red'
                  : status === 'skipped'
                    ? 'orange'
                    : 'gray';
          return (
            <Group key={n} gap="xs" wrap="nowrap">
              <Badge size="xs" color={color} variant="light" w={26} ff="monospace">
                {n}
              </Badge>
              <Text size="xs" style={{ flex: 1 }} c={step ? undefined : 'dimmed'}>
                {STEP_NAMES[n]}
              </Text>
              <Badge size="xs" color={color} variant={status === 'ok' ? 'light' : 'filled'}>
                {status}
              </Badge>
            </Group>
          );
        })}
      </Stack>
    </Paper>
  );
}
