/**
 * Dòng cảnh báo — LUẬT HIỂN THỊ SỐ MỘT của cả frontend (SDD 00 §5).
 *
 *   "A silent number is easy to ignore.
 *    A line reading `WARNING: judge biased toward passing` is not."
 *
 * Nên mỗi `event: warning` ở đây là MỘT DÒNG CHỮ ĐỌC ĐƯỢC: mã · tiêu đề thành
 * câu · giải thích vì sao con số bên cạnh không đọc như nó trông · và nguyên
 * văn `msg` của backend, không rút gọn.
 *
 * KHÔNG có nút đóng. Một cảnh báo tắt được là một cảnh báo sẽ bị tắt.
 */

import { Alert, Badge, Group, Paper, ScrollArea, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconInfoCircle, IconShieldCheck } from '@tabler/icons-react';
import type { WarningPayload } from '@/types/sse';
import { describeWarning, MANDATORY_WARNING_CODES, severityColor } from '@/lib/warnings';

interface Props {
  warnings: WarningPayload[];
}

export function WarningFeed({ warnings }: Props) {
  const missing = MANDATORY_WARNING_CODES.filter(
    (code) => !warnings.some((w) => w.code === code),
  );

  return (
    <Paper withBorder p="md" radius="md" h="100%">
      <Stack gap="sm" h="100%">
        <Group justify="space-between" align="center">
          <Title order={4}>Cảnh báo</Title>
          <Badge color={warnings.length > 0 ? 'red' : 'gray'} variant="filled">
            {warnings.length}
          </Badge>
        </Group>

        <Text size="xs" c="dimmed">
          Mỗi cảnh báo là một dòng chữ đọc được, không phải một biểu tượng nhỏ. Danh sách này không
          đóng được: một con số im lặng thì dễ bỏ qua, một dòng chữ thì không.
        </Text>

        {warnings.length === 0 && (
          <Alert
            color="gray"
            variant="light"
            icon={<IconShieldCheck size={18} />}
            title="Chưa có cảnh báo nào"
          >
            Chạy một lượt phân tích để xem các cờ mà pipeline phát ra.
          </Alert>
        )}

        <ScrollArea.Autosize mah={620} type="auto" offsetScrollbars>
          <Stack gap="xs">
            {warnings.map((w, i) => {
              const style = describeWarning(w.code);
              const color = severityColor(style.severity);
              return (
                <Alert
                  key={`${w.code}-${i}`}
                  color={color}
                  variant="light"
                  icon={
                    style.severity === 'info' ? (
                      <IconInfoCircle size={18} />
                    ) : (
                      <IconAlertTriangle size={18} />
                    )
                  }
                  title={
                    <Group gap="xs" wrap="nowrap">
                      <Badge size="xs" color={color} ff="monospace">
                        {w.code}
                      </Badge>
                      <Text fw={600} size="sm">
                        {style.title}
                      </Text>
                    </Group>
                  }
                >
                  <Text size="xs" mb={4}>
                    {style.explain}
                  </Text>
                  <Text size="xs" c="dimmed" ff="monospace">
                    {w.msg}
                  </Text>
                </Alert>
              );
            })}
          </Stack>
        </ScrollArea.Autosize>

        {warnings.length > 0 && missing.length > 0 && (
          <Text size="xs" c="dimmed">
            Chưa thấy trong lượt này: {missing.join(' · ')}
          </Text>
        )}
      </Stack>
    </Paper>
  );
}
