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
 * Rút phần `"answer": "…"` ra khỏi một chuỗi JSON CÒN DANG DỞ.
 *
 * Cần hàm này vì token bây giờ chảy thật (backend phát từng mẩu trong lúc mô
 * hình viết, không dồn ra cuối). Nếu chỉ `JSON.parse` được bản hoàn chỉnh thì
 * suốt mấy chục giây người dùng nhìn thấy JSON thô đang bò ra — tệ hơn cả im
 * lặng, vì nó trông như hệ thống hỏng.
 *
 * Quét thủ công thay vì parse: cắt từ dấu `"` mở của giá trị, đọc tới dấu `"`
 * đóng chưa-thoát (nếu chưa có thì lấy hết những gì đã tới), rồi giải mã escape.
 * Trả `null` khi chưa thấy khoá `answer` — người gọi tự quyết hiển thị gì.
 */
function partialAnswer(raw: string): string | null {
  const at = raw.search(/"answer"\s*:\s*"/);
  if (at < 0) return null;
  const start = raw.indexOf('"', raw.indexOf(':', at)) + 1;
  let out = '';
  for (let i = start; i < raw.length; i += 1) {
    const ch = raw[i];
    if (ch === '\\') {
      const nxt = raw[i + 1];
      if (nxt === undefined) break; // escape bị cắt giữa chừng — dừng, chờ mẩu sau
      out +=
        nxt === 'n' ? '\n'
        : nxt === 't' ? '\t'
        : nxt === 'r' ? '\r'
        : nxt === 'u' ? String.fromCharCode(parseInt(raw.slice(i + 2, i + 6), 16) || 0)
        : nxt;
      i += nxt === 'u' ? 5 : 1;
      continue;
    }
    if (ch === '"') break; // hết giá trị
    out += ch;
  }
  return out;
}

/**
 * Bước diễn giải của backend thật bắt mô hình trả một object JSON
 * `{nonce, answer, claims}`; `event: token` stream NGUYÊN văn JSON đó. Lượt xong
 * thì parse đàng hoàng; lượt đang chạy thì rút tạm phần `answer` đã tới.
 * Mock/live phát prose thẳng (không mở `{`) nên trả nguyên.
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
    /* JSON chưa hoàn chỉnh (đang stream) — rút tạm phần đã tới */
  }
  return partialAnswer(trimmed) ?? '';
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
  const shown = displayAnswer(answer);

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

      {/* Điều kiện rỗng phải xét chuỗi ĐÃ RÚT, không phải chuỗi thô: những mẩu
          đầu của một câu trả lời JSON là `{"nonce": …` — có độ dài nhưng chưa có
          chữ nào cho người đọc. Xét chuỗi thô thì ô hiện trống trơn thay vì báo
          đang chờ. */}
      <Paper withBorder p="md" radius="md" mih={180}>
        {shown.length === 0 ? (
          <Text size="sm" c="dimmed">
            {running ? 'Đang chờ token đầu tiên…' : 'Câu trả lời sẽ hiện dần ở đây.'}
          </Text>
        ) : (
          <ScrollArea.Autosize mah={340} type="auto">
            <Box style={{ whiteSpace: 'pre-wrap' }}>
              <Text size="sm">
                {shown}
                {/* Con trỏ nháy: dấu hiệu "còn đang viết", cùng animation với
                    khung chat. Keyframe khai tại chỗ vì dự án chưa có CSS toàn cục. */}
                {running && (
                  <>
                    <Box
                      component="span"
                      ml={2}
                      style={{
                        display: 'inline-block',
                        width: '0.5em',
                        borderBottom: '2px solid currentColor',
                        animation: 'certus-caret 1s steps(2) infinite',
                      }}
                    />
                    <style>{'@keyframes certus-caret{50%{opacity:0}}'}</style>
                  </>
                )}
              </Text>
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
