# -*- coding: utf-8 -*-
"""
資料庫與設定管理模組 (db.py)
使用標準 SQLite 儲存平台、課程、講師、分潤規則與歷史對帳請款紀錄。
"""
import os
import sqlite3
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "royalty_system.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()

    # 1. 合作平台表 (A平台 104、B平台 Hahow、PPA 等)
    c.execute('''
    CREATE TABLE IF NOT EXISTS platforms (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        tax_id TEXT NOT NULL,
        revenue_type TEXT DEFAULT '版稅收入',
        item_name TEXT DEFAULT '線上課程訂閱',
        commission_rate REAL DEFAULT 0.80,
        due_cycle TEXT DEFAULT 'next_month_end',
        note TEXT
    )
    ''')

    # 2. 講師資料表
    c.execute('''
    CREATE TABLE IF NOT EXISTS teachers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT,
        bank_account TEXT,
        note TEXT
    )
    ''')

    # 3. 課程與分潤規則表
    c.execute('''
    CREATE TABLE IF NOT EXISTS courses (
        id TEXT PRIMARY KEY,
        course_name TEXT NOT NULL,
        platform_id TEXT NOT NULL,
        teacher_name TEXT NOT NULL,
        price REAL DEFAULT 0,
        teacher_share_rate REAL DEFAULT 0.50,
        production_cost REAL DEFAULT 0,
        deduction_type TEXT DEFAULT 'per_period',
        note TEXT,
        FOREIGN KEY (platform_id) REFERENCES platforms(id)
    )
    ''')

    # 4. 對帳紀錄表
    c.execute('''
    CREATE TABLE IF NOT EXISTS reconciliation_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT NOT NULL,
        platform_id TEXT NOT NULL,
        total_qty INTEGER DEFAULT 0,
        sales_gross REAL DEFAULT 0,
        sales_net REAL DEFAULT 0,
        split_rate REAL DEFAULT 0.8,
        supplier_gross REAL DEFAULT 0,
        supplier_net REAL DEFAULT 0,
        tax_amount REAL DEFAULT 0,
        status TEXT NOT NULL,
        diff_summary TEXT,
        details_json TEXT,
        created_at TEXT NOT NULL
    )
    ''')

    # 5. 發票請款單生成紀錄
    c.execute('''
    CREATE TABLE IF NOT EXISTS invoice_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT NOT NULL,
        platform_id TEXT NOT NULL,
        apply_date TEXT NOT NULL,
        title TEXT NOT NULL,
        tax_id TEXT NOT NULL,
        amount INTEGER NOT NULL,
        expected_deposit_date TEXT NOT NULL,
        file_path TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    ''')

    # 6. 講師分潤結算紀錄
    c.execute('''
    CREATE TABLE IF NOT EXISTS teacher_settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT NOT NULL,
        teacher_name TEXT NOT NULL,
        platform_id TEXT NOT NULL,
        course_name TEXT NOT NULL,
        price REAL DEFAULT 0,
        qty INTEGER DEFAULT 0,
        platform_net REAL DEFAULT 0,
        production_cost REAL DEFAULT 0,
        net_profit REAL DEFAULT 0,
        share_rate REAL DEFAULT 0.50,
        payable_amount REAL DEFAULT 0,
        excel_path TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    ''')

    # 預設預載資料 (若未初始化)
    c.execute('SELECT COUNT(*) FROM platforms')
    if c.fetchone()[0] == 0:
        platforms_seed = [
            ('104', '一零四資訊科技股份有限公司', '84598349', '版稅收入', '線上課程訂閱', 0.80, 'next_month_end', '104學習平台'),
            ('ppa', '瑞奧股份有限公司', '54225569', '版稅收入', '線上課程訂閱', 0.80, 'next_month_end', 'PressPlay Academy (金流2.25%、平台20%、行銷2:8分攤)')
        ]
        c.executemany('INSERT INTO platforms VALUES (?,?,?,?,?,?,?,?)', platforms_seed)

    c.execute('SELECT COUNT(*) FROM teachers')
    if c.fetchone()[0] == 0:
        teachers_seed = [
            ('hou', '侯玉彤', '', '', '數據分析顧問/講師'),
            ('chien', '簡志峰', '', '', 'AI應用顧問/講師')
        ]
        c.executemany('INSERT INTO teachers VALUES (?,?,?,?,?)', teachers_seed)

    c.execute('SELECT COUNT(*) FROM courses')
    if c.fetchone()[0] == 0:
        courses_seed = [
            ('c1', 'AIＸ數據分析術:從報表到洞察，全面升級你的職場決策力', '104', '侯玉彤', 1288, 0.50, 1069, 'per_period', '扣除平台服務費、課程製作相關費用'),
            ('c2', '生成式AI全解析:從概念到實戰落地應用', '104', '簡志峰', 1500, 0.50, 0, 'per_period', '扣除平台服務費')
        ]
        c.executemany('INSERT INTO courses VALUES (?,?,?,?,?,?,?,?,?)', courses_seed)

    conn.commit()
    conn.close()

# 取得所有設定資料
def get_all_configs():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM platforms')
    platforms = [dict(row) for row in c.fetchall()]
    c.execute('SELECT * FROM teachers')
    teachers = [dict(row) for row in c.fetchall()]
    c.execute('SELECT * FROM courses')
    courses = [dict(row) for row in c.fetchall()]
    conn.close()
    return {
        'platforms': platforms,
        'teachers': teachers,
        'courses': courses
    }

# 更新平台設定
def save_platform(platform_data):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
    INSERT INTO platforms (id, name, tax_id, revenue_type, item_name, commission_rate, due_cycle, note)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        name=excluded.name,
        tax_id=excluded.tax_id,
        revenue_type=excluded.revenue_type,
        item_name=excluded.item_name,
        commission_rate=excluded.commission_rate,
        due_cycle=excluded.due_cycle,
        note=excluded.note
    ''', (
        platform_data['id'],
        platform_data['name'],
        platform_data['tax_id'],
        platform_data.get('revenue_type', '版稅收入'),
        platform_data.get('item_name', '線上課程訂閱'),
        float(platform_data.get('commission_rate', 0.8)),
        platform_data.get('due_cycle', 'next_month_end'),
        platform_data.get('note', '')
    ))
    conn.commit()
    conn.close()

# 更新課程與分潤設定
def save_course(course_data):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
    INSERT INTO courses (id, course_name, platform_id, teacher_name, price, teacher_share_rate, production_cost, deduction_type, note)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        course_name=excluded.course_name,
        platform_id=excluded.platform_id,
        teacher_name=excluded.teacher_name,
        price=excluded.price,
        teacher_share_rate=excluded.teacher_share_rate,
        production_cost=excluded.production_cost,
        deduction_type=excluded.deduction_type,
        note=excluded.note
    ''', (
        course_data['id'],
        course_data['course_name'],
        course_data['platform_id'],
        course_data['teacher_name'],
        float(course_data.get('price', 0)),
        float(course_data.get('teacher_share_rate', 0.5)),
        float(course_data.get('production_cost', 0)),
        course_data.get('deduction_type', 'per_period'),
        course_data.get('note', '')
    ))
    conn.commit()
    conn.close()

# 刪除平台
def delete_platform(platform_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM platforms WHERE id = ?', (platform_id,))
    conn.commit()
    conn.close()

# 刪除課程
def delete_course(course_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM courses WHERE id = ?', (course_id,))
    conn.commit()
    conn.close()

# 儲存講師
def save_teacher(teacher_data):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
    INSERT INTO teachers (id, name, email, bank_account, note)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        name=excluded.name,
        email=excluded.email,
        bank_account=excluded.bank_account,
        note=excluded.note
    ''', (
        teacher_data['id'],
        teacher_data['name'],
        teacher_data.get('email', ''),
        teacher_data.get('bank_account', ''),
        teacher_data.get('note', '')
    ))
    conn.commit()
    conn.close()

# 取得歷史對帳紀錄
def get_history():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM reconciliation_records ORDER BY id DESC LIMIT 50')
    recons = [dict(row) for row in c.fetchall()]
    c.execute('SELECT * FROM invoice_requests ORDER BY id DESC LIMIT 50')
    invoices = [dict(row) for row in c.fetchall()]
    c.execute('SELECT * FROM teacher_settlements ORDER BY id DESC LIMIT 50')
    settlements = [dict(row) for row in c.fetchall()]
    conn.close()
    return {
        'reconciliations': recons,
        'invoices': invoices,
        'settlements': settlements
    }

# 刪除單筆歷史紀錄 (支援 invoice, settlement, reconciliation)
def delete_history_record(record_type, record_id):
    conn = get_connection()
    c = conn.cursor()
    deleted = False
    try:
        if record_type == 'invoice':
            c.execute('DELETE FROM invoice_requests WHERE id = ?', (record_id,))
        elif record_type == 'settlement':
            c.execute('DELETE FROM teacher_settlements WHERE id = ?', (record_id,))
        elif record_type == 'reconciliation':
            c.execute('DELETE FROM reconciliation_records WHERE id = ?', (record_id,))
        conn.commit()
        deleted = c.rowcount > 0
    finally:
        conn.close()
    return deleted

if __name__ == '__main__':
    init_db()
    print("Database initialized at:", DB_PATH)
