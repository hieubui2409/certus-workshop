/**
 * Danh sách cờ của một claim / cell.
 *
 * Cờ nào có trong bảng tra `lib/warnings.ts` thì mượn màu và TIÊU ĐỀ của nó,
 * để cùng một khái niệm không mang hai cách gọi ở hai chỗ trên màn hình. Cờ
 * lạ vẫn hiện nguyên văn — không lọc bỏ thứ mình không nhận ra.
 */

import { Badge, Group, Tooltip } from '@mantine/core';
import { describeWarning, severityColor, WARNING_CATALOGUE } from '@/lib/warnings';

interface Props {
  flags: string[];
  size?: 'xs' | 'sm';
}

export function FlagList({ flags, size = 'xs' }: Props) {
  if (flags.length === 0) return null;

  return (
    <Group gap={4} wrap="wrap">
      {flags.map((flag, i) => {
        const known = flag in WARNING_CATALOGUE;
        const style = describeWarning(flag);
        return (
          <Tooltip key={`${flag}-${i}`} multiline w={320} label={known ? style.explain : flag}>
            <Badge
              size={size}
              variant={known ? 'filled' : 'outline'}
              color={known ? severityColor(style.severity) : 'gray'}
              ff="monospace"
            >
              {flag}
            </Badge>
          </Tooltip>
        );
      })}
    </Group>
  );
}
