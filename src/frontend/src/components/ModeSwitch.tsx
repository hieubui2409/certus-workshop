/**
 * Công tắc chế độ LLM của backend ở header: cassette (mock) ⇄ live.
 *
 * "cassette" = backend phát lại bản ghi có sẵn, tất định, cả lớp thấy như nhau,
 * KHÔNG cần khoá. "live" = backend gọi model Anthropic thật (qua khoá API hoặc
 * proxy ccs/cliproxy) — phi tất định, tốn tài nguyên, và CẦN credentials nằm
 * sẵn trong process backend.
 *
 * Vì sao có màn hướng dẫn: công tắc này KHÔNG tự bơm được credentials vào một
 * process đang chạy — creds đọc từ biến môi trường lúc backend khởi động. Nên
 * nếu backend chạy mà không có creds (`live_available=false`), bấm "live" chỉ
 * đổi cờ chứ lượt phân tích kế tiếp vẫn nổ. Đúng lúc đó ta mở hướng dẫn từng
 * bước thay vì để người dùng đâm vào lỗi khó hiểu.
 *
 * Chỉ render khi FE đang nói chuyện với backend thật (USE_MOCK=false); ở chế độ
 * dữ-liệu-giả-FE thì không có backend để đổi, công tắc vô nghĩa.
 */

import {
  Alert,
  Badge,
  Button,
  Code,
  Group,
  List,
  Loader,
  Modal,
  SegmentedControl,
  Stack,
  Text,
  Tooltip,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconAlertTriangle, IconBolt, IconDatabase, IconPlugConnected } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { getMode, setMode, type LlmMode } from '@/api/mode';

export function ModeSwitch() {
  const qc = useQueryClient();
  const [guideOpen, guide] = useDisclosure(false);

  const modeQuery = useQuery({
    queryKey: ['llm-mode'],
    queryFn: ({ signal }) => getMode(signal),
    // Đọc lại đều đặn: nếu giảng viên khởi động lại backend kèm ccs env thì
    // live_available lật sang true mà không cần người dùng thao tác gì.
    refetchInterval: 15_000,
  });

  const mutation = useMutation({
    mutationFn: (mode: LlmMode) => setMode(mode),
    onSuccess: (state) => qc.setQueryData(['llm-mode'], state),
  });

  if (modeQuery.isLoading) {
    return <Loader size="xs" />;
  }
  if (modeQuery.isError || !modeQuery.data) {
    // Không nuốt lỗi: nếu không đọc được /mode, nói thẳng thay vì hiện một công
    // tắc giả vờ hoạt động.
    return (
      <Tooltip label="Không đọc được /api/mode — backend có đang chạy không?">
        <Badge color="red" variant="light">
          chế độ: ?
        </Badge>
      </Tooltip>
    );
  }

  const { mode, live_available, model } = modeQuery.data;
  // 'record' (bật qua CLI) không nằm trong công tắc; hiện đúng trạng thái nhưng
  // để SegmentedControl ở 'mock' về mặt hình thức, kèm badge cảnh báo.
  const isRecord = mode === 'record';
  const current: LlmMode = mode === 'live' ? 'live' : 'mock';

  const handleChange = (value: string) => {
    const next = value as LlmMode;
    if (next === current) return;
    if (next === 'live' && !live_available) {
      // Chưa có creds trong process → không lật cờ một cách vô ích, mở hướng dẫn.
      guide.open();
      return;
    }
    mutation.mutate(next);
  };

  return (
    <>
      <Group gap={6} wrap="nowrap">
        {isRecord && (
          <Tooltip label="Backend đang ở chế độ 'record' (bật qua CLI) — đang GHI cassette, không chỉ phát lại.">
            <Badge color="grape" variant="light">
              record
            </Badge>
          </Tooltip>
        )}
        <Tooltip
          label={
            current === 'live'
              ? `Gọi model thật: ${model}. Phi tất định, tốn tài nguyên.`
              : 'Phát lại cassette — tất định, không cần khoá. Mặc định cho lớp học.'
          }
        >
          <SegmentedControl
            size="xs"
            value={current}
            onChange={handleChange}
            disabled={mutation.isPending}
            data={[
              {
                value: 'mock',
                label: (
                  <Group gap={4} wrap="nowrap">
                    <IconDatabase size={13} />
                    <span>cassette</span>
                  </Group>
                ),
              },
              {
                value: 'live',
                label: (
                  <Group gap={4} wrap="nowrap">
                    <IconBolt size={13} />
                    <span>live</span>
                    {!live_available && <IconAlertTriangle size={12} />}
                  </Group>
                ),
              },
            ]}
          />
        </Tooltip>
        {current === 'live' && (
          <Badge color={live_available ? 'teal' : 'orange'} variant="light" ff="monospace">
            {live_available ? model : 'chưa cấu hình'}
          </Badge>
        )}
      </Group>

      <LiveSetupGuide
        opened={guideOpen}
        onClose={guide.close}
        onRecheck={() => modeQuery.refetch()}
        onForceLive={() => {
          mutation.mutate('live');
          guide.close();
        }}
        liveAvailable={live_available}
      />
    </>
  );
}

function LiveSetupGuide({
  opened,
  onClose,
  onRecheck,
  onForceLive,
  liveAvailable,
}: {
  opened: boolean;
  onClose: () => void;
  onRecheck: () => void;
  onForceLive: () => void;
  liveAvailable: boolean;
}) {
  return (
    <Modal opened={opened} onClose={onClose} title="Bật chế độ live (gọi model thật)" size="lg" centered>
      <Stack gap="md">
        <Alert
          color="blue"
          variant="light"
          icon={<IconPlugConnected size={18} />}
          title="Live cần credentials TRONG process backend"
        >
          <Text size="sm">
            Công tắc này không tự bơm khoá vào backend đang chạy được — khoá đọc từ biến môi trường
            lúc backend <b>khởi động</b>. Nên hãy dừng backend, nạp biến, rồi bật lại; sau đó công
            tắc live tự sáng.
          </Text>
        </Alert>

        <div>
          <Text fw={600} size="sm" mb={4}>
            Cách 1 — có khoá API Anthropic trả tiền
          </Text>
          <Code block>
            {`export CERTUS_LLM_MODE=live
export CERTUS_ANTHROPIC_API_KEY=sk-ant-...
uvicorn app.main:app --reload --port 8000`}
          </Code>
        </div>

        <div>
          <Text fw={600} size="sm" mb={4}>
            Cách 2 — dùng gói Claude qua proxy ccs/cliproxy (không tốn khoá API)
          </Text>
          <List size="sm" spacing={6} type="ordered">
            <List.Item>
              Bật proxy cục bộ, để nguyên terminal đó chạy: <Code>ccs local</Code>
            </List.Item>
            <List.Item>
              Terminal chạy backend, nạp biến của proxy rồi bật:
              <Code block mt={4}>
                {`eval "$(ccs env local)"
export ANTHROPIC_BASE_URL=http://localhost:8317
export CERTUS_LLM_MODE=live
export CERTUS_MODEL=claude-opus-5
uvicorn app.main:app --reload --port 8000`}
              </Code>
            </List.Item>
          </List>
        </div>

        <Alert color="orange" variant="light" icon={<IconAlertTriangle size={16} />} title="Hai chỗ hay vấp (đã kiểm chứng)">
          <List size="sm" spacing={4}>
            <List.Item>
              Dùng <Code>localhost</Code>, đừng <Code>127.0.0.1</Code> — proxy thường chỉ nghe trên
              IPv6 (<Code>[::1]</Code>), nên <Code>127.0.0.1:8317</Code> báo <i>connection refused</i>.
            </List.Item>
            <List.Item>
              Tránh biến thể model có hậu tố <Code>[1m]</Code> (ví dụ <Code>claude-opus-5[1m]</Code>) —
              nó có thể làm proxy treo. Dùng tên trần <Code>claude-opus-5</Code> hoặc{' '}
              <Code>claude-haiku-4-5</Code>.
            </List.Item>
          </List>
        </Alert>

        <Group justify="space-between" mt="xs">
          <Button
            variant="light"
            leftSection={<IconPlugConnected size={15} />}
            onClick={() => {
              onRecheck();
            }}
          >
            Tôi đã bật lại backend — kiểm tra lại
          </Button>
          {!liveAvailable && (
            <Tooltip label="Vẫn chuyển cờ sang live; lượt phân tích kế tiếp sẽ báo lỗi thiếu khoá nếu chưa cấu hình.">
              <Button variant="subtle" color="orange" onClick={onForceLive}>
                Vẫn bật live để thử
              </Button>
            </Tooltip>
          )}
        </Group>

        <Text size="xs" c="dimmed">
          Chế độ cassette (mặc định) không cần bước nào ở trên — đủ cho mọi bài trên lớp. Live chỉ
          dùng khi muốn xem model thật diễn giải trực tiếp.
        </Text>
      </Stack>
    </Modal>
  );
}
