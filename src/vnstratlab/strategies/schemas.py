"""Console metadata of the built-in strategies: Vietnamese names and parameter schemas.

Kept apart from the strategy modules on purpose: a strategy's trial id includes the hash of its
module source (ADR-003 section 3), so adding this to the modules would change every trial id.
``tests/test_console_api.py`` checks that every packaged parameter set validates against its schema
here and that every schema value is accepted by the strategy's own ``validate_params`` (drift
guard). Pure: no I/O.

A parameter spec is a mapping ``{name, type: "int"|"float"|"enum", help_vi, allowed?, min?, max?,
min_exclusive?}``. ``allowed`` lists the only accepted values; ``min``/``max`` are inclusive
unless ``min_exclusive`` is true.
"""

from __future__ import annotations

from typing import Any

ParamSpec = dict[str, Any]


def _int(
    name: str, help_vi: str, *, min: int | None = None, allowed: list[int] | None = None
) -> ParamSpec:
    spec: ParamSpec = {"name": name, "type": "int", "help_vi": help_vi}
    if allowed is not None:
        spec["allowed"] = allowed
    if min is not None:
        spec["min"] = min
    return spec


def _float(name: str, help_vi: str, *, min: float = 0, max: float | None = None) -> ParamSpec:
    spec: ParamSpec = {"name": name, "type": "float", "help_vi": help_vi, "min": min}
    spec["min_exclusive"] = True
    if max is not None:
        spec["max"] = max
    return spec


_N = "Số mã tối đa được mua (mỗi mã tỷ trọng bằng nhau)"
_MONTHS = "Số tháng nhìn lại (bỏ qua tháng gần nhất)"

STRATEGY_INFO: dict[str, dict[str, Any]] = {
    "S00_composite": {
        "name_vi": "Tổng hợp 4 khối tín hiệu",
        "description_vi": "Xếp hạng theo xu hướng, sức mạnh tương đối, hồi quy về trung bình "
        "và khối lượng; mua top N mã có tín hiệu kích hoạt.",
        "basis": "Thiết kế nội bộ (định giá chưa có dữ liệu, GAP-11)",
        "params": [
            {
                "name": "weights",
                "type": "enum",
                "allowed": ["equal", "trend_heavy"],
                "help_vi": "Bộ trọng số của 4 khối: đều nhau hoặc thiên về xu hướng",
            },
            _int("top_n", "Số mã tối đa được mua", min=1),
        ],
    },
    "S01_weekly_reversal": {
        "name_vi": "Đảo chiều tuần",
        "description_vi": "Mua các mã giảm mạnh nhất tuần trước, kỳ vọng hồi lại.",
        "basis": "Jegadeesh (1990)",
        "params": [_int("n", "Số mã có lợi suất tuần thấp nhất được mua", min=1)],
    },
    "S02_breakout_volume": {
        "name_vi": "Bứt phá kèm khối lượng",
        "description_vi": "Mua mã vượt đỉnh 20 phiên khi khối lượng cao hơn bình quân.",
        "basis": "Brock, Lakonishok & LeBaron (1992)",
        "params": [
            _int(
                "lookback",
                "Cửa sổ đỉnh (cố định 20 phiên, theo đặc trưng close_20d_break)",
                allowed=[20],
            ),
            _float("vol_mult", "Khối lượng phải cao hơn bình quân 20 phiên bao nhiêu lần"),
            _int("max_n", "Số mã tối đa được mua", min=1),
        ],
    },
    "S03_oversold_uptrend": {
        "name_vi": "Quá bán trong xu hướng tăng",
        "description_vi": "Mua mã có RSI thấp nhưng vẫn nằm trên đường trung bình 50 phiên.",
        "basis": "Jegadeesh (1990); Moskowitz, Ooi & Pedersen (2012)",
        "params": [
            _int("rsi_len", "Chu kỳ RSI (2 hoặc 14)", allowed=[2, 14]),
            _float("rsi_max", "Ngưỡng RSI tối đa để coi là quá bán (0 đến 100)", max=100),
            _int("ma_len", "Cửa sổ trung bình (cố định 50 phiên)", allowed=[50]),
            _int("max_n", "Số mã tối đa được mua", min=1),
        ],
    },
    "S04_bank_pairs": {
        "name_vi": "Cặp ngân hàng (chỉ mua)",
        "description_vi": "Mua mã tụt lại của các cặp ngân hàng tương quan cao đang lệch xa.",
        "basis": "Gatev, Goetzmann & Rouwenhorst (2006); phiên bản chỉ mua",
        "params": [
            _int("form", "Số phiên hình thành cặp", min=3),
            _int("k", "Số cặp tốt nhất được chọn", min=1),
            _float("entry_z", "Ngưỡng z-score để vào lệnh"),
            _int("max_hold", "Số phiên giữ tối đa", min=1),
        ],
    },
    "S05_residual_reversion": {
        "name_vi": "Hồi quy phần dư",
        "description_vi": "Mua các mã có phần dư tích lũy so với cả nhóm thấp bất thường.",
        "basis": "Avellaneda & Lee (2010)",
        "params": [
            _int("window", "Số phiên ước lượng phần dư", min=3),
            _float("entry_z", "Ngưỡng z-score để vào lệnh"),
            _int("n", _N, min=1),
        ],
    },
    "S08_momentum": {
        "name_vi": "Động lượng",
        "description_vi": "Mua các mã tăng mạnh nhất trong 6 hoặc 12 tháng (bỏ tháng gần nhất).",
        "basis": "Jegadeesh & Titman (1993)",
        "params": [_int("L_months", _MONTHS, allowed=[6, 12]), _int("n", _N, min=1)],
    },
    "S09_reversal": {
        "name_vi": "Đảo chiều trung hạn",
        "description_vi": "Xếp hạng ngược với động lượng: mua các mã yếu nhất.",
        "basis": "Các nghiên cứu thị trường Việt Nam về đảo chiều",
        "params": [_int("L_months", _MONTHS, allowed=[6, 12]), _int("n", _N, min=1)],
    },
    "S14_low_volatility": {
        "name_vi": "Biến động thấp",
        "description_vi": "Mua các mã có độ biến động 60 phiên thấp nhất.",
        "basis": "Frazzini & Pedersen (2014)",
        "params": [
            _int(
                "window",
                "Cửa sổ biến động (cố định 60 phiên, theo đặc trưng std_60d)",
                allowed=[60],
            ),
            _int("n", _N, min=1),
        ],
    },
    "S15_sector_trend": {
        "name_vi": "Xu hướng ngành",
        "description_vi": "Giữ nhóm ngành khi chỉ số nhóm có xu hướng tăng.",
        "basis": "Moskowitz, Ooi & Pedersen (2012)",
        "params": [
            _int("lookback_months", "Số tháng xét xu hướng nhóm (6 hoặc 12)", allowed=[6, 12])
        ],
    },
    "S17_equal_weight": {
        "name_vi": "Chia đều 1/N",
        "description_vi": "Mua đều mọi mã trong danh mục; dùng làm chuẩn so sánh.",
        "basis": "DeMiguel, Garlappi & Uppal (2009)",
        "params": [],
    },
    "S18_hrp": {
        "name_vi": "Phân bổ rủi ro phân cấp (HRP)",
        "description_vi": "Chia tỷ trọng theo cụm tương quan để đa dạng hóa rủi ro.",
        "basis": "Lopez de Prado (2016)",
        "params": [_int("window", "Số phiên lợi suất dùng để ước lượng", min=3)],
    },
}


def params_schema(strategy_id: str) -> list[ParamSpec]:
    """The parameter specs of a built-in strategy (``[]`` for an unknown id or no params)."""
    info = STRATEGY_INFO.get(strategy_id)
    return [dict(p) for p in info["params"]] if info else []
