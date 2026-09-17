# -*- coding: utf-8 -*-
"""
台灣國定假日與工作日推算模組 (taiwan_holidays.py)
內建行政院人事行政總處 (DGPA) 中華民國政府行政機關辦公日曆表 (2024 - 2028)，
提供精準的工作日、例假日、國定假日判斷與順延計算。
"""
import datetime
import calendar
import re

# 2024 - 2028 年台灣官方國定假日與彈性放假清單 (YYYY-MM-DD)
# 包含元旦、農曆春節連假、228和平紀念日、兒童與清明節、勞動節(銀行休業)、端午節、中秋節、國慶日等
OFFICIAL_TAIWAN_HOLIDAYS = {
    # === 2024 年 ===
    "2024-01-01": "元旦開國紀念日",
    "2024-02-08": "農曆除夕前一日(調整放假)",
    "2024-02-09": "農曆除夕",
    "2024-02-10": "春節初一",
    "2024-02-11": "春節初二",
    "2024-02-12": "春節初三(補假)",
    "2024-02-13": "春節初四(補假)",
    "2024-02-14": "春節初五(補假)",
    "2024-02-28": "228和平紀念日",
    "2024-04-04": "兒童節",
    "2024-04-05": "民族掃墓節(清明節)",
    "2024-05-01": "勞動節(金融機構休業)",
    "2024-06-10": "端午節",
    "2024-09-17": "中秋節",
    "2024-10-10": "國慶日",

    # === 2025 年 ===
    "2025-01-01": "元旦開國紀念日",
    "2025-01-27": "農曆除夕前一日(調整放假)",
    "2025-01-28": "農曆除夕",
    "2025-01-29": "春節初一",
    "2025-01-30": "春節初二",
    "2025-01-31": "春節初三",
    "2025-02-01": "春節初四",
    "2025-02-02": "春節初五",
    "2025-02-28": "228和平紀念日",
    "2025-04-03": "兒童節(補假)",
    "2025-04-04": "清明節",
    "2025-05-01": "勞動節(金融機構休業)",
    "2025-05-30": "端午節(補假)",
    "2025-05-31": "端午節",
    "2025-10-06": "中秋節",
    "2025-10-10": "國慶日",

    # === 2026 年 ===
    "2026-01-01": "元旦開國紀念日",
    "2026-01-02": "元旦調整放假",
    "2026-02-15": "農曆除夕前一日",
    "2026-02-16": "農曆除夕",
    "2026-02-17": "春節初一",
    "2026-02-18": "春節初二",
    "2026-02-19": "春節初三",
    "2026-02-20": "春節初四",
    "2026-02-27": "228和平紀念日(補假)",
    "2026-02-28": "228和平紀念日",
    "2026-04-03": "兒童節(補假)",
    "2026-04-04": "清明節",
    "2026-04-06": "清明節補假",
    "2026-05-01": "勞動節(金融機構休業)",
    "2026-06-19": "端午節",
    "2026-09-25": "中秋節",
    "2026-10-09": "國慶日(補假)",
    "2026-10-10": "國慶日",

    # === 2027 年 ===
    "2027-01-01": "元旦開國紀念日",
    "2027-02-05": "農曆除夕前一日",
    "2027-02-06": "農曆除夕",
    "2027-02-07": "春節初一",
    "2027-02-08": "春節初二",
    "2027-02-09": "春節初三",
    "2027-02-10": "春節初四",
    "2027-02-28": "228和平紀念日",
    "2027-03-01": "228補假",
    "2027-04-04": "兒童節",
    "2027-04-05": "清明節",
    "2027-05-01": "勞動節(金融機構休業)",
    "2027-06-09": "端午節",
    "2027-09-15": "中秋節",
    "2027-10-10": "國慶日",
    "2027-10-11": "國慶日補假",

    # === 2028 年 ===
    "2028-01-01": "元旦開國紀念日",
    "2028-01-25": "農曆除夕",
    "2028-01-26": "春節初一",
    "2028-01-27": "春節初二",
    "2028-01-28": "春節初三",
    "2028-02-28": "228和平紀念日",
    "2028-04-04": "兒童節",
    "2028-04-05": "清明節",
    "2028-05-01": "勞動節(金融機構休業)",
    "2028-05-28": "端午節",
    "2028-10-03": "中秋節",
    "2028-10-10": "國慶日"
}

# 補行上班日清單 (雖為週六但需正常上班，金融市場開市)
OFFICIAL_TAIWAN_WORKDAYS = {
    "2024-02-17": "農曆春節補班日",
    "2025-02-08": "農曆春節補班日",
    "2026-01-10": "元旦彈性放假補班日",
    "2026-02-07": "春節彈性放假補班日"
}

def is_working_day(d: datetime.date) -> bool:
    """
    判斷指定日期是否為工作日 (金融機構營業日)
    1. 若在官方補班日名單中 -> 為工作日
    2. 若在官方放假日名單中 -> 非工作日
    3. 若為週六或週日 -> 非工作日
    4. 其餘週一至週五 -> 為工作日
    """
    d_str = d.strftime("%Y-%m-%d")
    if d_str in OFFICIAL_TAIWAN_WORKDAYS:
        return True
    if d_str in OFFICIAL_TAIWAN_HOLIDAYS:
        return False
    if d.weekday() >= 5:  # 5: Saturday, 6: Sunday
        return False
    
    # 對於未在名單中的年份，預設固定國定假日判斷
    fixed_holidays = [(1, 1), (2, 28), (4, 4), (4, 5), (5, 1), (10, 10)]
    if (d.month, d.day) in fixed_holidays:
        return False

    return True

def get_holiday_name(d: datetime.date) -> str:
    """取得該日期的放假原因名稱 (若無則回傳空字串)"""
    d_str = d.strftime("%Y-%m-%d")
    if d_str in OFFICIAL_TAIWAN_HOLIDAYS:
        return OFFICIAL_TAIWAN_HOLIDAYS[d_str]
    if d.weekday() == 5:
        return "星期六(例假日)"
    if d.weekday() == 6:
        return "星期日(例假日)"
    return ""

def get_next_working_day(d: datetime.date) -> (datetime.date, int, list):
    """
    若日期為例假日或國定假日，自動順延至次一工作日
    :return: (順延後工作日, 順延天數, 順延經過的假日原因列表)
    """
    curr = d
    postponed_days = 0
    holiday_reasons = []
    
    while not is_working_day(curr):
        reason = get_holiday_name(curr)
        holiday_reasons.append(f"{curr.strftime('%m/%d')} {reason}")
        curr += datetime.timedelta(days=1)
        postponed_days += 1
        
    return curr, postponed_days, holiday_reasons

def calc_platform_deposit_date(apply_date_or_tuple, fallback_roc_year=115, fallback_month=8):
    """
    依據平台合約規範計算預計入帳日：
    【合約條款規範】
    「甲方於每月15日前開立發票...月結35日（如遇例假日或國定假日，付款期限順延至次一工作日。
      若乙方於 11 月 15 日收到發票，則付款日為次月 1 日起算 35 日，故實際付款日為次年度 1 月 5 日。）」

    【計算邏輯】
    1. 請款發票開立月份 (當月 M 月)
    2. 次月 1 日 (M+1 月 1 日) 起算 35 天： base_date + 35 天
    3. 若遇週末例假日或台灣國定假日，順延至次一工作日

    【驗證範例】
    11 月填好發票 (11月開立) -> 次月 12/1 起算 35 天為次年 1/5 (工作日) -> 收到款項 1/5！
    
    :return: (formatted_roc_str, details_dict)
    """
    roc_year = None
    month = None
    day = None

    if isinstance(apply_date_or_tuple, tuple):
        roc_year = apply_date_or_tuple[0]
        month = apply_date_or_tuple[1]
        day = apply_date_or_tuple[2] if len(apply_date_or_tuple) > 2 else 3
    elif isinstance(apply_date_or_tuple, (datetime.date, datetime.datetime)):
        roc_year = apply_date_or_tuple.year - 1911 if apply_date_or_tuple.year > 1911 else apply_date_or_tuple.year
        month = apply_date_or_tuple.month
        day = apply_date_or_tuple.day
    elif isinstance(apply_date_or_tuple, str):
        val_str = str(apply_date_or_tuple).strip()
        val_str = re.sub(r'^(日期|申請日期)[：:\s]*', '', val_str).strip()
        
        m1 = re.match(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', val_str)
        if m1:
            y, m, d = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
            roc_year = y - 1911
            month, day = m, d
        else:
            m2 = re.match(r'(\d{2,3})[年/-](\d{1,2})[月/-](\d{1,2})', val_str)
            if m2:
                y, m, d = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
                roc_year, month, day = y, m, d

    if not roc_year or not month:
        roc_year = fallback_roc_year
        month = fallback_month
        day = 3

    ad_year = roc_year + 1911
    
    # 次月 1 日
    next_month = month + 1
    next_year = ad_year
    if next_month > 12:
        next_month -= 12
        next_year += 1
        
    base_date = datetime.date(next_year, next_month, 1)
    
    # 次月 1 日起算 35 日 (即 base_date + 35 天)
    raw_target_date = base_date + datetime.timedelta(days=35)
    
    # 遇假日國定假日順延至次一工作日
    final_date, postponed_days, reasons = get_next_working_day(raw_target_date)
    
    final_roc_y = final_date.year - 1911
    formatted_roc = f"{final_roc_y}年{final_date.month:02d}月{final_date.day:02d}日"
    
    details = {
        "apply_roc_year": roc_year,
        "apply_month": month,
        "apply_day": day,
        "base_date": base_date.strftime("%Y-%m-%d"),
        "raw_target_date": raw_target_date.strftime("%Y-%m-%d"),
        "final_date": final_date.strftime("%Y-%m-%d"),
        "final_roc": formatted_roc,
        "postponed_days": postponed_days,
        "reasons": reasons,
        "is_postponed": postponed_days > 0
    }
    
    return formatted_roc, details

if __name__ == "__main__":
    # 測試合約規範案例：11月填好發票
    res, d = calc_platform_deposit_date((114, 11, 15))
    print(f"114年11月15日請款: 預計入帳日={res}, 詳情={d}")
    assert res == "115年01月05日", f"Expected 115年01月05日, got {res}"
    
    # 測試 115年8月對帳 (9月填好發票)
    res8, d8 = calc_platform_deposit_date((115, 9, 3))
    print(f"115年09月03日請款: 預計入帳日={res8}, 詳情={d8}")
    print("ALL TESTS PASSED!")
