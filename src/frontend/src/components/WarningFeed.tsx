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

import { Alert, Badge, Box, Group, Paper, ScrollArea, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconInfoCircle, IconShieldCheck } from '@tabler/icons-react';
import type { WarningPayload } from '@/types/sse';
import { describeWarning, MANDATORY_WARNING_CODES, severityColor } from '@/lib/warnings';

const SEVERITY_LABEL: Record<string, string> = {
  critical: 'nghiêm trọng',
  warn: 'cảnh báo',
  info: 'thông tin',
};

interface Props {
  warnings: WarningPayload[];
}

export function WarningFeed({ warnings }: Props) {
  const missing = MANDATORY_WARNING_CODES.filter(
    (code) => !warnings.some((w) => w.code === code),
  );

  return (
    <Paper
      withBorder
      p="md"
      radius="md"
      /* `flex: 1` để chiếm hết phần thừa khi cột còn rộng chỗ, nhưng KHÔNG được
         co dưới một mức đọc được: cột phải nay tự cuộn, nên khi các khối trên
         nó cao lên (chẩn đoán `SuiteRunFailed` chẳng hạn) thì flexbox sẽ bóp
         khối này xuống còn vài pixel — danh sách cảnh báo biến mất khỏi màn
         hình đúng lúc có nhiều cảnh báo nhất. `minHeight` là sàn chống việc đó;
         `flexShrink: 0` để nó bị đẩy xuống dưới thay vì bị nén. */
      style={{
        flex: 1,
        minHeight: 220,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Stack gap="sm" style={{ flex: 1, minHeight: 0 }}>
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

        <ScrollArea style={{ flex: 1, minHeight: 0 }} type="auto" offsetScrollbars>
          <Stack gap="xs">
            {warnings.map((w, i) => {
              const style = describeWarning(w.code);
              const color = severityColor(style.severity);
              return (
                <Alert
                  key={`${w.code}-${i}`}
                  color={color}
                  variant="light"
                  // KHÔNG dùng slot `icon` của Alert: nó chừa lề trái cho icon và
                  // đẩy CẢ body (giải thích + khung nguyên văn) thụt vào theo. Đưa
                  // icon vào cạnh tiêu đề để thân thẻ tràn hết chiều ngang.
                  title={
                    <Group gap={6} wrap="nowrap" align="flex-start">
                      {style.severity === 'info' ? (
                        <IconInfoCircle size={18} style={{ flexShrink: 0, marginTop: 1 }} />
                      ) : (
                        <IconAlertTriangle size={18} style={{ flexShrink: 0, marginTop: 1 }} />
                      )}
                      <Text fw={700} size="sm" lh={1.3}>
                        {style.title}
                      </Text>
                    </Group>
                  }
                  styles={{ body: { gap: 6 } }}
                >
                  {/* Mã + mức độ thành chip phụ, KHÔNG viết hoa/cắt như badge mặc
                      định — dòng chính là tiêu đề thành câu ở trên. */}
                  <Group gap={6} mb={6} wrap="wrap">
                    <Badge size="xs" color={color} variant="outline" ff="monospace" tt="none">
                      {w.code}
                    </Badge>
                    <Badge size="xs" color={color} variant="light" tt="none">
                      {SEVERITY_LABEL[style.severity] ?? style.severity}
                    </Badge>
                  </Group>

                  <Text size="xs" mb={6} lh={1.4}>
                    {style.explain}
                  </Text>

                  {/* Nguyên văn backend, không rút gọn — đóng khung phụ để tách
                      rõ khỏi phần diễn giải của UI. */}
                  <Box
                    p={8}
                    style={{
                      borderRadius: 6,
                      background: 'var(--mantine-color-gray-light)',
                      borderInlineStart: `2px solid var(--mantine-color-${color}-5)`,
                    }}
                  >
                    <Text
                      size="xs"
                      c="dimmed"
                      ff="monospace"
                      style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                    >
                      {w.msg}
                    </Text>
                  </Box>
                </Alert>
              );
            })}
          </Stack>
        </ScrollArea>

        {warnings.length > 0 && missing.length > 0 && (
          <Text size="xs" c="dimmed">
            Chưa thấy trong lượt này: {missing.join(' · ')}
          </Text>
        )}
      </Stack>
    </Paper>
  );
}
