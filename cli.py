# -*- coding: utf-8 -*-
"""
命令列與自動批次月結工具 (cli.py)
支援自動偵測、一鍵雙向對帳、資料庫存檔、產出請款 Word 單據及講師分潤 Excel。
"""
import os
import sys
import argparse

# 確保輸出支援 UTF-8
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.db import init_db, get_connection, get_all_configs
from core.reconciler import Reconciler
from core.invoice_doc import InvoiceDocGenerator
from core.teacher_settlement import TeacherSettlement

def run_monthly_settlement(roc_year=115, month=8, platform_id="104", user_file=None, plat_file=None):
    init_db()
    period_str = f"{roc_year}年{month}月"
    print("=" * 65)
    print(f" 🚀 開始執行線上課程版稅銷售與請款月結作業 [{period_str}]")
    print("=" * 65)

    # 1. 尋找或驗證檔案
    if not user_file:
        for f in os.listdir(BASE_DIR):
            if f.endswith(".xlsx") and "平台版稅明細" in f and "老師" not in f and str(month) in f:
                user_file = os.path.join(BASE_DIR, f)
                break
        if not user_file:
            user_file = os.path.join(BASE_DIR, f"104平台版稅明細-{period_str}.xlsx")

    if not plat_file:
        for f in os.listdir(BASE_DIR):
            if f.endswith(".xlsx") and "對帳" in f and str(month) in f:
                plat_file = os.path.join(BASE_DIR, f)
                break
        if not plat_file:
            plat_file = os.path.join(BASE_DIR, f"2026年{month}月對帳for中華民國電腦技能基金會.xlsx")

    print(f"📄 使用者自填明細: {os.path.basename(user_file)}")
    print(f"📬 平台對帳明細:   {os.path.basename(plat_file)}")

    if not os.path.exists(user_file) or not os.path.exists(plat_file):
        print(f"❌ 錯誤: 找不到對帳所需檔案！")
        return False

    # 2. 雙向對帳稽核
    rec = Reconciler()
    audit_res = rec.reconcile(user_file, plat_file)

    print("\n---------------- 對帳審計報告 ----------------")
    print(f"審計狀態: {audit_res['status_text']}")
    for a in audit_res["audit_items"]:
        symbol = "✔" if a["matched"] else "✖"
        print(f" [{symbol}] {a['label']:<18} 自填: {a['user_val']:<12} 平台: {a['platform_val']:<12} (差異: {a['diff']})")

    if audit_res["status"] != "MATCHED":
        print("\n⚠️ 注意: 對帳發現差異，請確認自填表單或平台對帳單內容！")
    else:
        print("\n✅ 核對完全吻合，繼續自動化產檔流程...")

    # 3. 取得平台資訊
    configs = get_all_configs()
    plat_info = next((p for p in configs["platforms"] if p["id"] == platform_id), None)
    if not plat_info:
        plat_info = {
            "name": "一零四資訊科技股份有限公司",
            "tax_id": "84598349"
        }

    # 4. 生成發票請款申請單 (Word)
    final_amount = audit_res["final_invoice_amount"]
    out_dir = os.path.join(BASE_DIR, period_str)
    os.makedirs(out_dir, exist_ok=True)

    user_meta = audit_res.get("user_data", {}).get("meta", {})
    apply_date = user_meta.get("apply_date")
    expected_deposit = user_meta.get("expected_deposit_date")

    inv_gen = InvoiceDocGenerator()
    doc_path = inv_gen.generate(
        title=plat_info["name"],
        tax_id=plat_info["tax_id"],
        amount=final_amount,
        period_roc_year=roc_year,
        period_month=month,
        apply_date=apply_date,
        expected_deposit_date=expected_deposit,
        output_dir=out_dir
    )
    actual_apply, roc_y, m_val, _ = inv_gen.parse_roc_date(apply_date) if apply_date else (inv_gen.calc_apply_date(roc_year, month), None, None, None)
    actual_deposit = expected_deposit or inv_gen.calc_deposit_date_from_apply_date(actual_apply, roc_year, month)
    print(f"\n📄 [1/2] 已自動生成發票請款申請單:")
    print(f"   抬頭: {plat_info['name']}")
    print(f"   統編: {plat_info['tax_id']}")
    print(f"   金額: NT$ {final_amount:,}")
    print(f"   申請日期: {actual_apply}")
    print(f"   預計入帳(隔月底): (預計) {actual_deposit}")
    print(f"   路徑: {doc_path}")

    # 5. 結算講師分潤 (Excel)
    items = audit_res["user_data"]["items"]
    settler = TeacherSettlement()
    teacher_results = settler.calculate_royalty(items, course_configs=configs["courses"])

    print(f"\n📊 [2/2] 講師分潤結算明細:")
    plat_short_name = "104平台" if platform_id == "104" else plat_info["name"]
    for t_name, t_items in teacher_results.items():
        t_excel_path = settler.generate_excel(
            teacher_name=t_name,
            period_str=period_str,
            teacher_items=t_items,
            platform_name=plat_short_name,
            output_dir=out_dir
        )
        for it in t_items:
            print(f"   講師: {t_name} | 課程: {it['course_name'][:25]}...")
            print(f"   平台淨額: ${it['platform_net']:,.1f} - 製作成本: ${it['production_cost']:,.1f} = 結餘: ${it['net_profit']:,.1f}")
            print(f"   分潤: {it['share_rate_str']} -> 本期應付: ${it['payable']:,.1f}")
        print(f"   匯出 Excel: {t_excel_path}")

    print("\n" + "=" * 65)
    print(f"🎉 全部月結流程已完成！所有檔案已自動存入:")
    print(f"👉 {out_dir}")
    print("=" * 65)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="線上課程版稅銷售與請款結算自動化工具")
    parser.add_argument("--year", type=int, default=115, help="民國年份 (預設 115)")
    parser.add_argument("--month", type=int, default=8, help="結算月份 (預設 8)")
    parser.add_argument("--platform", type=str, default="104", help="平台代碼 (預設 104)")
    args = parser.parse_args()

    run_monthly_settlement(roc_year=args.year, month=args.month, platform_id=args.platform)
