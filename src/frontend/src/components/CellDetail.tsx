/**
 * Chi tiết một ô của lưới — mở khi bấm vào heatmap (SDD 08 §5.4).
 *
 * In `id` CANONICAL đầy đủ chứ không rút gọn: `cell:<axis>=<v>|<axis>=<v>` là
 * hợp đồng, và một ô mang hai cách viết id là một ô sẽ được đếm hai lần.
 *
 * `evidence_id` rỗng ⇒ in UNVERIFIED, không in dấu gạch ngang. Luật 4 của
 * system-design §4.1: mọi con số kèm evidence_id, hoặc in UNVERIFIED.
 *
 * Bảng trục liệt kê MỌI trục của lưới, không chỉ hai trục ô mang. Ở `t=2` một ô
 * khoá đúng hai trục và KHÔNG ràng buộc phần còn lại — bảng chỉ in hai hàng thì
 * người đọc suy ra "lưới có hai trục", sai. Hai hàng kia in `bất kỳ` kèm miền
 * giá trị, vì đó là sự thật: ô ấy nói cặp này đã được chạm, và câu đó đúng bất
 * kể các trục kia mang giá trị nào.
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
import { axisRoles, type AxisDomain } from '@/lib/slices';
import { FlagList } from './FlagList';

interface Props {
  cell: Cell | null;
  /** miền giá trị từng trục của CẢ lưới — để nói được ô đang gộp qua cái gì */
  domains: readonly AxisDomain[];
  onClose: () => void;
}

export function CellDetail({ cell, domains, onClose }: Props) {
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

          <AxisTable cell={cell} domains={domains} />

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

/**
 * Mọi trục của lưới, chia làm hai hạng: KHOÁ và KHÔNG RÀNG BUỘC.
 *
 * Chỗ dễ sai nhất của cả màn hình này nằm ở hai hàng dưới. Chúng KHÔNG phải
 * "dữ liệu còn thiếu" và tuyệt đối không được điền một giá trị đoán vào: ô
 * `customer_tier=standard|shipping_zone=domestic` không hề nói gì về
 * `payment_method`, và nó vẫn là một ô hợp lệ, đã được chạm, có bằng chứng.
 * In `bất kỳ` kèm miền giá trị là cách nói đúng chuyện đó.
 */
function AxisTable({ cell, domains }: { cell: Cell; domains: readonly AxisDomain[] }) {
  const roles = axisRoles(cell, domains);
  const free = roles.filter((r) => !r.locked);

  return (
    <Box>
      <Text size="xs" fw={600} mb={4}>
        Trục — {roles.length - free.length} khoá / {free.length} không ràng buộc
      </Text>
      <Table withTableBorder fz="xs">
        <Table.Thead>
          <Table.Tr>
            <Table.Th w="34%">trục</Table.Th>
            <Table.Th w="30%">giá trị ô khoá</Table.Th>
            <Table.Th>miền giá trị trong lưới</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {roles.map((role) => (
            <Table.Tr key={role.name}>
              <Table.Td ff="monospace">
                <Group gap={6} wrap="nowrap">
                  <Badge size="xs" variant={role.locked ? 'filled' : 'outline'} color="certus">
                    {role.locked ? 'khoá' : 'tự do'}
                  </Badge>
                  {role.name}
                </Group>
              </Table.Td>
              <Table.Td ff="monospace">
                {role.locked ? (
                  role.value
                ) : (
                  <Text span size="xs" c="dimmed" fs="italic">
                    bất kỳ
                  </Text>
                )}
              </Table.Td>
              <Table.Td ff="monospace" c={role.locked ? 'dimmed' : undefined}>
                {role.domain.join(' · ') || '—'}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {free.length > 0 && (
        <Text size="xs" c="dimmed" mt={6}>
          Lưới chạy ở bậc t=2, nên một ô khoá đúng hai trục và GỘP QUA toàn bộ miền của{' '}
          {free.length} trục còn lại. Ô này khai “cặp ({roles
            .filter((r) => r.locked)
            .map((r) => r.value)
            .join(', ')}) đã được chạm” — câu đó đúng bất kể{' '}
          <Text span ff="monospace">
            {free.map((r) => r.name).join(', ')}
          </Text>{' '}
          mang giá trị nào. Đó là chỗ trống có chủ ý của phủ t-wise, không phải dữ liệu bị thiếu.
        </Text>
      )}
    </Box>
  );
}
