# ledger — sổ kế toán có đường ghi song song

Repo mẫu **lành mạnh**: không có lỗi chủ đích nào, không có payload nào. Nhưng
nó có **đúng một khiếm khuyết kỹ thuật
thật**, loại khiếm khuyết mà mọi dự án có concurrency đều từng dính.

```bash
python -m pytest -q      # 27 passed — xanh, ổn định
python demo_race.py      # và đây là chỗ tiền bốc hơi
```

## Khiếm khuyết: read-modify-write không khoá

`LedgerEngine.post()` (`ledger/engine.py`) làm bốn việc:

1. đọc `account.balance`
2. tính số dư mới
3. kiểm tra âm quỹ, ghi một dòng nhật ký
4. ghi `account.balance`

Giữa bước 1 và bước 4 không có khoá nào. `AccountBook` có `self._lock` cho
việc mở tài khoản, `LedgerEngine` có `self._lock` cho `snapshot()` —
người viết **đã nghĩ đến khoá**, chỉ là không nghĩ tới đường nóng. Đây là hình
dạng thật của lỗi loại này: nó không trông giống lỗi.

Hai luồng cùng ghi vào một tài khoản sẽ ghi đè kết quả của nhau. Kết quả đo
được trên máy dựng repo này (Python 3.12.13, switch interval 5ms,
4 luồng × 20 000 bút toán):

| vòng | kỳ vọng | thực tế | thiếu |
|---:|---:|---:|---:|
| 1 | 80 000 | 66 288 | 13 712 |
| 2 | 80 000 | 59 411 | 20 589 |
| 3 | 80 000 | 51 252 | 28 748 |
| 4 | 80 000 | 72 038 | 7 962 |
| 5 | 80 000 | 36 517 | 43 483 |

5/5 vòng mất tiền. Số dòng nhật ký thì **luôn đúng 80 000**.

## Vì sao ba tầng mẫu số nhìn thấy khác nhau

| Tầng | Nó nói gì | Có bắt được không |
|---|---|---|
| line coverage | mọi dòng của `post()` đều đã chạy | **không** |
| mutation score | đổi bất kỳ toán tử nào trong `post()` → test tuần tự đỏ ngay, mutant bị giết | **không** |
| grid coverage | trục `interleaving` có 3 giá trị, chỉ 2 giá trị từng chạy qua ô có tranh chấp | **có** — ô `interleaving=concurrent_shared` × `account=shared` chưa ai chấm |

Không dòng nào trong `post()` sai. Cái sai là **khoảng cách** giữa dòng đọc và
dòng ghi. Đó là thứ chỉ lộ ra khi bạn coi *thứ tự thi hành* là một trục biến
thiên chứ không phải một chi tiết cài đặt.

## Trục biến thiên tự nhiên

| Trục | `ref` | Số giá trị |
|---|---|---|
| `interleaving` | `ledger/engine.py::Interleaving` | 3 |
| `entry_type` | `ledger/entries.py::EntryType` | 2 |

`Interleaving` là một enum có thật, được `post_batch()` dùng thật — nên
`admit_axis()` phân giải được `ref` của nó.

## Vì sao bộ kiểm thử vẫn xanh

`tests/test_engine.py` có hẳn một ca chạy song song
(`test_post_batch_chia_theo_tai_khoan_chay_song_song`) — nhưng nó dùng chế độ
`CONCURRENT_SHARDED`, mỗi luồng một tài khoản riêng, nên không có tranh chấp.
Ca còn lại (`..._du_so_dong_nhat_ky`) chạy đúng chế độ nguy hiểm nhưng chỉ
assert **số dòng nhật ký** — mà `list.append` thì an toàn với luồng. Test
chạm đúng chỗ hiểm và vẫn xanh vì nó nhìn nhầm chỗ.

Đây là bài học, không phải một lỗi cần sửa trong repo mẫu. Giữ nguyên.

## Cách sửa (để tham khảo, **đừng** áp vào repo mẫu)

Bọc toàn bộ đoạn đọc-tính-ghi trong `post()` bằng khoá per-account, hoặc
chuyển số dư thành một hàng có phiên bản và ghi bằng compare-and-swap có
thử lại.
