# Ba tầng mẫu số trên repo mẫu

> Sinh tự động bởi `evals/collect.py` lúc 2026-08-06 06:16 UTC.
> Lệnh: `python -m certus analyze <target> --json`
> **Đừng sửa tay tệp này** — chạy lại script để cập nhật.


## Grid coverage đo được

| repo | **line coverage** | ô | grid phủ | grid tỉ lệ | wilson 95% | chưa ai canh | cờ |
|---|---|---|---|---|---|---|---|
| `shopcart` | **156/160 = 97.5%** | 63 | 16/63 | **25.4%** | [16.3%, 37.3%] | 47 | — |
| `ledger` | **136/136 = 100.0%** | 6 | 0/6 | **0.0%** | [0.0%, 39.0%] | 6 | n-too-small, interval-wide, interval-saturated |
| `payments` | **122/122 = 100.0%** | 8 | 0/8 | **0.0%** | [0.0%, 32.4%] | 8 | n-too-small, interval-wide, interval-saturated |

## Điều con số này nói, và điều nó không nói

Hai cột đầu là toàn bộ bài học. `payments` phủ **100% số dòng** và **0/8 ô**
lưới rủi ro. Cả hai con số đều đúng — chúng đo hai mẫu số khác nhau:

| tầng | mẫu số là | trả lời câu hỏi |
|---|---|---|
| line coverage | các dòng code có tồn tại | dòng nào chưa từng chạy |
| mutation score | các dòng test đã chạm | test có bắt được lỗi không |
| **grid coverage** | **không gian rủi ro** | **góc nào chưa ai nhìn** |

Một repo phủ 98% dòng vẫn có thể chưa từng chạy `checkout()` với
`WALLET`, và chưa từng ghép `INTERNATIONAL × VIP`. Line coverage không có
chỗ nào để nói điều đó, vì tổ hợp không phải là một dòng.

## Giới hạn của phép đo grid — nói trước khi ai hỏi

Ô được coi là *có người canh* khi tồn tại một hàm test **nhắc tới** cả hai
giá trị. Đây là suy luận theo cú pháp, không theo vết chạy: một test nhắc
hai giá trị mà không thật sự gọi tổ hợp đó vẫn được tính.

Nghĩa là phép đo này **rộng rãi hơn sự thật** — nó ước lượng TRÊN. Con số
phủ thật chỉ có thể thấp hơn con số ở bảng trên, không bao giờ cao hơn.
Ghi ở đây thay vì trong một tệp không ai mở, vì con số này lên thẳng UI.
