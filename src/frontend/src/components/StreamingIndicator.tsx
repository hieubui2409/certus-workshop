/**
 * Chỉ báo "đang chờ mô hình" — dùng chung cho mọi chỗ có stream.
 *
 * Trước đây mỗi tab tự chế một kiểu: khung Hội thoại in đúng một dấu `…` xám,
 * panel Chọn trục in `…` bên cạnh tên bước, ô Hỏi đáp in một câu chữ tĩnh. Cả
 * ba đứng im, nên không phân biệt được "mô hình đang nghĩ" với "kết nối đã
 * chết" — mà lượt phân tích thật chờ tới hàng phút.
 *
 * Ba biến thể, cùng một nhịp:
 *   `bubble` — bong bóng chat có avatar, ba chấm nảy, và một dòng chữ đổi theo
 *              thời gian đã chờ (5s / 15s / 30s) để người xem biết nó còn sống.
 *   `inline` — ba chấm nảy cỡ chữ, nhét cạnh một dòng text.
 *   `caret`  — con trỏ nháy sau chữ đang chảy.
 *
 * Keyframes khai một lần ở đây rồi mọi nơi dùng lại: trước bản này cùng một
 * `@keyframes certus-caret` được khai lặp trong hai component, và một cái sửa
 * còn cái kia không là chuyện sẽ xảy ra.
 */

import { useEffect, useState } from 'react';
import { Box, Group, Paper, Text } from '@mantine/core';

/** Khai một lần cho cả app — mọi biến thể dưới đây đọc từ đây. */
export function StreamingKeyframes() {
  return (
    <style>{`
      @keyframes certus-caret { 50% { opacity: 0 } }
      @keyframes certus-dot {
        0%, 60%, 100% { transform: translateY(0); opacity: .35 }
        30%           { transform: translateY(-4px); opacity: 1 }
      }
      @keyframes certus-shimmer {
        0%   { background-position: -180% 0 }
        100% { background-position:  180% 0 }
      }
      @media (prefers-reduced-motion: reduce) {
        /* Người tắt hiệu ứng vẫn phải THẤY là có thứ đang chạy — giữ nhịp mờ/tỏ,
           bỏ chuyển động. Tắt sạch thì chỉ báo biến thành ba chấm đứng im. */
        [data-certus-anim] { animation-duration: 1.6s !important; }
        [data-certus-anim="dot"] { animation-name: certus-caret !important; }
      }
    `}</style>
  );
}

/** Ba chấm nảy so le. Cỡ theo `size` (px). */
export function BouncingDots({ size = 6, color }: { size?: number; color?: string }) {
  return (
    <Box component="span" style={{ display: 'inline-flex', gap: size * 0.6, alignItems: 'flex-end' }}>
      <StreamingKeyframes />
      {[0, 1, 2].map((i) => (
        <Box
          key={i}
          component="span"
          aria-hidden
          data-certus-anim="dot"
          style={{
            width: size,
            height: size,
            borderRadius: '50%',
            background: color ?? 'var(--mantine-color-certus-5, var(--mantine-color-blue-5))',
            animation: 'certus-dot 1.2s ease-in-out infinite',
            animationDelay: `${i * 0.16}s`,
          }}
        />
      ))}
    </Box>
  );
}

/** Con trỏ nháy đặt sau đoạn chữ đang chảy. */
export function StreamingCaret() {
  return (
    <>
      <StreamingKeyframes />
      <Box
        component="span"
        aria-hidden
        ml={2}
        data-certus-anim="caret"
        style={{
          display: 'inline-block',
          width: '0.5em',
          borderBottom: '2px solid currentColor',
          animation: 'certus-caret 1s steps(2) infinite',
        }}
      />
    </>
  );
}

/**
 * Chữ đổi theo thời gian đã chờ. Không phải để trang trí: một lượt phân tích
 * thật chạy vài phút, và một chỉ báo nói đúng một câu suốt ba phút đọc như đã
 * treo. Mỗi mốc nói một điều KIỂM ĐƯỢC (nó đang làm gì), không hứa hẹn.
 */
const WAIT_STAGES: { after: number; text: string }[] = [
  { after: 0, text: 'đang soạn câu trả lời' },
  { after: 5, text: 'đang gọi tool để lấy số' },
  { after: 15, text: 'vẫn đang chạy — bộ kiểm của repo thật mất vài phút' },
  { after: 30, text: 'còn sống, chưa treo — số nào chưa có thì chưa in ra' },
];

function useElapsed(active: boolean): number {
  const [sec, setSec] = useState(0);
  useEffect(() => {
    if (!active) {
      setSec(0);
      return;
    }
    const t = setInterval(() => setSec((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [active]);
  return sec;
}

/**
 * Bong bóng chờ trong khung hội thoại — thay cho dấu `…` cũ.
 *
 * `label` ghi đè dòng chữ tự đổi khi nơi gọi biết rõ hơn nó đang chờ cái gì.
 */
export function StreamingBubble({ label }: { label?: string }) {
  const sec = useElapsed(true);
  const stage = [...WAIT_STAGES].reverse().find((s) => sec >= s.after) ?? WAIT_STAGES[0];
  const text = label ?? stage.text;

  return (
    <Group justify="flex-start" gap="xs" wrap="nowrap">
      <StreamingKeyframes />
      <Paper
        withBorder
        radius="md"
        p="xs"
        maw="80%"
        aria-live="polite"
        style={{
          background:
            'linear-gradient(100deg, var(--mantine-color-body) 30%, var(--mantine-color-default-hover) 50%, var(--mantine-color-body) 70%)',
          backgroundSize: '180% 100%',
          animation: 'certus-shimmer 2.2s linear infinite',
        }}
        data-certus-anim="shimmer"
      >
        <Group gap="sm" wrap="nowrap" align="center">
          <BouncingDots />
          <Text size="sm" c="dimmed">
            {text}
            {sec >= 5 && (
              <Text span size="xs" c="dimmed" ff="monospace" ml={6}>
                {sec}s
              </Text>
            )}
          </Text>
        </Group>
      </Paper>
    </Group>
  );
}

/** Ba chấm cỡ chữ, để nhét cạnh một dòng text đang chờ. */
export function StreamingInline({ text }: { text?: string }) {
  return (
    <Group gap={6} wrap="nowrap" component="span" style={{ display: 'inline-flex' }}>
      <BouncingDots size={4} color="var(--mantine-color-dimmed)" />
      {text && (
        <Text span size="xs" c="dimmed">
          {text}
        </Text>
      )}
    </Group>
  );
}
