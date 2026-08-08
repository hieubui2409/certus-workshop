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
import { StreamingBubble, StreamingCaret } from './StreamingIndicator';

type Item =
  | { kind: 'user'; text: string }
  // `streaming`: bong bóng đang được viết dở (đang nhận message_delta). Sự kiện
  // `message` cuối chốt nó lại — cùng một bong bóng, không đẻ thêm dòng mới.
  | { kind: 'assistant'; text: string; streaming?: boolean }
  | { kind: 'tool'; name: string; input: unknown; output: unknown | null }
  | { kind: 'error'; text: string };

function newThreadId(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') return `web-${c.randomUUID()}`;
  return `web-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

// Ở chế độ mock (mặc định cho 1000 SV), backend PHÁT LẠI một cassette theo khoá
// sha256(model+system+messages+tools) — chỉ câu đã thu mới khớp. Gợi ý phải LÀ
// đúng câu trong kịch bản đã thu, ĐÚNG THỨ TỰ: câu 2 (ISO) chỉ replay được SAU
// câu 1 vì khoá của nó gồm cả lịch sử lượt 1. Câu ngoài kịch bản → cassette miss
// → sự kiện error (đúng bản chất: mock không sinh câu mới). Xem A4 / system-arch §7.2.
const SUGGESTIONS = [
  'Đếm giúp tôi số ô của grid 3 trục: payment {card, cash}, amount {small, large}, region {vn, us}, ở mức t=2. Hãy dùng tool.',
  'Tiêu chuẩn ISO nào quy định ngưỡng branch coverage tối thiểu, và ngưỡng cụ thể là bao nhiêu phần trăm?',
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
    } else if (ev.event === 'message_delta') {
      // Chữ đang chảy: nối vào bong bóng đang viết, hoặc mở một cái mới. Bong bóng
      // này mang cờ `streaming` để hiện con trỏ nhấp nháy — người dùng phân biệt
      // được "đang viết" với "đã viết xong", vốn là hai trạng thái khác nhau.
      setItems((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.kind === 'assistant' && last.streaming) {
          return [...prev.slice(0, -1), { ...last, text: last.text + String(p.text ?? '') }];
        }
        return [...prev, { kind: 'assistant', text: String(p.text ?? ''), streaming: true }];
      });
    } else if (ev.event === 'message') {
      // Câu ĐẦY ĐỦ từ backend chốt lại bong bóng đang chảy — không tin bản tự ghép
      // ở client (một gói rơi là lệch chữ mà không ai biết).
      setItems((prev) => {
        const last = prev[prev.length - 1];
        const final = { kind: 'assistant' as const, text: String(p.text ?? ''), streaming: false };
        if (last && last.kind === 'assistant' && last.streaming) {
          return [...prev.slice(0, -1), final];
        }
        return [...prev, final];
      });
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

      {/* Chiều cao CỐ ĐỊNH theo viewport (không minHeight — min cho phép nở quá
          màn khiến cả cột trái cuộn, kéo tab-header dịch). Cột trái đã bị App khoá
          ở calc(100dvh - 94px); trừ thêm ~360px (tab list + tiêu đề + gợi ý + hàng
          nhập + caption) để khung khớp đúng, cột trái KHÔNG cuộn → tab đứng yên,
          chỉ ScrollArea bên trong khung cuộn. */}
      <Paper
        withBorder
        p="md"
        radius="md"
        style={{ height: 'calc(100dvh - 360px)', display: 'flex', flexDirection: 'column' }}
      >
        {items.length === 0 ? (
          <Text size="sm" c="dimmed">
            Hỏi nhiều lượt. Mỗi lời gọi tool sẽ hiện ngay bên dưới câu hỏi — con số
            trong câu trả lời phải khớp với tool đã gọi.
          </Text>
        ) : (
          <ScrollArea style={{ flex: 1 }} type="auto">
            <Stack gap="xs">
              {items.map((it, i) => (
                <ConversationItem key={i} item={it} />
              ))}
              {/* Chỉ hiện khi CHƯA có bong bóng nào đang chảy chữ: lúc mô hình
                  đã bắt đầu viết thì con trỏ nháy trong chính bong bóng đó đã
                  nói "còn đang gõ", thêm một chỉ báo nữa là nói hai lần. */}
              {busy && !items.some((it) => it.kind === 'assistant' && it.streaming) && (
                <StreamingBubble />
              )}
            </Stack>
          </ScrollArea>
        )}
      </Paper>

      <Stack gap={4}>
        <Text size="xs" c="dimmed">
          Kịch bản mẫu (bấm để điền vào ô nhập, hỏi theo thứ tự):
        </Text>
        {SUGGESTIONS.map((s, i) => (
          <Button
            key={s}
            size="compact-xs"
            variant="subtle"
            justify="flex-start"
            disabled={busy}
            onClick={() => setInput(s)}
            styles={{ label: { whiteSpace: 'normal', textAlign: 'left', lineHeight: 1.3 } }}
            leftSection={
              <Badge size="xs" circle variant="light">
                {i + 1}
              </Badge>
            }
          >
            {s}
          </Button>
        ))}
      </Stack>

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
            {/* Con trỏ khi đang viết dở: phân biệt "mô hình còn đang gõ" với
                "nó đã trả lời xong và câu ngắn thế thôi" — hai chuyện khác nhau. */}
            {item.streaming && <StreamingCaret />}
          </Text>
        </Paper>
      </Group>
    );
  }
  if (item.kind === 'error') {
    // Ở mock, câu ngoài kịch bản đã thu → không có cassette khớp. Đó KHÔNG phải
    // sự cố hệ thống mà là bản chất replay tất định: chỉ câu đã thu mới phát lại
    // được. Diễn giải thành lời cho người học thay vì phơi ra một chuỗi hash.
    const isCassetteMiss = item.text.includes('không có cassette khớp');
    return (
      <Paper withBorder radius="md" p="xs" bg="var(--mantine-color-red-light)">
        <Text size="sm" c="red">
          {isCassetteMiss
            ? 'Câu này chưa có trong kịch bản mẫu đã thu, nên chế độ mô phỏng không phát lại được. Hãy bấm một câu trong "Kịch bản mẫu" ở trên và hỏi theo đúng thứ tự.'
            : `Lỗi: ${item.text}`}
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
