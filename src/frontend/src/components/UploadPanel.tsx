/**
 * Panel 1 — chọn repo mẫu hoặc kéo thả .zip (SDD 08 §5.1).
 *
 * Hai danh sách TÁCH BIỆT: file đã nhận, và file bị loại KÈM LÝ DO. Danh sách
 * bị loại không bao giờ được rút gọn thành một con số — "đã loại 4 file" đúng
 * là cái cách một mẫu số biến mất trong im lặng.
 *
 * Mỗi hàng bị loại in cả `matched_pattern`, vì đó là thứ sinh viên đối chiếu
 * với `config/data-policy.yaml` khi truy lỗi 8.
 */

import { useCallback, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Group,
  Loader,
  Paper,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { IconFileZip, IconUpload, IconX } from '@tabler/icons-react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { notifications } from '@mantine/notifications';
import { listSamples, pickSample, sendZip } from '@/api/analyze';
import type { UploadResult } from '@/types/api';
import { formatBytes, shortId } from '@/lib/format';

interface Props {
  result: UploadResult | null;
  onResult: (result: UploadResult) => void;
}

export function UploadPanel({ result, onResult }: Props) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const samplesQuery = useQuery({
    queryKey: ['samples'],
    queryFn: ({ signal }) => listSamples(signal),
  });

  const failed = useCallback((err: unknown) => {
    notifications.show({
      color: 'red',
      title: 'Nạp mã nguồn thất bại',
      message: err instanceof Error ? err.message : String(err),
    });
  }, []);

  const sampleMutation = useMutation({
    mutationFn: pickSample,
    onSuccess: onResult,
    onError: failed,
  });

  const zipMutation = useMutation({
    mutationFn: sendZip,
    onSuccess: onResult,
    onError: failed,
  });

  const busy = sampleMutation.isPending || zipMutation.isPending;

  const handleFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0];
      if (!file) return;
      if (!file.name.toLowerCase().endsWith('.zip')) {
        notifications.show({
          color: 'red',
          title: 'Chỉ nhận tệp .zip',
          message: `"${file.name}" không phải .zip. Không đoán định dạng thay bạn.`,
        });
        return;
      }
      zipMutation.mutate(file);
    },
    [zipMutation],
  );

  return (
    <Stack gap="md">
      <Box>
        <Title order={3}>Nạp mã nguồn</Title>
        <Text size="sm" c="dimmed">
          Chọn một repo mẫu, hoặc kéo thả tệp .zip của bạn.
        </Text>
      </Box>

      {samplesQuery.isLoading && <Loader size="sm" />}
      {samplesQuery.isError && (
        <Alert color="red" title="Không lấy được danh sách repo mẫu">
          {String(samplesQuery.error)}
        </Alert>
      )}

      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
        {(samplesQuery.data ?? []).map((sample) => {
          const active = result?.label === sample.name;
          return (
            <Card
              key={sample.id}
              withBorder
              padding="sm"
              radius="md"
              style={{
                borderColor: active ? 'var(--mantine-color-certus-6)' : undefined,
                borderWidth: active ? 2 : 1,
              }}
            >
              <Stack gap={6} h="100%" justify="space-between">
                <Box>
                  <Group justify="space-between" align="center">
                    <Text fw={650} ff="monospace">
                      {sample.name}
                    </Text>
                    <Badge size="xs" variant="light">
                      {sample.files} tệp
                    </Badge>
                  </Group>
                  <Text size="xs" c="dimmed" mt={4}>
                    {sample.description}
                  </Text>
                  <Text size="xs" mt={6}>
                    {sample.test_files} tệp kiểm thử
                  </Text>
                </Box>
                <Button
                  size="xs"
                  variant={active ? 'filled' : 'light'}
                  loading={sampleMutation.isPending && sampleMutation.variables === sample.id}
                  disabled={busy}
                  onClick={() => sampleMutation.mutate(sample.id)}
                >
                  {active ? 'Đang dùng' : 'Chọn repo này'}
                </Button>
              </Stack>
            </Card>
          );
        })}
      </SimpleGrid>

      <Paper
        withBorder
        p="lg"
        radius="md"
        style={{
          borderStyle: 'dashed',
          borderWidth: 2,
          borderColor: dragging ? 'var(--mantine-color-certus-6)' : undefined,
          cursor: 'pointer',
        }}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
      >
        <Group justify="center" gap="sm">
          {zipMutation.isPending ? <Loader size="sm" /> : <IconUpload size={22} />}
          <Text size="sm">Kéo thả tệp .zip vào đây, hoặc bấm để chọn</Text>
        </Group>
        <input
          ref={inputRef}
          type="file"
          accept=".zip"
          hidden
          onChange={(e) => handleFiles(e.target.files)}
        />
      </Paper>

      {result && <IngestResult result={result} />}
    </Stack>
  );
}

function IngestResult({ result }: { result: UploadResult }) {
  return (
    <Stack gap="sm">
      <Group gap="xs">
        <IconFileZip size={18} />
        <Text fw={650}>{result.label}</Text>
        <Badge variant="light" ff="monospace">
          {result.run_id}
        </Badge>
        <Badge variant="light" color="gray">
          nguồn: {result.source === 'sample' ? 'repo mẫu' : 'tệp .zip'}
        </Badge>
      </Group>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        <Paper withBorder p="sm" radius="md">
          <Group justify="space-between" mb="xs">
            <Text fw={600} size="sm">
              Đã nhận
            </Text>
            <Badge color="green" variant="light">
              {result.accepted.length} tệp
            </Badge>
          </Group>
          <ScrollArea.Autosize mah={220} type="auto">
            <Table striped highlightOnHover withRowBorders={false} fz="xs">
              <Table.Tbody>
                {result.accepted.map((f) => (
                  <Table.Tr key={f.path}>
                    <Table.Td ff="monospace">{f.path}</Table.Td>
                    <Table.Td w={80} ta="right" c="dimmed">
                      {formatBytes(f.bytes)}
                    </Table.Td>
                    <Table.Td w={110} c="dimmed" ff="monospace">
                      {shortId(f.sha256)}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea.Autosize>
        </Paper>

        <Paper withBorder p="sm" radius="md">
          <Group justify="space-between" mb="xs">
            <Text fw={600} size="sm">
              Đã loại — kèm lý do
            </Text>
            <Badge color="orange" variant="light">
              {result.rejected.length} tệp
            </Badge>
          </Group>
          {result.rejected.length === 0 ? (
            <Text size="xs" c="dimmed">
              Không tệp nào bị loại. Nếu bạn mong đợi có, hãy kiểm tra
              <Text span ff="monospace">
                {' '}
                config/data-policy.yaml
              </Text>
              .
            </Text>
          ) : (
            <ScrollArea.Autosize mah={220} type="auto">
              <Stack gap={6}>
                {result.rejected.map((f) => (
                  <Group key={f.path} gap={8} wrap="nowrap" align="flex-start">
                    <IconX size={14} style={{ marginTop: 3, flexShrink: 0 }} />
                    <Box>
                      <Group gap={6}>
                        <Text size="xs" ff="monospace" fw={600}>
                          {f.path}
                        </Text>
                        {f.matched_pattern && (
                          <Badge size="xs" color="orange" variant="light" ff="monospace">
                            {f.matched_pattern}
                          </Badge>
                        )}
                      </Group>
                      <Text size="xs" c="dimmed">
                        {f.reason}
                      </Text>
                    </Box>
                  </Group>
                ))}
              </Stack>
            </ScrollArea.Autosize>
          )}
        </Paper>
      </SimpleGrid>
    </Stack>
  );
}
