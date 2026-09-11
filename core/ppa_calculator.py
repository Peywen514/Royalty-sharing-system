# -*- coding: utf-8 -*-
"""
測試 PPA (PressPlay) 版稅計算公式
"""
def calc_ppa_royalty(gross_consumption, marketing_cost=0):
    """
    依據 PressPlay 商務合約第 1 條計算：
    :param gross_consumption: 消費總額 (消費者實際支付之金額，含稅)
    :param marketing_cost: 行銷活動總成本 (如優惠券、折扣等，含稅)
    :return: 詳細費用拆解 dict
    """
    # 1. 消費未稅總額
    untaxed_consumption = gross_consumption / 1.05
    
    # 2. 金流手續費 (以消費者實際支付之金額計算 2.25%)
    gateway_fee = gross_consumption * 0.0225
    
    # 3. 平台服務費 [(消費總額/1.05) - (消費總額*2.25%)] * 20%
    platform_base = untaxed_consumption - gateway_fee
    platform_fee = platform_base * 0.20
    
    # 4. 行銷費 (依甲方20% : 乙方80%負擔，且以未稅價計算)
    untaxed_marketing_total = marketing_cost / 1.05
    csf_marketing_share = untaxed_marketing_total * 0.80
    ppa_marketing_share = untaxed_marketing_total * 0.20
    
    # 5. 銷售所得 (乙方未稅銷售所得)
    csf_sales_income_untaxed = untaxed_consumption - gateway_fee - platform_fee - csf_marketing_share
    
    # 6. 發票開立金額 (含稅 5%)
    invoice_tax_5pct = csf_sales_income_untaxed * 0.05
    invoice_amount_gross = csf_sales_income_untaxed * 1.05

    return {
        "gross_consumption": round(gross_consumption, 2),
        "untaxed_consumption": round(untaxed_consumption, 2),
        "gateway_fee": round(gateway_fee, 2),
        "platform_fee": round(platform_fee, 2),
        "csf_marketing_share": round(csf_marketing_share, 2),
        "ppa_marketing_share": round(ppa_marketing_share, 2),
        "csf_sales_income_untaxed": round(csf_sales_income_untaxed, 2),
        "invoice_tax_5pct": round(invoice_tax_5pct, 2),
        "invoice_amount_gross": round(invoice_amount_gross, 2),
        "invoice_amount_integer": int(round(invoice_amount_gross))
    }

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    res = calc_ppa_royalty(1288, marketing_cost=0)
    print("--- 測試 1 (單筆實付 $1,288，無行銷折扣) ---")
    for k, v in res.items():
        print(f"  {k}: {v}")

    res2 = calc_ppa_royalty(1288, marketing_cost=300)
    print("\n--- 測試 2 (單筆實付 $1,288，優惠活動 $300) ---")
    for k, v in res2.items():
        print(f"  {k}: {v}")
