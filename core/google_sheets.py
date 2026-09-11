# -*- coding: utf-8 -*-
"""
Google Sheets 自動串聯與同步模組 (google_sheets.py)
支援「平台對帳請款表 (分 104 與 PPA 分頁)」與「講師分潤結算表 (獨立 Google Sheet)」雙表架構。
"""
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "google_sheets_config.json")

def get_sheets_config():
    """取得 Google Sheets 同步設定"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "platform_webhook_url": "",  # Google Sheet 1: 平台對帳請款表 Webhook 網址
        "teacher_webhook_url": "",   # Google Sheet 2: 講師分潤結算表 Webhook 網址
        "auto_sync_on_reconcile": True
    }

def save_sheets_config(config_data):
    """儲存 Google Sheets 設定"""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)
    return True

def sync_to_google_sheets(period, platform_id, platform_name, items, summary, invoice_info=None, teacher_settlements=None, ppa_details=None):
    """
    雙表分流同步至 Google Sheets:
    1. 平台對帳請款表 (依平台寫入 104平台 或 PPA平台 分頁)
    2. 講師分潤結算表 (寫入獨立的講師 Google Sheet)
    """
    config = get_sheets_config()
    plat_webhook = config.get("platform_webhook_url", "").strip()
    teacher_webhook = config.get("teacher_webhook_url", "").strip()

    messages = []
    success_count = 0

    # -------------------------------------------------------------
    # 任務 1：同步至【平台對帳請款表】(Sheet 1: 104 / PPA 分頁)
    # -------------------------------------------------------------
    if plat_webhook:
        is_ppa = (platform_id == "ppa" or "ppa" in str(platform_name).lower() or "瑞奧" in str(platform_name))
        target_tab = "PPA" if is_ppa else "104"
        
        if is_ppa and not ppa_details:
            from core.ppa_calculator import calc_ppa_royalty
            total_sales = summary.get("total_sales") or sum(it.get("price", 0) * it.get("qty", 0) for it in items)
            ppa_details = calc_ppa_royalty(total_sales, 0)

        plat_rows = []
        if is_ppa and ppa_details:
            # PPA 專屬欄位結構
            for it in items:
                plat_rows.append({
                    "期別": period,
                    "平台": platform_name,
                    "課程名稱": it.get("course_name", ""),
                    "定價": it.get("price", 0),
                    "銷售數量": it.get("qty", 0),
                    "消費總額(實付)": ppa_details.get("gross_consumption", 0),
                    "金流手續費(2.25%)": ppa_details.get("gateway_fee", 0),
                    "PPA平台服務費(20%)": ppa_details.get("platform_fee", 0),
                    "我方分攤行銷費": ppa_details.get("csf_marketing_share", 0),
                    "CSF銷售所得(未稅)": ppa_details.get("csf_sales_income_untaxed", 0),
                    "發票請款總額(含稅)": ppa_details.get("invoice_amount_integer", 0),
                    "發票抬頭": invoice_info.get("title", "瑞奧股份有限公司") if invoice_info else "瑞奧股份有限公司",
                    "統一編號": invoice_info.get("tax_id", "54225569") if invoice_info else "54225569",
                    "預計入帳日期": invoice_info.get("expected_deposit_date", "") if invoice_info else "",
                    "更新時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
        else:
            # 104 或標準平台欄位結構
            for it in items:
                plat_rows.append({
                    "期別": period,
                    "平台": platform_name,
                    "課程名稱": it.get("course_name", ""),
                    "定價": it.get("price", 0),
                    "銷售數量": it.get("qty", 0),
                    "平台淨額(80%)": it.get("platform_gross", 0),
                    "未稅金額": it.get("net_amount", 0),
                    "代扣稅額": it.get("tax_amount", 0),
                    "應收請款總額(含稅)": round(it.get("royalty_gross", 0)),
                    "發票抬頭": invoice_info.get("title", "一零四資訊科技股份有限公司") if invoice_info else "",
                    "統一編號": invoice_info.get("tax_id", "84598349") if invoice_info else "",
                    "預計入帳日期": invoice_info.get("expected_deposit_date", "") if invoice_info else "",
                    "更新時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

        plat_payload = {
            "type": "platform",
            "sheet_name": target_tab,
            "period": period,
            "platform": platform_name,
            "rows": plat_rows
        }

        try:
            req_data = json.dumps(plat_payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                plat_webhook,
                data=req_data,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                messages.append(f"✔ 成功寫入【平台對帳請款表】➔ 分頁「{target_tab}」({len(plat_rows)} 筆)")
                success_count += 1
        except Exception as e:
            messages.append(f"✖ 平台表同步失敗: {str(e)}")
    else:
        messages.append("ℹ 尚未設定【平台對帳表 Webhook 網址】(略過)")

    # -------------------------------------------------------------
    # 任務 2：同步至【講師分潤結算表】(Sheet 2 - 獨立試算表: 依講師分頁)
    # -------------------------------------------------------------
    if teacher_webhook and teacher_settlements:
        teacher_rows = []
        for teacher_name, t_items in teacher_settlements.items():
            for ti in t_items:
                teacher_rows.append({
                    "期別": period,
                    "授課講師": teacher_name,
                    "課程名稱": ti.get("course_name", ""),
                    "所屬平台": platform_name,
                    "平台撥入淨額": ti.get("platform_net", 0),
                    "製作費用扣除(攤提)": ti.get("production_cost", 0),
                    "結餘淨利": ti.get("net_profit", 0),
                    "講師分潤比率": ti.get("share_rate_str", "50%"),
                    "本期應付講師版稅": ti.get("payable", 0),
                    "備註": ti.get("note", ""),
                    "更新時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

        teacher_payload = {
            "type": "teacher",
            "period": period,
            "rows": teacher_rows
        }

        try:
            req_data = json.dumps(teacher_payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                teacher_webhook,
                data=req_data,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                messages.append(f"✔ 成功寫入【講師分潤結算表】({len(teacher_rows)} 位老師明細)")
                success_count += 1
        except Exception as e:
            messages.append(f"✖ 講師表同步失敗: {str(e)}")
    elif not teacher_webhook:
        messages.append("ℹ 尚未設定【講師分潤表 Webhook 網址】(略過)")

    return {
        "success": success_count > 0,
        "message": "；".join(messages),
        "details": messages
    }

# =========================================================================
# 試算表 ①【平台對帳請款表】專用 Google Apps Script 程式碼 (分頁：104、PPA)
# =========================================================================
GAS_PLATFORM_CODE = '''/**
 * =========================================================================
 * 【試算表 ①：平台對帳請款表】專用 Google Apps Script (含自動表頭與視覺美化)
 * =========================================================================
 * 適用分頁：104、PPA
 * 
 * 💡 貼心功能：
 * 1. 若分頁已存在數據但「缺少表頭」，會自動在最頂端插入表頭，絕不覆蓋既有數據！
 * 2. 104 平台套用「經典深海軍藍 (#1e3a8a)」，PPA 平台套用「尊爵皇家靛紫 (#4338ca)」，連同下方分頁標籤一併染色！
 * 3. 凍結首行、加寬列高、自動調整欄寬。
 * 4. 隨時可在 Apps Script 上方選取「setupHeadersNow」點擊「執行」，立即一鍵美化現有表單！
 */

var HEADERS_104 = [
  "結算期別", "平台名稱", "課程名稱", "課程定價", "銷售數量",
  "平台淨額(80%)", "銷售未稅金額", "代扣營業稅額", "應收請款總額(含稅)",
  "發票抬頭", "統一編號", "預計入帳日期", "寫入時間"
];

var HEADERS_PPA = [
  "結算期別", "平台名稱", "課程名稱", "課程定價", "銷售數量",
  "消費總額(實付)", "金流手續費(2.25%)", "PPA平台服務費(20%)",
  "我方分攤行銷費(80%)", "CSF銷售所得(未稅)", "發票請款總額(含稅)",
  "發票抬頭", "統一編號", "預計入帳日期", "寫入時間"
];

function doGet(e) {
  setupHeadersNow();
  var html = '<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; padding: 30px; line-height: 1.6; max-width: 580px; margin: 40px auto; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.06); background: white;">'
    + '<h2 style="color: #1e3a8a; margin-top: 0; font-size: 1.3rem;">🎉 平台對帳請款表（104 / PPA）表頭已更新成功！</h2>'
    + '<p style="color: #334155; font-size: 14px;">已自動為您的試算表分頁建立深海軍藍/皇家靛紫表頭、凍結首行、欄寬自適應與標籤配色。</p>'
    + '<p style="color: #64748b; font-size: 13px; margin-bottom: 0;">💡 您現在可以切換回 Google 試算表直接查看套用結果。</p>'
    + '</div>';
  return HtmlService.createHtmlOutput(html).setTitle("平台對帳表美化成功");
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.tryLock(10000);

  try {
    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.getActiveSpreadsheet();

    // 判斷目標分頁 (104 或 PPA)
    var rawName = String(data.sheet_name || data.platform || "104");
    var isPPA = (rawName.toUpperCase().indexOf("PPA") !== -1 || rawName.indexOf("瑞奧") !== -1);
    var targetName = isPPA ? "PPA" : "104";

    // 取得或自動建立分頁
    var sheet = ss.getSheetByName(targetName) || ss.getSheetByName(targetName + "平台");
    if (!sheet) {
      // 若試算表僅有預設空白「工作表1」，直接更名為目標分頁
      var defaultSheet = ss.getSheetByName("工作表1") || ss.getSheetByName("Sheet1");
      if (defaultSheet && defaultSheet.getLastRow() === 0 && ss.getSheets().length === 1) {
        defaultSheet.setName(targetName);
        sheet = defaultSheet;
      } else {
        sheet = ss.insertSheet(targetName);
      }
    }

    // 確保目標分頁移至最前方並處於啟用中
    try {
      ss.setActiveSheet(sheet);
      ss.moveActiveSheet(1);
    } catch (e) {}

    // 確保表頭存在並進行高雅視覺美化
    var headers = isPPA ? HEADERS_PPA : HEADERS_104;
    var themeColor = isPPA ? "#4338ca" : "#1e3a8a"; // PPA 皇家靛紫 / 104 深海軍藍
    ensureHeaderAndStyle(sheet, headers, themeColor);

    // 寫入明細資料列
    var rows = data.rows || [];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (isPPA) {
        sheet.appendRow([
          r["期別"] || "",
          r["平台"] || "PressPlay Academy",
          r["課程名稱"] || "",
          r["定價"] || 0,
          r["銷售數量"] || 0,
          r["消費總額(實付)"] || 0,
          r["金流手續費(2.25%)"] || 0,
          r["PPA平台服務費(20%)"] || 0,
          r["我方分攤行銷費"] || 0,
          r["CSF銷售所得(未稅)"] || 0,
          r["發票請款總額(含稅)"] || 0,
          r["發票抬頭"] || "瑞奧股份有限公司",
          r["統一編號"] || "54225569",
          r["預計入帳日期"] || "",
          r["更新時間"] || Utilities.formatDate(new Date(), "Asia/Taipei", "yyyy-MM-dd HH:mm:ss")
        ]);
      } else {
        sheet.appendRow([
          r["期別"] || "",
          r["平台"] || "104人力銀行",
          r["課程名稱"] || "",
          r["定價"] || 0,
          r["銷售數量"] || 0,
          r["平台淨額(80%)"] || 0,
          r["未稅金額"] || 0,
          r["代扣稅額"] || 0,
          r["應收請款總額(含稅)"] || 0,
          r["發票抬頭"] || "一零四資訊科技股份有限公司",
          r["統一編號"] || "84598349",
          r["預計入帳日期"] || "",
          r["更新時間"] || Utilities.formatDate(new Date(), "Asia/Taipei", "yyyy-MM-dd HH:mm:ss")
        ]);
      }
    }

    formatDataRows(sheet, headers.length);

    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      sheet: sheet.getName(),
      rows_added: rows.length
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  } finally {
    lock.releaseLock();
  }
}

/**
 * 確保表頭存在並套用配色
 */
function ensureHeaderAndStyle(sheet, headers, headerBgColor) {
  var lastRow = sheet.getLastRow();

  if (lastRow === 0) {
    // 全新空表：直接新增表頭
    sheet.appendRow(headers);
  } else {
    // 已有資料：檢查第一格是否為表頭文字
    var firstVal = String(sheet.getRange(1, 1).getValue()).trim();
    if (firstVal !== "結算期別" && firstVal !== "期別") {
      // 第一列是資料而非表頭，在最上方插入一列
      sheet.insertRowBefore(1);
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    } else {
      // 確保第一列文字完整
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    }
  }

  // 套用專業高質感表頭樣式
  var headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange.setBackground(headerBgColor)
             .setFontColor("#ffffff")
             .setFontWeight("bold")
             .setFontSize(10)
             .setHorizontalAlignment("center")
             .setVerticalAlignment("middle");

  sheet.setRowHeight(1, 38);       // 表頭高度加大更舒適
  sheet.setFrozenRows(1);          // 凍結首行
  try {
    sheet.setTabColor(headerBgColor); // 將下方分頁標籤同步上色
  } catch (e) {}

  // 自動調整欄寬
  for (var c = 1; c <= headers.length; c++) {
    sheet.autoResizeColumn(c);
  }
}

/**
 * 格式化數據列
 */
function formatDataRows(sheet, colCount) {
  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) return;

  sheet.getRange(2, 1, lastRow - 1, 1).setHorizontalAlignment("center");
  sheet.getRange(2, 5, lastRow - 1, 1).setHorizontalAlignment("center");
}

/**
 * 💡【手動一鍵美化現有工作表】
 * 可在 Apps Script 上方選取「setupHeadersNow」並點擊「執行」，立即一鍵為目前所有分頁加上表頭與顏色！
 */
function setupHeadersNow() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    var s = sheets[i];
    var name = s.getName().toUpperCase();
    if (name.indexOf("PPA") !== -1 || name.indexOf("瑞奧") !== -1) {
      ensureHeaderAndStyle(s, HEADERS_PPA, "#4338ca");
      formatDataRows(s, HEADERS_PPA.length);
    } else {
      // 若為「工作表1」且為空，且有其他分頁，則刪除空白「工作表1」；若僅有此頁或有資料，則套用 104 表頭
      if ((name === "工作表1" || name === "SHEET1") && s.getLastRow() === 0 && sheets.length > 1) {
        try { ss.deleteSheet(s); } catch (e) {}
        continue;
      }
      ensureHeaderAndStyle(s, HEADERS_104, "#1e3a8a");
      formatDataRows(s, HEADERS_104.length);
    }
  }
}
'''

# =========================================================================
# 試算表 ②【講師分潤結算表】專用 Google Apps Script 程式碼 (分頁：侯玉彤、簡志峰)
# =========================================================================
GAS_TEACHER_CODE = '''/**
 * =========================================================================
 * 【試算表 ②：講師分潤結算表】專用 Google Apps Script (含自動表頭與視覺美化)
 * =========================================================================
 * 適用分頁：侯玉彤、簡志峰 等講師分頁
 * 
 * 💡 貼心功能：
 * 1. 自動依授課講師姓名分流寫入所屬分頁。
 * 2. 若分頁已存在數據但「缺少表頭」，會自動在最頂端插入表頭，絕不覆蓋既有數據！
 * 3. 侯玉彤老師套用「高雅森林深綠 (#065f46)」，簡志峰老師套用「雅緻湖水墨綠 (#0f766e)」，連同分頁標籤一併上色！
 * 4. 凍結首行、加寬列高、自動調整欄寬。
 * 5. 隨時可在 Apps Script 上方選取「setupHeadersNow」點擊「執行」，立即一鍵美化現有表單！
 */

var TEACHER_HEADERS = [
  "結算期別", "授課講師", "課程名稱", "所屬平台",
  "平台撥入淨額", "製作費用扣除(攤提)", "結餘淨利",
  "講師分潤比率", "本期應付講師版稅", "備註說明", "寫入時間"
];

function doGet(e) {
  setupHeadersNow();
  var html = '<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; padding: 30px; line-height: 1.6; max-width: 580px; margin: 40px auto; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.06); background: white;">'
    + '<h2 style="color: #065f46; margin-top: 0; font-size: 1.3rem;">🎉 講師分潤結算表表頭已更新成功！</h2>'
    + '<p style="color: #334155; font-size: 14px;">已自動為所有講師分頁（侯玉彤、簡志峰等）建立專屬高雅綠色系表頭、凍結首行、欄寬自適應與標籤配色。</p>'
    + '<p style="color: #64748b; font-size: 13px; margin-bottom: 0;">💡 您現在可以切換回 Google 試算表直接查看套用結果。</p>'
    + '</div>';
  return HtmlService.createHtmlOutput(html).setTitle("講師結算表美化成功");
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.tryLock(10000);

  try {
    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var rows = data.rows || [];
    var processedSheets = {};

    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var teacherName = (r["授課講師"] || "").trim();
      if (!teacherName) {
        teacherName = "未指定講師";
      }

      // 取得或自動建立該講師專屬分頁
      var sheet = ss.getSheetByName(teacherName);
      if (!sheet) {
        var defaultSheet = ss.getSheetByName("工作表1") || ss.getSheetByName("Sheet1");
        if (defaultSheet && defaultSheet.getLastRow() === 0 && ss.getSheets().length === 1) {
          defaultSheet.setName(teacherName);
          sheet = defaultSheet;
        } else {
          sheet = ss.insertSheet(teacherName);
        }
      }

      // 確保目標講師分頁啟用
      try {
        ss.setActiveSheet(sheet);
      } catch (e) {}

      // 依講師指派專屬綠色系配色
      var themeColor = getTeacherColor(teacherName);

      // 確保表頭存在並進行高雅視覺美化
      ensureHeaderAndStyle(sheet, TEACHER_HEADERS, themeColor);

      // 寫入該講師的版稅明細
      sheet.appendRow([
        r["期別"] || "",
        teacherName,
        r["課程名稱"] || "",
        r["所屬平台"] || "",
        r["平台撥入淨額"] || 0,
        r["製作費用扣除(攤提)"] || 0,
        r["結餘淨利"] || 0,
        r["講師分潤比率"] || "50%",
        r["本期應付講師版稅"] || 0,
        r["備註"] || "",
        r["更新時間"] || Utilities.formatDate(new Date(), "Asia/Taipei", "yyyy-MM-dd HH:mm:ss")
      ]);

      formatDataRows(sheet, TEACHER_HEADERS.length);
      processedSheets[teacherName] = (processedSheets[teacherName] || 0) + 1;
    }

    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      details: processedSheets
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  } finally {
    lock.releaseLock();
  }
}

/**
 * 講師專屬色彩配置
 */
function getTeacherColor(teacherName) {
  if (teacherName.indexOf("侯玉彤") !== -1) {
    return "#065f46"; // 森林深綠 (侯玉彤老師)
  } else if (teacherName.indexOf("簡志峰") !== -1) {
    return "#0f766e"; // 雅緻藍綠 (簡志峰老師)
  }
  return "#134e4a";   // 深青墨綠 (其他老師)
}

/**
 * 確保表頭存在並套用配色
 */
function ensureHeaderAndStyle(sheet, headers, headerBgColor) {
  var lastRow = sheet.getLastRow();

  if (lastRow === 0) {
    // 全新空表：直接新增表頭
    sheet.appendRow(headers);
  } else {
    // 已有資料：檢查第一格是否為表頭文字
    var firstVal = String(sheet.getRange(1, 1).getValue()).trim();
    if (firstVal !== "結算期別" && firstVal !== "期別") {
      // 第一列是資料而非表頭，在最上方插入一列
      sheet.insertRowBefore(1);
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    } else {
      // 確保第一列文字完整
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    }
  }

  // 套用專業高質感表頭樣式
  var headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange.setBackground(headerBgColor)
             .setFontColor("#ffffff")
             .setFontWeight("bold")
             .setFontSize(10)
             .setHorizontalAlignment("center")
             .setVerticalAlignment("middle");

  sheet.setRowHeight(1, 38);       // 表頭高度加大
  sheet.setFrozenRows(1);          // 凍結首行
  try {
    sheet.setTabColor(headerBgColor); // 將下方分頁標籤同步上色
  } catch (e) {}

  // 自動調整欄寬
  for (var c = 1; c <= headers.length; c++) {
    sheet.autoResizeColumn(c);
  }
}

/**
 * 格式化數據列
 */
function formatDataRows(sheet, colCount) {
  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) return;

  sheet.getRange(2, 1, lastRow - 1, 1).setHorizontalAlignment("center");
  sheet.getRange(2, 2, lastRow - 1, 1).setHorizontalAlignment("center");
  sheet.getRange(2, 4, lastRow - 1, 1).setHorizontalAlignment("center");
  sheet.getRange(2, 8, lastRow - 1, 1).setHorizontalAlignment("center");
}

/**
 * 💡【手動一鍵美化現有工作表】
 * 可在 Apps Script 上方選取「setupHeadersNow」並點擊「執行」，立即一鍵為目前所有分頁加上表頭與顏色！
 */
function setupHeadersNow() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    var s = sheets[i];
    var name = s.getName();
    if ((name === "工作表1" || name.toUpperCase() === "SHEET1") && s.getLastRow() === 0 && sheets.length > 1) {
      try { ss.deleteSheet(s); } catch(e) {}
      continue;
    }
    var themeColor = getTeacherColor(name);
    ensureHeaderAndStyle(s, TEACHER_HEADERS, themeColor);
    formatDataRows(s, TEACHER_HEADERS.length);
  }
}
'''

# 相容通用版
GAS_TEMPLATE_CODE = GAS_PLATFORM_CODE


