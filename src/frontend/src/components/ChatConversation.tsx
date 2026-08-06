/**
 * Panel Hội thoại — multiturn có tool-use LIVE (system-design §7).
 *
 * Đặt CẠNH panel "Hỏi CERTUS" (analyze single-shot), không thay. Mỗi lượt: hiện
 * câu người dùng, rồi stream các sự kiện — MỖI lời gọi tool hiện thành một thẻ
 * "🔧 tên(đầu vào) → đầu ra" NGAY khi nó xảy ra, rồi tới câu trả lời cuối.
 *
 * Điểm dạy học: nếu câu trả lời khẳng định một con số mà PHÍA TRÊN không có thẻ
 * tool nào cấp con số đó, người học nhìn thấy tận mắt "số không có tool đứng sau".
 * Render văn bản thuần (không markdown): nội dung đến từ mô hình vừa đọc dữ liệu
 * không tin cậy.
 */

import { useCallback, useRef, useState } from 'react';
import {
  Badge,
  Box,
  Button,
  Card,
  Code,
  Group,
  Paper,
  ScrollArea,
  Stack,
  Text,
  Textarea,
  Title,
} from '@mantine/core';
import { IconSend, IconTool } from '@tabler/icons-react';
import { openChatStream, type ChatEvent } from '@/api/chat';

type Item =
  | { kind: 'user'; text: string }
  | { kind: 'assistant'; text: string }
  | { kind: 'tool'; name: string; input: unknown; output: unknown | null }
  | { kind: 'error'; text: string };

function newThreadId(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') return `web-${c.randomUUID()}`;
  return `web-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

const SUGGESTIONS = [
  'Grid có bao nhiêu ô rủi ro?',
  'Độ tin của con số phủ tới đâu, n bao nhiêu?',
  'Còn góc nào chưa ai nhìn không?',
];

export function ChatConversation() {
  const threadId = useRef<string>(newThreadId());
  const [items, setItems] = useState<Item[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);

  const handleEvent = useCallback((ev: ChatEvent) => {
    const p = ev.data.payload;
    if (ev.event === 'tool_use') {
      setItems((prev) => [
        ...prev,
        { kind: 'tool', name: String(p.name), input: p.input, output: null },
      ]);
    } else if (ev.event === 'tool_result') {
      // Điền đầu ra vào thẻ tool chưa có output gần nhất (cùng tên).
      setItems((prev) => {
        const next = [...prev];
        for (let i = next.length - 1; i >= 0; i -= 1) {
          const it = next[i];
          if (it.kind === 'tool' && it.name === String(p.name) && it.output === null) {
            next[i] = { ...it, output: p.output };
            break;
          }
        }
        return next;
      });
    } else if (ev.event === 'message') {
      setItems((prev) => [...prev, { kind: 'assistant', text: String(p.text ?? '') }]);
    } else if (ev.event === 'error') {
      setItems((prev) => [...prev, { kind: 'error', text: String(p.detail ?? 'lỗi không rõ') }]);
    }
  }, []);

  const send = useCallback(async () => {
    const message = input.trim();
    if (message.length === 0 || busy) return;
    setInput('');
    setItems((prev) => [...prev, { kind: 'user', text: message }]);
    setBusy(true);
    try {
      await openChatStream(threadId.current, message, { onEvent: handleEvent });
    } catch (err) {
      setItems((prev) => [
        ...prev,
        { kind: 'error', text: err instanceof Error ? err.message : String(err) },
      ]);
    } finally {
      setBusy(false);
    }
  }, [input, busy, handleEvent]);

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="center">
        <Title order={3}>Hội thoại</Title>
        <Badge color={busy ? 'blue' : 'gray'} variant="light">
          {busy ? 'đang trả lời' : 'sẵn sàng'}
        </Badge>
      </Group>

      <Paper withBorder p="md" radius="md" mih={260}>
        {items.length === 0 ? (
          <Text size="sm" c="dimmed">
            Hỏi nhiều lượt. Mỗi lời gọi tool sẽ hiện ngay bên dưới câu hỏi — con số
            trong câu trả lời phải khớp với tool đã gọi.
          </Text>
        ) : (
          <ScrollArea.Autosize mah={420} type="auto">
            <Stack gap="xs">
              {items.map((it, i) => (
                <ConversationItem key={i} item={it} />
              ))}
              {busy && (
                <Text size="xs" c="dimmed">
                  …
                </Text>
              )}
            </Stack>
          </ScrollArea.Autosize>
        )}
      </Paper>

      <Group gap="xs">
        {SUGGESTIONS.map((s) => (
          <Button
            key={s}
            size="compact-xs"
            variant="subtle"
            disabled={busy}
            onClick={() => setInput(s)}
          >
            {s}
          </Button>
        ))}
      </Group>

      <Group align="flex-end" gap="xs">
        <Textarea
          style={{ flex: 1 }}
          value={input}
          onChange={(e) => setInput(e.currentTarget.value)}
          placeholder="Nhập câu hỏi… (Ctrl+Enter để gửi)"
          autosize
          minRows={1}
          maxRows={4}
          disabled={busy}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <Button
          leftSection={<IconSend size={16} />}
          onClick={() => void send()}
          disabled={busy || input.trim().length === 0}
        >
          Gửi
        </Button>
      </Group>

      <Text size="xs" c="dimmed">
        Mô hình được phép diễn đạt; mọi con số phải đến từ một thẻ tool ở trên. Đối
        chiếu con số trong câu trả lời với các lời gọi tool của chính lượt đó.
      </Text>
    </Stack>
  );
}

function ConversationItem({ item }: { item: Item }) {
  if (item.kind === 'user') {
    return (
      <Group justify="flex-end">
        <Paper withBorder radius="md" p="xs" bg="var(--mantine-color-blue-light)" maw="80%">
          <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
            {item.text}
          </Text>
        </Paper>
      </Group>
    );
  }
  if (item.kind === 'assistant') {
    return (
      <Group justify="flex-start">
        <Paper withBorder radius="md" p="xs" maw="80%">
          <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
            {item.text}
          </Text>
        </Paper>
      </Group>
    );
  }
  if (item.kind === 'error') {
    return (
      <Paper withBorder radius="md" p="xs" bg="var(--mantine-color-red-light)">
        <Text size="sm" c="red">
          Lỗi: {item.text}
        </Text>
      </Paper>
    );
  }
  // tool
  return (
    <Card withBorder radius="md" padding="xs" bg="var(--mantine-color-gray-light)">
      <Group gap={6} mb={4}>
        <IconTool size={14} />
        <Text size="xs" fw={600}>
          {item.name}
        </Text>
        <Badge size="xs" variant="light" color={item.output === null ? 'yellow' : 'green'}>
          {item.output === null ? 'đang chạy' : 'xong'}
        </Badge>
      </Group>
      <Box>
        <Text size="xs" c="dimmed">
          đầu vào
        </Text>
        <Code block>{JSON.stringify(item.input, null, 2)}</Code>
        {item.output !== null && (
          <>
            <Text size="xs" c="dimmed" mt={4}>
              đầu ra
            </Text>
            <Code block>{JSON.stringify(item.output, null, 2)}</Code>
          </>
        )}
      </Box>
    </Card>
  );
}
