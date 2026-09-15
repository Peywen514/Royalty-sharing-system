# -*- coding: utf-8 -*-
"""
版稅銷售與請款結算系統 - 本地伺服器 (server.py)
採用 Python 內建 http.server，零依賴即可啟動，提供 REST API 與現代化前端介面。
"""
import os
import sys
import json
import urllib.parse
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from datetime import datetime

# 加入 core 模組搜尋路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.db import (
    init_db, get_connection, get_all_configs, 
    save_platform, delete_platform, save_course, delete_course, save_teacher, get_history,
    delete_history_record
)
from core.reconciler import Reconciler
from core.invoice_doc import InvoiceDocGenerator
from core.teacher_settlement import TeacherSettlement
from core.google_sheets import (
    get_sheets_config, save_sheets_config, sync_to_google_sheets, 
    GAS_TEMPLATE_CODE, GAS_PLATFORM_CODE, GAS_TEACHER_CODE
)
from core.ppa_calculator import calc_ppa_royalty

PORT = 8990
WEB_DIR = os.path.join(BASE_DIR, "web")

def open_native_file_dialog(title="請選取 Excel 檔案", initial_dir=None):
    """
    開啟 Windows 檔案總管原生選取視窗，支援桌面與任何資料夾，零延遲置頂彈出。
    """
    import subprocess
    import json
    
    script_path = os.path.join(BASE_DIR, "choose_file.py")
    cmd = [sys.executable, script_path, title]
    if initial_dir and os.path.exists(initial_dir):
        cmd.append(initial_dir)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=10
        )
        out = proc.stdout.decode('utf-8', errors='ignore').strip()
        if out:
            lines = [l.strip() for l in out.split('\n') if l.strip()]
            for l in reversed(lines):
                if l.startswith('{') and l.endswith('}'):
                    return json.loads(l)
    except Exception as e:
        return {"error": str(e)}

    return {"selected": False, "cancelled": True}

class RoyaltyHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, HEAD')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Range, Authorization')
        self.send_header('MS-Author-Via', 'DAV')
        self.send_header('DAV', '1, 2')
        self.send_header('Allow', 'GET, HEAD, OPTIONS, POST')
        self.end_headers()

    def do_HEAD(self):
        self._head_only = True
        try:
            self.do_GET()
        finally:
            self._head_only = False

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path == "/api/status":
            self._send_json({"status": "ok", "time": datetime.now().isoformat()})
            return
            
        elif path == "/api/configs":
            configs = get_all_configs()
            self._send_json(configs)
            return

        elif path == "/api/detect_files":
            files = []
            for f in os.listdir(BASE_DIR):
                full_path = os.path.join(BASE_DIR, f)
                if os.path.isfile(full_path):
                    ext = os.path.splitext(f)[1].lower()
                    if ext in [".xlsx", ".xls", ".docx"]:
                        files.append({
                            "name": f,
                            "path": full_path,
                            "size": os.path.getsize(full_path),
                            "ext": ext
                        })
            self._send_json({"files": files, "base_dir": BASE_DIR})
            return

        elif path == "/api/history":
            hist = get_history()
            self._send_json(hist)
            return

        elif path == "/api/google_sheets/config":
            cfg = get_sheets_config()
            cfg["gas_code"] = GAS_TEMPLATE_CODE
            cfg["gas_platform_code"] = GAS_PLATFORM_CODE
            cfg["gas_teacher_code"] = GAS_TEACHER_CODE
            self._send_json(cfg)
            return

        elif path.startswith("/docs/"):
            rel_path = urllib.parse.unquote(path[6:])
            target_file = os.path.normpath(os.path.join(BASE_DIR, rel_path))
            if not os.path.exists(target_file) or not os.path.isfile(target_file):
                self._send_json({"error": f"找不到指定文件: {os.path.basename(target_file)}"}, status=404)
                return
            try:
                fname = os.path.basename(target_file)
                encoded_fname = urllib.parse.quote(fname)
                with open(target_file, "rb") as f:
                    content = f.read()

                ext = os.path.splitext(fname)[1].lower()
                if ext == ".docx":
                    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                elif ext in [".xlsx", ".xls"]:
                    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                else:
                    mime = "application/octet-stream"

                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Content-Disposition', f'inline; filename="{encoded_fname}"; filename*=UTF-8\'\'{encoded_fname}')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS')
                self.send_header('MS-Author-Via', 'DAV')
                self.send_header('DAV', '1, 2')
                self.send_header('Allow', 'GET, HEAD, OPTIONS, POST')
                self.end_headers()
                if not getattr(self, "_head_only", False):
                    self.wfile.write(content)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        elif path == "/api/download":
            qs = urllib.parse.parse_qs(parsed.query)
            target_file = qs.get("file", [""])[0]
            if not target_file:
                self._send_json({"error": "未提供檔案參數"}, status=400)
                return
            if not os.path.isabs(target_file):
                target_file = os.path.join(BASE_DIR, target_file)
            target_file = os.path.normpath(target_file)
            
            if not os.path.exists(target_file) or not os.path.isfile(target_file):
                self._send_json({"error": f"找不到下載檔案: {target_file}"}, status=404)
                return
                
            try:
                fname = os.path.basename(target_file)
                encoded_fname = urllib.parse.quote(fname)
                with open(target_file, "rb") as f:
                    content = f.read()

                ext = os.path.splitext(fname)[1].lower()
                if ext == ".docx":
                    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                elif ext in [".xlsx", ".xls"]:
                    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                else:
                    mime = "application/octet-stream"
                
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Content-Disposition', f'attachment; filename="{encoded_fname}"; filename*=UTF-8\'\'{encoded_fname}')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        elif path == "/api/printers":
            default_printer = ""
            printers = []
            try:
                import win32print
                printers = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
                default_printer = win32print.GetDefaultPrinter()
            except Exception:
                pass
            self._send_json({
                "default_printer": default_printer,
                "printers": printers
            })
            return

        # 預設處理靜態檔案
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        content_len = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_len) if content_len > 0 else b'{}'
        
        try:
            req_data = json.loads(post_body.decode('utf-8'))
        except Exception:
            req_data = {}

        if path == "/api/reconcile":
            user_file = req_data.get("user_file")
            plat_file = req_data.get("platform_file")
            
            if not user_file or not os.path.exists(user_file):
                self._send_json({"error": f"找不到自填表單: {user_file}"}, status=400)
                return
            if not plat_file or not os.path.exists(plat_file):
                self._send_json({"error": f"找不到平台對帳單: {plat_file}"}, status=400)
                return

            try:
                platform_id = req_data.get("platform_id")
                rec = Reconciler()
                res = rec.reconcile(user_file, plat_file, platform_id=platform_id)
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        elif path == "/api/import":
            period = req_data.get("period", "115年8月")
            platform_id = req_data.get("platform_id", "104")
            audit_result = req_data.get("audit_result", {})
            u_sum = audit_result.get("user_data", {}).get("summary", {})
            p_sum = audit_result.get("platform_data", {}).get("summary", {})
            
            conn = get_connection()
            c = conn.cursor()
            c.execute('''
            INSERT INTO reconciliation_records (
                period, platform_id, total_qty, sales_gross, sales_net, split_rate,
                supplier_gross, supplier_net, tax_amount, status, diff_summary, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                period,
                platform_id,
                u_sum.get("total_qty", 0),
                u_sum.get("total_sales", 0),
                p_sum.get("total_sales_untaxed", 0),
                p_sum.get("avg_split_rate", 0.8),
                u_sum.get("total_gross", 0),
                u_sum.get("total_net", 0),
                u_sum.get("total_tax", 0),
                audit_result.get("status", "MATCHED"),
                audit_result.get("status_text", ""),
                json.dumps(audit_result, ensure_ascii=False),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            conn.close()
            self._send_json({"success": True, "message": "已成功匯入系統資料庫"})
            return

        elif path == "/api/generate_invoice":
            title = req_data.get("title", "一零四資訊科技股份有限公司")
            tax_id = req_data.get("tax_id", "84598349")
            amount = req_data.get("amount", 1030)
            roc_year = int(req_data.get("roc_year", 115))
            month = int(req_data.get("month", 8))
            apply_date = req_data.get("apply_date")
            expected_deposit = req_data.get("expected_deposit_date")
            platform_id = req_data.get("platform_id", "104")
            item_name = req_data.get("item_name")
            
            try:
                gen = InvoiceDocGenerator()
                if apply_date:
                    parsed_apply, _, _, _ = gen.parse_roc_date(apply_date)
                    apply_date = parsed_apply or apply_date
                else:
                    apply_date = gen.calc_apply_date(roc_year, month)

                if not expected_deposit:
                    expected_deposit = gen.calc_deposit_date_from_apply_date(apply_date, roc_year, month)

                save_path = gen.generate(
                    title=title,
                    tax_id=tax_id,
                    amount=amount,
                    period_roc_year=roc_year,
                    period_month=month,
                    apply_date=apply_date,
                    expected_deposit_date=expected_deposit,
                    item_name=item_name
                )
                
                # 記錄到 DB
                conn = get_connection()
                c = conn.cursor()
                period_str = f"{roc_year}年{month}月"
                c.execute('''
                INSERT INTO invoice_requests (period, platform_id, apply_date, title, tax_id, amount, expected_deposit_date, file_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    period_str, platform_id,
                    apply_date,
                    title, tax_id, int(amount),
                    expected_deposit,
                    save_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                conn.commit()
                conn.close()

                self._send_json({
                    "success": True,
                    "file_path": save_path,
                    "filename": os.path.basename(save_path),
                    "dir": os.path.dirname(save_path)
                })
            except Exception as e:
                err_msg = str(e)
                if "Permission denied" in err_msg or "Errno 13" in err_msg:
                    err_msg = "檔案儲存失敗：請先關閉電腦中已開啟的 Word《發票請款申請單》檔案，然後再點擊產出！"
                self._send_json({"error": err_msg}, status=500)
            return

        elif path == "/api/settle_teacher":
            period_str = req_data.get("period", "115年8月")
            items = req_data.get("items", [])
            platform_name = req_data.get("platform_name", "104平台")
            platform_id = req_data.get("platform_id", "104")
            
            try:
                configs = get_all_configs()
                settler = TeacherSettlement()
                results = settler.calculate_royalty(items, course_configs=configs["courses"])
                
                generated_files = []
                conn = get_connection()
                c = conn.cursor()

                for t_name, t_items in results.items():
                    excel_path = settler.generate_excel(
                        teacher_name=t_name,
                        period_str=period_str,
                        teacher_items=t_items,
                        platform_name=platform_name
                    )
                    generated_files.append({
                        "teacher_name": t_name,
                        "file_path": excel_path,
                        "filename": os.path.basename(excel_path),
                        "items": t_items
                    })
                    
                    for it in t_items:
                        c.execute('''
                        INSERT INTO teacher_settlements (
                            period, teacher_name, platform_id, course_name, price, qty, platform_net,
                            production_cost, net_profit, share_rate, payable_amount, excel_path, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            period_str, t_name, platform_id, it["course_name"],
                            it["price"], it["qty"], it["platform_net"], it["production_cost"],
                            it["net_profit"], it["share_rate"], it["payable"], excel_path,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        ))
                
                conn.commit()
                conn.close()

                self._send_json({
                    "success": True,
                    "teachers": generated_files
                })
            except Exception as e:
                err_msg = str(e)
                if "Permission denied" in err_msg or "Errno 13" in err_msg:
                    err_msg = "檔案儲存失敗：請先關閉電腦中已開啟的 Excel 講師分潤明細檔案，然後再點擊結算！"
                self._send_json({"error": err_msg}, status=500)
            return

        elif path == "/api/batch_run":
            # 一鍵全自動月結流程
            user_file = req_data.get("user_file")
            plat_file = req_data.get("platform_file")
            roc_year = int(req_data.get("roc_year", 115))
            month = int(req_data.get("month", 8))
            period_str = f"{roc_year}年{month}月"
            platform_id = req_data.get("platform_id", "104")
            
            try:
                # 1. 對帳
                rec = Reconciler()
                audit_res = rec.reconcile(user_file, plat_file, platform_id=platform_id)
                
                # 2. 取得平台資訊
                configs = get_all_configs()
                plat_info = next((p for p in configs["platforms"] if p["id"] == platform_id), None)
                if not plat_info:
                    plat_info = {"name": "一零四資訊科技股份有限公司", "tax_id": "84598349"}
                
                final_amt = audit_res["final_invoice_amount"]
                user_meta = audit_res.get("user_data", {}).get("meta", {})
                apply_date = user_meta.get("apply_date")
                expected_deposit = user_meta.get("expected_deposit_date")

                # 3. 產出發票申請單
                inv_gen = InvoiceDocGenerator()
                if apply_date:
                    parsed_apply, _, _, _ = inv_gen.parse_roc_date(apply_date)
                    apply_date = parsed_apply or apply_date
                else:
                    apply_date = inv_gen.calc_apply_date(roc_year, month)

                if not expected_deposit:
                    expected_deposit = inv_gen.calc_deposit_date_from_apply_date(apply_date, roc_year, month)

                inv_path = inv_gen.generate(
                    title=plat_info["name"],
                    tax_id=plat_info["tax_id"],
                    amount=final_amt,
                    period_roc_year=roc_year,
                    period_month=month,
                    apply_date=apply_date,
                    expected_deposit_date=expected_deposit
                )

                # 4. 結算講師分潤並匯出 Excel
                items = audit_res["user_data"]["items"]
                settler = TeacherSettlement()
                t_results = settler.calculate_royalty(items, course_configs=configs["courses"])
                teacher_files = []
                for t_name, t_items in t_results.items():
                    p_name = "104平台" if platform_id == "104" else (plat_info.get("name") or "平台")
                    t_path = settler.generate_excel(t_name, period_str, t_items, p_name)
                    teacher_files.append({"teacher": t_name, "path": t_path})

                # 5. 寫入 DB
                conn = get_connection()
                c = conn.cursor()
                u_sum = audit_res["user_data"]["summary"]
                p_sum = audit_res["platform_data"]["summary"]
                c.execute('''
                INSERT INTO reconciliation_records (
                    period, platform_id, total_qty, sales_gross, sales_net, split_rate,
                    supplier_gross, supplier_net, tax_amount, status, diff_summary, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    period_str, platform_id, u_sum["total_qty"], u_sum["total_sales"],
                    p_sum["total_sales_untaxed"], p_sum["avg_split_rate"], u_sum["total_gross"],
                    u_sum["total_net"], u_sum["total_tax"], audit_res["status"],
                    audit_res["status_text"], json.dumps(audit_res, ensure_ascii=False),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                c.execute('''
                INSERT INTO invoice_requests (period, platform_id, apply_date, title, tax_id, amount, expected_deposit_date, file_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    period_str, platform_id, apply_date,
                    plat_info["name"], plat_info["tax_id"], final_amt,
                    expected_deposit, inv_path,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                conn.commit()
                conn.close()

                self._send_json({
                    "success": True,
                    "audit": audit_res,
                    "invoice_file": inv_path,
                    "teacher_files": teacher_files,
                    "output_dir": os.path.join(BASE_DIR, period_str)
                })
            except Exception as e:
                err_msg = str(e)
                if "Permission denied" in err_msg or "Errno 13" in err_msg:
                    err_msg = (
                        "檔案儲存失敗（檔案已被開啟佔用）：\n\n"
                        "系統偵測到該月份的 Word 請款單或 Excel 結算表檔案目前正被 Microsoft Office 開啟鎖定中。\n\n"
                        "👉 解決方法：請先將已開啟的 Word 或 Excel 檔案存檔並關閉，然後再點擊一次「🌟 一鍵全自動月結」即可順利完成！"
                    )
                self._send_json({"error": err_msg}, status=500)
            return

        elif path == "/api/open_folder" or path == "/api/open_file":
            import subprocess
            target = req_data.get("folder_path") or req_data.get("path") or BASE_DIR
            action = req_data.get("action", "auto") # "open_file", "select_in_folder", "open_folder", "auto"
            
            if not os.path.isabs(target):
                target = os.path.join(BASE_DIR, target)
            target = os.path.normpath(target)
            
            try:
                if action == "select_in_folder" or (action == "open_folder" and os.path.isfile(target)):
                    # 在檔案總管開啟資料夾並反白選取該檔案
                    if os.path.exists(target):
                        subprocess.Popen(['explorer.exe', f'/select,{target}'])
                        self._send_json({"success": True, "message": f"已在檔案總管開啟並選取：{os.path.basename(target)}"})
                    elif os.path.exists(os.path.dirname(target)):
                        try:
                            os.startfile(os.path.dirname(target))
                        except Exception:
                            subprocess.Popen(['explorer.exe', os.path.dirname(target)])
                        self._send_json({"success": True, "message": f"已開啟資料夾：{os.path.dirname(target)}"})
                    else:
                        self._send_json({"error": f"找不到指定路徑: {target}"}, status=404)
                    return
                
                elif action == "open_file" or (action == "auto" and os.path.isfile(target)):
                    # 使用預設軟體開啟檔案 (Word / Excel 等)
                    if not os.path.exists(target):
                        self._send_json({"error": f"檔案尚未產出或不存在: {os.path.basename(target)}"}, status=404)
                        return
                    
                    opened = False
                    # 1. 寫入專屬本機啟動腳本 open_doc.bat 並透過互動工作階段觸發
                    try:
                        bat_path = os.path.join(BASE_DIR, "open_doc.bat")
                        with open(bat_path, "w", encoding="utf-8") as bf:
                            bf.write(f'@echo off\r\nchcp 65001 >nul\r\nstart "" "{target}"\r\n')
                        subprocess.run(['schtasks', '/run', '/tn', 'RoyaltySystemOpenDoc'], capture_output=True, timeout=3)
                        opened = True
                    except Exception:
                        pass

                    # 2. 系統原生 startfile 管道
                    try:
                        os.startfile(target)
                        opened = True
                    except Exception as e_start:
                        pass
                    
                    # 3. 同時呼叫 Windows 檔案總管選取該檔案，確保前台 100% 立即跳出視窗
                    try:
                        subprocess.Popen(['explorer.exe', f'/select,{target}'])
                    except Exception:
                        pass

                    self._send_json({"success": True, "message": f"已在電腦呼叫開啟並在資料夾選取：{os.path.basename(target)}"})
                    return
                
                else:
                    # 開啟資料夾 (open_folder)
                    if not os.path.exists(target):
                        os.makedirs(target, exist_ok=True)
                    
                    try:
                        os.startfile(target)
                    except Exception:
                        subprocess.Popen(['explorer.exe', target])
                    self._send_json({"success": True, "message": f"已在檔案總管開啟資料夾：{os.path.basename(target)}"})
                    return
            except Exception as e:
                self._send_json({"error": f"開啟操作失敗: {str(e)}"}, status=500)
            return

        elif path == "/api/platform/save":
            try:
                save_platform(req_data)
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        elif path == "/api/platform/delete":
            try:
                delete_platform(req_data.get("id"))
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        elif path == "/api/course/save":
            try:
                save_course(req_data)
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        elif path == "/api/course/delete":
            try:
                delete_course(req_data.get("id"))
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        elif path == "/api/teacher/save":
            try:
                save_teacher(req_data)
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        elif path == "/api/google_sheets/config":
            try:
                save_sheets_config(req_data)
                self._send_json({"success": True, "message": "Google Sheets 連線設定已儲存"})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        elif path == "/api/google_sheets/sync":
            try:
                period = req_data.get("period", "115年8月")
                platform_id = req_data.get("platform_id", "104")
                platform_name = req_data.get("platform_name", "104平台")
                items = req_data.get("items", [])
                summary = req_data.get("summary", {})
                invoice_info = req_data.get("invoice_info")
                teacher_settlements = req_data.get("teacher_settlements")
                ppa_details = req_data.get("ppa_details")
                
                # 自動計算講師分潤供講師總表同步
                if not teacher_settlements and items:
                    configs = get_all_configs()
                    settler = TeacherSettlement()
                    teacher_settlements = settler.calculate_royalty(items, course_configs=configs["courses"])

                res = sync_to_google_sheets(
                    period=period,
                    platform_id=platform_id,
                    platform_name=platform_name,
                    items=items,
                    summary=summary,
                    invoice_info=invoice_info,
                    teacher_settlements=teacher_settlements,
                    ppa_details=ppa_details
                )
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return
        elif path == "/api/ppa/calculate":
            try:
                gross = float(req_data.get("gross", 0))
                marketing = float(req_data.get("marketing", 0))
                res = calc_ppa_royalty(gross, marketing)
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        elif path == "/api/print_doc_data":
            file_path = req_data.get("file_path", "")
            doc_type = req_data.get("doc_type", "")
            doc_id = req_data.get("id")

            # 1. 若有提供 file_path 且存在
            if file_path and os.path.exists(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                if ext == ".docx":
                    try:
                        import docx
                        doc = docx.Document(file_path)
                        t0, t1, t2 = doc.tables[0], doc.tables[1], doc.tables[2]
                        tax_id_text = t1.rows[1].cells[2].text.strip()
                        clean_tax_id = tax_id_text.split("：")[-1].strip() if "：" in tax_id_text else tax_id_text
                        self._send_json({
                            "success": True,
                            "type": "invoice",
                            "file_path": file_path,
                            "dept": t0.rows[0].cells[1].text.strip(),
                            "apply_date": t0.rows[0].cells[3].text.strip(),
                            "title": t1.rows[0].cells[1].text.strip(),
                            "amount": t1.rows[0].cells[7].text.strip(),
                            "tax_id": clean_tax_id,
                            "item_name": t1.rows[6].cells[1].text.replace("(請詳填品名)", "").strip(),
                            "expected_deposit_date": t2.rows[5].cells[1].text.strip()
                        })
                        return
                    except Exception as e:
                        self._send_json({"error": f"解析 Word 請款單失敗: {str(e)}"}, status=500)
                        return
                elif ext in [".xlsx", ".xls"]:
                    try:
                        import openpyxl
                        wb = openpyxl.load_workbook(file_path, data_only=True)
                        ws = wb.active
                        t_header = ws['A1'].value or ''
                        teacher_name = str(t_header).replace("講師 ：", "").replace("講師:", "").replace("講師", "").strip()
                        period_str = ws['J3'].value or ''
                        items = []
                        for r in range(6, ws.max_row + 1):
                            if ws.cell(r, 1).value is not None and str(ws.cell(r, 1).value).strip() != "":
                                items.append({
                                    "no": ws.cell(r, 1).value,
                                    "course_name": ws.cell(r, 2).value or "",
                                    "price": ws.cell(r, 3).value or 0,
                                    "qty": ws.cell(r, 4).value or 0,
                                    "platform_net": ws.cell(r, 5).value or 0,
                                    "production_cost": ws.cell(r, 6).value or 0,
                                    "net_profit": ws.cell(r, 7).value or 0,
                                    "share_rate_str": str(ws.cell(r, 8).value or "50%"),
                                    "payable": ws.cell(r, 9).value or 0,
                                    "note": ws.cell(r, 10).value or ""
                                })
                        self._send_json({
                            "success": True,
                            "type": "settlement",
                            "file_path": file_path,
                            "teacher_name": teacher_name,
                            "period": str(period_str),
                            "items": items
                        })
                        return
                    except Exception as e:
                        self._send_json({"error": f"解析 Excel 表單失敗: {str(e)}"}, status=500)
                        return

            # 2. 若無實體檔案或提供 DB ID 查詢
            if doc_type == "invoice" and doc_id:
                conn = get_connection()
                c = conn.cursor()
                c.execute('SELECT * FROM invoice_requests WHERE id = ?', (doc_id,))
                row = c.fetchone()
                conn.close()
                if row:
                    r = dict(row)
                    self._send_json({
                        "success": True,
                        "type": "invoice",
                        "file_path": r.get("file_path", ""),
                        "dept": "綜合推廣中心",
                        "apply_date": r.get("apply_date", ""),
                        "title": r.get("title", ""),
                        "amount": f"NT${int(r.get('amount', 0)):,}",
                        "tax_id": r.get("tax_id", ""),
                        "item_name": "線上課程訂閱",
                        "expected_deposit_date": r.get("expected_deposit_date", ""),
                        "period": r.get("period", "")
                    })
                    return

            if doc_type == "settlement" and doc_id:
                conn = get_connection()
                c = conn.cursor()
                c.execute('SELECT * FROM teacher_settlements WHERE id = ?', (doc_id,))
                row = c.fetchone()
                if row:
                    r = dict(row)
                    c.execute('SELECT * FROM teacher_settlements WHERE period = ? AND teacher_name = ?', (r["period"], r["teacher_name"]))
                    rows = [dict(x) for x in c.fetchall()]
                    conn.close()
                    items = []
                    for idx, x in enumerate(rows, 1):
                        items.append({
                            "no": idx,
                            "course_name": x["course_name"],
                            "price": x["price"],
                            "qty": x["qty"],
                            "platform_net": x["platform_net"],
                            "production_cost": x["production_cost"],
                            "net_profit": x["net_profit"],
                            "share_rate_str": f"{int(x['share_rate']*100)}%",
                            "payable": x["payable_amount"],
                            "note": ""
                        })
                    self._send_json({
                        "success": True,
                        "type": "settlement",
                        "file_path": r.get("excel_path", ""),
                        "teacher_name": r.get("teacher_name", ""),
                        "period": r.get("period", ""),
                        "items": items
                    })
                    return
                conn.close()

            self._send_json({"error": "找不到指定的文件資料"}, status=404)
            return

        elif path == "/api/system_print":
            file_path = req_data.get("file_path")
            action = req_data.get("action", "open")
            if not file_path or not os.path.exists(file_path):
                self._send_json({"error": f"檔案不存在: {file_path}"}, status=400)
                return
            try:
                if action == "print":
                    os.startfile(file_path, "print")
                else:
                    os.startfile(file_path)
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
                return

        elif path == "/api/choose_file":
            title = req_data.get("title", "請選取 Excel 檔案 (自填明細或對帳單)")
            initial_dir = req_data.get("initial_dir")
            res = open_native_file_dialog(title=title, initial_dir=initial_dir)
            self._send_json(res)
            return

        elif path == "/api/upload_file":
            try:
                import base64
                filename = req_data.get("filename", "uploaded_file.xlsx")
                b64_content = req_data.get("content", "")
                safe_name = os.path.basename(filename)
                save_dir = os.path.join(BASE_DIR, "uploads")
                os.makedirs(save_dir, exist_ok=True)
                save_path = os.path.join(save_dir, safe_name)
                with open(save_path, "wb") as f:
                    f.write(base64.b64decode(b64_content))
                self._send_json({
                    "success": True,
                    "path": os.path.normpath(save_path),
                    "filename": safe_name
                })
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        elif path == "/api/history/delete":
            rec_type = req_data.get("type")
            rec_id = req_data.get("id")
            if not rec_type or not rec_id:
                self._send_json({"error": "缺少 type 或 id 參數"}, status=400)
                return
            try:
                success = delete_history_record(rec_type, rec_id)
                if success:
                    self._send_json({"success": True, "message": "歷史紀錄已成功刪除"})
                else:
                    self._send_json({"error": "查無該筆紀錄或已刪除"}, status=404)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        self._send_json({"error": "Unknown API endpoint"}, status=404)

def run_server():
    init_db()
    url = f"http://127.0.0.1:{PORT}"
    try:
        server_address = ('', PORT)
        httpd = ThreadingHTTPServer(server_address, RoyaltyHandler)
    except OSError:
        print(f"==================================================")
        print(f" 線上課程版稅銷售與請款結算系統 已在背景運行中！")
        print(f" 本機網址: {url}")
        print(f" 已自動為您重新開啟瀏覽器介面。")
        print(f"==================================================")
        webbrowser.open(url)
        return

    print(f"==================================================")
    print(f" 線上課程版稅銷售與請款結算系統 已啟動")
    print(f" 本機網址: {url}")
    print(f" 資料庫: {os.path.join(BASE_DIR, 'royalty_system.db')}")
    print(f"==================================================")
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n系統已停止")
        httpd.server_close()

if __name__ == '__main__':
    run_server()
