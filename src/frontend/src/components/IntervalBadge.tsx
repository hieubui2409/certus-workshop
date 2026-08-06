/**
 * Hiển thị một `Interval`.
 *
 * Luật: `k/n` NGUYÊN BẢN hiện ra TRƯỚC phần trăm, và mọi cờ đi kèm interval
 * đều thành chữ. Một interval `saturated` mà chỉ hiện `[0.44, 1.00]` thì đọc
 * như một interval bình thường — người đọc sẽ tưởng nó hẹp vì dữ liệu chắc.
 */

import { Badge, Group, Text, Tooltip } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import type { Interval } from '@/types/contracts';
import { formatInterval, fraction, pct, ratio } from '@/lib/format';

interface Props {
  /** Có thể `null`: tầng CHƯA ĐO (`/api/coverage` trả `interval: null`). */
  interval: Interval | null;
  /** hiện `k/n` ở đầu dòng — tắt khi chỗ gọi đã in k/n rồi */
  showFraction?: boolean;
  size?: 'xs' | 'sm' | 'md';
}

export function IntervalBadge({ interval, showFraction = true, size = 'sm' }: Props) {
  // Tầng chưa đo không có khoảng tin cậy. Hiện "chưa đo" thay vì deref `null`.
  if (!interval) {
    return (
      <Badge size={size} variant="light" color="gray" ff="monospace">
        chưa đo
      </Badge>
    );
  }
  const clusterFloor = interval.route === 'cluster-floor';

  return (
    <Group gap="xs" wrap="wrap">
      {showFraction && (
        <Text size={size} fw={600} ff="monospace">
          {fraction(interval.k, interval.n)}
        </Text>
      )}
      <Text size={size} c="dimmed" ff="monospace">
        {pct(ratio(interval.k, interval.n))}
      </Text>
      <Badge size={size} variant="light" color="gray" ff="monospace">
        {formatInterval(interval)}
      </Badge>

      {interval.saturated && (
        <Tooltip
          multiline
          w={320}
          label="Interval đã tràn ra ngoài [0,1] rồi bị cắt về biên. Nó trông hẹp vì bị cắt, không phải vì dữ liệu chắc."
        >
          <Badge size={size} color="red" leftSection={<IconAlertTriangle size={12} />}>
            saturated — chạm biên, hẹp giả
          </Badge>
        </Tooltip>
      )}

      {clusterFloor && (
        <Badge size={size} color="red" leftSection={<IconAlertTriangle size={12} />}>
          cluster-floor · n_eff = {interval.n_eff?.toFixed(1) ?? '?'} trên n = {interval.n}
        </Badge>
      )}

      {!clusterFloor && interval.route && (
        <Badge size={size} color="blue" variant="light">
          route: {interval.route}
        </Badge>
      )}
    </Group>
  );
}
