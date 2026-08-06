/**
 * Panel 8 — "Dữ liệu đã gửi cho mô hình" (SDD 08 §5.8).
 *
 * Liệt kê file + ĐOẠN NỘI DUNG THỰC SỰ đi vào prompt. Không phải toàn bộ file:
 * thứ đi vào prompt mới là thứ rời khỏi hạ tầng.
 *
 * Panel này nằm ở TAB PHỤ và MẶC ĐỊNH ĐÓNG. Đó không phải sơ suất thiết kế mà
 * là đặc tả của lỗi 8 (workshop-plan §3): "panel này nằm ở tab phụ, mặc định
 * đóng". Bài học là một panel đúng mà không ai mở thì bằng không có — sinh
 * viên phải tự phát hiện ra nó trong lúc truy dấu `sk_live`.
 */

import { Accordion, Alert, Badge, Box, Code, Group, Paper, Stack, Text, Title } from '@mantine/core';
import { IconEyeOff } from '@tabler/icons-react';
import type { PromptPayload } from '@/types/api';

interface Props {
  payload: PromptPayload | null;
  loading?: boolean;
}

export function PromptDataPanel({ payload, loading }: Props) {
  if (loading) return <Text size="sm">Đang tải…</Text>;

  if (!payload) {
    return (
      <Alert color="gray" variant="light" title="Chưa có payload nào">
        Chạy một lượt phân tích để xem đúng những gì đã được gửi đi.
      </Alert>
    );
  }

  return (
    <Stack gap="sm">
      <Box>
        <Title order={3}>Dữ liệu đã gửi cho mô hình</Title>
        <Text size="sm" c="dimmed">
          Đây là nội dung ĐÃ RỜI KHỎI máy bạn ở bước {payload.step}, tới model {payload.model}.
        </Text>
      </Box>

      <Group gap="xs">
        <Badge variant="light" ff="monospace">
          {payload.run_id}
        </Badge>
        <Badge variant="light" color="gray">
          {payload.chunks.length} đoạn · {payload.total_chars} ký tự
        </Badge>
      </Group>

      <Alert color="orange" variant="light" icon={<IconEyeOff size={18} />}>
        <Text size="xs">
          Danh sách này luôn có mặt trong sản phẩm, nhưng nó nằm ở tab phụ và mặc định đóng. Hãy đối
          chiếu từng dòng dưới đây với danh sách "đã loại" ở panel nạp mã nguồn: một tệp có mặt ở
          đây mà không có mặt ở đó nghĩa là danh sách chặn đã không giữ nó lại.
        </Text>
      </Alert>

      <Paper withBorder p="sm" radius="md">
        <Text size="xs" fw={600} mb={4}>
          Trích system prompt
        </Text>
        <Code block>{payload.system_prompt_excerpt}</Code>
      </Paper>

      <Accordion variant="separated" radius="md" multiple defaultValue={[]}>
        {payload.chunks.map((chunk) => (
          <Accordion.Item key={`${chunk.order}-${chunk.path}`} value={`${chunk.order}`}>
            <Accordion.Control>
              <Group gap="xs" wrap="nowrap">
                <Badge size="xs" variant="light" color="gray" ff="monospace">
                  #{chunk.order}
                </Badge>
                <Text size="sm" ff="monospace" fw={600}>
                  {chunk.path}
                </Text>
                <Badge size="xs" variant="light" color="gray">
                  {chunk.chars} ký tự
                </Badge>
                <Badge size="xs" color={chunk.redacted ? 'green' : 'red'} variant="light">
                  {chunk.redacted ? 'đã redact' : 'chưa redact'}
                </Badge>
              </Group>
            </Accordion.Control>
            <Accordion.Panel>
              <Code block style={{ whiteSpace: 'pre-wrap' }}>
                {chunk.excerpt}
              </Code>
            </Accordion.Panel>
          </Accordion.Item>
        ))}
      </Accordion>
    </Stack>
  );
}
