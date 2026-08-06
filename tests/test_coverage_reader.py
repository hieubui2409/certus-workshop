"""Ghim hành vi của `core/exec/coverage_reader.py`.

Luật trung tâm bị ghim ở đây: **report rỗng thì NỔ, không trả về độ phủ 0**.
Note 02 §8.9 — năm dòng của chính script probe đủ để đẩy toàn bộ lưới về
`unknown` trong khi báo cáo vẫn "read as confident". Một report rỗng là SỰ CỐ
CẤU HÌNH, không phải một KẾT QUẢ ĐO.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.contracts.errors import EmptyDenominatorError  # noqa: E402
from app.core.exec.coverage_reader import (  # noqa: E402
    read_cobertura,
    read_coverage_data,
    read_lcov,
    read_report,
)
from app.core.exec.runner import ExecConfig, load_exec_config  # noqa: E402

COBERTURA = textwrap.dedent(
    """\
    <?xml version="1.0" ?>
    <coverage line-rate="0.75">
      <packages>
        <package name="pkg">
          <classes>
            <class filename="pkg/cart.py" name="cart">
              <lines>
                <line number="4" hits="3"/>
                <line number="5" hits="1"/>
                <line number="9" hits="0"/>
              </lines>
            </class>
            <class filename="pkg/util.py" name="util">
              <lines>
                <line number="2" hits="7"/>
              </lines>
            </class>
          </classes>
        </package>
      </packages>
    </coverage>
    """
)

LCOV = textwrap.dedent(
    """\
    TN:
    SF:pkg/cart.py
    DA:4,3
    DA:5,1
    DA:9,0
    LF:3
    LH:2
    end_of_record
    SF:pkg/util.py
    DA:2,7,abc123
    end_of_record
    """
)


@pytest.fixture
def cfg() -> ExecConfig:
    return load_exec_config(reload=True)


# ── Cobertura ───────────────────────────────────────────────────────────


def test_cobertura_walks_the_dom(tmp_path: Path, cfg: ExecConfig) -> None:
    path = tmp_path / "coverage.xml"
    path.write_text(COBERTURA, encoding="utf-8")
    report = read_cobertura(path, config=cfg)

    assert report.fmt == "cobertura"
    assert set(report.files) == {"pkg/cart.py", "pkg/util.py"}
    assert report.lines_total == 4
    assert report.lines_covered == 3
    assert report.line_rate == 0.75


def test_touches_distinguishes_run_from_not_run(tmp_path: Path, cfg: ExecConfig) -> None:
    path = tmp_path / "coverage.xml"
    path.write_text(COBERTURA, encoding="utf-8")
    report = read_cobertura(path, config=cfg)

    assert report.touches("pkg/cart.py", 4) is True
    assert report.touches("pkg/cart.py", 9) is False  # có trong report, hits=0
    assert report.touches("pkg/cart.py", 99) is False  # không có trong report
    assert report.is_measured("pkg/cart.py") is True
    assert report.is_measured("pkg/khac.py") is False


def test_absolute_paths_resolve_against_relative_report_entries(
    tmp_path: Path, cfg: ExecConfig
) -> None:
    path = tmp_path / "coverage.xml"
    path.write_text(COBERTURA, encoding="utf-8")
    report = read_cobertura(path, config=cfg)
    assert report.touches("/srv/app/pkg/cart.py", 4) is True


def test_a_same_named_file_in_another_tree_does_not_match(
    tmp_path: Path, cfg: ExecConfig
) -> None:
    """"khop duoi duong dan" khong duoc bien thanh "khop ten file"."""
    path = tmp_path / "coverage.xml"
    path.write_text(COBERTURA, encoding="utf-8")
    report = read_cobertura(path, config=cfg)
    assert report.is_measured("vendor/other/cart.py") is False


# ── LCOV ────────────────────────────────────────────────────────────────


def test_lcov_reads_the_same_shape(tmp_path: Path, cfg: ExecConfig) -> None:
    path = tmp_path / "lcov.info"
    path.write_text(LCOV, encoding="utf-8")
    report = read_lcov(path, config=cfg)

    assert report.fmt == "lcov"
    assert report.lines_total == 4
    assert report.lines_covered == 3


def test_lcov_da_with_a_checksum_field_still_parses(tmp_path: Path, cfg: ExecConfig) -> None:
    path = tmp_path / "lcov.info"
    path.write_text(LCOV, encoding="utf-8")
    report = read_lcov(path, config=cfg)
    assert report.touches("pkg/util.py", 2) is True


def test_lcov_keeps_a_path_containing_a_colon(tmp_path: Path, cfg: ExecConfig) -> None:
    """Tách đúng dấu hai chấm ĐẦU TIÊN — value của SF: là đường dẫn."""
    path = tmp_path / "lcov.info"
    path.write_text("SF:C:/repo/pkg/cart.py\nDA:1,1\nend_of_record\n", encoding="utf-8")
    report = read_lcov(path, config=cfg)
    assert "C:/repo/pkg/cart.py" in report.files


def test_two_formats_agree_on_the_same_run(tmp_path: Path, cfg: ExecConfig) -> None:
    xml = tmp_path / "coverage.xml"
    xml.write_text(COBERTURA, encoding="utf-8")
    info = tmp_path / "lcov.info"
    info.write_text(LCOV, encoding="utf-8")

    a = read_cobertura(xml, config=cfg)
    b = read_lcov(info, config=cfg)
    assert a.lines_total == b.lines_total
    assert a.lines_covered == b.lines_covered


# ── mẫu số rỗng: nhánh quan trọng nhất của module ───────────────────────


def test_missing_report_raises_instead_of_reporting_zero(tmp_path: Path, cfg: ExecConfig) -> None:
    with pytest.raises(EmptyDenominatorError):
        read_cobertura(tmp_path / "khong-co.xml", config=cfg)


def test_report_with_no_files_raises(tmp_path: Path, cfg: ExecConfig) -> None:
    """Ca đã đo: quên `--source` ⇒ report đọc được nhưng rỗng ⇒ grid sập về
    unknown trong im lặng, và báo cáo vẫn "read as confident"."""
    path = tmp_path / "coverage.xml"
    path.write_text('<?xml version="1.0" ?><coverage><packages/></coverage>', encoding="utf-8")
    with pytest.raises(EmptyDenominatorError):
        read_cobertura(path, config=cfg)


def test_file_with_no_measurable_lines_raises(tmp_path: Path, cfg: ExecConfig) -> None:
    path = tmp_path / "coverage.xml"
    path.write_text(
        '<?xml version="1.0" ?><coverage><packages><package><classes>'
        '<class filename="pkg/cart.py"><lines/></class>'
        "</classes></package></packages></coverage>",
        encoding="utf-8",
    )
    with pytest.raises(EmptyDenominatorError):
        read_cobertura(path, config=cfg)


def test_empty_lcov_raises(tmp_path: Path, cfg: ExecConfig) -> None:
    path = tmp_path / "lcov.info"
    path.write_text("TN:\n", encoding="utf-8")
    with pytest.raises(EmptyDenominatorError):
        read_lcov(path, config=cfg)


def test_the_floor_comes_from_config_not_from_code(tmp_path: Path) -> None:
    cfg = load_exec_config(reload=True).model_copy(deep=True)
    cfg.coverage.min_files_in_report = 3
    path = tmp_path / "coverage.xml"
    path.write_text(COBERTURA, encoding="utf-8")
    with pytest.raises(EmptyDenominatorError):
        read_cobertura(path, config=cfg)


# ── dispatch ────────────────────────────────────────────────────────────


def test_read_report_dispatches_on_the_filename(tmp_path: Path, cfg: ExecConfig) -> None:
    xml = tmp_path / "coverage.xml"
    xml.write_text(COBERTURA, encoding="utf-8")
    info = tmp_path / "lcov.info"
    info.write_text(LCOV, encoding="utf-8")

    assert read_report(xml, config=cfg).fmt == "cobertura"
    assert read_report(info, config=cfg).fmt == "lcov"


def test_an_unknown_format_is_refused_not_guessed(tmp_path: Path, cfg: ExecConfig) -> None:
    """"sai format/filename" là một trong ba cách hỏng IM LẶNG của note 02 §8.9."""
    path = tmp_path / "coverage.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(EmptyDenominatorError):
        read_report(path, config=cfg)


def test_coverage_py_data_file_is_read_through_the_library_api(
    tmp_path: Path, cfg: ExecConfig
) -> None:
    """Đọc `.coverage` bằng CoverageData, không đọc SQLite tay."""
    coverage_module = pytest.importorskip("coverage")

    source = tmp_path / "sample.py"
    source.write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    data_file = tmp_path / ".coverage"

    data = coverage_module.CoverageData(basename=str(data_file))
    data.add_lines({str(source): [1, 2]})
    data.write()

    report = read_coverage_data(data_file, config=cfg)
    assert report.fmt == "coveragepy"
    assert report.touches(str(source), 2) is True
