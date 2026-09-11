# -*- coding: utf-8 -*-
"""
本機檔案選取輔助模組 (choose_file.py)
供 server.py 叫起 Windows 原生檔案總管選取視窗，置頂顯示於最上層。
"""
import sys
import os
import json
import tkinter as tk
from tkinter import filedialog

def choose_file(title="請選取 Excel 檔案", initial_dir=None):
    if not initial_dir or not os.path.exists(initial_dir):
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        initial_dir = desktop if os.path.exists(desktop) else os.path.dirname(os.path.abspath(__file__))

    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.attributes("-topmost", True)
    root.focus_force()

    file_path = filedialog.askopenfilename(
        parent=root,
        title=title,
        initialdir=initial_dir,
        filetypes=[
            ("Excel 活頁簿 (*.xlsx, *.xls)", "*.xlsx;*.xls"),
            ("所有檔案 (*.*)", "*.*")
        ]
    )
    root.destroy()

    if file_path:
        file_path = os.path.normpath(file_path)
        return {"selected": True, "path": file_path, "filename": os.path.basename(file_path)}
    else:
        return {"selected": False, "cancelled": True}

if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "請選取 Excel 檔案"
    d = sys.argv[2] if len(sys.argv) > 2 else None
    res = choose_file(title=t, initial_dir=d)
    # 輸出 UTF-8 JSON 結果
    sys.stdout.buffer.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
