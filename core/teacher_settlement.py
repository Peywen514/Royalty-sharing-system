# -*- coding: utf-8 -*-
"""
講師分潤結算引擎 (teacher_settlement.py)
依課程所屬講師與分潤合約公式，自動計算各講師之版稅，並產生符合標準格式的 Excel 明細表。
"""
import os
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

class TeacherSettlement:
    def __init__(self, db_conn=None):
        self.db_conn = db_conn

    def calculate_royalty(self, items, course_configs=None):
        """
        計算各項課程分潤並歸組至各講師
        :param items: 當期對帳課程明細清單 (每筆包含 course_name, price, qty, platform_gross 等)
        :param course_configs: 課程與講師設定 (若無則使用預設規則或資料庫查詢)
        :return: 依講師分組的結算結果 dict
        """
        # 預設課程設定 (若未傳入)
        default_rules = {
            "AIＸ數據分析術:從報表到洞察，全面升級你的職場決策力": {
                "teacher": "侯玉彤",
                "share_rate": 0.50,
                "production_cost": 1069.0,
                "note": "扣除平台服務費、課程製作相關費用"
            },
            "生成式AI全解析:從概念到實戰落地應用": {
                "teacher": "簡志峰",
                "share_rate": 0.50,
                "production_cost": 0.0,
                "note": "扣除平台服務費"
            }
        }
        
        rules = default_rules.copy()
        if course_configs:
            for c in course_configs:
                c_name = c.get("course_name")
                if c_name:
                    rules[c_name] = {
                        "teacher": c.get("teacher_name", "未知講師"),
                        "share_rate": float(c.get("teacher_share_rate", 0.5)),
                        "production_cost": float(c.get("production_cost", 0.0)),
                        "note": c.get("note", "扣除平台服務費")
                    }

        teachers_data = {}
        for it in items:
            c_name = it["course_name"]
            # 模糊匹配或精確匹配
            rule = None
            for key, val in rules.items():
                if key in c_name or c_name in key:
                    rule = val
                    break
            
            if not rule:
                rule = {
                    "teacher": "未指定講師",
                    "share_rate": 0.50,
                    "production_cost": 0.0,
                    "note": "扣除平台服務費"
                }

            t_name = rule["teacher"]
            if t_name not in teachers_data:
                teachers_data[t_name] = []

            price = it["price"]
            qty = it["qty"]
            # 若對帳後有整數供應商應收金額則優先取整數(符合會計實務無角分入帳)
            raw_plat = it.get("platform_gross", price * qty * 0.8)
            platform_gross = round(raw_plat) if abs(raw_plat - round(raw_plat)) < 0.5 else raw_plat
            cost = rule["production_cost"]
            net_profit = platform_gross - cost
            share_rate = rule["share_rate"]
            payable = round(net_profit * share_rate, 1)

            teachers_data[t_name].append({
                "course_name": c_name,
                "price": price,
                "qty": qty,
                "platform_net": platform_gross,
                "production_cost": cost,
                "net_profit": net_profit,
                "share_rate": share_rate,
                "share_rate_str": f"{int(share_rate*100)}%",
                "payable": payable,
                "note": rule["note"]
            })

        return teachers_data

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
            
            # 平台扣除服務費淨額 (公式: =C{r}*0.8)
            c_plat = ws.cell(r, 5, f"=C{r}*0.8")
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
        wb.save(save_path)
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
