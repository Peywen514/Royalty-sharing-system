# -*- coding: utf-8 -*-
"""
講師分潤結算引擎 (teacher_settlement.py)
依課程所屬講師與分潤合約公式，自動計算各講師之版稅，並產生符合標準格式的 Excel 明細表。
"""
import os
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

import unicodedata
import re

def normalize_course_name(name):
    """標準化課程名稱，消除全形/半形、符號差異、空格等影響 (例如 ｜ vs |, ： vs :, Ｘ vs X)"""
    if not name:
        return ""
    s = unicodedata.normalize('NFKC', str(name)).lower().strip()
    return re.sub(r'[\s\|\:\：\-\_\~\,\，\。\、\(\)\（\）\/\\]+', '', s)

def parse_roc_period(period_str):
    """將 '115年8月' 或 '115年09月' 解析為 (roc_year, month) 數值元組以供期別先後比對"""
    if not period_str:
        return (0, 0)
    m = re.search(r'(\d+)年(\d+)月', str(period_str))
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (0, 0)

def get_prior_deducted_costs(period_str=None):
    """
    自資料庫 teacher_settlements 統計在指定 period_str 之前，各課程累計已扣除的製作費用。
    回傳字典: { normalized_course_name: float(accumulated_cost) }
    """
    from core.db import get_connection
    target_period = parse_roc_period(period_str)
    accumulated = {}
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT period, course_name, production_cost FROM teacher_settlements')
        rows = c.fetchall()
        conn.close()
        for r in rows:
            r_period = r[0] if isinstance(r, tuple) else r['period']
            r_course = r[1] if isinstance(r, tuple) else r['course_name']
            r_cost = float((r[2] if isinstance(r, tuple) else r['production_cost']) or 0)
            
            p_tuple = parse_roc_period(r_period)
            # 若有指定 period_str，僅統計該期「之前」已扣除的歷史紀錄
            if target_period == (0, 0) or p_tuple < target_period:
                nk = normalize_course_name(r_course)
                accumulated[nk] = accumulated.get(nk, 0.0) + r_cost
    except Exception as e:
        print(f"Error querying prior deducted costs: {e}")
    return accumulated

class TeacherSettlement:
    def __init__(self, db_conn=None):
        self.db_conn = db_conn

    def calculate_royalty(self, items, course_configs=None, period_str=None, custom_costs=None):
        """
        計算各項課程分潤並歸組至各講師，具備全半形/符號容錯匹配、同門課程跨列統整、
        以及【前期製作費用累計攤提遞減】與【選填自訂覆寫】機制。
        :param items: 當期對帳課程明細清單 (每筆包含 course_name, price, qty, platform_gross 等)
        :param course_configs: 課程與講師設定 (若無則使用預設規則或資料庫查詢)
        :param period_str: 當前期別 (例如 '115年9月')，用於比對歷史累計扣除之製作費
        :param custom_costs: 使用者自訂選填之各課程製作費用 dict {course_name: cost}
        :return: 依講師分組的結算結果 dict
        """
        # 取得前期已扣除之製作費用 (供遞減攤提計算)
        prior_costs = get_prior_deducted_costs(period_str) if period_str else {}

        # 預設課程設定 (若未傳入)
        default_rules = [
            {
                "course_name": "AIＸ數據分析術:從報表到洞察，全面升級你的職場決策力",
                "teacher_name": "侯玉彤",
                "teacher_share_rate": 0.50,
                "production_cost": 1069.0,
                "deduction_type": "cumulative",
                "note": "扣除平台服務費、課程製作相關費用"
            },
            {
                "course_name": "生成式AI全解析|從工具應用到系統開發的技術核心黃金雙軌課",
                "teacher_name": "簡志峰",
                "teacher_share_rate": 0.50,
                "production_cost": 1069.0,
                "deduction_type": "cumulative",
                "note": "扣除平台服務費、製作課程等費用"
            },
            {
                "course_name": "生成式AI全解析:從概念到實戰落地應用",
                "teacher_name": "簡志峰",
                "teacher_share_rate": 0.50,
                "production_cost": 0.0,
                "deduction_type": "cumulative",
                "note": "扣除平台服務費"
            }
        ]
        
        all_configs = []
        if course_configs:
            for c in course_configs:
                c_name = c.get("course_name")
                if c_name:
                    all_configs.append({
                        "course_name": c_name,
                        "teacher_name": c.get("teacher_name", "未知講師"),
                        "teacher_share_rate": float(c.get("teacher_share_rate", 0.5)),
                        "production_cost": float(c.get("production_cost", 0.0)),
                        "deduction_type": c.get("deduction_type", "cumulative"),
                        "note": c.get("note", "扣除平台服務費")
                    })
        # 補充預設規則以防漏缺
        for dr in default_rules:
            if not any(normalize_course_name(dr["course_name"]) == normalize_course_name(c["course_name"]) for c in all_configs):
                all_configs.append(dr)

        def match_rule(query_name):
            nq = normalize_course_name(query_name)
            # 1. 完全標準化匹配
            for c in all_configs:
                if nq == normalize_course_name(c["course_name"]):
                    return c
            # 2. 子字串匹配 (優先匹配較長更精確的課程名稱)
            sorted_cfgs = sorted(all_configs, key=lambda x: len(normalize_course_name(x["course_name"])), reverse=True)
            for c in sorted_cfgs:
                nc = normalize_course_name(c["course_name"])
                if len(nc) >= 4 and (nc in nq or nq in nc):
                    return c
            # 3. 關鍵字語意回退防護 (避免「生成式AI」或「數據分析」因標題細微變更漏配)
            for c in sorted_cfgs:
                nc = normalize_course_name(c["course_name"])
                if "生成式ai" in nq and "生成式ai" in nc:
                    return c
                if "數據分析" in nq and "數據分析" in nc:
                    return c
            return None

        # 依 (講師, 課程) 進行統整 (同一門課若在自填表拆為 1、2 列，自動合算至同一老師的該門課)
        teachers_data = {}
        for it in items:
            c_name = it["course_name"]
            rule = match_rule(c_name)
            
            if rule:
                t_name = rule["teacher_name"]
                canonical_course = rule["course_name"]
                share_rate = rule["teacher_share_rate"]
                base_cost = rule["production_cost"]
                ded_type = rule.get("deduction_type", "cumulative")
                note = rule["note"]
            else:
                t_name = "未指定講師"
                canonical_course = c_name
                share_rate = 0.50
                base_cost = 0.0
                ded_type = "cumulative"
                note = "扣除平台服務費"

            if t_name not in teachers_data:
                teachers_data[t_name] = {}

            c_key = normalize_course_name(canonical_course)
            if c_key not in teachers_data[t_name]:
                # 計算當期製作費用 (支援使用者自訂選填與前期累計遞減攤提)
                user_override = None
                if custom_costs:
                    for k, v in custom_costs.items():
                        if normalize_course_name(k) == c_key:
                            try:
                                user_override = float(v)
                            except (ValueError, TypeError):
                                pass
                            break

                already_deducted = prior_costs.get(c_key, 0.0)
                if user_override is not None:
                    actual_cost = max(0.0, user_override)
                    cost_status = "custom_override"
                    cost_status_text = f"自訂選填 (NT$ {int(actual_cost):,})"
                elif ded_type == "per_period":
                    actual_cost = base_cost
                    cost_status = "per_period"
                    cost_status_text = f"每期固定扣除 (NT$ {int(actual_cost):,})"
                elif ded_type == "none":
                    actual_cost = 0.0
                    cost_status = "none"
                    cost_status_text = "免扣製作費"
                else:
                    # cumulative 累計扣抵，扣完即止 (預設)
                    actual_cost = max(0.0, base_cost - already_deducted)
                    if base_cost > 0 and already_deducted >= base_cost:
                        cost_status = "already_deducted"
                        cost_status_text = f"前期已扣 ${int(already_deducted):,} (已攤提完畢)"
                    elif base_cost > 0 and already_deducted > 0:
                        cost_status = "partial_deducted"
                        cost_status_text = f"前期已扣 ${int(already_deducted):,}，本期剩餘 ${int(actual_cost):,}"
                    elif base_cost > 0:
                        cost_status = "first_time"
                        cost_status_text = f"本期首次攤提 (${int(actual_cost):,})"
                    else:
                        cost_status = "zero"
                        cost_status_text = "無製作費"

                # 動態調整備註：若製作費為 0，則備註改為扣除平台服務費
                final_note = note
                if actual_cost == 0.0:
                    if "課程製作" in final_note or "製作課程" in final_note:
                        final_note = "扣除平台服務費"
                elif actual_cost > 0.0 and "製作" not in final_note:
                    final_note = "扣除平台服務費、課程製作相關費用"

                teachers_data[t_name][c_key] = {
                    "course_name": canonical_course,
                    "price": it["price"],
                    "qty": 0,
                    "platform_net": 0.0,
                    "base_cost": base_cost,
                    "prior_deducted": already_deducted,
                    "production_cost": actual_cost,
                    "cost_status": cost_status,
                    "cost_status_text": cost_status_text,
                    "share_rate": share_rate,
                    "share_rate_str": f"{int(share_rate*100)}%",
                    "note": final_note
                }

            price = it["price"]
            qty = it["qty"]
            raw_plat = it.get("platform_gross", price * qty * 0.8)
            item_net = round(raw_plat) if abs(raw_plat - round(raw_plat)) < 0.5 else raw_plat
            teachers_data[t_name][c_key]["qty"] += qty
            teachers_data[t_name][c_key]["platform_net"] += item_net

        # 將每個講師的課程字典轉為已結算清單 (正確扣除當期製作費與計算應付版稅)
        final_result = {}
        for t_name, courses_dict in teachers_data.items():
            final_result[t_name] = []
            for c_key, c_data in courses_dict.items():
                raw_net = c_data["platform_net"]
                platform_gross = round(raw_net) if abs(raw_net - round(raw_net)) < 0.5 else raw_net
                cost = c_data["production_cost"]
                net_profit = platform_gross - cost
                payable = round(net_profit * c_data["share_rate"], 1)

                c_data["platform_net"] = platform_gross
                c_data["net_profit"] = net_profit
                c_data["payable"] = payable
                final_result[t_name].append(c_data)

        return final_result

    def get_settlement_preview(self, items, course_configs=None, period_str=None):
        """
        供前端彈出「製作費用選填與核對」視窗時使用的即時預覽方法
        """
        res = self.calculate_royalty(items, course_configs=course_configs, period_str=period_str)
        preview_list = []
        for t_name, c_list in res.items():
            for c in c_list:
                preview_list.append({
                    "teacher_name": t_name,
                    "course_name": c["course_name"],
                    "price": c["price"],
                    "qty": c["qty"],
                    "platform_net": c["platform_net"],
                    "base_cost": c.get("base_cost", c["production_cost"]),
                    "prior_deducted": c.get("prior_deducted", 0.0),
                    "recommended_cost": c["production_cost"],
                    "cost_status": c.get("cost_status", ""),
                    "cost_status_text": c.get("cost_status_text", ""),
                    "share_rate": c["share_rate"],
                    "share_rate_str": c["share_rate_str"],
                    "net_profit": c["net_profit"],
                    "payable": c["payable"],
                    "note": c["note"]
                })
        return preview_list

    def generate_excel(self, teacher_name, period_str, teacher_items, platform_name="104平台", output_dir=None):
        """
        匯出特定講師的版稅明細 Excel，100% 還原原始範本樣式與公式
        """
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "工作表1"

        # 樣式設定 (新細明體 12pt)
        font_main = Font(name="新細明體", size=12, bold=False)
        font_header = Font(name="新細明體", size=12, bold=False)
        
        align_center = Alignment(horizontal="center", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")

        thin_border = Border(
            left=Side(style='thin', color='A0A0A0'),
            right=Side(style='thin', color='A0A0A0'),
            top=Side(style='thin', color='A0A0A0'),
            bottom=Side(style='thin', color='A0A0A0')
        )

        # 1. Row 1: 講師姓名
        ws["A1"] = f"講師 ：{teacher_name}"
        ws["A1"].font = font_main
        ws["A1"].alignment = align_left

        # 2. Row 3: 期別 (J3)
        ws["J3"] = period_str
        ws["J3"].font = font_main
        ws["J3"].alignment = align_right

        # 3. Row 4: 表頭
        headers = [
            "NO.", "課程名稱", "定價", "數量", "平台扣除服務費淨額", 
            "課程製作相關費用", "結餘淨利", "講師分潤", "本期應付", "備註"
        ]
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(4, col_idx, h)
            cell.font = font_header
            cell.alignment = align_center

        # 4. 寫入資料列 (從 Row 6 開始，保留 Row 5 作為間隔或依範本)
        current_row = 6
        for idx, item in enumerate(teacher_items, start=1):
            r = current_row
            ws.cell(r, 1, idx).alignment = align_center # NO.
            ws.cell(r, 2, item["course_name"]).alignment = align_left # 課程名稱
            
            # 定價
            c_price = ws.cell(r, 3, item["price"])
            c_price.number_format = '#,##0_);[Red]\\(#,##0\\)'
            
            # 數量
            ws.cell(r, 4, item["qty"]).alignment = align_center
            
            # 平台扣除服務費淨額 (公式: =C{r}*D{r}*0.8 若數量>1，否則 =C{r}*0.8)
            formula_plat = f"=C{r}*D{r}*0.8" if item["qty"] > 1 else f"=C{r}*0.8"
            c_plat = ws.cell(r, 5, formula_plat)
            c_plat.number_format = '#,##0_);[Red]\\(#,##0\\)'
            
            # 課程製作相關費用
            c_cost = ws.cell(r, 6, item["production_cost"])
            c_cost.number_format = '#,##0_);[Red]\\(#,##0\\)'
            
            # 結餘淨利 (公式: =E{r}-F{r})
            c_net = ws.cell(r, 7, f"=E{r}-F{r}")
            c_net.number_format = '#,##0_);[Red]\\(#,##0\\)'
            
            # 講師分潤比率
            ws.cell(r, 8, item["share_rate_str"]).alignment = align_center
            
            # 本期應付 (若是負數顯示負額，或使用公式)
            ws.cell(r, 9, item["payable"]).alignment = align_right
            
            # 備註
            ws.cell(r, 10, item["note"]).alignment = align_left

            # 套用字型
            for col in range(1, 11):
                ws.cell(r, col).font = font_main

            current_row += 1

        # 5. 設定欄寬 (比照範本)
        col_widths = {
            'A': 9.88,
            'B': 82.75,
            'C': 13.0,
            'D': 13.0,
            'E': 18.5,
            'F': 18.25,
            'G': 12.63,
            'H': 22.0,
            'I': 10.13,
            'J': 40.5
        }
        for col_letter, width in col_widths.items():
            ws.column_dimensions[col_letter].width = width

        # 6. 決定儲存路徑與檔名
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not output_dir:
            output_dir = os.path.join(base_dir, period_str)
        os.makedirs(output_dir, exist_ok=True)

        filename = f"{platform_name}版稅明細-{period_str}({teacher_name}老師).xlsx"
        save_path = os.path.join(output_dir, filename)
        try:
            wb.save(save_path)
        except PermissionError:
            raise PermissionError(
                f"檔案儲存失敗：【{filename}】目前正被 Microsoft Excel 開啟佔用中！\n\n"
                f"👉 解決方法：請先將電腦中開啟的 Excel 講師分潤明細檔案存檔並關閉，然後再點擊一次即可！"
            )
        return save_path

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    settler = TeacherSettlement()
    sample_items = [{
        "course_name": "AIＸ數據分析術:從報表到洞察，全面升級你的職場決策力",
        "price": 1288,
        "qty": 1,
        "platform_gross": 1030.4
    }]
    results = settler.calculate_royalty(sample_items)
    for t_name, t_items in results.items():
        out = settler.generate_excel(t_name, "115年8月", t_items, "104平台")
        print(f"Generated teacher excel for {t_name}: {out}")
