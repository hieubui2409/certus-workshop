/**
 * Khung ứng dụng — SDD 08 §3.
 *
 * Bố cục: header + cột nội dung (Tabs) + cột cảnh báo luôn hiển thị.
 *
 * `WarningFeed` KHÔNG nằm trong Tabs. Nó đứng cạnh mọi tab, vì một cảnh báo
 * chỉ thấy được khi đang mở đúng tab là một cảnh báo sẽ bị bỏ lỡ.
 *
 * Tab "Dữ liệu đã gửi cho mô hình" là tab PHỤ và không phải `defaultValue` —
 * đúng đặc tả lỗi 8.
 */

import { useCallback, useRef, useState } from 'react';
import {
  ActionIcon,
  AppShell,
  Badge,
  Button,
  Container,
  Grid,
  Group,
  Paper,
  Stack,
  Tabs,
  Text,
  Title,
  Tooltip,
  useComputedColorScheme,
  useMantineColorScheme,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import {
  IconChartGridDots,
  IconFileDescription,
  IconLayoutGrid,
  IconListCheck,
  IconMessage,
  IconMessages,
  IconMoon,
  IconPlayerPlay,
  IconPlayerStop,
  IconRoute,
  IconShieldLock,
  IconSun,
  IconUpload,
} from '@tabler/icons-react';

import { UploadPanel } from '@/components/UploadPanel';
import { ChatPanel } from '@/components/ChatPanel';
import { ChatConversation } from '@/components/ChatConversation';
import { CoverageTriptych } from '@/components/CoverageTriptych';
import { GridHeatmap } from '@/components/GridHeatmap';
import { GateChain } from '@/components/GateChain';
import { ClaimInspector } from '@/components/ClaimInspector';
import { TraceViewer } from '@/components/TraceViewer';
import { PromptDataPanel } from '@/components/PromptDataPanel';
import { WarningFeed } from '@/components/WarningFeed';
import { StepProgress } from '@/components/StepProgress';

import { getCoverage, getPromptPayload, openAnalyzeStream, USE_MOCK } from '@/api/analyze';
import { useAnalysisStore } from '@/store/analysisStore';
import type { UploadResult } from '@/types/api';
import { TAGLINE } from '@/theme';

export default function App() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme('light');

  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [question, setQuestion] = useState('Bộ kiểm thử của tôi phủ tới đâu?');
  const [tab, setTab] = useState<string>('upload');
  const abortRef = useRef<AbortController | null>(null);

  const store = useAnalysisStore();
  const finished = store.status === 'done';

  const coverageQuery = useQuery({
    queryKey: ['coverage', upload?.run_id, finished],
    queryFn: ({ signal }) => getCoverage(upload!.run_id, signal),
    enabled: Boolean(upload) && finished,
  });

  const promptQuery = useQuery({
    queryKey: ['prompt-payload', upload?.run_id, finished],
    queryFn: ({ signal }) => getPromptPayload(upload!.run_id, signal),
    enabled: Boolean(upload) && finished,
  });

  const run = useCallback(async () => {
    if (!upload) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const { start, apply, finish } = useAnalysisStore.getState();
    start(upload.run_id, question);
    setTab('coverage');

    // Backend `AnalyzeRequest` nhận đúng MỘT trong `target` (repo mẫu) hoặc
    // `upload_id` (tệp vừa tải lên thật) — không có trường `run_id`. Repo mẫu
    // không đi qua `/api/upload` nên chỉ có `target`; tệp .zip thật thì
    // `client.uploadZip` đã gắn `upload_id` từ `UploadAck` trả về.
    const req = upload.target
      ? { target: upload.target, question }
      : { upload_id: upload.upload_id ?? upload.run_id, question };

    await openAnalyzeStream(
      req,
      { onEvent: apply, signal: controller.signal },
    );
    finish();
  }, [upload, question]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    useAnalysisStore.getState().finish();
  }, []);

  const handleUpload = useCallback((result: UploadResult) => {
    setUpload(result);
    useAnalysisStore.getState().reset();
  }, []);

  return (
    <AppShell header={{ height: 62 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Title order={3}>CERTUS</Title>
            <Text size="sm" c="dimmed">
              {TAGLINE}
            </Text>
          </Group>
          <Group gap="xs">
            {USE_MOCK && (
              <Tooltip label="VITE_USE_MOCK=1 — stream đang được phát lại từ api/mock.ts, không phải từ backend.">
                <Badge color="orange" variant="light">
                  dữ liệu giả lập
                </Badge>
              </Tooltip>
            )}
            {store.done && (
              <Badge variant="light" ff="monospace">
                trace: {store.done.trace_id}
              </Badge>
            )}
            <ActionIcon
              variant="default"
              size="lg"
              aria-label="Chuyển sáng/tối"
              onClick={() => setColorScheme(scheme === 'dark' ? 'light' : 'dark')}
            >
              {scheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
            </ActionIcon>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <Container size="xl" px={0}>
          <Grid gutter="md">
            <Grid.Col span={{ base: 12, lg: 9 }}>
              <Tabs value={tab} onChange={(v) => setTab(v ?? 'upload')} keepMounted={false}>
                <Tabs.List mb="md">
                  <Tabs.Tab value="upload" leftSection={<IconUpload size={15} />}>
                    Nạp mã nguồn
                  </Tabs.Tab>
                  <Tabs.Tab value="conversation" leftSection={<IconMessages size={15} />}>
                    Hội thoại
                  </Tabs.Tab>
                  <Tabs.Tab value="chat" leftSection={<IconMessage size={15} />}>
                    Hỏi đáp
                  </Tabs.Tab>
                  <Tabs.Tab value="coverage" leftSection={<IconLayoutGrid size={15} />}>
                    Ba tầng mẫu số
                  </Tabs.Tab>
                  <Tabs.Tab value="grid" leftSection={<IconChartGridDots size={15} />}>
                    Lưới rủi ro
                  </Tabs.Tab>
                  <Tabs.Tab value="gates" leftSection={<IconShieldLock size={15} />}>
                    Chuỗi cổng
                  </Tabs.Tab>
                  <Tabs.Tab value="claims" leftSection={<IconListCheck size={15} />}>
                    Claim inspector
                  </Tabs.Tab>
                  <Tabs.Tab value="trace" leftSection={<IconRoute size={15} />}>
                    Trace viewer
                  </Tabs.Tab>
                  {/* Tab phụ — cố ý KHÔNG phải defaultValue (đặc tả lỗi 8). */}
                  <Tabs.Tab value="prompt-data" leftSection={<IconFileDescription size={15} />}>
                    Dữ liệu đã gửi
                  </Tabs.Tab>
                </Tabs.List>

                <Tabs.Panel value="upload">
                  <UploadPanel result={upload} onResult={handleUpload} />
                </Tabs.Panel>

                <Tabs.Panel value="conversation">
                  <ChatConversation />
                </Tabs.Panel>

                <Tabs.Panel value="chat">
                  <ChatPanel
                    question={question}
                    onQuestionChange={setQuestion}
                    onRun={run}
                    onStop={stop}
                    status={store.status}
                    answer={store.answer}
                    disabled={!upload}
                  />
                </Tabs.Panel>

                <Tabs.Panel value="coverage">
                  <CoverageTriptych
                    layers={coverageQuery.data ?? []}
                    loading={coverageQuery.isLoading}
                  />
                </Tabs.Panel>

                <Tabs.Panel value="grid">
                  <GridHeatmap cells={store.cells} />
                </Tabs.Panel>

                <Tabs.Panel value="gates">
                  <GateChain gates={store.gates} />
                </Tabs.Panel>

                <Tabs.Panel value="claims">
                  <ClaimInspector claims={store.claims} />
                </Tabs.Panel>

                <Tabs.Panel value="trace">
                  <TraceViewer spans={store.spans} fallbackTraceId={store.done?.trace_id} />
                </Tabs.Panel>

                <Tabs.Panel value="prompt-data">
                  <PromptDataPanel
                    payload={promptQuery.data ?? null}
                    loading={promptQuery.isLoading}
                  />
                </Tabs.Panel>
              </Tabs>
            </Grid.Col>

            <Grid.Col span={{ base: 12, lg: 3 }}>
              <Stack gap="md">
                <RunControls
                  running={store.status === 'running'}
                  disabled={!upload}
                  onRun={run}
                  onStop={stop}
                  answerLength={store.answer.length}
                />
                <StepProgress steps={store.steps} />
                <WarningFeed warnings={store.warnings} />
              </Stack>
            </Grid.Col>
          </Grid>
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}

/**
 * Nút chạy luôn trong tầm mắt ở cột phải, để chạy lại được từ bất kỳ tab nào
 * mà không phải quay về tab hỏi đáp.
 */
function RunControls({
  running,
  disabled,
  onRun,
  onStop,
  answerLength,
}: {
  running: boolean;
  disabled: boolean;
  onRun: () => void;
  onStop: () => void;
  answerLength: number;
}) {
  return (
    <Paper withBorder p="sm" radius="md">
      <Group gap="xs" wrap="nowrap">
        <Button
          size="xs"
          leftSection={<IconPlayerPlay size={15} />}
          disabled={disabled || running}
          onClick={onRun}
        >
          Chạy phân tích
        </Button>
        <Button
          size="xs"
          variant="light"
          color="red"
          leftSection={<IconPlayerStop size={15} />}
          disabled={!running}
          onClick={onStop}
        >
          Dừng
        </Button>
      </Group>
      <Text size="xs" c="dimmed" mt={6}>
        {running
          ? `đang nhận token (${answerLength} ký tự)`
          : disabled
            ? 'chưa có mã nguồn — hãy chọn một repo mẫu'
            : 'sẵn sàng'}
      </Text>
    </Paper>
  );
}
