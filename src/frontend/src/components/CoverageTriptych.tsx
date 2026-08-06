/**
 * Panel 3 — BA TẦNG MẪU SỐ (SDD 08 §5.3, system-design §1.3).
 *
 * Đây là trục xương sống của cả sản phẩm. Ba khối RIÊNG BIỆT cạnh nhau, tuyệt
 * đối KHÔNG gộp thành một số:
 *
 *   line coverage    "bao nhiêu dòng đã chạy"
 *   mutation score   "test có bắt được lỗi không"
 *   grid coverage    "còn góc rủi ro nào chưa ai nhìn"
 *
 * CẤM trong file này: một ô thứ tư tên "điểm tổng", một progress bar gộp, một
 * màu nền chung theo điểm trung bình. Đó chính là `overall_coverage_score` của
 * lỗi 4 mọc lại ở tầng UI — và tài liệu nền cấm nó ở tầng backend đúng vì
 * "an average lets one high zone hide a low in a completely different zone".
 */

import { Alert, Badge, Box, Group, Paper, Progress, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import type { CoverageLayer } from '@/types/api';
import { UNVERIFIED } from '@/types/contracts';
import { fraction, pct, ratio } from '@/lib/format';
import { THREE_LAYER_LESSON } from '@/theme';
import { IntervalBadge } from './IntervalBadge';
import { FlagList } from './FlagList';

interface Props {
  layers: CoverageLayer[];
  loading?: boolean;
}

export function CoverageTriptych({ layers, loading }: Props) {
  return (
    <Stack gap="sm">
      <Box>
        <Title order={3}>Ba tầng mẫu số</Title>
        <Text size="sm" c="dimmed">
          Ba con số này có thể lần lượt là 94%, 88% và 3 trên 17 ô — và cả ba đều đúng.
        </Text>
      </Box>

      {loading && <Text size="sm">Đang lấy số…</Text>}

      <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
        {layers.map((layer) => (
          <CoverageBlock key={layer.id} layer={layer} />
        ))}
      </SimpleGrid>

      <Alert color="certus" variant="light" icon={<IconInfoCircle size={18} />}>
        <Text fw={700}>{THREE_LAYER_LESSON}</Text>
        <Text size="xs" mt={4}>
          Mỗi khối có mẫu số riêng và mẫu số đó nằm ngay dưới con số. Không có ô nào ở đây gộp ba
          khối lại thành một điểm: một điểm trung bình cho phép một vùng an toàn che một vùng nguy
          hiểm ở chỗ hoàn toàn khác.
        </Text>
      </Alert>
    </Stack>
  );
}

function CoverageBlock({ layer }: { layer: CoverageLayer }) {
  const value = ratio(layer.k, layer.n);
  const unverified = layer.evidence_ids.length === 0;
  const alarming = layer.flags.length > 0;

  return (
    <Paper
      withBorder
      p="md"
      radius="md"
      style={{
        borderColor: alarming ? 'var(--mantine-color-red-6)' : undefined,
        borderWidth: alarming ? 2 : 1,
      }}
    >
      <Stack gap={8}>
        <Group justify="space-between" align="flex-start">
          <Box>
            <Text fw={700}>{layer.title}</Text>
            <Text size="xs" c="dimmed">
              {layer.question}
            </Text>
          </Box>
          <Badge size="xs" variant="light" ff="monospace">
            {layer.source}
          </Badge>
        </Group>

        {/* k/n NGUYÊN BẢN đứng trước, phần trăm đứng sau và nhỏ hơn. */}
        <Group align="baseline" gap="xs">
          <Text fz={30} fw={700} ff="monospace" lh={1}>
            {fraction(layer.k, layer.n)}
          </Text>
          <Text fz="lg" c="dimmed" ff="monospace">
            {pct(value)}
          </Text>
        </Group>

        <Progress value={value * 100} color={alarming ? 'red' : 'certus'} size="sm" />

        <IntervalBadge interval={layer.interval} showFraction={false} size="xs" />

        <FlagList flags={layer.flags} />

        <Box>
          <Text size="xs" fw={600}>
            Mẫu số này là gì
          </Text>
          <Text size="xs" c="dimmed">
            {layer.denominator_note}
          </Text>
        </Box>

        {/* Luật 4 (system-design §4.1): mọi con số kèm evidence_id, hoặc in UNVERIFIED. */}
        <Group gap={6}>
          <Text size="xs" fw={600}>
            Neo bằng chứng:
          </Text>
          {unverified ? (
            <Badge size="xs" color="red" ff="monospace">
              {UNVERIFIED}
            </Badge>
          ) : (
            layer.evidence_ids.map((id) => (
              <Badge key={id} size="xs" variant="light" ff="monospace">
                {id}
              </Badge>
            ))
          )}
        </Group>
      </Stack>
    </Paper>
  );
}
