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

import { Alert, Badge, Code, Group, Paper, Stack, Text } from '@mantine/core';
import type { ErrorPayload, StepPayload } from '@/types/sse';
import { BouncingDots } from './StreamingIndicator';

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
  /** Lỗi có cấu trúc backend đã phát. Nó DỪNG pipeline, nên bảng phải nói ra. */
  error?: ErrorPayload | null;
  /** Lượt chạy còn đang mở (`store.status === 'running'`). */
  running?: boolean;
}

export function StepProgress({ steps, error, running = false }: Props) {
  /** Trạng thái CUỐI CÙNG của mỗi bước; danh sách event gốc không bị sửa. */
  const latest = new Map<number, StepPayload>();
  for (const s of steps) latest.set(s.step, s);

  // Hai cách viết cùng một trạng thái: backend thật phát `done` (mặc định của
  // `_step`), mock phát `ok`. Nhận cả hai, không thì một lượt chạy trên backend
  // thật hiện xám toàn bộ trong khi mọi bước đã xong.
  const isDone = (st: string | undefined) => st === 'ok' || st === 'done';

  // Bước đầu tiên chưa xong khi lỗi nổ = bước đã CHẾT. Không có phép quy này
  // thì backend nói "bộ kiểm không chạy được" mà bảng vẫn hiện bước 4 "chưa
  // chạy" và bước 5–9 y hệt — người đọc kết luận hệ thống treo, trong khi nó
  // đã dừng có lý do và đã nói ra lý do. Im lặng ở đây tệ hơn cả báo sai: nó
  // biến một lỗi môi trường đọc được thành một sự cố không tên.
  const failedAt = error ? STEP_ORDER.find((n) => !isDone(latest.get(n)?.status)) : undefined;

  // Backend phát event cho một bước KHI BƯỚC ĐÓ XONG (`_step` mặc định
  // `status="done"`), không phát lúc bắt đầu. Nên bước đang chạy không có event
  // nào, và bảng in "chưa chạy" cho nó — kể cả bước 4 chạy bộ kiểm mất vài phút
  // trên repo thật. Người xem nhìn thấy một bảng đứng im và kết luận đã treo.
  //
  // Pipeline chạy TUẦN TỰ theo STAGES, nên "bước chưa xong đầu tiên trong khi
  // lượt chạy còn mở" chính là bước đang chạy. Suy ở UI chứ không thêm event
  // mới ở backend: cassette khoá theo nội dung, thêm event là đổi cả bộ ghi đã
  // thu cho 1000 sinh viên.
  const runningAt =
    running && !error ? STEP_ORDER.find((n) => !isDone(latest.get(n)?.status)) : undefined;

  return (
    <Paper withBorder p="sm" radius="md">
      <Text size="xs" fw={600} mb={6}>
        Pipeline — 9 bước
      </Text>
      <Stack gap={4}>
        {STEP_ORDER.map((n) => {
          const step = latest.get(n);
          let status = step?.status ?? 'chưa chạy';
          if (error && n === failedAt) status = 'failed';
          else if (error && failedAt !== undefined && n > failedAt) status = 'skipped';
          else if (n === runningAt) status = 'running';
          const color =
            isDone(status)
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
              {status === 'running' ? (
                // Bước đang chạy là bước duy nhất người xem cần biết CÓ đang
                // nhúc nhích không — bước 4 (chạy bộ kiểm) mất vài phút trên repo
                // thật, và một chữ "running" đứng im ở đó đọc y như đã treo.
                <Badge size="xs" color={color} variant="filled" pl={6} pr={8}>
                  <Group gap={5} wrap="nowrap" align="center">
                    <BouncingDots size={3} color="currentColor" />
                    <span>đang chạy</span>
                  </Group>
                </Badge>
              ) : (
                <Badge size="xs" color={color} variant={isDone(status) ? 'light' : 'filled'}>
                  {status}
                </Badge>
              )}
            </Group>
          );
        })}
      </Stack>
      {error && (
        // Câu backend viết ra được in NGUYÊN VĂN, không tóm tắt: nó đã nêu môi
        // trường đã dùng, lệnh đã chạy và đuôi log. Tóm tắt lại ở đây là ném đi
        // đúng phần giúp người dùng sửa được.
        <Alert color="red" variant="light" mt="sm" p="xs" title={error.code}>
          {/* `overflowWrap: anywhere` vì thông điệp này chứa lệnh và URL dài
              không có khoảng trắng để ngắt: `pre-wrap` một mình để chúng chạy
              thẳng ra ngoài khung, và phần khuất luôn là phần đuôi — đúng chỗ
              đặt cổng, tên DB, tên biến cần khai. */}
          <Code
            block
            style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 11 }}
          >
            {error.msg}
          </Code>
        </Alert>
      )}
    </Paper>
  );
}
