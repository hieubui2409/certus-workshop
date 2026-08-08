/**
 * Mã warning → MỘT DÒNG CHỮ ĐỌC ĐƯỢC.
 *
 * Đây là luật hiển thị số một của cả frontend (SDD 00 §5):
 *
 *   "A silent number is easy to ignore.
 *    A line reading `WARNING: judge biased toward passing` is not."
 *
 * Nên bảng dưới không trả về icon, không trả về màu suông. Nó trả về một
 * TIÊU ĐỀ đọc thành câu và một đoạn GIẢI THÍCH nói rõ *vì sao con số bên cạnh
 * không đọc như nó trông*. Icon nhỏ và badge màu cam nằm im là cách một cảnh
 * báo tồn tại mà không ai đọc.
 */

export type WarningSeverity = 'info' | 'warn' | 'critical';

export interface WarningStyle {
  severity: WarningSeverity;
  title: string;
  explain: string;
}

/**
 * Bốn dấu hiệu cargo cult mà system-design §11.1 yêu cầu phải hiện ra trong
 * buổi học đều nằm trong bảng này: `saturated`, `cluster-floor`,
 * `judge-rejected`, và metadata tuning golden set.
 */
export const WARNING_CATALOGUE: Record<string, WarningStyle> = {
  saturated: {
    severity: 'critical',
    title: 'Interval SATURATED — chạm biên, hẹp giả',
    explain:
      'Khoảng tin cậy đã tràn ra ngoài [0,1] rồi bị cắt về biên. Nó trông hẹp KHÔNG PHẢI vì dữ liệu chắc, mà vì bị cắt. Đừng đọc độ rộng của nó như độ chắc chắn.',
  },
  // Backend phát mã `interval-saturated`/`interval-wide` từ cờ của Wilson interval
  // (pipeline.py `line_rate.flags`/`grid_rate.flags`); phải có mặt ở bảng tra, nếu
  // không hai cảnh báo hay gặp nhất lại rơi vào FALLBACK "chưa phân loại".
  'interval-saturated': {
    severity: 'critical',
    title: 'Khoảng tin cậy chạm biên [0,1] — hẹp giả',
    explain:
      'Khoảng đã tràn ra ngoài [0,1] rồi bị cắt về biên. Nó trông hẹp vì bị cắt, không phải vì dữ liệu chắc — đừng đọc độ rộng của nó như độ chắc chắn.',
  },
  'interval-wide': {
    severity: 'critical',
    title: 'Khoảng tin cậy rộng hơn 30 điểm phần trăm',
    explain:
      'Khoảng tin cậy rộng hơn cả 30 điểm phần trăm — bản thân con số điểm gần như không mang thông tin. Cần thêm mẫu trước khi đọc tỉ lệ này như một kết luận.',
  },
  // Lưới nhiều trục sinh hàng trăm ô; backend chặn trần số ô đẩy qua SSE. Trần đó
  // phải TỰ KHAI, vì nếu im lặng thì người xem đếm ô trên bản đồ nhiệt và tưởng
  // đó là mẫu số — đo được trên document-intake: lưới thật 421 ô, UI từng in 200.
  'cells-truncated': {
    severity: 'warn',
    title: 'Lưới bị cắt bớt khi gửi lên giao diện',
    explain:
      'Chỉ một phần đầu của lưới được gửi lên để trình duyệt không đứng hình. Mẫu số THẬT của grid_coverage vẫn là toàn bộ lưới — đọc con số ở tab “Ba tầng mẫu số”, đừng đếm ô trên bản đồ nhiệt.',
  },
  'cluster-floor': {
    severity: 'critical',
    title: 'Zone rơi vào route cluster-floor',
    explain:
      'Không ước lượng được hệ số tương quan trong cụm nên hệ thống rơi về SÀN thận trọng nhất: n hiệu dụng bị hạ mạnh. Con số đi kèm dựa trên ít mẫu độc lập hơn nhiều so với n bạn thấy.',
  },
  'judge-rejected': {
    severity: 'critical',
    title: 'Judge bị TỪ CHỐI (J < 0.5)',
    explain:
      'Bộ chấm tự động không đạt ngưỡng đồng thuận với nhãn người. Mọi con số đi qua nó không có tư cách làm bằng chứng — kể cả khi nó trông đẹp.',
  },
  'judge-biased': {
    severity: 'critical',
    title: 'Judge LỆCH về phía cho qua',
    explain:
      'Bộ chấm gắn nhãn "đạt" nhiều hơn hẳn nhãn người trên cùng mẫu. Tỉ lệ pass bạn đang đọc bị thổi lên bởi chính công cụ đo, không phải bởi chất lượng code.',
  },
  'prior-used': {
    severity: 'warn',
    title: 'Đã dùng PRIOR — kiến thức huấn luyện, không phải quan sát',
    explain:
      'Một phần câu trả lời dựa trên kiến thức có sẵn của mô hình chứ không dựa trên kết quả đo trên repo của bạn. Kiến thức đó có thể đã cũ và không kiểm chứng được ở đây.',
  },
  'n-too-small': {
    severity: 'critical',
    title: 'n quá nhỏ — tỉ lệ này chưa nói được gì',
    explain:
      'Mẫu số nhỏ tới mức phần trăm gần như không mang thông tin. 3/3 và 300/300 cùng là 100%, nhưng một cái chỉ đảm bảo ≥43,9% còn cái kia đảm bảo ≥98,9%.',
  },
  'denominator-shrunk': {
    severity: 'critical',
    title: 'Mẫu số đã TỤT so với số ô liệt kê ban đầu',
    explain:
      'Một số ô đã rời khỏi mẫu số sau khi lưới được sinh ra. Phần trăm được tính trên phần còn lại. Hãy so số ô liệt kê với số ô thực sự vào mẫu trước khi đọc con số này.',
  },
  'na-from-analysis': {
    severity: 'critical',
    title: 'Có ô được đặt N/A từ phần phân tích của mô hình',
    explain:
      'N/A chỉ được phép vào qua constraints.yaml đã qua admit_constraint(). Ô N/A đến từ đường khác nghĩa là nội dung file đang điều khiển phán quyết.',
  },
  'empty-denominator': {
    severity: 'critical',
    title: 'Một cổng có mẫu số bằng 0',
    explain:
      'Cổng chạy nhưng chưa soi cái nào. Không có gì để soi là MỘT SỰ CỐ CẤU HÌNH, không phải một kết quả tốt.',
  },
  'trace-broken': {
    severity: 'critical',
    title: 'Trace bị đứt — nhiều trace_id trong một lần phân tích',
    explain:
      'Một lần phân tích phải là MỘT trace. Nhiều trace_id nghĩa là không nối được câu trả lời ngược về prompt đã sinh ra nó. Khi có sự cố, bạn sẽ debug bằng mắt.',
  },
  'golden-set-tuned': {
    severity: 'warn',
    title: 'Golden set đã qua nhiều vòng tinh chỉnh',
    explain:
      'Bộ đối chứng đã được sửa nhiều lần theo kết quả. Số vòng tuning là metadata phải hiện ra: một golden set đã tuning nhiều lần đo cái nó đã được sửa để đo.',
  },
  'unverified-number': {
    severity: 'warn',
    title: 'Có con số không kèm evidence_id',
    explain:
      'Luật 4: mọi con số trong response phải kèm evidence_id, hoặc in UNVERIFIED. Một con số không neo thì downstream phải coi như nó không tồn tại.',
  },
  'context-truncated': {
    severity: 'warn',
    title: 'Ngữ cảnh bị cắt trước khi vào prompt',
    explain:
      'Một phần knowledge base đã bị cắt do giới hạn context. Nếu bị cắt giữa câu, mô hình có thể phát biểu NGƯỢC nội dung chuẩn mà vẫn trích dẫn đúng file, đúng dòng.',
  },
  'sse-unknown-event': {
    severity: 'warn',
    title: 'Nhận được một loại SSE event không có trong hợp đồng',
    explain:
      'Backend gửi một event mà hợp đồng SDD 00 §5 không có. Không bỏ qua trong im lặng: nuốt im lặng một event lạ là cách hai nửa hệ thống trôi khỏi nhau.',
  },
  'sse-malformed-data': {
    severity: 'critical',
    title: 'Một frame SSE có phần data không parse được',
    explain:
      'Frame bị hỏng hoặc sai định dạng JSON. Sự kiện đó đã MẤT khỏi màn hình — con số bạn đang đọc có thể đang thiếu một phần.',
  },
  'llm-output': {
    severity: 'warn',
    title: 'Phần diễn giải bằng lời của mô hình không trọn vẹn',
    explain:
      'Một phần — đôi khi toàn bộ — phần diễn giải bằng lời bị bỏ; đọc dòng lý do NGAY DƯỚI để biết chính xác cái gì: có thể vài claim bị validator của hệ từ chối, hoặc câu trả lời sai định dạng JSON / lệch nonce chống bơm nên không đọc được. Đây KHÔNG phải chuyện chính sách dữ liệu và KHÔNG đụng tới số đo — mọi con số phía trên vẫn do pipeline tính độc lập, chỉ phần chữ diễn giải là thiếu.',
  },
  'data-policy': {
    severity: 'warn',
    title: 'Chính sách dữ liệu đã can thiệp trước khi gửi cho mô hình',
    explain:
      'Một số tệp bị GIỮ LẠI (không gửi cho mô hình) theo config/data-policy.yaml, hoặc bước diễn giải báo một điều kiện về dữ liệu. Con số phía sau chỉ dựa trên phần dữ liệu THỰC SỰ đã gửi — đọc nguyên văn bên dưới để biết cái gì đã bị giữ.',
  },
};

const FALLBACK: WarningStyle = {
  severity: 'warn',
  title: 'Cảnh báo từ backend',
  explain:
    'Mã cảnh báo này chưa có trong bảng tra của UI. Nội dung nguyên văn của backend được in bên dưới, không rút gọn.',
};

/**
 * Mã lạ VẪN render. Không có nhánh nào bỏ qua một warning vì UI không nhận ra
 * nó — một cảnh báo bị lọc vì "không biết là gì" là một cảnh báo bị mất.
 */
export function describeWarning(code: string): WarningStyle {
  return WARNING_CATALOGUE[code] ?? { ...FALLBACK, title: `${FALLBACK.title}: ${code}` };
}

export function severityColor(severity: WarningSeverity): string {
  switch (severity) {
    case 'critical':
      return 'red';
    case 'warn':
      return 'orange';
    case 'info':
      return 'blue';
  }
}

/**
 * Năm trường hợp bắt buộc phải sinh ra một dòng chữ (yêu cầu của SDD 08 §1.1).
 * Dùng để tự kiểm: mock nào không phát đủ năm mã này là mock chưa tái hiện
 * đúng hiện trường của buổi workshop.
 */
export const MANDATORY_WARNING_CODES: readonly string[] = [
  'saturated',
  'cluster-floor',
  'judge-rejected',
  'prior-used',
  'n-too-small',
];
