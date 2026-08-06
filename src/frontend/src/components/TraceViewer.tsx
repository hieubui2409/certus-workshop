/**
 * Panel 7 — cây span dạng waterfall (SDD 08 §5.7).
 *
 * Dựng bằng Mantine primitives, không cần thư viện: một hàng, một thanh có
 * `left` và `width` tính theo phần trăm của tổng thời lượng.
 *
 * QUY TẮC PHÁT HIỆN LỖI 11:
 *
 *   distinct(trace_id) > 1  ⇒  cảnh báo đỏ "trace bị đứt: tìm thấy N trace_id"
 *
 * Một lần phân tích PHẢI là một trace. Nhiều trace_id nghĩa là không nối được
 * câu trả lời ngược về prompt đã sinh ra nó — khi có sự cố ở production, bạn
 * sẽ debug bằng mắt.
 */

import { useMemo } from 'react';
import { Alert, Badge, Box, Group, Paper, Stack, Text, Title, Tooltip } from '@mantine/core';
import { IconAlertTriangle, IconUnlink } from '@tabler/icons-react';
import type { SpanPayload } from '@/types/sse';
import { distinctTraceIds, traceIdOf } from '@/store/analysisStore';
import { formatMs, shortId } from '@/lib/format';

interface Props {
  spans: SpanPayload[];
  /** trace_id từ `event: done` — dùng khi span không mang trace_id */
  fallbackTraceId?: string | null;
}

interface Row {
  span: SpanPayload;
  depth: number;
  offsetMs: number;
  orphan: boolean;
  traceId: string;
}

/** Màu ổn định cho từng trace_id, để mắt nhóm được span cùng trace. */
const TRACE_COLORS = ['certus', 'grape', 'teal', 'orange', 'pink', 'lime'];

export function TraceViewer({ spans, fallbackTraceId }: Props) {
  const traces = distinctTraceIds(spans, fallbackTraceId);
  const broken = traces.length > 1;

  const rows = useMemo<Row[]>(() => buildRows(spans, fallbackTraceId), [spans, fallbackTraceId]);
  const total = Math.max(1, ...rows.map((r) => r.offsetMs + r.span.ms));

  if (spans.length === 0) {
    return (
      <Alert color="gray" variant="light" title="Chưa có span nào">
        Chạy một lượt phân tích để xem cây span.
      </Alert>
    );
  }

  return (
    <Stack gap="sm">
      <Box>
        <Title order={3}>Trace viewer</Title>
        <Text size="sm" c="dimmed">
          {spans.length} span · {traces.length} trace_id phân biệt
        </Text>
      </Box>

      {broken && (
        <Alert
          color="red"
          variant="filled"
          icon={<IconAlertTriangle size={18} />}
          title={`Trace bị đứt: tìm thấy ${traces.length} trace_id`}
        >
          <Text size="sm" mb="xs">
            Một lần phân tích phải là MỘT trace. Khi span của lời gọi mô hình tự sinh trace_id mới,
            cây đứt đúng ở chỗ đắt nhất: không nối được prompt với kết quả.
          </Text>
          <Stack gap={4}>
            {traces.map((id, i) => {
              const count = spans.filter((s) => traceIdOf(s, fallbackTraceId) === id).length;
              return (
                <Group key={id} gap="xs">
                  <Badge size="xs" color={TRACE_COLORS[i % TRACE_COLORS.length]} ff="monospace">
                    {id}
                  </Badge>
                  <Text size="xs">
                    {count} span
                    {count === 1 ? ' — trace mồ côi, chỉ có đúng một span' : ''}
                  </Text>
                </Group>
              );
            })}
          </Stack>
        </Alert>
      )}

      <Paper withBorder radius="md" p="sm">
        <Stack gap={3}>
          {rows.map((row) => {
            const traceIndex = traces.indexOf(row.traceId);
            const color = TRACE_COLORS[traceIndex % TRACE_COLORS.length];
            const left = (row.offsetMs / total) * 100;
            const width = Math.max(1.2, (row.span.ms / total) * 100);

            return (
              <Group key={row.span.span_id} gap="xs" wrap="nowrap" align="center">
                <Box w={230} style={{ flexShrink: 0, paddingLeft: row.depth * 14 }}>
                  <Group gap={4} wrap="nowrap">
                    {row.orphan && (
                      <Tooltip label="Span mồ côi: parent không có trong tập span nhận được.">
                        <IconUnlink size={13} color="var(--mantine-color-red-6)" />
                      </Tooltip>
                    )}
                    <Text size="xs" ff="monospace" truncate>
                      {row.span.name}
                    </Text>
                  </Group>
                </Box>

                <Box w={132} style={{ flexShrink: 0 }}>
                  <Tooltip label={`trace_id đầy đủ: ${row.traceId}`}>
                    <Badge size="xs" color={color} variant="light" ff="monospace">
                      {shortId(row.traceId)}
                    </Badge>
                  </Tooltip>
                </Box>

                <Box style={{ flex: 1, position: 'relative', height: 18 }}>
                  <Box
                    style={{
                      position: 'absolute',
                      left: `${left}%`,
                      width: `${width}%`,
                      height: 14,
                      top: 2,
                      borderRadius: 3,
                      background: `var(--mantine-color-${color}-6)`,
                    }}
                  />
                </Box>

                <Text size="xs" ff="monospace" w={62} ta="right" style={{ flexShrink: 0 }}>
                  {formatMs(row.span.ms)}
                </Text>
                <Text size="xs" ff="monospace" w={78} ta="right" c="dimmed" style={{ flexShrink: 0 }}>
                  {row.span.tokens != null ? `${row.span.tokens} tok` : '—'}
                </Text>
              </Group>
            );
          })}
        </Stack>
      </Paper>
    </Stack>
  );
}

/**
 * Dựng cây theo `parent`. Span có `parent` không tồn tại trong tập span nhận
 * được thì hiện ở CẤP GỐC kèm dấu hiệu riêng — không im lặng gắn nó vào một
 * cha gần đúng, vì "gần đúng" ở đây chính là thứ che mất lỗi 11.
 */
function buildRows(spans: SpanPayload[], fallback?: string | null): Row[] {
  const ids = new Set(spans.map((s) => s.span_id));
  const children = new Map<string | null, SpanPayload[]>();

  for (const span of spans) {
    const parent = span.parent && ids.has(span.parent) ? span.parent : null;
    const bucket = children.get(parent) ?? [];
    bucket.push(span);
    children.set(parent, bucket);
  }

  const rows: Row[] = [];

  /**
   * Mỗi span gốc bắt đầu ở mốc 0 (chúng là những trace riêng, không nối tiếp
   * nhau). Con của một span xếp tuần tự kể từ mốc bắt đầu của cha.
   */
  const walk = (parent: string | null, depth: number, startMs: number) => {
    let cursor = startMs;
    for (const span of children.get(parent) ?? []) {
      const offsetMs = depth === 0 ? 0 : cursor;
      rows.push({
        span,
        depth,
        offsetMs,
        orphan: span.parent != null && !ids.has(span.parent),
        traceId: traceIdOf(span, fallback),
      });
      walk(span.span_id, depth + 1, offsetMs);
      cursor = offsetMs + span.ms;
    }
  };

  walk(null, 0, 0);
  return rows;
}
