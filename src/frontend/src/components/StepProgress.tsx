/**
 * Tiến trình các bước của `analyze_pipeline`.
 *
 * Mỗi bước phát một SSE event nên UI thấy được tiến trình. Bước bị `skipped`
 * hiện khác hẳn bước `ok`: một bước bị bỏ qua mà đọc như một bước đã chạy là
 * cách nửa pipeline biến mất trong im lặng.
 *
 * Số + tên ở đây phải KHỚP TỪNG-BƯỚC với `STAGES` của backend
 * (`orchestrator/pipeline.py`): `_step` phát `step = STAGES.index(name)+1`. Trước
 * đây bảng này là một mô hình "8 bước" khác — có "Mutation" mà STAGES không có, và
 * lệch số ở bước 5/8 — nên hai bước thật (`read_coverage`, `run_gates`) luôn hiện
 * "chưa chạy". Bảng này giờ phản chiếu đúng 9 stage thật sự chạy.
 */

import { Badge, Group, Paper, Stack, Text } from '@mantine/core';
import type { StepPayload } from '@/types/sse';

/** Khớp 1-1 với STAGES của backend — thứ tự là hợp đồng. */
const STEP_NAMES: Record<number, string> = {
  1: 'Ingest — chọn repo, giải nén',
  2: 'Lọc theo chính sách dữ liệu',
  3: 'Đóng băng axes',
  4: 'Chạy bộ kiểm',
  5: 'Đọc coverage (phủ dòng)',
  6: 'Sinh cell + project band',
  7: 'Rollup risk-weighted + per-zone',
  8: 'Gate chain — sàn per-zone',
  9: 'Tổng hợp & trả lời (LLM)',
};

const STEP_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9];

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
        Pipeline — 9 bước
      </Text>
      <Stack gap={4}>
        {STEP_ORDER.map((n) => {
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
