# -*- coding: utf-8 -*-
"""
入帳提醒與桌面通知模組 (reminder.py)
負責排程檢測《發票收據申請單》之預計入帳日，於「前1天」自動發送 Windows 桌面通知，
並提供 API 供前端網頁看板即時展示入帳倒數與核對狀態。
"""
import os
import sys
import time
import json
import base64
import datetime
import threading
import subprocess

# 加入專案根目錄至 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.db import get_connection

# 通知狀態記錄檔案
NOTIFIED_LOG_PATH = os.path.join(BASE_DIR, "notification_history.json")

def send_windows_notification(title, message):
    """
    透過 Windows 原生 NotifyIcon / 氣泡提示與系統通知發送桌面通知 (非阻塞)
    """
    def _run_notify():
        try:
            # 準備 PowerShell 腳本 (經 Base64 編碼，徹底避免字元編碼或特殊符號異常)
            ps_code = f"""
Add-Type -AssemblyName System.Windows.Forms
$balloon = New-Object System.Windows.Forms.NotifyIcon
$balloon.Icon = [System.Drawing.SystemIcons]::Information
$balloon.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
$balloon.BalloonTipTitle = '{title}'
$balloon.BalloonTipText = '{message}'
$balloon.Visible = $true
$balloon.ShowBalloonTip(7000)
Start-Sleep -Seconds 2
$balloon.Dispose()
"""
            encoded = base64.b64encode(ps_code.encode('utf-16le')).decode('utf-8')
            subprocess.run(
                ['powershell', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                capture_output=True,
                text=True,
                timeout=10
            )
        except Exception as e:
            print(f"[Reminder] 發送桌面通知失敗: {e}", file=sys.stderr)

    t = threading.Thread(target=_run_notify, daemon=True)
    t.start()

def parse_deposit_date_to_ad(date_str):
    """將民國年或西元年字串解析為 datetime.date 物件"""
    if not date_str:
        return None
    s = str(date_str).replace("(預計)", "").strip()
    import re
    # 民國格式 115年01月05日
    m_roc = re.match(r'(\d{2,3})[年/-](\d{1,2})[月/-](\d{1,2})', s)
    if m_roc:
        y, m, d = int(m_roc.group(1)), int(m_roc.group(2)), int(m_roc.group(3))
        ad_y = y + 1911 if y < 1900 else y
        try:
            return datetime.date(ad_y, m, d)
        except ValueError:
            return None
    # 西元格式 2026-01-05
    m_ad = re.match(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', s)
    if m_ad:
        y, m, d = int(m_ad.group(1)), int(m_ad.group(2)), int(m_ad.group(3))
        try:
            return datetime.date(y, m, d)
        except ValueError:
            return None
    return None

def load_notified_history():
    """載入已發送過通知的紀錄，避免同天重複轟炸"""
    if os.path.exists(NOTIFIED_LOG_PATH):
        try:
            with open(NOTIFIED_LOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_notified_history(history):
    try:
        with open(NOTIFIED_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Reminder] 儲存通知紀錄失敗: {e}", file=sys.stderr)

def get_reminders_status(today=None):
    """
    掃描資料庫中所有發票請款單，比對入帳日期與今天差距
    :return: dict (含 tomorrow, today, upcoming, overdue, all_items)
    """
    if today is None:
        today = datetime.date.today()

    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT id, period, platform_id, apply_date, title, tax_id, amount, expected_deposit_date, file_path, created_at,
               is_deposited, deposited_date, deposited_at, deposited_note
        FROM invoice_requests
        ORDER BY id DESC
    ''')
    rows = c.fetchall()
    conn.close()

    tomorrow_list = []
    today_list = []
    upcoming_list = []
    later_list = []
    overdue_list = []
    deposited_list = []
    all_items = []

    for r in rows:
        item = dict(r)
        is_dep = bool(item.get("is_deposited"))
        item["is_deposited"] = 1 if is_dep else 0

        dep_str = item.get("expected_deposit_date", "")
        dep_date = parse_deposit_date_to_ad(dep_str)

        if dep_date:
            item["deposit_date_ad"] = dep_date.strftime("%Y-%m-%d")
            diff = (dep_date - today).days
            item["diff_days"] = diff
        else:
            item["diff_days"] = None
            item["deposit_date_ad"] = None

        if is_dep:
            item["status"] = "deposited"
            item["status_text"] = f"款項已入帳 ({item.get('deposited_date') or '已確認'})"
            item["status_badge"] = "badge-success"
            deposited_list.append(item)
            all_items.append(item)
            continue

        if not dep_date:
            item["status"] = "unknown"
            item["status_text"] = "日期未知"
            item["status_badge"] = "badge-secondary"
            all_items.append(item)
            continue

        if diff == 1:
            item["status"] = "tomorrow"
            item["status_text"] = "🔔 明日入帳！"
            item["status_badge"] = "badge-warning"
            tomorrow_list.append(item)
        elif diff == 0:
            item["status"] = "today"
            item["status_text"] = "💰 今日入帳！"
            item["status_badge"] = "badge-danger"
            today_list.append(item)
        elif 0 < diff <= 3:
            item["status"] = "upcoming"
            item["status_text"] = f"倒數 {diff} 天"
            item["status_badge"] = "badge-info"
            upcoming_list.append(item)
        elif diff > 3:
            item["status"] = "later"
            item["status_text"] = f"尚餘 {diff} 天"
            item["status_badge"] = "badge-secondary"
            later_list.append(item)
        else:
            item["status"] = "overdue"
            item["status_text"] = f"已到期 {abs(diff)} 天 (請核對帳戶)"
            item["status_badge"] = "badge-dark"
            overdue_list.append(item)

        all_items.append(item)

    return {
        "today_str": today.strftime("%Y-%m-%d"),
        "today_roc": f"{today.year - 1911}年{today.month:02d}月{today.day:02d}日",
        "counts": {
            "tomorrow": len(tomorrow_list),
            "today": len(today_list),
            "upcoming": len(upcoming_list),
            "overdue": len(overdue_list),
            "deposited": len(deposited_list),
            "total": len(all_items)
        },
        "tomorrow": tomorrow_list,
        "today": today_list,
        "upcoming": upcoming_list,
        "later": later_list,
        "overdue": overdue_list,
        "deposited": deposited_list,
        "all_items": all_items
    }

def check_and_send_due_reminders(force=False):
    """
    定時檢查並發送「前1天」入帳通知 (或今日入帳提醒)
    :param force: 若為 True 則強制發送 (不檢查當日重複)
    :return: 發送的通知數量
    """
    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")
    status = get_reminders_status(today)
    history = load_notified_history()

    sent_count = 0

    # 1. 優先處理「明日即將入帳 (前1天)」
    for item in status["tomorrow"]:
        record_key = f"{item['id']}_tomorrow_{today_str}"
        if force or record_key not in history:
            title = "【平台版稅入帳前1天提醒】"
            clean_dep = str(item['expected_deposit_date']).replace('(預計)', '').strip()
            msg = (
                f"明日（{clean_dep}）為【{item['title']}】平台版稅預計入帳日！\n"
                f"期別：{item['period']}，請款金額：NT$ {int(item['amount']):,}。\n"
                f"提醒您明日留意銀行帳戶平台撥款狀況。"
            )
            send_windows_notification(title, msg)
            history[record_key] = {
                "invoice_id": item['id'],
                "type": "tomorrow",
                "sent_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            sent_count += 1
            time.sleep(1)

    # 2. 處理「今日已到期入帳」
    for item in status["today"]:
        record_key = f"{item['id']}_today_{today_str}"
        if force or record_key not in history:
            title = "【平台版稅今日到期入帳提醒】"
            clean_dep = str(item['expected_deposit_date']).replace('(預計)', '').strip()
            msg = (
                f"今日（{clean_dep}）為【{item['title']}】平台版稅預計入帳日！\n"
                f"期別：{item['period']}，請款金額：NT$ {int(item['amount']):,}。\n"
                f"請核對公司銀行帳戶是否已收到款項。"
            )
            send_windows_notification(title, msg)
            history[record_key] = {
                "invoice_id": item['id'],
                "type": "today",
                "sent_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            sent_count += 1
            time.sleep(1)

    save_notified_history(history)
    return sent_count

class ReminderScheduler:
    """背景定時輪詢守護執行緒"""
    def __init__(self, interval_seconds=1800): # 預設每 30 分鐘檢查一次
        self.interval = interval_seconds
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print(f"[Reminder] 入帳提醒背景定時守護緒已啟動 (每 {self.interval // 60} 分鐘自動檢查)")

    def stop(self):
        self.running = False

    def _loop(self):
        # 啟動時先立即執行一次檢查
        time.sleep(5)
        try:
            check_and_send_due_reminders()
        except Exception as e:
            print(f"[Reminder] 啟動檢查異常: {e}", file=sys.stderr)

        while self.running:
            time.sleep(self.interval)
            try:
                check_and_send_due_reminders()
            except Exception as e:
                print(f"[Reminder] 週期檢查異常: {e}", file=sys.stderr)

# 全域排程單例
reminder_scheduler = ReminderScheduler()

if __name__ == "__main__":
    print("=== 測試入帳提醒模組 ===")
    stat = get_reminders_status()
    print(f"今日統計: {stat['counts']}")
    print("發送測試通知...")
    send_windows_notification("【測試通知】", "這是一則版稅入帳系統測試通知！")
    print("測試完成！")
