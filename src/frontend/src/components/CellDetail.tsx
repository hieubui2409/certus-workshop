/**
 * Chi tiết một ô của lưới — mở khi bấm vào heatmap (SDD 08 §5.4).
 *
 * In `id` CANONICAL đầy đủ chứ không rút gọn: `cell:<axis>=<v>|<axis>=<v>` là
 * hợp đồng, và một ô mang hai cách viết id là một ô sẽ được đếm hai lần.
 *
 * `evidence_id` rỗng ⇒ in UNVERIFIED, không in dấu gạch ngang. Luật 4 của
 * system-design §4.1: mọi con số kèm evidence_id, hoặc in UNVERIFIED.
 */

import {
  Badge,
  Box,
  Code,
  Drawer,
  Group,
  Stack,
  Table,
  Text,
  useComputedColorScheme,
} from '@mantine/core';
import type { Cell } from '@/types/contracts';
import { UNVERIFIED } from '@/types/contracts';
import { BAND_STYLES, bandColor } from '@/lib/bands';
import { FlagList } from './FlagList';

interface Props {
  cell: Cell | null;
  onClose: () => void;
}

export function CellDetail({ cell, onClose }: Props) {
  const scheme = useComputedColorScheme('light');

  return (
    <Drawer
      opened={cell !== null}
      onClose={onClose}
      position="right"
      size="lg"
      title={
        <Text fw={700} fz="h4">
          Chi tiết ô lưới
        </Text>
      }
    >
      {cell && (
        <Stack gap="md">
          <Box>
            <Text size="xs" c="dimmed">
              Định danh canonical
            </Text>
            <Code block>{cell.id}</Code>
          </Box>

          <Group gap="xs">
            <Badge
              size="lg"
              styles={{
                root: {
                  background: bandColor(cell.band, scheme),
                  color: BAND_STYLES[cell.band].fg,
                },
              }}
            >
              band: {BAND_STYLES[cell.band].label}
            </Badge>
            <Badge size="lg" variant="light" color="certus">
              zone: {cell.zone_id}
            </Badge>
            <Badge size="lg" variant="light" color="certus">
              w = {cell.zone_w}
            </Badge>
            <Badge size="lg" variant="outline" color="gray" ff="monospace">
              source: {cell.source}
            </Badge>
          </Group>

          <Text size="sm">{BAND_STYLES[cell.band].meaning}</Text>

          {!BAND_STYLES[cell.band].inDenominator && (
            <Text size="xs" c="violet" fw={600}>
              Ô này KHÔNG nằm trong mẫu số. Mọi tỉ lệ của lượt chạy được tính như thể nó không tồn
              tại.
            </Text>
          )}

          <Box>
            <Text size="xs" fw={600} mb={4}>
              Trục
            </Text>
            <Table withTableBorder fz="xs">
              <Table.Tbody>
                {Object.entries(cell.axes).map(([axis, value]) => (
                  <Table.Tr key={axis}>
                    <Table.Td ff="monospace" w="45%">
                      {axis}
                    </Table.Td>
                    <Table.Td ff="monospace">{value}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Box>

          <Box>
            <Text size="xs" fw={600} mb={4}>
              Cờ
            </Text>
            {cell.flags.length === 0 ? (
              <Text size="xs" c="dimmed">
                Không có cờ nào.
              </Text>
            ) : (
              <FlagList flags={cell.flags} size="sm" />
            )}
          </Box>

          <Box>
            <Text size="xs" fw={600} mb={4}>
              Neo bằng chứng (evidence_id)
            </Text>
            {cell.evidence_id.length === 0 ? (
              <Group gap="xs">
                <Badge color="red" ff="monospace">
                  {UNVERIFIED}
                </Badge>
                <Text size="xs" c="dimmed">
                  Không có bản ghi nào trong evidence ledger neo vào ô này.
                </Text>
              </Group>
            ) : (
              <Group gap={6}>
                {cell.evidence_id.map((id) => (
                  <Badge key={id} variant="light" ff="monospace">
                    {id}
                  </Badge>
                ))}
              </Group>
            )}
          </Box>
        </Stack>
      )}
    </Drawer>
  );
}
