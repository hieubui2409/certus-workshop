/**
 * Kiểu của lớp REST — SDD 08 §4.3.
 *
 * Ba đường: danh sách repo mẫu, kết quả ingest (bước 1 của pipeline), và
 * payload thực sự đã đi vào prompt của mô hình.
 */

export type SampleRepoId = 'shopcart' | 'ledger' | 'payments';

/**
 * Đúng hình dạng `/api/samples` trả về (`src/backend/app/api/routes/samples.py`):
 * `files` = số tệp `.py`, `test_files` = số tệp `test_*.py`. KHÔNG có `file_count`
 * hay `teaches` — hai trường đó chưa từng tồn tại ở backend thật, chỉ có trong
 * `api/mock.ts` cho mục đích dạy.
 */
export interface SampleRepo {
  id: SampleRepoId;
  name: string;
  description: string;
  files: number;
  test_files: number;
}

export interface FileEntry {
  path: string;
  bytes: number;
  sha256: string;
}

/**
 * `reason` BẮT BUỘC khác rỗng. Một file biến mất không lý do là một mẫu số
 * tụt không lý do — đúng cái cách lỗi 8 đi lọt.
 */
export interface RejectedFile {
  path: string;
  reason: string;
  /** pattern trong `config/data-policy.yaml` đã khớp, nếu có */
  matched_pattern?: string | null;
}

export interface UploadResult {
  run_id: string;
  source: 'sample' | 'zip' | 'folder';
  label: string;
  accepted: FileEntry[];
  rejected: RejectedFile[];
  /**
   * Định danh dùng để gọi `/api/analyze` (SDD 08 §4.3): đúng MỘT trong hai.
   * `target` cho repo mẫu chọn sẵn (không đi qua `/api/upload`); `upload_id`
   * cho tệp `.zip` vừa tải lên thật — giá trị `UploadAck.upload_id` mà
   * `/api/upload` trả về. KHÔNG PHẢI `run_id`: đó là id của LẦN PHÂN TÍCH,
   * chưa hề tồn tại ở bước ingest này.
   */
  target?: string;
  upload_id?: string;
  /**
   * Thư mục có sẵn trên máy chạy backend. Nguồn thứ ba vì một repo thật không
   * đi qua zip được nguyên vẹn: `.venv` neo đường dẫn tuyệt đối nên nén theo
   * là vô dụng, còn nén trần thì mất môi trường.
   */
  local_path?: string;
}

/**
 * Một mẩu văn bản THỰC SỰ đi vào prompt. Không phải toàn bộ file: thứ đi vào
 * prompt mới là thứ rời khỏi hạ tầng.
 */
export interface PromptChunk {
  path: string;
  /** vị trí trong prompt cuối cùng */
  order: number;
  chars: number;
  excerpt: string;
  redacted: boolean;
}

/** Một tệp bị GIỮ LẠI, không gửi cho mô hình — đúng shape backend thật trả. */
export interface HeldFile {
  path: string;
  reason: string;
}

/**
 * Hai phương ngữ cùng một endpoint. `api/mock.ts` phát bản GIÀU (chunks kèm
 * `excerpt` — nội dung thật đã rời khỏi máy, gồm cả `payments/.env`); backend
 * thật (`/prompt-payload/{run_id}`) phát bản MỎNG (chỉ danh sách `files_sent`
 * + `files_held` kèm lý do). Mọi trường ngoài `run_id` là TUỲ CHỌN: một shape
 * thiếu trường của shape kia KHÔNG được làm vỡ panel — một panel vỡ ở đây là
 * một panel không ai đọc được payload, đúng chỗ lỗi 8 cần phơi ra.
 */
export interface PromptPayload {
  run_id: string;
  // Bản giàu (mock):
  /** bước nào của pipeline gửi payload này */
  step?: number;
  model?: string;
  system_prompt_excerpt?: string;
  chunks?: PromptChunk[];
  total_chars?: number;
  // Bản mỏng (backend thật):
  files_sent?: string[];
  files_held?: HeldFile[];
  blocklist?: string[];
  note?: string;
}

/**
 * Đúng `AnalyzeRequest` ở backend (`src/backend/app/api/schemas.py`): đúng MỘT
 * trong `target` (repo mẫu) hoặc `upload_id` (tệp vừa tải lên thật) — backend
 * KHÔNG có trường `run_id` trên request, chỉ có trên response.
 */
export interface AnalyzeRequest {
  target?: string;
  upload_id?: string;
  local_path?: string;
  question: string;
  /**
   * Lệnh chạy bộ kiểm của repo đích. Bỏ trống ⇒ backend tự dò (uv / venv sẵn
   * có / môi trường CERTUS). Có mặt vì không cách nào đoán đúng cho mọi repo.
   */
  test_command?: string[];
  /** Biến môi trường cho lượt chạy bộ kiểm — nhiều repo có guard đòi đúng biến. */
  test_env?: Record<string, string>;
  /**
   * HITL: tập trục người dùng ĐÃ CHỐT sau khi xem đề xuất của engine ToT. Key là
   * tên trục cần giữ, value là danh sách giá trị (rỗng ⇒ giữ mọi giá trị). Bỏ
   * trống ⇒ engine tự chọn (beam ρ + sàn viability).
   */
  confirmed_axes?: Record<string, string[]>;
}

/** Một trục ứng viên kèm phán quyết của engine ToT (khớp AxisCandidate backend). */
export interface AxisCandidate {
  axis: string;
  members: string[];
  source: string;
  kept: boolean;
  verdict: 'locked' | 'quarantined' | 'rejected' | 'floored';
  rho?: number | null;
  reason?: string | null;
  /** Nguồn proposer tìm ra trục. */
  origin: 'enum' | 'config' | 'branch';
  /** Tier provenance — giải thích vì sao branch (asserted) bị loại khỏi default. */
  tier: 'executed' | 'retrieved' | 'derived' | 'asserted';
  /** Diễn giải của mô hình (advisory, chỉ live). */
  rationale?: string | null;
}

/** Kết quả `/api/axes/discover` — đề xuất tập trục cho bước HITL. */
export interface AxisDiscoveryResponse {
  target?: string | null;
  upload_id?: string | null;
  local_path?: string | null;
  candidates: AxisCandidate[];
  engine: 'tot' | 'floor' | 'hitl';
  note?: string | null;
  /** TRUE cho repo mẫu — panel khóa, xem nhưng không sửa (giá trị học thuật). */
  read_only: boolean;
}

/**
 * Ba tầng mẫu số (system-design §1.3). Backend gửi ba khối RIÊNG BIỆT; không
 * có trường thứ tư nào gộp chúng lại.
 */
export interface CoverageLayer {
  id: 'line' | 'mutation' | 'grid';
  title: string;
  question: string;
  source: string;
  k: number;
  n: number;
  interval: import('./contracts').Interval | null;
  flags: string[];
  /** ghi chú về mẫu số — vì sao n lại là con số đó */
  denominator_note: string;
  evidence_ids: string[];
}
