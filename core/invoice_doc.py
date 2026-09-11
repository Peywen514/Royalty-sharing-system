# -*- coding: utf-8 -*-
"""
發票請款單生成器 (invoice_doc.py)
將抬頭、統編、金額、申請日期、預計於下個月底入帳日等自動填入《附件1_發票收據申請單》，並依月份另存檔案。
"""
import os
import calendar
import datetime
import docx

class InvoiceDocGenerator:
    def __init__(self, template_path=None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if template_path and os.path.exists(template_path):
            self.template_path = template_path
        else:
            # 優先搜尋範本資料夾或預設檔案
            candidate_paths = [
                os.path.join(base_dir, "範本", "附件1_發票收據申請單_範本.docx"),
                os.path.join(base_dir, "附件1_發票收據申請單_20220621版本-Hahow版稅20260811.docx")
            ]
            self.template_path = None
            for p in candidate_paths:
                if os.path.exists(p):
                    self.template_path = p
                    break

    @staticmethod
    def parse_roc_date(raw_val):
        """解析日期並轉為民國年格式 (如 115年09月03日) 及 (roc_year, month, day)"""
        import re
        if isinstance(raw_val, (datetime.datetime, datetime.date)):
            ad_year = raw_val.year
            month = raw_val.month
            day = raw_val.day
            roc_year = ad_year - 1911 if ad_year > 1911 else ad_year
            return f"{roc_year}年{month:02d}月{day:02d}日", roc_year, month, day
        
        val_str = str(raw_val or "").strip()
        val_str = re.sub(r'^(日期|申請日期)[：:\s]*', '', val_str).strip()
        
        m1 = re.match(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', val_str)
        if m1:
            y, m, d = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
            roc_year = y - 1911
            return f"{roc_year}年{m:02d}月{d:02d}日", roc_year, m, d
        
        m2 = re.match(r'(\d{2,3})[年/-](\d{1,2})[月/-](\d{1,2})', val_str)
        if m2:
            y, m, d = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
            return f"{y}年{m:02d}月{d:02d}日", y, m, d
            
        return val_str, None, None, None

    @staticmethod
    def calc_deposit_date_from_apply_date(apply_date_str_or_tuple, fallback_roc_year=115, fallback_month=8):
        """
        以「申請日期」為基準，計算「申請日期隔月底」作為預計入帳日
        例如：申請日期 115年09月03日 (9月) -> 隔月底為 115年10月31日
        """
        if isinstance(apply_date_str_or_tuple, tuple):
            roc_year, month = apply_date_str_or_tuple[0], apply_date_str_or_tuple[1]
        else:
            _, roc_year, month, _ = InvoiceDocGenerator.parse_roc_date(apply_date_str_or_tuple)
        
        if not roc_year or not month:
            roc_year, month = fallback_roc_year, fallback_month
            
        ad_year = roc_year + 1911
        target_month = month + 1
        target_year = ad_year
        if target_month > 12:
            target_month -= 12
            target_year += 1
            
        last_day = calendar.monthrange(target_year, target_month)[1]
        target_roc = target_year - 1911
        return f"{target_roc}年{target_month:02d}月{last_day:02d}日"

    @staticmethod
    def calc_next_month_end(roc_year, month):
        """
        計算預計入帳日期（次次月底入帳，供未提供申請日期時回退使用）
        """
        ad_year = roc_year + 1911
        target_month = month + 2
        target_year = ad_year
        if target_month > 12:
            target_month -= 12
            target_year += 1
            
        last_day = calendar.monthrange(target_year, target_month)[1]
        target_roc = target_year - 1911
        return f"{target_roc}年{target_month:02d}月{last_day:02d}日"

    @staticmethod
    def calc_apply_date(roc_year, month, day=3):
        """
        計算請款申請日期 (預設為次月初，例如 115年09月03日)
        """
        ad_year = roc_year + 1911
        apply_month = month + 1
        apply_year = ad_year
        if apply_month > 12:
            apply_month -= 12
            apply_year += 1
        apply_roc = apply_year - 1911
        return f"{apply_roc}年{apply_month:02d}月{day:02d}日"

    def _set_cell_text(self, cell, new_text, bold=None):
        """安全修改單元格文字，並保持原字型與樣式"""
        if len(cell.paragraphs) > 0:
            p = cell.paragraphs[0]
            font_name = None
            font_size = None
            if len(p.runs) > 0:
                font_name = p.runs[0].font.name
                font_size = p.runs[0].font.size
                if bold is None:
                    bold = p.runs[0].bold
            p.text = new_text
            if len(p.runs) > 0:
                if font_name:
                    p.runs[0].font.name = font_name
                if font_size:
                    p.runs[0].font.size = font_size
                if bold is not None:
                    p.runs[0].bold = bold
        else:
            p = cell.add_paragraph(new_text)
            if bold is not None:
                p.runs[0].bold = bold

    def generate(self, title, tax_id, amount, period_roc_year=115, period_month=8, 
                 apply_date=None, expected_deposit_date=None, output_dir=None, custom_filename=None):
        """
        自動填寫並生成請款單 Word 文件
        :param title: 抬頭 (例如 一零四資訊科技股份有限公司)
        :param tax_id: 統一編號 (例如 84598349)
        :param amount: 請款金額 (例如 1030)
        :param period_roc_year: 民國年份 (如 115)
        :param period_month: 銷售月份 (如 8)
        :param apply_date: 申請日期 (若為 None 則自動計算次月3日)
        :param expected_deposit_date: 預計入帳日期 (若為 None 則自動計算下個月底)
        :param output_dir: 另存目錄 (預設為系統月份專屬目錄)
        :param custom_filename: 自訂檔名
        :return: 生成的檔案絕對路徑
        """
        if not self.template_path or not os.path.exists(self.template_path):
            raise FileNotFoundError(f"找不到發票請款範本文件: {self.template_path}")

        doc = docx.Document(self.template_path)

        # 1. 申請日期與隔月底入帳日期計算
        if apply_date:
            apply_date, roc_y, m_val, _ = self.parse_roc_date(apply_date)
        else:
            apply_date = self.calc_apply_date(period_roc_year, period_month, day=3)
            roc_y, m_val = period_roc_year, period_month + 1
        
        if not expected_deposit_date:
            expected_deposit_date = self.calc_deposit_date_from_apply_date(
                (roc_y, m_val) if roc_y else apply_date, 
                fallback_roc_year=period_roc_year, 
                fallback_month=period_month
            )
        else:
            if not expected_deposit_date.startswith("("):
                parsed_dep, _, _, _ = self.parse_roc_date(expected_deposit_date)
                expected_deposit_date = parsed_dep or expected_deposit_date

        expected_deposit_str = f"(預計) {expected_deposit_date}" if not expected_deposit_date.startswith("(") else expected_deposit_date

        # 2. 金額格式化 (NT$1,030)
        amount_int = int(round(float(amount)))
        amount_str = f"NT${amount_int:,}"

        # 3. 統編文字
        tax_id_str = f"有統編，請填統編：{tax_id}"

        # 4. 寫入 Table 0 (基本資料)
        # 申請日期: Table 0, Row 0, Col 3
        self._set_cell_text(doc.tables[0].rows[0].cells[3], apply_date)

        # 5. 寫入 Table 1 (開立資料)
        # 抬頭: Table 1, Row 0, Col 1
        self._set_cell_text(doc.tables[1].rows[0].cells[1], title, bold=True)
        # 金額: Table 1, Row 0, Col 7
        self._set_cell_text(doc.tables[1].rows[0].cells[7], amount_str, bold=True)
        # 統編: Table 1, Row 1, Col 2
        self._set_cell_text(doc.tables[1].rows[1].cells[2], tax_id_str)

        # 6. 寫入 Table 2 (入帳資料)
        # 未入帳預計日: Table 2, Row 5, Col 1
        self._set_cell_text(doc.tables[2].rows[5].cells[1], expected_deposit_str)

        # 7. 決定儲存路徑
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        period_str = f"{period_roc_year}年{period_month}月"
        if not output_dir:
            output_dir = os.path.join(base_dir, period_str)
        os.makedirs(output_dir, exist_ok=True)

        if not custom_filename:
            short_name = "104" if "一零四" in title or "104" in title else ("Hahow" if "好學校" in title or "朋聚" in title else "平台")
            filename = f"附件1_發票收據申請單_{short_name}版稅{period_str}.docx"
        else:
            filename = custom_filename
            if not filename.endswith(".docx"):
                filename += ".docx"

        save_path = os.path.join(output_dir, filename)
        doc.save(save_path)
        return save_path

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    gen = InvoiceDocGenerator()
    out = gen.generate(
        title="一零四資訊科技股份有限公司",
        tax_id="84598349",
        amount=1030,
        period_roc_year=115,
        period_month=8
    )
    print("Generated invoice docx at:", out)
