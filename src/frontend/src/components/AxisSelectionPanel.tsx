/**
 * Bước HITL chọn trục — người dùng xem đề xuất của engine ToT rồi CHỐT.
 *
 * Engine ĐỀ XUẤT (beam theo mật độ rủi ro biên ρ), người dùng PHÁN XỬ: tick giữ/bỏ
 * từng trục. Trục engine tự giữ (`locked`/`floored`) tick sẵn; trục bị loại
 * (`quarantined`/`rejected`) bỏ tick sẵn, kèm lý do — người học THẤY cái bị loại
 * và vì sao, không chỉ cái được giữ. Lựa chọn cuối đi vào `confirmed_axes` của lượt
 * phân tích; bỏ trống (không mở panel) ⇒ engine tự quyết.
 *
 * Ở chế độ mock KHÔNG có backend engine, `getAxisDiscovery` trả null → panel tự ẩn.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Loader,
  Paper,
  Stack,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import { IconAdjustments, IconCheck, IconInfoCircle } from '@tabler/icons-react';
import { getAxisDiscovery, USE_MOCK } from '@/api/analyze';
import {
  EMPTY_AXIS_STREAM,
  openAxisStream,
  reduceAxisEvent,
  type AxisStreamState,
} from '@/api/axes';
import type { AxisCandidate, AxisDiscoveryResponse, UploadResult } from '@/types/api';

const STEP_LABEL: Record<string, string> = {
  scan_repo: 'Quét mã nguồn tìm Enum',
  propose: 'Đề xuất trục ứng viên',
  admit_axes: 'Chấm ρ và kết nạp',
  llm_rationale: 'Mô hình diễn giải từng trục',
};

/**
 * Nhật ký sống của lượt khám phá trục.
 *
 * Có mặt vì một thanh chờ im lặng không phân biệt được "đang quét 3000 tệp" với
 * "đã treo". Ba tầng, theo đúng thứ tự công việc thật: bước → trục vừa chấm →
 * chữ mô hình đang viết.
 */
function AxisStreamLog({ state, running }: { state: AxisStreamState; running: boolean }) {
  return (
    <Paper withBorder p="xs" radius="sm" bg="var(--mantine-color-gray-0)">
      <Stack gap={6}>
        {state.steps.map((s) => (
          <Group key={s.name} gap="xs" wrap="nowrap">
            {s.status === 'running' ? <Loader size={12} /> : <IconCheck size={13} color="var(--mantine-color-green-6)" />}
            <Text size="xs" fw={500}>{STEP_LABEL[s.name] ?? s.name}</Text>
            <Text size="xs" c="dimmed" style={{ fontFamily: 'var(--mantine-font-family-monospace)' }}>
              {s.status === 'done' ? summarizeStep(s) : '…'}
            </Text>
          </Group>
        ))}

        {state.candidates.length > 0 && (
          <Text size="xs" c="dimmed">
            đã chấm {state.candidates.length} trục
            {running ? ' — đang chạy' : ''}
          </Text>
        )}

        {/* Mô hình bị bỏ qua: nói THẲNG lý do. Im lặng ở đây đọc thành "mô hình
            không có gì để nói", vốn là một câu khác hẳn. */}
        {state.llmSkipped && (
          <Group gap="xs" wrap="nowrap" align="flex-start">
            <IconInfoCircle size={13} style={{ marginTop: 2, flexShrink: 0 }} />
            <Text size="xs" c="dimmed">{state.llmSkipped}</Text>
          </Group>
        )}

        {state.llmText && (
          <Stack gap={2}>
            <Text size="xs" fw={500}>Mô hình đang viết</Text>
            <Text
              size="xs"
              c="dimmed"
              style={{
                fontFamily: 'var(--mantine-font-family-monospace)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                maxHeight: 160,
                overflowY: 'auto',
              }}
            >
              {state.llmText}
            </Text>
          </Stack>
        )}
      </Stack>
    </Paper>
  );
}

/** Một dòng tóm tắt cho bước đã xong — con số cụ thể, không phải "OK". */
function summarizeStep(s: Record<string, unknown>): string {
  if (s.name === 'scan_repo') return `${s.enums_found} enum`;
  if (s.name === 'propose') {
    const by = (s.by_origin ?? {}) as Record<string, number>;
    const parts = Object.entries(by).map(([k, v]) => `${k}:${v}`);
    return `${s.candidates} ứng viên${parts.length ? ` (${parts.join(' · ')})` : ''}`;
  }
  if (s.name === 'admit_axes') return `giữ ${s.locked}/${s.total} · ${s.engine}`;
  if (s.name === 'llm_rationale') return `${s.got} trục có diễn giải`;
  return 'xong';
}

interface Props {
  upload: UploadResult;
  /** Gọi khi người dùng chốt; null = trả quyền chọn lại cho engine (bỏ override). */
  onConfirm: (confirmedAxes: Record<string, string[]> | null) => void;
  /** Tập trục đang chốt (để hiển thị trạng thái đã áp). */
  confirmed: Record<string, string[]> | null;
}

const VERDICT_COLOR: Record<AxisCandidate['verdict'], string> = {
  locked: 'green',
  floored: 'blue',
  quarantined: 'orange',
  rejected: 'red',
};

const VERDICT_LABEL: Record<AxisCandidate['verdict'], string> = {
  locked: 'engine giữ',
  floored: 'giữ (sàn)',
  quarantined: 'cách ly',
  rejected: 'loại',
};

const ORIGIN_LABEL: Record<AxisCandidate['origin'], string> = {
  enum: 'enum',
  config: 'config',
  branch: 'branch',
};

const ORIGIN_COLOR: Record<AxisCandidate['origin'], string> = {
  enum: 'teal',
  config: 'indigo',
  branch: 'gray',
};

// Tier provenance — giải thích sức nặng bằng chứng. asserted (branch) không đủ tư
// cách vào lưới mặc định, đó là lý do nó bị loại no_provenance.
const TIER_HINT: Record<AxisCandidate['tier'], string> = {
  executed: 'đã chạy — bằng chứng mạnh nhất',
  retrieved: 'đọc từ khai báo (Enum) — chắc',
  derived: 'suy ra từ kiểu (Literal) — vừa',
  asserted: 'chỉ thấy nhánh so sánh — chưa chứng, bị loại khỏi default',
};

export function AxisSelectionPanel({ upload, onConfirm, confirmed }: Props) {
  const [data, setData] = useState<AxisDiscoveryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [stream, setStream] = useState<AxisStreamState>(EMPTY_AXIS_STREAM);

  const body = upload.target
    ? { target: upload.target }
    : upload.local_path
      ? { local_path: upload.local_path }
      : { upload_id: upload.upload_id ?? upload.run_id };

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    setStream(EMPTY_AXIS_STREAM);

    if (USE_MOCK) {
      // Mock frontend: không có backend nào để stream. Giữ nguyên đường cũ
      // (trả null ⇒ panel tự ẩn) thay vì mở một dòng SSE không bao giờ có dữ liệu.
      getAxisDiscovery(body)
        .then((res) => alive && setData(res))
        .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)))
        .finally(() => alive && setLoading(false));
      return () => {
        alive = false;
      };
    }

    const ctrl = new AbortController();
    let acc = EMPTY_AXIS_STREAM;
    openAxisStream(
      {
        target: upload.target,
        uploadId: upload.local_path ? undefined : (upload.upload_id ?? upload.run_id),
        localPath: upload.local_path,
      },
      {
        signal: ctrl.signal,
        onEvent: (ev) => {
          if (!alive) return;
          acc = reduceAxisEvent(acc, ev);
          setStream(acc);
          if (ev.event === 'done') setData(acc.result);
          if (ev.event === 'error') setError(acc.error);
        },
      },
    )
      .catch((e) => {
        // Huỷ do đổi repo/unmount không phải lỗi để báo lên người dùng.
        if (!alive || ctrl.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => alive && setLoading(false));

    return () => {
      alive = false;
      ctrl.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [upload.target, upload.upload_id, upload.run_id, upload.local_path]);

  // Tick khởi tạo tách khỏi vòng nạp: chỉ chạy khi ĐÃ có kết quả cuối, nếu không
  // mỗi sự kiện `axis` sẽ ghi đè lựa chọn người dùng vừa tick giữa chừng.
  useEffect(() => {
    if (!data) return;
    const init: Record<string, boolean> = {};
    for (const c of data.candidates) {
      init[c.axis] = confirmed ? c.axis in confirmed : c.kept;
    }
    setChecked(init);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const apply = useCallback(() => {
    if (!data) return;
    const out: Record<string, string[]> = {};
    for (const c of data.candidates) {
      if (checked[c.axis]) out[c.axis] = c.members;
    }
    onConfirm(out);
  }, [data, checked, onConfirm]);

  // Mock (null) hoặc chưa có dữ liệu: ẩn hẳn, không chiếm chỗ.
  if (!loading && !error && data === null) return null;

  const keptCount = Object.values(checked).filter(Boolean).length;
  const belowFloor = keptCount < 2;

  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="sm">
        <Group justify="space-between" align="center">
          <Group gap="xs">
            <IconAdjustments size={18} />
            <Title order={4}>Chọn trục rủi ro</Title>
          </Group>
          {data && (
            <Badge variant="light" color={data.engine === 'tot' ? 'green' : data.engine === 'floor' ? 'blue' : 'grape'}>
              engine: {data.engine}
            </Badge>
          )}
        </Group>

        {/* Nhật ký sống: hiện KHI ĐANG chạy, và ở lại nếu mô hình có nói gì —
            người dùng phải xem lại được cái đã chảy qua, không chỉ liếc một lần. */}
        {(loading || stream.llmText || stream.llmSkipped) && (
          <AxisStreamLog state={stream} running={loading} />
        )}
        {error && (
          <Alert color="red" variant="light" title="Không lấy được đề xuất trục">
            {error}
          </Alert>
        )}

        {data && (
          <>
            <Text size="xs" c="dimmed">
              {data.read_only
                ? 'Repo mẫu — trục đã CỐ ĐỊNH (khóa) để cassette và bài giảng tất định. Xem engine tỉa thế nào: nguồn (enum/config/branch), tier bằng chứng, ρ, và vì sao mỗi trục được giữ hay loại.'
                : 'Engine đề xuất tập trục theo mật độ rủi ro biên (ρ). Bạn là bên chốt: tick trục muốn đưa vào lưới. Trục bị cách ly/loại hiện kèm lý do.'}
            </Text>

            <Stack gap={6}>
              {data.candidates.map((c) => (
                <Group key={c.axis} gap="sm" wrap="nowrap" align="flex-start">
                  <Checkbox
                    checked={checked[c.axis] ?? false}
                    disabled={data.read_only}
                    onChange={(e) => {
                      // Chốt giá trị TRƯỚC khi vào updater: React 18 gọi updater lúc
                      // render (sau khi handler đã trả về), mà `e.currentTarget` bị
                      // reset về null ngay khi handler kết thúc → đọc trong updater là
                      // đọc `.checked` trên null, cả panel sập. Đọc ngoài rồi đóng vào.
                      const next = e.currentTarget.checked;
                      setChecked((prev) => ({ ...prev, [c.axis]: next }));
                    }}
                    mt={2}
                  />
                  <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
                    <Group gap={6} wrap="wrap">
                      <Text size="sm" fw={600} ff="monospace">
                        {c.axis}
                      </Text>
                      <Badge size="xs" color={VERDICT_COLOR[c.verdict]} variant="light">
                        {VERDICT_LABEL[c.verdict]}
                      </Badge>
                      <Tooltip label={TIER_HINT[c.tier]}>
                        <Badge size="xs" color={ORIGIN_COLOR[c.origin]} variant="dot">
                          {ORIGIN_LABEL[c.origin]} · {c.tier}
                        </Badge>
                      </Tooltip>
                      {c.rho != null && (
                        <Tooltip label="mật độ rủi ro biên — rủi ro thêm trên mỗi ô mới">
                          <Badge size="xs" variant="outline" ff="monospace">
                            ρ={c.rho.toFixed(2)}
                          </Badge>
                        </Tooltip>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed" style={{ wordBreak: 'break-word' }}>
                      {c.members.length} giá trị: {c.members.join(', ')}
                    </Text>
                    <Text size="xs" c="dimmed" ff="monospace" style={{ wordBreak: 'break-word' }}>
                      {c.source}
                    </Text>
                    {c.reason && (
                      <Text size="xs" c="orange">
                        lý do loại: {c.reason}
                      </Text>
                    )}
                    {c.rationale && (
                      <Text size="xs" c="dimmed" fs="italic" style={{ wordBreak: 'break-word' }}>
                        mô hình: {c.rationale}
                      </Text>
                    )}
                  </Stack>
                </Group>
              ))}
            </Stack>

            {data.note && (
              <Alert color="gray" variant="light" icon={<IconInfoCircle size={16} />} p="xs">
                <Text size="xs">{data.note}</Text>
              </Alert>
            )}

            {!data.read_only && belowFloor && (
              <Text size="xs" c="red">
                Cần ≥ 2 trục để dựng lưới t-wise. Đang chọn {keptCount}.
              </Text>
            )}

            {data.read_only ? (
              <Text size="xs" c="dimmed">
                🔒 Trục khóa. Muốn tự chọn trục thì tải lên repo của bạn — repo thật bắt
                buộc qua bước này.
              </Text>
            ) : (
              <>
                <Group gap="xs">
                  <Button
                    size="xs"
                    leftSection={<IconAdjustments size={15} />}
                    disabled={belowFloor}
                    onClick={apply}
                  >
                    Áp {keptCount} trục vào lượt phân tích
                  </Button>
                  {confirmed && (
                    <Button size="xs" variant="subtle" color="gray" onClick={() => onConfirm(null)}>
                      Trả lại cho engine
                    </Button>
                  )}
                </Group>
                {confirmed && (
                  <Text size="xs" c="green">
                    Đang dùng lựa chọn của bạn: {Object.keys(confirmed).join(', ')}
                  </Text>
                )}
              </>
            )}
          </>
        )}
      </Stack>
    </Paper>
  );
}
