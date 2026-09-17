# -*- coding: utf-8 -*-
"""
平台版稅入帳定時自動檢查腳本 (check_reminders_cli.py)
由 Windows 工作排程器 (Task Scheduler) 每日自動定時靜默執行，
無需手動開啟網頁系統，若遇到「平台版稅入帳日前1天」即自動跳出 Windows 桌面通知提醒！
"""
import os
import sys
import datetime

# 加入專案目錄至模組搜尋路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.reminder import check_and_send_due_reminders, get_reminders_status

def run_auto_check():
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = os.path.join(BASE_DIR, "reminder_scheduler.log")
    
    try:
        # 取得目前入帳到期狀態
        status = get_reminders_status()
        sent = check_and_send_due_reminders(force=False)
        
        log_line = (
            f"[{now_str}] 自動排程檢查完成: "
            f"明日入帳={status['counts']['tomorrow']}筆, "
            f"今日到期={status['counts']['today']}筆, "
            f"7日內={status['counts']['upcoming']}筆, "
            f"本次自動發送通知數={sent}\n"
        )
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_line)
            
        print(log_line.strip())
        return sent
    except Exception as e:
        err_line = f"[{now_str}] 自動排程檢查異常: {e}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(err_line)
        print(err_line.strip(), file=sys.stderr)
        return 0

if __name__ == "__main__":
    run_auto_check()
