# vnstratlab

**Phòng lab chiến lược cho cổ phiếu Việt Nam.** Mỗi tối sau phiên giao dịch, vnstratlab tải dữ
liệu thị trường, chạy cả thư viện chiến lược qua cùng một bộ mô phỏng sát thực tế, chỉ giữ lại
những chiến lược vượt qua kiểm định thống kê, rồi đưa ra **khuyến nghị** cho ba khung thời gian:
ngắn hạn (1 tuần), trung hạn (3–6 tháng) và dài hạn (1 năm).

> 🇬🇧 English: [README.md](README.md)

**Website:** [lephucchi.github.io/vnstratlab](https://lephucchi.github.io/vnstratlab/) ·
**Tài liệu:** [https://lephucchi.github.io/vnstratlab/docs/](https://lephucchi.github.io/vnstratlab/docs/)

[![Website vnstratlab: phòng lab chiến lược cho cổ phiếu Việt Nam](docs/assets/site.png)](https://lephucchi.github.io/vnstratlab/)

> [!IMPORTANT]
> **vnstratlab không bao giờ đặt lệnh.** Phần mềm không kết nối với công ty chứng khoán nào
> và sẽ không bao giờ có chức năng này ([ADR-001](docs/adr/ADR-001-python-core-recommend-only.md)).
> Nó chỉ đưa ra khuyến nghị; bạn tự quyết định và tự đặt lệnh trên app của công ty chứng khoán.
> Đây là phần mềm nghiên cứu, không phải lời khuyên đầu tư. Đọc [DISCLAIMER.md](DISCLAIMER.md).

---

## Điểm khác biệt

1. **Mô phỏng đúng luật sàn HOSE.** Thanh toán T+, biên độ trần/sàn ±7%, lô chẵn 100 và lô lẻ,
   bước giá, thuế bán 0,1%, phí giao dịch và trượt giá đều được mô phỏng và có test tính tay.
   Lệnh mua không khớp được khi giá mở cửa đã ở trần; cổ phiếu mua thứ Hai không bán được vào
   thứ Ba.
2. **Không chọn "backtest đẹp nhất".** Mỗi bộ (chiến lược, tham số) được đăng ký là một *trial*
   trước khi chạy. Chiến lược phải qua hai cổng thống kê (Deflated Sharpe Ratio, xác suất
   overfit PBO, kiểm định SPA của Hansen) và Model Confidence Set, sau đó được phân bổ trọng số
   có co về chia đều. Nếu không chiến lược nào thắng mốc so sánh, khuyến nghị là *giữ danh mục
   chia đều*.
3. **Kiểm tra tính thực tế trước mỗi bản phát hành.** Stress test (phí ×2/×3, khớp lệnh trễ,
   giới hạn thanh khoản, nhiễu tham số, các giai đoạn thị trường) và đối chiếu chéo với các
   engine backtest khác ([QA gates](docs/qa-gates.md)).

## Kiến trúc

[![Kiến trúc vnstratlab: dữ liệu, chỉ báo, chiến lược, engine, lab, rủi ro, khuyến nghị, rồi bạn tự quyết](docs/assets/architecture.png)](docs/architecture.md)

Một engine, một vòng lặp mỗi tối chạy trên máy của bạn; pipeline dừng ở khuyến nghị và không
bao giờ kết nối công ty chứng khoán. Chi tiết: [docs/architecture.md](docs/architecture.md) ·
[luồng end-to-end](docs/end-to-end-flow.md). Nguồn ảnh:
[docs/assets/architecture.html](docs/assets/architecture.html).

## Trạng thái

**v0.1.0.** Đã có: tải dữ liệu (thị trường giả lập và adapter Yahoo tạm thời), kiểm tra chất lượng
dữ liệu, giá điều chỉnh và giá thực thi, chỉ báo (features), bộ mô phỏng HOSE kèm lớp rủi ro,
19 trial của 12 chiến lược, `demo` offline, `init` và Console chạy trên máy (`serve`). Lab thống
kê (`backtest`, chu trình `lab`, cổng, trọng số, `stress`, `daily`) và lịch chạy tự động chưa có,
sẽ ra ở v0.2 và v0.3. Kết quả trên dữ liệu thật từ nguồn Yahoo tạm thời không phải bằng chứng
(thiên lệch sống sót, xem [data gaps](docs/data-gaps.md)). Xem [lộ trình](docs/roadmap.md).

| Bản | Nội dung |
|---|---|
| v0.1 (bản này) | Tải dữ liệu, bộ mô phỏng theo luật HOSE, các chiến lược đầu tiên, `demo` offline |
| v0.2 | `backtest` walk-forward, lab thống kê: DSR, PBO, SPA, MCS, trọng số, meta-backtest, stress test, báo cáo |
| v0.3 | Danh mục giả lập (paper book), dashboard chạy trên máy, lịch chạy tự động, báo cáo Telegram (tùy chọn) |
| v0.4 | Thu thập và chấm điểm tin tức bằng LLM, đánh giá bằng kiểm định đăng ký trước (ADR-002) |
| v0.5+ | Tối ưu danh mục: mean-variance có shrinkage, HRP, risk parity, Black-Litterman dùng tín hiệu của lab, có tính lô |

## Cài đặt

Chưa có trên PyPI. Cài từ mã nguồn:

```bash
git clone https://github.com/lephucchi/vnstratlab.git
cd vnstratlab
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
vnstratlab doctor
```

Khi đã phát hành: `uv tool install vnstratlab` hoặc `pipx install vnstratlab`.

## Bắt đầu nhanh

Có trong v0.1.0:

```bash
vnstratlab doctor                        # kiểm tra cài đặt
vnstratlab demo                          # chạy toàn bộ trên dữ liệu giả, không cần mạng, ~45 giây
vnstratlab serve                         # Console trên máy tại 127.0.0.1:8000: hướng dẫn, lần chạy, log, kết quả
vnstratlab init                          # tạo config.yaml (vốn, nguồn dữ liệu, phí)
vnstratlab ingest --source synthetic     # nạp dữ liệu vào kho cục bộ (hoặc: --source yahoo, gói tùy chọn)
vnstratlab data rebuild                  # giá điều chỉnh và giá thực thi
vnstratlab features build                # chỉ báo theo từng thời điểm
vnstratlab lab register --dry-run        # liệt kê 19 trial sẽ được đăng ký
```

Dự kiến (lệnh đã có nhưng báo chưa cài đặt):

```bash
vnstratlab backtest --strategy S02_breakout_volume   # v0.2
vnstratlab lab --horizon short                       # v0.2: cổng thống kê -> MCS -> trọng số -> khuyến nghị
vnstratlab stress --horizon short                    # v0.2
vnstratlab daily                                     # v0.3: vòng lặp mỗi tối kèm lịch chạy
```

| Lệnh | Việc làm | Card |
|---|---|---|
| `demo` | Toàn bộ pipeline trên thị trường giả lập, offline, trong thư mục tạm | ✅ P1-T32 |
| `init` | Thiết lập cấu hình người dùng | ✅ P1-T35 |
| `ingest` | Tải hoặc làm mới dữ liệu (synthetic, Yahoo) | ✅ P1-T36, P1-T37 |
| `serve` | Console trên máy (lần chạy, log, hướng dẫn, kết quả); chưa có lịch chạy | ✅ P1-T27a, P1-T28a |
| `backtest`, `lab` (chu trình), `meta-backtest`, `stress` | Lab thống kê | P1-T20, T22, T23, T33 (v0.2) |
| `daily` | Vòng lặp mỗi tối | P1-T26 (v0.3) |

`--dry-run` có ở `ingest`, `data rebuild`, `features build`, `lab register`, chu trình `lab` và
`daily`; `demo` chạy trong thư mục tạm và không ghi gì vào thư mục dữ liệu của bạn. Chưa có lịch
chạy tự động; dự kiến ở v0.3.

## Mỗi tối hệ thống làm gì (dự kiến từ v0.3)

| Giờ | Bước |
|---|---|
| 15:30 | Tải dữ liệu, kiểm tra chất lượng; nếu lỗi thì dừng và báo |
| 16:00 | Tính các chỉ báo (features) |
| 16:15 | Lab: cập nhật kết quả ngoài mẫu; chọn lại trọng số vào ngày quyết định |
| 16:30 | Lớp quản trị rủi ro, ghi khuyến nghị vào nhật ký (không sửa được) |
| 17:00 | Cập nhật dashboard, gửi báo cáo |
| 17:15 | Thu thập tin tức thô |

**Bạn** đọc khuyến nghị, rồi tự đặt lệnh nếu đồng ý. Có thể ghi lại lệnh đã khớp vào nhật ký để
so sánh kết quả thật với khuyến nghị.

## Cấu hình và khóa bí mật

- **Tham số** (phí, giới hạn rủi ro, ngưỡng kiểm định, tham số chiến lược) nằm trong YAML.
- **Khóa bí mật** (khóa vnstock nếu cần, Telegram) chỉ đọc từ biến môi trường hoặc file `.env`
  (sao chép từ [`.env.example`](.env.example)). Không bao giờ commit, ghi log hay hiển thị.
- **Dữ liệu nằm trên máy bạn.** vnstratlab không phân phối lại dữ liệu giá.

## Tài liệu

Tài liệu kỹ thuật viết bằng tiếng Anh, nằm trong [docs/](docs/index.md): bắt đầu nhanh, kiến trúc,
cấu hình, nguồn dữ liệu, cách viết chiến lược, benchmark, quy trình phát triển, chia nhánh git,
các cổng QA và lộ trình.

## Quy trình phát triển

[![Quy trình: nhánh feat vào develop sau CI (G1) và review (G2), nhánh release qua kiểm tra sẵn sàng (G3), chủ dự án duyệt (G4) trước khi vào main](docs/assets/workflow.png)](docs/git-branching.md)

Mọi thay đổi đi qua bốn cổng; `main` và `develop` chỉ nhận thay đổi qua pull request. Chi tiết:
[nhánh git](docs/git-branching.md) · [cổng QA](docs/qa-gates.md) ·
[quy trình](docs/workflow.md). Nguồn ảnh: [docs/assets/workflow.html](docs/assets/workflow.html).

## Đóng góp

Đọc [CONTRIBUTING.md](CONTRIBUTING.md). Tóm tắt: tạo nhánh từ `develop`, mỗi task card một nhánh,
viết test trước, commit theo Conventional Commits, và mọi PR phải qua CI cùng một lượt review
độc lập.

## Giấy phép

[Apache-2.0](LICENSE). Dữ liệu bạn tải về tuân theo điều khoản của nhà cung cấp dữ liệu đó.
