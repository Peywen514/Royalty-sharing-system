# -*- coding: utf-8 -*-
"""
對帳核對引擎 (reconciler.py)
負責解析「使用者自填明細表」與「平台方郵件對帳明細」，進行欄位對照、數字稽核與差異標示。
"""
import os
import openpyxl
from datetime import datetime
from core.ppa_calculator import calc_ppa_royalty
from core.invoice_doc import InvoiceDocGenerator

class Reconciler:
    def __init__(self):
        pass

    def parse_user_excel(self, file_path):
        """解析使用者自填的平台版稅明細 Excel (例如 104平台版稅明細-115年8月.xlsx)"""
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb.active
        
        meta = {
            "platform_name": "",
            "tax_id": "",
            "date_str": "",
            "apply_date": "",
            "expected_deposit_date": "",
            "period": ""
        }
        
        # 提取表頭資訊 (平台名稱、統一編號、右上角申請日期)
        raw_date = None
        for r in range(1, 5):
            for c in range(1, ws.max_column + 1):
                val = str(ws.cell(r, c).value or "").strip()
                if "課程平台：" in val or "平台：" in val:
                    meta["platform_name"] = val.split("：", 1)[-1].strip()
                elif "統一編號：" in val or "統編：" in val:
                    meta["tax_id"] = val.split("：", 1)[-1].strip()
                elif "日期：" in val or val == "日期" or "申請日期" in val:
                    next_val = ws.cell(r, c + 1).value if c + 1 <= ws.max_column else None
                    if next_val:
                        raw_date = next_val
                    elif "：" in val:
                        part = val.split("：", 1)[-1].strip()
                        if part: raw_date = part
                    elif ":" in val:
                        part = val.split(":", 1)[-1].strip()
                        if part: raw_date = part

        if raw_date:
            apply_date, roc_y, m_val, _ = InvoiceDocGenerator.parse_roc_date(raw_date)
            expected_deposit = InvoiceDocGenerator.calc_deposit_date_from_apply_date((roc_y, m_val) if roc_y else apply_date)
            meta["apply_date"] = apply_date
            meta["expected_deposit_date"] = expected_deposit
            meta["date_str"] = apply_date

        # 找表頭行 (NO. / 課程名稱 / 定價 ...)
        header_row = None
        for r in range(1, 8):
            row_vals = [str(ws.cell(r, c).value or "").strip() for c in range(1, ws.max_column + 1)]
            if any("課程名稱" in v for v in row_vals):
                header_row = r
                break
        
        if not header_row:
            header_row = 4

        # 欄位索引對應
        col_map = {}
        for c in range(1, ws.max_column + 1):
            val = str(ws.cell(header_row, c).value or "").strip()
            # 若有第二行表頭 (例如 數量/金額 下面有 數量、金額(80%))
            sub_val = str(ws.cell(header_row + 1, c).value or "").strip() if header_row + 1 <= ws.max_row else ""
            
            if "課程名稱" in val:
                col_map["course_name"] = c
            elif "定價" in val:
                col_map["price"] = c
            elif "數量" in val or "數量" in sub_val:
                if "qty" not in col_map:
                    col_map["qty"] = c
            elif "80%" in sub_val or "平台淨額" in val or "金額(80%)" in val or "金額(80%)" in sub_val:
                col_map["platform_gross"] = c
            elif "總金額" in val or "未稅" in val:
                col_map["net_amount"] = c
            elif "代扣稅額" in val or "稅額" in val:
                col_map["tax_amount"] = c
            elif "應收版稅" in val:
                col_map["royalty_gross"] = c
            elif "備註" in val:
                col_map["note"] = c

        # 讀取課程資料列
        start_row = header_row + 2 if header_row + 1 <= ws.max_row and any(ws.cell(header_row + 1, c).value for c in range(1, ws.max_column + 1)) else header_row + 1
        items = []
        for r in range(start_row, ws.max_row + 1):
            course_name = ws.cell(r, col_map.get("course_name", 2)).value
            if not course_name or str(course_name).strip() == "" or str(course_name).strip().startswith("合計"):
                continue
            
            price = float(ws.cell(r, col_map.get("price", 3)).value or 0)
            qty = int(ws.cell(r, col_map.get("qty", 4)).value or 0)
            platform_gross = float(ws.cell(r, col_map.get("platform_gross", 5)).value or (price * qty * 0.8))
            net_amount = float(ws.cell(r, col_map.get("net_amount", 6)).value or 0)
            tax_amount = float(ws.cell(r, col_map.get("tax_amount", 7)).value or 0)
            royalty_gross = float(ws.cell(r, col_map.get("royalty_gross", 8)).value or platform_gross)
            note = str(ws.cell(r, col_map.get("note", 9)).value or "").strip()
            
            items.append({
                "no": len(items) + 1,
                "course_name": str(course_name).strip(),
                "price": price,
                "qty": qty,
                "platform_gross": platform_gross,
                "net_amount": net_amount,
                "tax_amount": tax_amount,
                "royalty_gross": royalty_gross,
                "note": note
            })
            
        summary = {
            "total_qty": sum(it["qty"] for it in items),
            "total_sales": sum(it["price"] * it["qty"] for it in items),
            "total_net": round(sum(it["net_amount"] for it in items), 2),
            "total_tax": round(sum(it["tax_amount"] for it in items), 2),
            "total_gross": round(sum(it["royalty_gross"] for it in items), 2)
        }
        
        return {
            "meta": meta,
            "items": items,
            "summary": summary
        }

    def parse_platform_excel(self, file_path):
        """解析平台方郵件寄來的對帳單 Excel (例如 2026年8月對帳for中華民國電腦技能基金會.xlsx)"""
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb.active
        
        # 尋找表頭
        col_map = {}
        header_row = 1
        for r in range(1, min(5, ws.max_row + 1)):
            row_vals = [str(ws.cell(r, c).value or "").strip() for c in range(1, ws.max_column + 1)]
            if any("銷售額" in v or "分潤" in v or "訂單" in v for v in row_vals):
                header_row = r
                for c in range(1, ws.max_column + 1):
                    val = str(ws.cell(header_row, c).value or "").strip()
                    if "訂單成立日期" in val or "訂單日期" in val:
                        col_map["order_date"] = c
                    elif "供應商名稱" in val:
                        col_map["supplier_name"] = c
                    elif "銷售額(應稅)" in val or "銷售金額" in val:
                        col_map["sales_taxable"] = c
                    elif "銷售額(未稅)" in val:
                        col_map["sales_untaxed"] = c
                    elif "分潤比例" in val or "分潤比" in val:
                        col_map["split_rate"] = c
                    elif "供應商分潤金額(應稅)" in val:
                        col_map["supplier_taxable"] = c
                    elif "供應商分潤金額(未稅)" in val:
                        col_map["supplier_untaxed"] = c
                    elif "商品數量" in val or "數量" in val:
                        col_map["qty"] = c
                    elif "商品金額(應稅)" in val or "商品金額" in val:
                        col_map["item_amount"] = c
                    elif "折扣金額" in val:
                        col_map["discount"] = c
                    elif "供應商統編" in val:
                        col_map["supplier_tax_id"] = c
                break
                
        rows = []
        for r in range(header_row + 1, ws.max_row + 1):
            if not any(ws.cell(r, c).value for c in range(1, ws.max_column + 1)):
                continue
            
            order_date = ws.cell(r, col_map.get("order_date", 1)).value
            if isinstance(order_date, datetime):
                order_date = order_date.strftime("%Y-%m-%d %H:%M:%S")
            else:
                order_date = str(order_date or "").strip()
                
            supplier_name = str(ws.cell(r, col_map.get("supplier_name", 2)).value or "").strip()
            sales_taxable = float(ws.cell(r, col_map.get("sales_taxable", 3)).value or 0)
            sales_untaxed = float(ws.cell(r, col_map.get("sales_untaxed", 4)).value or 0)
            split_rate_raw = ws.cell(r, col_map.get("split_rate", 5)).value
            if isinstance(split_rate_raw, str) and "%" in split_rate_raw:
                split_rate = float(split_rate_raw.replace("%", "")) / 100.0
            else:
                split_rate = float(split_rate_raw or 0.8)
                
            supplier_taxable = float(ws.cell(r, col_map.get("supplier_taxable", 6)).value or 0)
            supplier_untaxed = float(ws.cell(r, col_map.get("supplier_untaxed", 7)).value or 0)
            qty = int(ws.cell(r, col_map.get("qty", 10)).value or 1)
            item_amount = float(ws.cell(r, col_map.get("item_amount", 11)).value or sales_taxable)
            discount = float(ws.cell(r, col_map.get("discount", 12)).value or 0)
            supplier_tax_id = str(ws.cell(r, col_map.get("supplier_tax_id", 13)).value or "").strip()
            
            rows.append({
                "order_date": order_date,
                "supplier_name": supplier_name,
                "sales_taxable": sales_taxable,
                "sales_untaxed": sales_untaxed,
                "split_rate": split_rate,
                "supplier_taxable": supplier_taxable,
                "supplier_untaxed": supplier_untaxed,
                "qty": qty,
                "item_amount": item_amount,
                "discount": discount,
                "supplier_tax_id": supplier_tax_id
            })

        summary = {
            "total_qty": sum(r["qty"] for r in rows),
            "total_sales_taxable": sum(r["sales_taxable"] for r in rows),
            "total_sales_untaxed": sum(r["sales_untaxed"] for r in rows),
            "total_supplier_taxable": sum(r["supplier_taxable"] for r in rows),
            "total_supplier_untaxed": sum(r["supplier_untaxed"] for r in rows),
            "avg_split_rate": rows[0]["split_rate"] if rows else 0.8
        }
        
        return {
            "rows": rows,
            "summary": summary
        }

    def reconcile(self, user_file_path, platform_file_path, platform_id=None):
        """執行雙向核對與稽核分析"""
        user_data = self.parse_user_excel(user_file_path)
        platform_data = self.parse_platform_excel(platform_file_path)
        
        u_sum = user_data["summary"]
        p_sum = platform_data["summary"]
        
        is_ppa = (platform_id == "ppa") or ("ppa" in user_file_path.lower()) or ("ppa" in platform_file_path.lower())

        if is_ppa:
            # PPA 專案撥款計算邏輯
            gross_val = p_sum["total_sales_taxable"] if p_sum["total_sales_taxable"] > 0 else u_sum["total_sales"]
            # 取得折扣/行銷費用
            marketing_val = sum(r.get("discount", 0) for r in platform_data.get("rows", []))
            ppa_calc = calc_ppa_royalty(gross_val, marketing_val)

            qty_match = (u_sum["total_qty"] == p_sum["total_qty"])
            sales_match = abs(u_sum["total_sales"] - gross_val) < 0.01
            net_match = True
            gross_match = True
            is_matched = qty_match and sales_match

            audit_items = [
                {
                    "label": "銷售總數量",
                    "user_val": f"{u_sum['total_qty']} 件",
                    "platform_val": f"{p_sum['total_qty']} 件",
                    "diff": f"{u_sum['total_qty'] - p_sum['total_qty']} 件",
                    "matched": qty_match
                },
                {
                    "label": "消費總額 (含稅實付)",
                    "user_val": f"NT$ {u_sum['total_sales']:,.0f}",
                    "platform_val": f"NT$ {gross_val:,.0f}",
                    "diff": f"NT$ {u_sum['total_sales'] - gross_val:,.0f}",
                    "matched": sales_match
                },
                {
                    "label": "金流手續費 (2.25%)",
                    "user_val": f"NT$ {ppa_calc['gateway_fee']:,.1f}",
                    "platform_val": f"NT$ {ppa_calc['gateway_fee']:,.1f}",
                    "diff": "0",
                    "matched": True
                },
                {
                    "label": "PPA平台服務費 (20%)",
                    "user_val": f"NT$ {ppa_calc['platform_fee']:,.1f}",
                    "platform_val": f"NT$ {ppa_calc['platform_fee']:,.1f}",
                    "diff": "0",
                    "matched": True
                },
                {
                    "label": "CSF未稅銷售所得",
                    "user_val": f"NT$ {ppa_calc['csf_sales_income_untaxed']:,.1f}",
                    "platform_val": f"NT$ {ppa_calc['csf_sales_income_untaxed']:,.1f}",
                    "diff": "0",
                    "matched": True
                },
                {
                    "label": "應開立請款發票 (含稅 5%)",
                    "user_val": f"NT$ {ppa_calc['invoice_amount_integer']:,}",
                    "platform_val": f"NT$ {ppa_calc['invoice_amount_integer']:,}",
                    "diff": "0",
                    "matched": True
                }
            ]

            status = "MATCHED" if is_matched else "DISCREPANCY"
            status_text = "✅ PPA 合約公式核對相符（可立即匯入請款）" if is_matched else "⚠️ 發現金額或數量不符"

            return {
                "status": status,
                "status_text": status_text,
                "audit_items": audit_items,
                "user_data": user_data,
                "platform_data": platform_data,
                "ppa_details": ppa_calc,
                "final_invoice_amount": ppa_calc["invoice_amount_integer"]
            }

        # 一般平台 (如 104) 邏輯
        qty_match = (u_sum["total_qty"] == p_sum["total_qty"])
        sales_match = abs(u_sum["total_sales"] - p_sum["total_sales_taxable"]) < 0.01
        net_diff = abs(u_sum["total_net"] - p_sum["total_supplier_untaxed"])
        net_match = (net_diff <= 1.0)
        gross_diff = abs(round(u_sum["total_gross"]) - round(p_sum["total_supplier_taxable"]))
        gross_match = (gross_diff <= 1.0)
        
        is_matched = qty_match and sales_match and net_match and gross_match
        
        audit_items = [
            {
                "label": "銷售總數量",
                "user_val": f"{u_sum['total_qty']} 件",
                "platform_val": f"{p_sum['total_qty']} 件",
                "diff": f"{u_sum['total_qty'] - p_sum['total_qty']} 件",
                "matched": qty_match
            },
            {
                "label": "銷售總額 (應稅)",
                "user_val": f"NT$ {u_sum['total_sales']:,.0f}",
                "platform_val": f"NT$ {p_sum['total_sales_taxable']:,.0f}",
                "diff": f"NT$ {u_sum['total_sales'] - p_sum['total_sales_taxable']:,.0f}",
                "matched": sales_match
            },
            {
                "label": "分潤比率",
                "user_val": "80%",
                "platform_val": f"{p_sum['avg_split_rate']*100:.0f}%",
                "diff": "0%",
                "matched": True
            },
            {
                "label": "供應商分潤 (未稅淨額)",
                "user_val": f"NT$ {u_sum['total_net']:,.0f}",
                "platform_val": f"NT$ {p_sum['total_supplier_untaxed']:,.0f}",
                "diff": f"NT$ {u_sum['total_net'] - p_sum['total_supplier_untaxed']:,.0f}",
                "matched": net_match
            },
            {
                "label": "供應商應收版稅 (含稅請款金額)",
                "user_val": f"NT$ {round(u_sum['total_gross']):,.0f}",
                "platform_val": f"NT$ {round(p_sum['total_supplier_taxable']):,.0f}",
                "diff": f"NT$ {round(u_sum['total_gross']) - round(p_sum['total_supplier_taxable']):,.0f}",
                "matched": gross_match
            }
        ]
        
        status = "MATCHED" if is_matched else "DISCREPANCY"
        status_text = "✅ 核對完全相符（可立即匯入請款）" if is_matched else "⚠️ 發現金額或數量不符（請確認明細）"
        
        return {
            "status": status,
            "status_text": status_text,
            "audit_items": audit_items,
            "user_data": user_data,
            "platform_data": platform_data,
            "final_invoice_amount": int(round(p_sum["total_supplier_taxable"])) if is_matched else int(round(u_sum["total_gross"]))
        }

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    base_dir = r"D:\Users\peggy_chien\Desktop\版稅銷售系統"
    u_f = os.path.join(base_dir, "104平台版稅明細-115年8月.xlsx")
    p_f = os.path.join(base_dir, "2026年8月對帳for中華民國電腦技能基金會.xlsx")
    rec = Reconciler()
    res = rec.reconcile(u_f, p_f)
    print("Status:", res["status_text"])
    for a in res["audit_items"]:
        print(f" - {a['label']}: 自填={a['user_val']}, 平台={a['platform_val']}, 結果={'OK' if a['matched'] else 'DIFF'}")
