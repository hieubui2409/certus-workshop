# Nội quy nhà — định nghĩa dải rủi ro (risk band)

Đây là từ vựng chung khi đội nói *"ô này đã được chấm tới đâu"*. Sáu dải dưới
đây là **kết quả suy diễn** từ bằng chứng đã thu, không phải nhãn ai đó chọn.

## 1. Sáu dải

| Dải | Nghĩa | Điều kiện tối thiểu |
|---|---|---|
| `high` | đã chấm, và có bằng chứng bộ kiểm bắt được lỗi | có probe chạy qua đúng đường mã, ≥2 assert độc lập, và có mutant bị giết neo đúng vòng |
| `med` | đã chấm, bằng chứng mỏng hơn | probe chạy qua đúng đường mã, ≥2 assert độc lập |
| `low` | có chạm nhưng assert yếu | probe chạy qua, <2 assert độc lập |
| `stub` | có ca kiểm mang tên đúng ô, nhưng không assert gì có nghĩa | — |
| `N/A` | ô không có đối tượng để áp dụng | chỉ vào qua hồ sơ ràng buộc đã được duyệt |
| `unknown` | thiếu bằng chứng để xếp vào bất kỳ dải nào ở trên | mặc định của mọi ô chưa ai chạm |

Hai luật không đổi:

1. **`unknown` là mặc định.** Ô chưa có bằng chứng không tự rơi vào `low`, càng
   không rơi vào `N/A`. Không có bằng chứng ≠ không có rủi ro.
2. **Dải là suy diễn.** Không API nào, không mô hình nào, không comment nào
   trong file người dùng tải lên được phép đặt thẳng một dải.

## 2. `N/A` chỉ vào qua một cửa

`N/A` **không phải** là "rủi ro bằng không". Nó là "ô này không có đối tượng
để áp dụng". Vì thế ô `N/A` bị loại khỏi **cả tử số lẫn mẫu số**, và số ô bị
loại phải được in ra để người đọc **thấy** việc loại bỏ.

Một ô vừa `N/A` vừa có ca kiểm đã chạy là **mâu thuẫn** — phải báo lỗi, không
được tự chọn một bên.

Bốn lý do bị từ chối thẳng khi khai `N/A`: *hiếm khi xảy ra* · *khó kiểm* ·
*ít người dùng* · *hệ thống sẽ tự chặn*. Xem `kb/standards/owasp-asvs.md`
mục 4.

## 3. Trọng số vùng

Vùng (zone) là một tập ô có cùng mức rủi ro nghiệp vụ, mang trọng số `w` trong
khoảng 0..1.

| Ngưỡng | Giá trị nhà | Nghĩa |
|---|---|---|
| `blocking_w` | 0.70 | vùng có `w ≥ 0.70` thuộc **tập chặn phát hành** |
| `hot_w` | 0.85 | vùng có `w ≥ 0.85` là vùng nóng, phải leo lên bộ ba (t=3) |

Luật khớp vùng là **first-match-wins**: đảo thứ tự hai luật cùng khớp một ô sẽ
thật sự đổi vùng của ô đó. Vì vậy thứ tự trong tệp luật là một phần của đặc
tả, không phải chi tiết trình bày.

Hai guard bắt buộc:

- Biên dịch tệp vùng mà **không luật nào chạm `blocking_w`** ⇒ từ chối. Bên bị
  chấm không được phép làm rỗng tập chặn.
- Vùng mất hết ô chấm được (còn toàn `N/A`) ⇒ **báo lỗi**, không im lặng biến
  mất khỏi báo cáo.

## 4. Hai con số không bao giờ gộp

| Con số | Dùng để làm gì | Được dùng làm đầu vào cổng chặn không |
|---|---|---|
| độ phủ có trọng số rủi ro | theo dõi xu hướng | **không** |
| dải xấu nhất trong **từng** vùng | cổng chặn đọc cái này | có |

Trung bình có trọng số cho phép một vùng tốt che một vùng xấu ở chỗ hoàn toàn
khác. Không có con số thứ ba gộp hai thứ trên; ai thêm một hàm như vậy thì
build phải đỏ.

## 5. Bảng quy đổi khi cần báo cáo cho bên ngoài

Khi phải nói chuyện với người không dùng từ vựng này:

| Dải | Câu nói với người ngoài đội |
|---|---|
| `high` | "đã kiểm và bộ kiểm chứng minh được là nó bắt lỗi" |
| `med` | "đã kiểm" |
| `low` | "có chạm tới, chưa dám nói là đã kiểm" |
| `stub` | "có tên ca kiểm, chưa có nội dung" |
| `N/A` | "không áp dụng, kèm lý do đã duyệt" |
| `unknown` | "**chưa ai nhìn**" |

Cấm dịch `unknown` thành "ổn", "chưa thấy vấn đề", hay "không có phát hiện".
Ba cách nói đó đều biến sự vắng mặt của bằng chứng thành bằng chứng.
