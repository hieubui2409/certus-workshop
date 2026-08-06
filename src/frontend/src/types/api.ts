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
  source: 'sample' | 'zip';
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

export interface PromptPayload {
  run_id: string;
  /** bước nào của pipeline gửi payload này */
  step: number;
  model: string;
  system_prompt_excerpt: string;
  chunks: PromptChunk[];
  total_chars: number;
}

/**
 * Đúng `AnalyzeRequest` ở backend (`src/backend/app/api/schemas.py`): đúng MỘT
 * trong `target` (repo mẫu) hoặc `upload_id` (tệp vừa tải lên thật) — backend
 * KHÔNG có trường `run_id` trên request, chỉ có trên response.
 */
export interface AnalyzeRequest {
  target?: string;
  upload_id?: string;
  question: string;
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
  interval: import('./contracts').Interval;
  flags: string[];
  /** ghi chú về mẫu số — vì sao n lại là con số đó */
  denominator_note: string;
  evidence_ids: string[];
}
