/**
 * Panel 2 — hỏi đáp có stream (SDD 08 §5.2).
 *
 * Nhận `event: token` và render dần. KHÔNG markdown-render toàn phần: nội dung
 * này đến từ mô hình, mà mô hình vừa đọc dữ liệu không tin cậy (mã nguồn người
 * dùng upload). Render nó như văn bản thuần, giữ xuống dòng, là đủ.
 */

import { Badge, Box, Button, Group, Paper, ScrollArea, Stack, Text, Textarea, Title } from '@mantine/core';
import { IconPlayerPlay, IconPlayerStop } from '@tabler/icons-react';
import type { RunStatus } from '@/store/analysisStore';

interface Props {
  question: string;
  onQuestionChange: (value: string) => void;
  onRun: () => void;
  onStop: () => void;
  status: RunStatus;
  answer: string;
  disabled: boolean;
}

/** Câu hỏi gợi ý — mỗi câu dẫn tới một triệu chứng khác nhau trên UI. */
const SUGGESTIONS = [
  'Bộ kiểm thử của tôi phủ tới đâu?',
  'Tiêu chuẩn nào quy định ngưỡng branch coverage tối thiểu?',
  'Có góc rủi ro nào chưa ai nhìn không?',
];

/**
 * Bước diễn giải của backend thật bắt mô hình trả một object JSON
 * `{nonce, answer, claims}`; `event: token` stream NGUYÊN văn JSON đó. Khi lượt
 * đã xong, chuỗi là JSON hoàn chỉnh — lấy đúng phần `answer` (prose) để hiển thị.
 * Mock phát prose thẳng (không mở `{`) nên bỏ qua; JSON đang stream dở parse
 * lỗi nên cũng bỏ qua — người dùng thấy nó hình thành rồi snap về prose khi xong.
 * KHÔNG đụng tới `claims`: chúng có bảng riêng ở Claim inspector.
 */
function displayAnswer(answer: string): string {
  const trimmed = answer.trim();
  if (!trimmed.startsWith('{')) return answer;
  try {
    const obj = JSON.parse(trimmed) as { answer?: unknown };
    if (obj && typeof obj === 'object' && typeof obj.answer === 'string') {
      return obj.answer;
    }
  } catch {
    /* JSON chưa hoàn chỉnh (đang stream) — giữ thô cho tới khi lượt xong */
  }
  return answer;
}

export function ChatPanel({
  question,
  onQuestionChange,
  onRun,
  onStop,
  status,
  answer,
  disabled,
}: Props) {
  const running = status === 'running';

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="center">
        <Title order={3}>Hỏi CERTUS</Title>
        <Badge
          color={running ? 'blue' : status === 'error' ? 'red' : status === 'done' ? 'green' : 'gray'}
          variant="light"
        >
          {running ? 'đang chạy' : status === 'done' ? 'xong' : status === 'error' ? 'lỗi' : 'chờ'}
        </Badge>
      </Group>

      <Textarea
        value={question}
        onChange={(e) => onQuestionChange(e.currentTarget.value)}
        placeholder="Ví dụ: bộ kiểm thử của tôi phủ tới đâu?"
        autosize
        minRows={2}
        maxRows={5}
        disabled={running}
      />

      <Group gap="xs">
        {SUGGESTIONS.map((s) => (
          <Button
            key={s}
            size="compact-xs"
            variant="subtle"
            disabled={running}
            onClick={() => onQuestionChange(s)}
          >
            {s}
          </Button>
        ))}
      </Group>

      <Group gap="xs">
        <Button
          leftSection={<IconPlayerPlay size={16} />}
          onClick={onRun}
          disabled={disabled || running}
        >
          Chạy phân tích
        </Button>
        {running && (
          <Button
            variant="light"
            color="red"
            leftSection={<IconPlayerStop size={16} />}
            onClick={onStop}
          >
            Dừng
          </Button>
        )}
      </Group>

      {disabled && (
        <Text size="xs" c="dimmed">
          Hãy chọn một repo mẫu hoặc tải lên tệp .zip trước.
        </Text>
      )}

      <Paper withBorder p="md" radius="md" mih={180}>
        {answer.length === 0 ? (
          <Text size="sm" c="dimmed">
            {running ? 'Đang chờ token đầu tiên…' : 'Câu trả lời sẽ hiện dần ở đây.'}
          </Text>
        ) : (
          <ScrollArea.Autosize mah={340} type="auto">
            <Box style={{ whiteSpace: 'pre-wrap' }}>
              <Text size="sm">{displayAnswer(answer)}</Text>
            </Box>
          </ScrollArea.Autosize>
        )}
      </Paper>

      <Text size="xs" c="dimmed">
        Đoạn văn trên do mô hình viết. Mọi con số trong đó phải đối chiếu được với Claim inspector —
        mô hình được phép diễn đạt, nó không được phép cấp số.
      </Text>
    </Stack>
  );
}
