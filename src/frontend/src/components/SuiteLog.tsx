/**
 * Log của bước dựng môi trường + chạy bộ kiểm, chảy theo thời gian thực.
 *
 * Vì sao cần: bước 4 (`run_tests`) trên một repo thật mất 2–5 phút — đo được
 * 261 giây trên document-intake. Không có gì hiện ra trong khoảng đó thì với
 * người đang nhìn, im lặng 4 phút không phân biệt được với đã treo. Backend
 * phát từng dòng `event: log` ngay khi pytest in ra; chỗ này là nơi chúng đáp
 * xuống.
 *
 * Hai loại dòng, KHÔNG trộn lẫn:
 *   `level=INFO` — CERTUS nói về việc nó đang làm (chọn môi trường nào, vì sao,
 *                  lệnh gì). Đây là thứ giải thích một con số phủ về sau.
 *   `level=TEST` — output NGUYÊN VĂN của bộ kiểm repo. Không diễn giải, không
 *                  tô màu: đó là chữ của repo, không phải của CERTUS.
 */

import { useEffect, useRef } from 'react';
import { Badge, Box, Code, Group, Paper, ScrollArea, Text } from '@mantine/core';
import type { LogPayload } from '@/types/sse';

interface Props {
  logs: LogPayload[];
  running: boolean;
}

export function SuiteLog({ logs, running }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Tự cuộn xuống đáy khi có dòng mới — chỉ trong lúc đang chạy. Cuộn tiếp sau
  // khi xong sẽ giật cái nhìn của người đang đọc ngược lên tìm dòng lỗi.
  useEffect(() => {
    if (running) bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [logs.length, running]);

  if (logs.length === 0) return null;

  return (
    <Paper withBorder p="sm" radius="md">
      <Group justify="space-between" mb={6}>
        <Text size="xs" fw={600}>
          Nhật ký dựng môi trường & chạy bộ kiểm
        </Text>
        <Badge size="xs" variant="light" color={running ? 'blue' : 'gray'}>
          {logs.length} dòng
        </Badge>
      </Group>
      <ScrollArea.Autosize mah={260} type="auto">
        <Code block style={{ fontSize: 11, whiteSpace: 'pre-wrap' }}>
          {logs.map((l, i) => (
            <Box
              key={i}
              component="div"
              // Dòng của CERTUS đậm hơn dòng của repo: người đọc phải phân biệt
              // được "hệ thống nói" với "bộ kiểm của tôi in ra".
              style={{ opacity: l.level === 'TEST' ? 0.75 : 1 }}
            >
              {l.msg}
            </Box>
          ))}
        </Code>
        <div ref={bottomRef} />
      </ScrollArea.Autosize>
    </Paper>
  );
}
