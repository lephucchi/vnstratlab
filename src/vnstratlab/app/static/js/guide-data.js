// Static guide content (Vietnamese). One file so the PO page can reuse it.

export const STEPS = [
  {
    id: "ingest",
    name: "Ingest",
    what: "Nạp giá thô vào kho dữ liệu cục bộ: dữ liệu giả lập (offline) hoặc dữ liệu thật từ Yahoo.",
    command: "vnstratlab ingest --source synthetic",
    watch: [
      "Giả lập hay thật: Yahoo là nguồn tạm thời (interim), cần xác nhận điều khoản trước khi dùng.",
      "Nến chưa đóng: trước 16:00 phiên cuối chỉ là nến dở dang, đừng dùng làm tín hiệu.",
      "Trạng thái kiểm tra chất lượng (DQ): xem số lỗi và cảnh báo của lần nạp gần nhất.",
    ],
  },
  {
    id: "rebuild",
    name: "Rebuild",
    what: "Dựng lại hai chuỗi giá từ dữ liệu thô: giá điều chỉnh (để tính tín hiệu) và giá thực thi (để mô phỏng khớp lệnh).",
    command: "vnstratlab data rebuild",
    watch: [
      "Giá điều chỉnh khác giá thực thi: mỗi chuỗi dùng cho một mục đích riêng.",
      "Các dòng bị loại (excluded) được ghi lại, không bị bỏ qua âm thầm.",
      "Sổ khoảng trống dữ liệu (GAP-xx) liệt kê những gì còn thiếu; xem ở trang Dữ liệu.",
    ],
  },
  {
    id: "features",
    name: "Features",
    what: "Tính các đặc trưng theo từng ngày (features_daily) chỉ từ thông tin có sẵn tại thời điểm đó.",
    command: "vnstratlab features build",
    watch: [
      "Chỉ dùng thông tin tại thời điểm (point-in-time): không nhìn trước tương lai (no lookahead).",
      "Cờ survivorship_warning (GAP-13): danh sách mã hiện tại bỏ sót các mã đã hủy niêm yết, kết quả có thể đẹp hơn thực tế.",
    ],
  },
  {
    id: "strategies",
    name: "Strategies",
    what: "Chạy các chiến lược đã đăng ký (mỗi bản thử là một trial) trên đặc trưng đã tính.",
    command: "vnstratlab lab trials",
    watch: [
      "Tham số đã đóng băng: không chỉnh sau khi thấy kết quả.",
      "Mọi lần thử đều được đếm (every trial counted) để tránh tự lừa mình bằng cách chọn lọc.",
      "Chiến lược bị chặn (blocked) sẽ không chạy; xem lý do trong kết quả.",
    ],
  },
  {
    id: "simulator",
    name: "Simulator",
    what: "Mô phỏng khớp lệnh theo luật thị trường Việt Nam, kèm lớp quản trị rủi ro.",
    command: "vnstratlab demo",
    watch: [
      "T+: cổ phiếu mua hôm nay chưa bán được ngay; luật thanh toán được mô phỏng.",
      "Lô 100 cổ phiếu và lô lẻ; giá trần/sàn giới hạn khả năng khớp.",
      "Phí và thuế [VERIFY]: cần kiểm chứng lại theo biểu phí hiện hành.",
      "Dừng lỗ theo ATR và cầu dao (circuit breaker) có thể chặn lệnh mới.",
    ],
  },
  {
    id: "report",
    name: "Báo cáo",
    what: "Tổng hợp bảng chỉ số và đường vốn của từng trial thành báo cáo để bạn đọc.",
    command: "vnstratlab demo --out ./demo-out",
    watch: [
      "Nhãn SYNTHETIC: kết quả trên dữ liệu giả lập không nói gì về thị trường thật.",
      "Chỉ khuyến nghị: công cụ không bao giờ đặt lệnh, quyết định luôn là của bạn.",
    ],
  },
];

export const QUICK_START = [
  "Chạy vnstratlab init để tạo cấu hình.",
  "Chạy demo (nút bên dưới hoặc lệnh vnstratlab demo).",
  "Xem tiến trình ở trang Runs.",
  "Xem kết quả khi demo chạy xong.",
];
