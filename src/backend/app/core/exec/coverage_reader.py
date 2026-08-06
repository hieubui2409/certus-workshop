"""Đọc artifact độ phủ dòng: Cobertura XML · LCOV · `.coverage` của coverage.py.

Ba định dạng, một kiểu trả về. Không nhánh nào dùng regex: Cobertura đi theo cây
DOM, LCOV duyệt theo LOẠI RECORD, `.coverage` đi qua API `coverage.CoverageData`.
Bài học `B26` của tài liệu nền — *"khảo sát bằng regex trên mã luôn trả tập NHỎ
HƠN thật; dùng AST"* — áp nguyên vẹn cho artifact: một đường dẫn Windows chứa
dấu hai chấm hay một thẻ `<line>` xuống dòng là đủ để regex trượt, và cái nó
trượt thì im lặng.

Nguyên tắc nặng nhất của file này nằm ở `_finish()`: report rỗng thì NỔ, không
trả về độ phủ 0.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.contracts.errors import EmptyDenominatorError
from app.core.exec.runner import ExecConfig, load_exec_config

CoverageFormat = Literal["cobertura", "lcov", "coveragepy"]


@dataclass(frozen=True)
class FileCoverage:
    """Độ phủ của một file. `hits_by_line` chỉ chứa dòng KHẢ-ĐO.

    Dòng không khả đo (trắng, comment, docstring) không có mặt ở đây — chúng
    không thuộc mẫu số, và nhét chúng vào sẽ làm mọi tỉ lệ đẹp lên một cách vô
    nghĩa.
    """

    path: str
    hits_by_line: dict[int, int] = field(default_factory=dict)

    @property
    def lines_total(self) -> int:
        return len(self.hits_by_line)

    @property
    def lines_covered(self) -> int:
        return sum(1 for hits in self.hits_by_line.values() if hits > 0)


@dataclass(frozen=True)
class CoverageReport:
    """Một phép đo độ phủ dòng, đã biết chắc là KHÔNG rỗng.

    Không tồn tại instance nào của kiểu này với mẫu số bằng 0 — nhánh đó đi ra
    bằng EmptyDenominatorError chứ không bằng một object.
    """

    fmt: CoverageFormat
    source: str
    files: dict[str, FileCoverage]

    @property
    def lines_total(self) -> int:
        return sum(f.lines_total for f in self.files.values())

    @property
    def lines_covered(self) -> int:
        return sum(f.lines_covered for f in self.files.values())

    @property
    def line_rate(self) -> float:
        """An toàn vì mẫu số 0 đã bị chặn từ `_finish()`."""
        return self.lines_covered / self.lines_total

    def touches(self, path: str, line: int) -> bool:
        """Dòng `path:line` có được chạy ít nhất một lần không.

        Dùng cho bảng band projection: "cov_cell chạm code_path". Trả False cho
        cả hai ca "có trong report, hits=0" và "không có trong report" — người
        gọi phân biệt hai ca đó bằng `is_measured()` nếu cần.
        """
        record = self._lookup(path)
        return record is not None and record.hits_by_line.get(line, 0) > 0

    def is_measured(self, path: str) -> bool:
        return self._lookup(path) is not None

    def _lookup(self, path: str) -> FileCoverage | None:
        if path in self.files:
            return self.files[path]
        # Report ghi đường dẫn tương đối theo --source, người gọi thường cầm
        # đường dẫn tuyệt đối. So bằng đuôi đường dẫn thay vì normalize mù, để
        # "a/b/cart.py" không khớp nhầm với "other/cart.py".
        needle = Path(path)
        for key, record in self.files.items():
            candidate = Path(key)
            if candidate.name != needle.name:
                continue
            if str(needle).endswith(str(candidate)) or str(candidate).endswith(str(needle)):
                return record
        return None


def _finish(
    fmt: CoverageFormat,
    source: Path,
    files: dict[str, FileCoverage],
    cfg: ExecConfig,
) -> CoverageReport:
    """Cửa duy nhất tạo ra CoverageReport, và là cửa duy nhất từ chối.

    Ba cách một lệnh coverage "trông hợp lý" làm sập cả grid — chỉ collect mà
    không sinh report · sai format · quên `--source` — đều cho ra đúng một triệu
    chứng: report đọc được nhưng rỗng. Đã đo được: năm dòng của chính script
    probe đủ để đẩy toàn bộ lưới về `unknown` trong khi báo cáo vẫn "read as
    confident". Trả về 0.0 ở đây là biến một SỰ CỐ CẤU HÌNH thành một KẾT QUẢ ĐO.
    """
    if len(files) < cfg.coverage.min_files_in_report:
        raise EmptyDenominatorError(
            f"coverage report {source} chỉ có {len(files)} file, cần ít nhất "
            f"{cfg.coverage.min_files_in_report} (khoá coverage.min_files_in_report). "
            f"Report rỗng là sự cố cấu hình — kiểm tra --source và bước sinh report."
        )
    total = sum(f.lines_total for f in files.values())
    if total == 0:
        raise EmptyDenominatorError(
            f"coverage report {source} có file nhưng 0 dòng khả-đo. "
            f"Đây KHÔNG phải độ phủ 0% — đây là report không đo được gì."
        )
    return CoverageReport(fmt=fmt, source=str(source), files=files)


def read_cobertura(path: Path, *, config: ExecConfig | None = None) -> CoverageReport:
    """Đọc Cobertura XML (`coverage xml`)."""
    cfg = config or load_exec_config()
    path = Path(path)
    if not path.exists():
        raise EmptyDenominatorError(
            f"không có coverage report tại {path}. Thiếu report và độ phủ 0% là "
            f"hai chuyện khác nhau; module này từ chối gộp chúng."
        )

    root = ET.parse(path).getroot()
    files: dict[str, FileCoverage] = {}
    for class_node in root.iter("class"):
        filename = class_node.get("filename")
        if not filename:
            continue
        hits_by_line = files.get(filename, FileCoverage(filename)).hits_by_line
        for line_node in class_node.iter("line"):
            number = line_node.get("number")
            if number is None:
                continue
            hits = int(line_node.get("hits", "0"))
            # Một dòng xuất hiện ở nhiều <class> (decorator, nested class) thì
            # lấy tổng hit: nó được chạy ở cả hai chỗ, không phải chỉ chỗ sau.
            hits_by_line[int(number)] = hits_by_line.get(int(number), 0) + hits
        files[filename] = FileCoverage(filename, hits_by_line)

    return _finish("cobertura", path, files, cfg)


def read_lcov(path: Path, *, config: ExecConfig | None = None) -> CoverageReport:
    """Đọc LCOV `.info`.

    LCOV là định dạng record `KEY:value` mỗi dòng; ta tách đúng dấu hai chấm
    ĐẦU TIÊN, vì phần value của `SF:` là đường dẫn và đường dẫn được phép chứa
    dấu hai chấm.
    """
    cfg = config or load_exec_config()
    path = Path(path)
    if not path.exists():
        raise EmptyDenominatorError(f"không có coverage report tại {path}")

    files: dict[str, FileCoverage] = {}
    current: str | None = None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "end_of_record":
            current = None
            continue
        key, _, value = line.partition(":")
        if key == "SF":
            current = value
            files.setdefault(current, FileCoverage(current, {}))
        elif key == "DA" and current is not None:
            number, _, hits = value.partition(",")
            # DA có thể mang trường checksum thứ ba: "DA:12,1,abcdef".
            hit_count = int(hits.split(",")[0]) if hits else 0
            files[current].hits_by_line[int(number)] = hit_count

    return _finish("lcov", path, files, cfg)


def read_coverage_data(path: Path, *, config: ExecConfig | None = None) -> CoverageReport:
    """Đọc file dữ liệu `.coverage` bằng API của coverage.py.

    Dùng `CoverageData` chứ không đọc SQLite tay: schema của file đó là chuyện
    nội bộ của coverage.py và đã đổi giữa các bản major.

    Lưu ý về ngữ nghĩa: `CoverageData` chỉ lưu TẬP dòng đã chạy, không lưu số
    lần chạy. Nên `hits` ở đây luôn là 1 — đủ cho câu hỏi duy nhất mà band
    projection đặt ra ("dòng này có được chạm không"), và không được dùng để
    nói "dòng này chạy bao nhiêu lần".
    """
    cfg = config or load_exec_config()
    path = Path(path)
    if not path.exists():
        raise EmptyDenominatorError(f"không có coverage data tại {path}")

    try:
        from coverage import CoverageData
    except ImportError as exc:  # pragma: no cover - coverage nằm trong requirements
        raise EmptyDenominatorError(
            f"không đọc được {path}: chưa cài coverage.py. Không có nhánh đọc "
            f"tay thay thế — đọc sai định dạng còn tệ hơn không đọc."
        ) from exc

    data = CoverageData(basename=str(path))
    data.read()
    files: dict[str, FileCoverage] = {}
    for measured in data.measured_files():
        lines = data.lines(measured) or []
        files[measured] = FileCoverage(measured, {int(n): 1 for n in lines})

    return _finish("coveragepy", path, files, cfg)


def read_report(path: Path, *, config: ExecConfig | None = None) -> CoverageReport:
    """Chọn parser theo tên file.

    Định dạng không nhận ra thì NỔ chứ không đoán: `README.md:8.9` của note 02
    ghi rõ "sai format/filename — JSON coverage report không đọc được (chỉ
    Cobertura XML + LCOV)", và cái hỏng đó im lặng.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".xml":
        return read_cobertura(path, config=config)
    if suffix in {".info", ".lcov"}:
        return read_lcov(path, config=config)
    if path.name == ".coverage" or path.name.startswith(".coverage"):
        return read_coverage_data(path, config=config)
    raise EmptyDenominatorError(
        f"không nhận ra định dạng coverage của {path.name}. Hỗ trợ: Cobertura "
        f"(.xml), LCOV (.info/.lcov), coverage.py (.coverage*)."
    )


__all__ = [
    "CoverageFormat",
    "CoverageReport",
    "FileCoverage",
    "read_cobertura",
    "read_coverage_data",
    "read_lcov",
    "read_report",
]
