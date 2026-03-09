from flask import Flask, render_template_string, request, redirect, url_for, flash, send_file, jsonify
import sqlite3
from datetime import datetime, timedelta
import csv
import os
import shutil
from pathlib import Path
import PyPDF2
import docx
import pandas as pd

app = Flask(__name__)
app.secret_key = "otic-blacklist-secret"
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Configuration
UPLOAD_FOLDER = 'uploads'
CLEAN_FOLDER = 'clean_cvs'
BLACKLISTED_FOLDER = 'blacklisted_cvs'
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt'}

# Create folders if they don't exist
for folder in [UPLOAD_FOLDER, CLEAN_FOLDER, BLACKLISTED_FOLDER]:
    os.makedirs(folder, exist_ok=True)

def init_db():
    conn = sqlite3.connect("blacklist.db")
    cursor = conn.cursor()
    
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='blacklist'")
    table_exists = cursor.fetchone()
    
    if not table_exists:
        # Create new table with all columns
        cursor.execute("""
        CREATE TABLE blacklist(
            id INTEGER PRIMARY KEY,
            name TEXT,
            phone TEXT,
            email TEXT,
            position TEXT,
            reason TEXT,
            date_added TEXT,
            added_by TEXT,
            notes TEXT,
            status TEXT DEFAULT 'active'
        )
        """)
        print("✅ Created new blacklist table")
    else:
        # Check if email column exists
        cursor.execute("PRAGMA table_info(blacklist)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Add missing columns if they don't exist
        if 'email' not in columns:
            cursor.execute("ALTER TABLE blacklist ADD COLUMN email TEXT")
            print("✅ Added email column")
        
        if 'notes' not in columns:
            cursor.execute("ALTER TABLE blacklist ADD COLUMN notes TEXT")
            print("✅ Added notes column")
        
        if 'status' not in columns:
            cursor.execute("ALTER TABLE blacklist ADD COLUMN status TEXT DEFAULT 'active'")
            print("✅ Added status column")
    
    # Create scan history table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scan_history(
        id INTEGER PRIMARY KEY,
        scan_date TEXT,
        folder_name TEXT,
        total_files INTEGER,
        clean_count INTEGER,
        blacklisted_count INTEGER,
        found_names TEXT
    )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Database ready")

init_db()

def extract_text_from_pdf(filepath):
    """Extract text from PDF file"""
    text = ""
    try:
        with open(filepath, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() or ""
    except Exception as e:
        print(f"Error reading PDF: {e}")
    return text.lower()

def extract_text_from_docx(filepath):
    """Extract text from DOCX file"""
    try:
        doc = docx.Document(filepath)
        return ' '.join([paragraph.text for paragraph in doc.paragraphs]).lower()
    except Exception as e:
        print(f"Error reading DOCX: {e}")
        return ""

def extract_text_from_txt(filepath):
    """Extract text from TXT file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            return file.read().lower()
    except:
        return ""

def search_name_in_file(filepath, blacklisted_names):
    """Search for blacklisted names in file content"""
    ext = os.path.splitext(filepath)[1].lower()
    
    if ext == '.pdf':
        text = extract_text_from_pdf(filepath)
    elif ext == '.docx':
        text = extract_text_from_docx(filepath)
    elif ext == '.txt':
        text = extract_text_from_txt(filepath)
    else:
        return None
    
    for name in blacklisted_names:
        if name and name.lower() in text:
            return name
    return None

def get_file_count():
    """Get total file counts in clean and blacklisted folders"""
    clean_files_count = 0
    blacklisted_files_count = 0
    
    if os.path.exists(CLEAN_FOLDER):
        for root, dirs, files in os.walk(CLEAN_FOLDER):
            clean_files_count += len(files)
    
    if os.path.exists(BLACKLISTED_FOLDER):
        for root, dirs, files in os.walk(BLACKLISTED_FOLDER):
            blacklisted_files_count += len(files)
    
    return clean_files_count, blacklisted_files_count

def get_folder_structure():
    """Get folder structure for clean and blacklisted CVs"""
    clean_folders = []
    blacklisted_folders = []
    
    # Get clean folders
    if os.path.exists(CLEAN_FOLDER):
        for item in os.listdir(CLEAN_FOLDER):
            item_path = os.path.join(CLEAN_FOLDER, item)
            if os.path.isdir(item_path):
                files = []
                for f in os.listdir(item_path):
                    file_path = os.path.join(item_path, f)
                    if os.path.isfile(file_path):
                        size = f"{os.path.getsize(file_path) / 1024:.1f} KB"
                        mtime = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M')
                        files.append({'name': f, 'size': size, 'date': mtime})
                clean_folders.append({
                    'name': item,
                    'files': files,
                    'count': len(files)
                })
    
    # Get blacklisted folders
    if os.path.exists(BLACKLISTED_FOLDER):
        for item in os.listdir(BLACKLISTED_FOLDER):
            item_path = os.path.join(BLACKLISTED_FOLDER, item)
            if os.path.isdir(item_path):
                files = []
                for f in os.listdir(item_path):
                    file_path = os.path.join(item_path, f)
                    if os.path.isfile(file_path):
                        size = f"{os.path.getsize(file_path) / 1024:.1f} KB"
                        mtime = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M')
                        files.append({
                            'name': f, 
                            'size': size, 
                            'date': mtime,
                            'matched_name': 'Unknown'
                        })
                blacklisted_folders.append({
                    'name': item,
                    'files': files,
                    'count': len(files)
                })
    
    return clean_folders, blacklisted_folders

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>OTIC CV Scanner - Blacklist Management System</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: #F5F7FA;
            min-height: 100vh;
            color: #1E293B;
        }

        /* Company Colors - Solid */
        :root {
            --primary: #02319A;
            --secondary: #FF0000;
            --primary-light: #1E4BB3;
            --primary-dark: #012078;
            --secondary-light: #FF3333;
            --secondary-dark: #CC0000;
            --background: #F5F7FA;
            --card-bg: #FFFFFF;
            --text-primary: #1E293B;
            --text-secondary: #64748B;
            --border: #E2E8F0;
            --success: #10B981;
            --warning: #F59E0B;
            --info: #3B82F6;
        }

        /* Main Layout */
        .app-wrapper {
            display: flex;
            min-height: 100vh;
        }

        /* Sidebar */
        .sidebar {
            width: 280px;
            background: var(--primary-dark);
            color: white;
            padding: 30px 0;
            position: fixed;
            height: 100vh;
            overflow-y: auto;
            box-shadow: 4px 0 20px rgba(2, 49, 154, 0.2);
        }

        .sidebar-header {
            padding: 0 24px 30px 24px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo-icon {
            width: 48px;
            height: 48px;
            background: white;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            color: var(--primary);
            box-shadow: 0 4px 10px rgba(0,0,0,0.2);
        }

        .logo-text {
            font-size: 22px;
            font-weight: 700;
            letter-spacing: 0.5px;
            color: white;
        }

        .nav-menu {
            padding: 30px 16px;
        }

        .nav-item {
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 14px 20px;
            margin: 4px 0;
            border-radius: 10px;
            color: rgba(255,255,255,0.7);
            font-size: 15px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }

        .nav-item i {
            width: 22px;
            font-size: 18px;
        }

        .nav-item:hover {
            background: rgba(255,255,255,0.1);
            color: white;
        }

        .nav-item.active {
    background: white;
    color: var(--primary);
    box-shadow: 0 4px 10px rgba(255, 255, 255, 0.2);
        }

        /* Main Content */
        .main-content {
            flex: 1;
            margin-left: 280px;
            padding: 30px;
        }

        /* Top Bar */
        .top-bar {
            background: var(--card-bg);
            border-radius: 12px;
            padding: 20px 30px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            border: 1px solid var(--border);
        }

        .page-title {
            font-size: 24px;
            font-weight: 700;
            color: var(--primary);
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .page-title i {
            color: var(--secondary);
            font-size: 28px;
        }

        .date-badge {
            background: var(--background);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            color: var(--primary);
            border: 1px solid var(--border);
        }

        /* Stats Cards */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 25px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            border: 1px solid var(--border);
            transition: all 0.2s;
        }

        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(2, 49, 154, 0.1);
            border-color: var(--primary);
        }

        .stat-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 20px;
        }

        .stat-icon {
            width: 56px;
            height: 56px;
            background: var(--primary);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 24px;
        }

        .stat-value {
            font-size: 42px;
            font-weight: 700;
            color: var(--primary);
            line-height: 1.2;
            margin-bottom: 5px;
        }

        .stat-label {
            color: var(--text-secondary);
            font-size: 14px;
            font-weight: 500;
        }

        /* Quick Actions */
        .quick-actions {
            display: flex;
            gap: 15px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }

        .action-btn {
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            border: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }

        .action-btn.primary {
            background: var(--primary);
            color: white;
        }

        .action-btn.primary:hover {
            background: var(--primary-dark);
        }

        .action-btn.secondary {
            background: white;
            color: var(--primary);
            border: 2px solid var(--primary);
        }

        .action-btn.secondary:hover {
            background: var(--primary);
            color: white;
        }

        .action-btn.success {
            background: var(--success);
            color: white;
        }

        .action-btn.success:hover {
            background: #0EA271;
        }

        .action-btn.warning {
            background: var(--warning);
            color: white;
        }

        /* Content Cards */
        .content-card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            border: 1px solid var(--border);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid var(--border);
        }

        .card-title {
            font-size: 18px;
            font-weight: 600;
            color: var(--primary);
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .card-title i {
            color: var(--secondary);
            font-size: 20px;
        }

        .card-badge {
            background: var(--background);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            color: var(--primary);
            border: 1px solid var(--border);
        }

        /* Search Bar */
        .search-bar {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }

        .search-input {
            flex: 1;
            padding: 12px 16px;
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 14px;
            transition: all 0.2s;
        }

        .search-input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(2, 49, 154, 0.1);
        }

        .search-btn {
            padding: 12px 24px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
        }

        /* Upload Area */
        .upload-area {
            border: 2px dashed var(--primary);
            border-radius: 12px;
            padding: 40px;
            text-align: center;
            background: rgba(2, 49, 154, 0.02);
            cursor: pointer;
            transition: all 0.2s;
            margin-bottom: 20px;
        }

        .upload-area:hover {
            border-color: var(--secondary);
            background: rgba(255, 0, 0, 0.02);
        }

        .upload-area i {
            font-size: 48px;
            color: var(--primary);
            margin-bottom: 15px;
        }

        .upload-area h3 {
            font-size: 20px;
            font-weight: 600;
            color: var(--primary);
            margin-bottom: 8px;
        }

        .upload-area p {
            color: var(--text-secondary);
            font-size: 14px;
        }

        /* Form Styles */
        .form-group {
            margin-bottom: 20px;
        }

        .form-label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: var(--primary);
            font-size: 14px;
        }

        .form-control {
            width: 100%;
            padding: 12px 16px;
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 14px;
            transition: all 0.2s;
            background: white;
            font-family: 'Inter', sans-serif;
        }

        .form-control:focus {
            outline: none;
            border-color: var(--secondary);
            box-shadow: 0 0 0 3px rgba(255, 0, 0, 0.1);
        }

        .input-group {
            display: flex;
            gap: 12px;
        }

        /* Tables */
        .table-container {
            background: white;
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid var(--border);
        }

        .table-header {
            padding: 20px 25px;
            background: var(--background);
            border-bottom: 2px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .table-wrapper {
            overflow-x: auto;
            max-height: 500px;
            overflow-y: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }

        th {
            background: var(--background);
            padding: 16px 20px;
            text-align: left;
            font-weight: 600;
            color: var(--primary);
            font-size: 13px;
            letter-spacing: 0.3px;
            text-transform: uppercase;
            border-bottom: 2px solid var(--border);
            position: sticky;
            top: 0;
            z-index: 10;
        }

        td {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border);
            color: var(--text-primary);
        }

        tr:hover td {
            background: var(--background);
        }

        /* Badges */
        .badge {
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .badge-primary {
            background: rgba(2, 49, 154, 0.1);
            color: var(--primary);
        }

        .badge-danger {
            background: rgba(255, 0, 0, 0.1);
            color: var(--secondary);
        }

        .badge-success {
            background: rgba(16, 185, 129, 0.1);
            color: var(--success);
        }

        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }

        .modal-content {
            background: white;
            width: 500px;
            max-width: 90%;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(2, 49, 154, 0.2);
            animation: slideUp 0.3s ease;
            border: 1px solid var(--border);
        }

        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
        }

        .modal-header h3 {
            font-size: 20px;
            font-weight: 700;
            color: var(--primary);
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .modal-header h3 i {
            color: var(--secondary);
        }

        .close-modal {
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: var(--text-secondary);
            transition: all 0.2s;
        }

        .close-modal:hover {
            color: var(--secondary);
        }

        .modal-footer {
            display: flex;
            gap: 15px;
            margin-top: 30px;
        }

        /* Folder Grid */
        .folders-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }

        .folder-card {
            background: white;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
            position: relative;
        }

        .folder-card:hover {
            border-color: var(--primary);
            box-shadow: 0 4px 12px rgba(2, 49, 154, 0.1);
        }

        .folder-card i {
            font-size: 40px;
            color: var(--primary);
            margin-bottom: 12px;
        }

        .folder-card h4 {
            font-size: 16px;
            font-weight: 600;
            color: var(--primary);
            margin-bottom: 8px;
        }

        .folder-card p {
            color: var(--text-secondary);
            font-size: 13px;
        }

        .folder-count {
            position: absolute;
            top: 10px;
            right: 10px;
            background: var(--primary);
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }

        /* Back Button */
        .back-btn {
            padding: 8px 16px;
            background: white;
            border: 1px solid var(--border);
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
            margin-bottom: 20px;
            color: var(--primary);
        }

        .back-btn:hover {
            background: var(--primary);
            color: white;
            border-color: var(--primary);
        }

        /* Flash Messages */
        .flash-message {
            padding: 14px 18px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
            animation: slideIn 0.3s;
            border-left: 4px solid;
        }

        .flash-success {
            background: rgba(16, 185, 129, 0.1);
            color: #065f46;
            border-left-color: var(--success);
        }

        .flash-error {
            background: rgba(255, 0, 0, 0.1);
            color: var(--secondary-dark);
            border-left-color: var(--secondary);
        }

        /* Loading Spinner */
        .loading {
            display: none;
            text-align: center;
            padding: 40px;
        }

        .spinner {
            width: 40px;
            height: 40px;
            border: 3px solid var(--border);
            border-top: 3px solid var(--secondary);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        /* Responsive */
        @media (max-width: 768px) {
            .sidebar {
                transform: translateX(-100%);
                position: fixed;
                z-index: 100;
                transition: transform 0.3s;
            }
            
            .sidebar.active {
                transform: translateX(0);
            }
            
            .main-content {
                margin-left: 0;
            }
        }
    </style>
</head>
<body>
    <div class="app-wrapper">
        <!-- Sidebar -->
        <div class="sidebar">
            <div class="sidebar-header">
    <div class="logo-area">
            <img src="/static/otic-logo.png" alt="OTIC" style="height: 40px; width: auto; display: block;">
         </div>
            </div>
            
            <div class="nav-menu">
                <div class="nav-item active" onclick="showPage('dashboard', this)">
                    <i class="fas fa-chart-pie"></i>
                    Dashboard
                </div>
                <div class="nav-item" onclick="showPage('scan', this)">
                    <i class="fas fa-search"></i>
                    Scan CVs
                </div>
                <div class="nav-item" onclick="showPage('blacklist', this)">
                    <i class="fas fa-ban"></i>
                    Blacklist
                </div>
                <div class="nav-item" onclick="window.location.href='/clean'">
                    <i class="fas fa-check-circle"></i>
                    Clean CVs
                </div>
                <div class="nav-item" onclick="window.location.href='/blacklisted-files'">
                    <i class="fas fa-exclamation-triangle"></i>
                    Blacklisted CVs
                </div>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="main-content">
            <!-- Top Bar -->
            <div class="top-bar">
                <div class="page-title">
                    <i class="fas fa-shield-alt"></i>
                    OTIC CV Screening System
                </div>
                <div class="date-badge">
                    <i class="far fa-calendar"></i>
                    {{ datetime.now().strftime('%B %d, %Y') }}
                </div>
            </div>
            
            <!-- Flash Messages -->
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="flash-message flash-{{ category }}">
                            <i class="fas {% if category == 'success' %}fa-check-circle{% else %}fa-exclamation-circle{% endif %}"></i>
                            {{ message }}
                        </div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            
            <!-- Dashboard Page -->
            <div id="page-dashboard" class="page active-page">
                <!-- Stats Grid -->
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-header">
                            <div class="stat-icon">
                                <i class="fas fa-user-slash"></i>
                            </div>
                        </div>
                        <div class="stat-value">{{ total }}</div>
                        <div class="stat-label">Blacklisted Names</div>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-header">
                            <div class="stat-icon">
                                <i class="fas fa-file-alt"></i>
                            </div>
                        </div>
                        <div class="stat-value">{{ clean_files_count }}</div>
                        <div class="stat-label">Clean CV Files</div>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-header">
                            <div class="stat-icon">
                                <i class="fas fa-file-excel"></i>
                            </div>
                        </div>
                        <div class="stat-value">{{ blacklisted_files_count }}</div>
                        <div class="stat-label">Blacklisted Files</div>
                    </div>
                </div>
                
                <!-- Quick Actions -->
                <div class="quick-actions">
                    <button class="action-btn primary" onclick="showAddModal()">
                        <i class="fas fa-plus"></i>
                        Add to Blacklist
                    </button>
                    <button class="action-btn secondary" onclick="showImportModal()">
                        <i class="fas fa-upload"></i>
                        Import Data
                    </button>
                    <button class="action-btn success" onclick="window.location.href='/export'">
                        <i class="fas fa-download"></i>
                        Export CSV
                    </button>
                </div>
                
                <!-- Search Bar -->
                <div class="search-bar">
                    <input type="text" id="searchInput" class="search-input" placeholder="Search blacklist by name, phone, or reason..." onkeyup="searchTable()">
                    <button class="search-btn" onclick="searchTable()">
                        <i class="fas fa-search"></i> Search
                    </button>
                </div>
                
                <!-- Recent Blacklisted Names -->
                <div class="content-card">
                    <div class="card-header">
                        <div class="card-title">
                            <i class="fas fa-history"></i>
                            Recent Blacklisted Names
                        </div>
                        <div class="card-badge">{{ total }} Total</div>
                    </div>
                    
                    <div class="table-container">
                        <div class="table-wrapper">
                            <table id="blacklistTable">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Phone</th>
                                        <th>Position</th>
                                        <th>Reason</th>
                                        <th>Date</th>                                    
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for row in rows[:10] %}
    <tr>
        <td><strong style="color: var(--primary);">{{ row[0] }}</strong></td>
        <td>{{ row[1] or '-' }}</td>
        <td>{{ row[3] or '-' }}</td>
        <td>
            <span class="badge badge-danger">
                <i class="fas fa-exclamation"></i>
                {{ row[4] }}
            </span>
        </td>
        <td>{{ row[5] }}</td>
        <td>
            <div style="display: flex; gap: 5px;">
                <form method="POST" action="/delete/{{ row[9] }}" style="display:inline;" onsubmit="return confirm('Delete this name from blacklist?')">
                    <button class="action-btn" style="padding: 6px 10px; background: rgba(255,0,0,0.1); color: var(--secondary); border: none; border-radius: 4px;">
                        <i class="fas fa-trash"></i>
                    </button>
                </form>
            </div>
        </td>
    </tr>
    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                
                <!-- Folders Overview -->
                <div class="content-card">
                    <div class="card-header">
                        <div class="card-title">
                            <i class="fas fa-folder"></i>
                            CV Folders
                        </div>
                    </div>
                    
                    <div class="folders-grid">
                        <div class="folder-card" onclick="window.location.href='/clean'">
                            <div class="folder-count">{{ clean_folders|length }}</div>
                            <i class="fas fa-folder-open"></i>
                            <h4>Clean CVs</h4>
                            <p>{{ clean_files_count }} files</p>
                        </div>
                        
                        <div class="folder-card" onclick="window.location.href='/blacklisted-files'">
                            <div class="folder-count">{{ blacklisted_folders|length }}</div>
                            <i class="fas fa-folder-open" style="color: var(--secondary);"></i>
                            <h4>Blacklisted CVs</h4>
                            <p>{{ blacklisted_files_count }} files</p>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Scan Page -->
            <div id="page-scan" class="page">
                <div class="content-card">
                    <div class="card-header">
                        <div class="card-title">
                            <i class="fas fa-cloud-upload-alt"></i>
                            Upload & Scan CV Folder
                        </div>
                    </div>
                    
                    <form method="POST" action="/scan" enctype="multipart/form-data" id="scanForm">
                        <div class="form-group">
                            <label class="form-label">
                                <i class="fas fa-folder"></i>
                                Folder Name
                            </label>
                            <div class="input-group">
                                <input type="text" name="folder_name" id="folderName" class="form-control" placeholder="e.g., Operations, Accounts, Marketing" required>
                            </div>
                        </div>
                        
                        <div class="upload-area" onclick="document.getElementById('folderInput').click()">
                            <i class="fas fa-cloud-upload-alt"></i>
                            <h3>Click to select folder</h3>
                            <p>Select a folder containing CV files (PDF, DOCX, DOC, TXT)</p>
                            <p style="font-size: 12px; margin-top: 10px; color: var(--text-secondary);">
                                <i class="fas fa-info-circle"></i> Max file size: 50MB
                            </p>
                        </div>
                        
                        <input type="file" name="folder" id="folderInput" webkitdirectory directory multiple style="display: none;" required>
                        
                        <button type="submit" class="action-btn primary" style="width: 100%; justify-content: center; margin-top: 20px;" onclick="return validateAndShowLoading()">
                            <i class="fas fa-search"></i>
                            Start Scanning
                        </button>
                    </form>
                    
                    <div id="loading" class="loading">
                        <div class="spinner"></div>
                        <p style="color: var(--text-secondary);">Scanning CVs... This may take a moment.</p>
                    </div>
                </div>
                
                {% if scan_results %}
                <div class="content-card">
                    <div class="card-header">
                        <div class="card-title">
                            <i class="fas fa-chart-bar"></i>
                            Scan Results: {{ scan_results.folder_name }}
                        </div>
                    </div>
                    
                    <div class="stats-grid" style="margin-bottom: 20px;">
                        <div class="stat-card">
                            <div class="stat-header">
                                <div class="stat-icon" style="background: var(--success);">
                                    <i class="fas fa-check"></i>
                                </div>
                            </div>
                            <div class="stat-value">{{ scan_results.clean }}</div>
                            <div class="stat-label">Clean CVs</div>
                        </div>
                        
                        <div class="stat-card">
                            <div class="stat-header">
                                <div class="stat-icon" style="background: var(--secondary);">
                                    <i class="fas fa-exclamation"></i>
                                </div>
                            </div>
                            <div class="stat-value">{{ scan_results.blacklisted }}</div>
                            <div class="stat-label">Blacklisted CVs</div>
                        </div>
                    </div>
                    
                    {% if scan_results.found_names %}
                    <div style="background: rgba(255,0,0,0.05); border-radius: 8px; padding: 20px; border: 1px solid rgba(255,0,0,0.2);">
                        <h4 style="color: var(--secondary); margin-bottom: 15px; display: flex; align-items: center; gap: 8px;">
                            <i class="fas fa-exclamation-triangle"></i>
                            Blacklisted Names Found
                        </h4>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                            {% for name in scan_results.found_names %}
                            <span style="background: white; padding: 6px 12px; border-radius: 4px; border: 1px solid rgba(255,0,0,0.3); color: var(--secondary); font-size: 13px; font-weight: 500;">
                                <i class="fas fa-user-slash" style="margin-right: 6px;"></i>
                                {{ name }}
                            </span>
                            {% endfor %}
                        </div>
                    </div>
                    {% endif %}
                </div>
                {% endif %}
            </div>
            
            <!-- Blacklist Management Page -->
            <div id="page-blacklist" class="page">
                <div class="content-card">
                    <div class="card-header">
                        <div class="card-title">
                            <i class="fas fa-ban"></i>
                            Blacklist Management
                        </div>
                        <div class="card-badge">{{ total }} Names</div>
                    </div>
                    
                    <div class="quick-actions" style="margin-bottom: 25px;">
                        <button class="action-btn primary" onclick="showAddModal()">
                            <i class="fas fa-plus"></i>
                            Add New
                        </button>
                        <button class="action-btn secondary" onclick="showImportModal()">
                            <i class="fas fa-upload"></i>
                            Import
                        </button>
                        <button class="action-btn success" onclick="window.location.href='/export'">
                            <i class="fas fa-download"></i>
                            Export
                        </button>
                    </div>
                    
                    <div class="search-bar">
                        <input type="text" id="blacklistSearch" class="search-input" placeholder="Search blacklist..." onkeyup="searchBlacklist()">
                    </div>
                    
                    <div class="table-container">
                        <div class="table-wrapper" style="max-height: 600px;">
                            <table id="fullBlacklistTable">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Phone</th>
                                        <th>Position</th>
                                        <th>Reason</th>
                                        <th>Date Added</th>
                                        <th>Status</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for row in rows %}
                                    <tr>
                                        <td><strong style="color: var(--primary);">{{ row[0] }}</strong></td>
                                        <td>{{ row[1] or '-' }}</td>
                                        <td>{{ row[3] or '-' }}</td>
                                        <td>
                                            <span class="badge badge-danger">
                                                <i class="fas fa-exclamation"></i>
                                                {{ row[4] }}
                                            </span>
                                        </td>
                                        <td>{{ row[5] }}</td>
                                        <td>
                                            <span class="badge badge-primary">
                                                <i class="fas fa-circle"></i>
                                                {{ row[8] }}
                                            </span>
                                        </td>
                                        <td>
                                            <div style="display: flex; gap: 5px;">
                                                <form method="POST" action="/delete/{{ row[9] }}" style="display:inline;" onsubmit="return confirm('Delete this name from blacklist?')">
                                                    <button class="action-btn" style="padding: 6px 10px; background: rgba(255,0,0,0.1); color: var(--secondary); border: none; border-radius: 4px;">
                                                        <i class="fas fa-trash"></i>
                                                    </button>
                                                </form>
                                            </div>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Clean CVs Page -->
            <div id="page-clean" class="page">
                <div class="content-card">
                    <div class="card-header">
                        <div class="card-title">
                            <i class="fas fa-check-circle" style="color: var(--success);"></i>
                            Clean CV Folders
                        </div>
                    </div>
                    
                    {% if current_clean_folder %}
                        <button class="back-btn" onclick="window.location.href='/clean'">
                            <i class="fas fa-arrow-left"></i>
                            Back to Folders
                        </button>
                        
                        <div class="table-container">
                            <div class="table-header">
                                <h4 style="display: flex; align-items: center; gap: 8px; color: var(--primary);">
                                    <i class="fas fa-folder-open" style="color: var(--success);"></i>
                                    {{ current_clean_folder }}
                                </h4>
                                <span class="badge badge-success">{{ current_clean_files|length }} files</span>
                            </div>
                            <div class="table-wrapper">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Filename</th>
                                            <th>Size</th>
                                            <th>Date Modified</th>
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {% for file in current_clean_files %}
                                        <tr>
                                            <td>
                                                <i class="fas fa-file-pdf" style="color: var(--secondary); margin-right: 8px;"></i>
                                                {{ file.name }}
                                            </td>
                                            <td>{{ file.size }}</td>
                                            <td>{{ file.date }}</td>
                                            <td>
                                                <a href="/files/clean/{{ current_clean_folder }}/{{ file.name }}" target="_blank">
                                                    <button class="action-btn" style="padding: 6px 12px; background: rgba(2,49,154,0.1); color: var(--primary); border: none; border-radius: 4px;">
                                                        <i class="fas fa-eye"></i> View
                                                    </button>
                                                </a>
                                            </td>
                                        </tr>
                                        {% endfor %}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    {% else %}
                        <div class="folders-grid">
                            {% for folder in clean_folders %}
                            <div class="folder-card" onclick="window.location.href='/clean?folder={{ folder.name }}'">
                                <div class="folder-count">{{ folder.count }}</div>
                                <i class="fas fa-folder"></i>
                                <h4>{{ folder.name }}</h4>
                                <p>{{ folder.count }} files</p>
                            </div>
                            {% endfor %}
                        </div>
                    {% endif %}
                </div>
            </div>
            
            <!-- Blacklisted Files Page -->
            <div id="page-blacklisted-files" class="page">
                <div class="content-card">
                    <div class="card-header">
                        <div class="card-title">
                            <i class="fas fa-exclamation-triangle" style="color: var(--secondary);"></i>
                            Blacklisted CV Folders
                        </div>
                    </div>
                    
                    {% if current_blacklisted_folder %}
                        <button class="back-btn" onclick="window.location.href='/blacklisted-files'">
                            <i class="fas fa-arrow-left"></i>
                            Back to Folders
                        </button>
                        
                        <div class="table-container">
                            <div class="table-header">
                                <h4 style="display: flex; align-items: center; gap: 8px; color: var(--primary);">
                                    <i class="fas fa-folder-open" style="color: var(--secondary);"></i>
                                    {{ current_blacklisted_folder }}
                                </h4>
                                <span class="badge badge-danger">{{ current_blacklisted_files|length }} files</span>
                            </div>
                            <div class="table-wrapper">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Filename</th>
                                            <th>Size</th>
                                            <th>Matched Name</th>
                                            <th>Date Modified</th>
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {% for file in current_blacklisted_files %}
                                        <tr>
                                            <td>
                                                <i class="fas fa-file-pdf" style="color: var(--secondary); margin-right: 8px;"></i>
                                                {{ file.name }}
                                            </td>
                                            <td>{{ file.size }}</td>
                                            <td>
                                                <span class="badge badge-danger">
                                                    <i class="fas fa-user-slash"></i>
                                                    {{ file.matched_name }}
                                                </span>
                                            </td>
                                            <td>{{ file.date }}</td>
                                            <td>
                                                <a href="/files/blacklisted/{{ current_blacklisted_folder }}/{{ file.name }}" target="_blank">
                                                    <button class="action-btn" style="padding: 6px 12px; background: rgba(255,0,0,0.1); color: var(--secondary); border: none; border-radius: 4px;">
                                                        <i class="fas fa-eye"></i> View
                                                    </button>
                                                </a>
                                            </td>
                                        </tr>
                                        {% endfor %}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    {% else %}
                        <div class="folders-grid">
                            {% for folder in blacklisted_folders %}
                            <div class="folder-card" onclick="window.location.href='/blacklisted-files?folder={{ folder.name }}'">
                                <div class="folder-count">{{ folder.count }}</div>
                                <i class="fas fa-folder" style="color: var(--secondary);"></i>
                                <h4>{{ folder.name }}</h4>
                                <p>{{ folder.count }} files</p>
                            </div>
                            {% endfor %}
                        </div>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>
    
    <!-- Add Modal -->
    <div id="addModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>
                    <i class="fas fa-plus-circle"></i>
                    Add to Blacklist
                </h3>
                <button class="close-modal" onclick="hideAddModal()">&times;</button>
            </div>
            
            <form method="POST" action="/add">
                <div class="form-group">
                    <label class="form-label">Full Name <span style="color: var(--secondary);">*</span></label>
                    <input type="text" name="name" class="form-control" placeholder="Enter full name" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Phone Number</label>
                    <input type="text" name="phone" class="form-control" placeholder="Enter phone number">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Position Applied For</label>
                    <input type="text" name="position" class="form-control" placeholder="Enter position">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Reason <span style="color: var(--secondary);">*</span></label>
                    <select name="reason" id="reasonSelect" class="form-control" onchange="toggleOtherReason()" required>
                        <option value="">Select reason</option>
                        <option value="No-show interview">No-show interview</option>
                        <option value="No-show second interview">No-show second interview</option>
                        <option value="Repeated no-show">Repeated no-show</option>
                        <option value="Falsified documents">Falsified documents</option>
                        <option value="Unprofessional conduct">Unprofessional conduct</option>
                        <option value="Other">Other (specify)</option>
                    </select>
                </div>
                
                <div id="otherReasonDiv" style="display: none; margin-bottom: 20px;">
                    <label class="form-label">Specify Reason:</label>
                    <input type="text" name="other_reason" id="otherReason" class="form-control" placeholder="Enter custom reason">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Additional Notes</label>
                    <textarea name="notes" class="form-control" rows="3" placeholder="Enter any additional notes..."></textarea>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Added By</label>
                    <input type="text" name="added_by" class="form-control" value="HR Department">
                </div>
                
                <div class="modal-footer">
                    <button type="submit" class="action-btn primary" style="flex: 1;">
                        <i class="fas fa-save"></i>
                        Save to Blacklist
                    </button>
                    <button type="button" class="action-btn secondary" style="flex: 1;" onclick="hideAddModal()">
                        Cancel
                    </button>
                </div>
            </form>
        </div>
    </div>
    
    <!-- Import Modal -->
    <div id="importModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>
                    <i class="fas fa-upload"></i>
                    Import Blacklist Data
                </h3>
                <button class="close-modal" onclick="hideImportModal()">&times;</button>
            </div>
            
            <form method="POST" action="/import" enctype="multipart/form-data">
                <div class="form-group">
                    <label class="form-label">Select File <span style="color: var(--secondary);">*</span></label>
                    <input type="file" name="file" class="form-control" accept=".csv, .xlsx, .xls" required style="padding: 10px;">
                    <p style="font-size: 12px; color: var(--text-secondary); margin-top: 8px;">
                        <i class="fas fa-info-circle"></i>
                        Supported formats: CSV, Excel (.xlsx, .xls)<br>
                        Required columns: Name, Phone, Position, Reason
                    </p>
                </div>
                
                <div class="modal-footer">
                    <button type="submit" class="action-btn primary" style="flex: 1;">
                        <i class="fas fa-check"></i>
                        Import Data
                    </button>
                    <button type="button" class="action-btn secondary" style="flex: 1;" onclick="hideImportModal()">
                        Cancel
                    </button>
                </div>
            </form>
        </div>
    </div>
    <script>
    // Page Navigation
    function showPage(page, element) {
        console.log("Showing page: " + page);
        console.log("Element: ", element);
        
        // Hide all pages
        document.querySelectorAll('.page').forEach(p => {
            console.log("Hiding page: " + p.id);
            p.classList.remove('active-page');
        });
        
        // Show selected page
        var targetPage = document.getElementById('page-' + page);
        console.log("Target page: ", targetPage);
        if (targetPage) {
            targetPage.classList.add('active-page');
            console.log("Added active class to: page-" + page);
        } else {
            console.log("Page not found: page-" + page);
        }
        
        // Remove active class from all nav items
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.remove('active');
        });
        
        // Add active class to clicked nav item
        if (element) {
            element.classList.add('active');
            console.log("Added active class to clicked nav item");
        }
    }

    // Modal Functions
    function showAddModal() {
        document.getElementById('addModal').style.display = 'flex';
    }

    function hideAddModal() {
        document.getElementById('addModal').style.display = 'none';
        document.getElementById('reasonSelect').value = '';
        document.getElementById('otherReasonDiv').style.display = 'none';
        document.getElementById('otherReason').value = '';
    }

    function showImportModal() {
        document.getElementById('importModal').style.display = 'flex';
    }

    function hideImportModal() {
        document.getElementById('importModal').style.display = 'none';
    }

    function toggleOtherReason() {
        var select = document.getElementById('reasonSelect');
        var otherDiv = document.getElementById('otherReasonDiv');
        var otherInput = document.getElementById('otherReason');
        
        if (select.value === 'Other') {
            otherDiv.style.display = 'block';
            otherInput.required = true;
        } else {
            otherDiv.style.display = 'none';
            otherInput.required = false;
            otherInput.value = '';
        }
    }

    function validateAndShowLoading() {
        var folderName = document.getElementById('folderName').value;
        if (!folderName) {
            alert('Please enter a folder name');
            return false;
        }
        document.getElementById('loading').style.display = 'block';
        return true;
    }

    // Search functionality
    function searchTable() {
        var input = document.getElementById('searchInput');
        var filter = input.value.toUpperCase();
        var table = document.getElementById('blacklistTable');
        var tr = table.getElementsByTagName('tr');
        
        for (var i = 1; i < tr.length; i++) {
            var tdArray = tr[i].getElementsByTagName('td');
            var found = false;
            for (var j = 0; j < tdArray.length - 1; j++) {
                if (tdArray[j]) {
                    var txtValue = tdArray[j].textContent || tdArray[j].innerText;
                    if (txtValue.toUpperCase().indexOf(filter) > -1) {
                        found = true;
                        break;
                    }
                }
            }
            tr[i].style.display = found ? '' : 'none';
        }
    }

    function searchBlacklist() {
        var input = document.getElementById('blacklistSearch');
        var filter = input.value.toUpperCase();
        var table = document.getElementById('fullBlacklistTable');
        var tr = table.getElementsByTagName('tr');
        
        for (var i = 1; i < tr.length; i++) {
            var tdArray = tr[i].getElementsByTagName('td');
            var found = false;
            for (var j = 0; j < tdArray.length - 1; j++) {
                if (tdArray[j]) {
                    var txtValue = tdArray[j].textContent || tdArray[j].innerText;
                    if (txtValue.toUpperCase().indexOf(filter) > -1) {
                        found = true;
                        break;
                    }
                }
            }
            tr[i].style.display = found ? '' : 'none';
        }
    }

    // Close modal when clicking outside
    window.onclick = function(event) {
        if (event.target.classList.contains('modal')) {
            event.target.style.display = 'none';
        }
    }

    // Set active page based on URL
    document.addEventListener('DOMContentLoaded', function() {
        console.log("DOM loaded");
        const path = window.location.pathname;
        console.log("Current path:", path);
        
        if (path === '/clean') {
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active-page'));
            document.getElementById('page-clean').classList.add('active-page');
            
            document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
            document.querySelector('.nav-item:nth-child(4)').classList.add('active');
        } else if (path === '/blacklisted-files') {
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active-page'));
            document.getElementById('page-blacklisted-files').classList.add('active-page');
            
            document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
            document.querySelector('.nav-item:nth-child(5)').classList.add('active');
        }
    });
</script>
</body>
</html>
"""

@app.route("/")
def home():
    conn = sqlite3.connect("blacklist.db")
    
    # Get column names first
    cursor = conn.execute("PRAGMA table_info(blacklist)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Build query based on available columns
    if 'email' in columns and 'notes' in columns and 'status' in columns:
        rows = conn.execute(
            "SELECT name, phone, email, position, reason, date_added, added_by, notes, status, id FROM blacklist ORDER BY date_added DESC"
        ).fetchall()
    else:
        # Fallback to basic columns
        rows = conn.execute(
            "SELECT name, phone, position, reason, date_added, added_by, id FROM blacklist ORDER BY date_added DESC"
        ).fetchall()
        # Pad rows to match expected format
        rows = [list(row) + ['', 'active', row[-1]] for row in rows]
    
    total = conn.execute("SELECT COUNT(*) FROM blacklist").fetchone()[0]
    conn.close()
    
    # Get folder stats
    clean_folders, blacklisted_folders = get_folder_structure()
    clean_files_count, blacklisted_files_count = get_file_count()
    
    # Get scan results from query params
    scan_results = None
    if request.args.get('scan_results'):
        scan_results = {
            'clean': request.args.get('clean', 0),
            'blacklisted': request.args.get('blacklisted', 0),
            'found_names': request.args.get('names', '').split(',') if request.args.get('names') else [],
            'folder_name': request.args.get('folder', '')
        }
    
    return render_template_string(
        HTML,
        rows=rows,
        total=total,
        clean_files_count=clean_files_count,
        blacklisted_files_count=blacklisted_files_count,
        clean_folders=clean_folders,
        blacklisted_folders=blacklisted_folders,
        current_clean_folder=None,
        current_clean_files=[],
        current_blacklisted_folder=None,
        current_blacklisted_files=[],
        scan_results=scan_results,
        datetime=datetime
    )

@app.route("/scan", methods=["POST"])
def scan_folder():
    """Scan uploaded folder for CVs"""
    files = request.files.getlist('folder')
    folder_name = request.form.get('folder_name', '').strip()
    
    if not files or files[0].filename == '':
        flash("❌ No files selected", "error")
        return redirect("/#scan")
    
    if not folder_name:
        flash("❌ Please enter a folder name", "error")
        return redirect("/#scan")
    
    # Clean folder name
    folder_name = "".join(c for c in folder_name if c.isalnum() or c in (' ', '-', '_')).strip()
    folder_name = folder_name.replace(' ', '_')
    
    # Get blacklisted names from database
    conn = sqlite3.connect("blacklist.db")
    blacklisted = [row[0] for row in conn.execute("SELECT name FROM blacklist").fetchall()]
    
    # Create target folders
    clean_target = os.path.join(CLEAN_FOLDER, folder_name)
    blacklisted_target = os.path.join(BLACKLISTED_FOLDER, folder_name)
    
    os.makedirs(clean_target, exist_ok=True)
    os.makedirs(blacklisted_target, exist_ok=True)
    
    clean_count = 0
    blacklisted_count = 0
    found_names = set()
    total_files = len([f for f in files if f.filename])
    
    # Process each file
    for file in files:
        if file and file.filename:
            # Get just the filename without path
            original_filename = file.filename
            safe_filename = os.path.basename(original_filename)
            
            # Save to upload folder with safe name
            temp_path = os.path.join(UPLOAD_FOLDER, safe_filename)
            
            # Handle duplicate filenames
            counter = 1
            while os.path.exists(temp_path):
                name, ext = os.path.splitext(safe_filename)
                temp_path = os.path.join(UPLOAD_FOLDER, f"{name}_{counter}{ext}")
                counter += 1
            
            file.save(temp_path)
            
            # Search for blacklisted names
            matched_name = search_name_in_file(temp_path, blacklisted)
            
            if matched_name:
                # Move to blacklisted folder
                dest = os.path.join(blacklisted_target, os.path.basename(temp_path))
                shutil.move(temp_path, dest)
                blacklisted_count += 1
                found_names.add(matched_name)
            else:
                # Move to clean folder
                dest = os.path.join(clean_target, os.path.basename(temp_path))
                shutil.move(temp_path, dest)
                clean_count += 1
    
    # Save scan history if table exists
    try:
        conn.execute(
            "INSERT INTO scan_history (scan_date, folder_name, total_files, clean_count, blacklisted_count, found_names) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M"), folder_name, total_files, clean_count, blacklisted_count, ','.join(found_names))
        )
        conn.commit()
    except:
        pass  # Skip if table doesn't exist
    
    conn.close()
    
    flash(f"✅ Scan complete! Found {clean_count} clean CVs and {blacklisted_count} blacklisted CVs", "success")
    
    # Redirect with results
    return redirect(f"/?scan_results=1&clean={clean_count}&blacklisted={blacklisted_count}&folder={folder_name}&names={','.join(found_names)}")

@app.route("/clean")
def view_clean():
    """View clean folders or folder contents"""
    folder_name = request.args.get('folder')
    
    conn = sqlite3.connect("blacklist.db")
    
    # Get column names first
    cursor = conn.execute("PRAGMA table_info(blacklist)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Build query based on available columns
    if 'email' in columns and 'notes' in columns and 'status' in columns:
        rows = conn.execute(
            "SELECT name, phone, email, position, reason, date_added, added_by, notes, status, id FROM blacklist ORDER BY date_added DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name, phone, position, reason, date_added, added_by, id FROM blacklist ORDER BY date_added DESC"
        ).fetchall()
        rows = [list(row) + ['', 'active', row[-1]] for row in rows]
    
    total = conn.execute("SELECT COUNT(*) FROM blacklist").fetchone()[0]
    conn.close()
    
    clean_folders, blacklisted_folders = get_folder_structure()
    clean_files_count, blacklisted_files_count = get_file_count()
    
    current_clean_files = []
    current_clean_folder = None
    
    if folder_name:
        folder_path = os.path.join(CLEAN_FOLDER, folder_name)
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            current_clean_folder = folder_name
            for f in os.listdir(folder_path):
                file_path = os.path.join(folder_path, f)
                if os.path.isfile(file_path):
                    size = f"{os.path.getsize(file_path) / 1024:.1f} KB"
                    mtime = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M')
                    current_clean_files.append({'name': f, 'size': size, 'date': mtime})
    
    html = render_template_string(
        HTML,
        rows=rows,
        total=total,
        clean_files_count=clean_files_count,
        blacklisted_files_count=blacklisted_files_count,
        clean_folders=clean_folders,
        blacklisted_folders=blacklisted_folders,
        current_clean_folder=current_clean_folder,
        current_clean_files=current_clean_files,
        current_blacklisted_folder=None,
        current_blacklisted_files=[],
        scan_results=None,
        datetime=datetime
    )
    
    return html

@app.route("/blacklisted-files")
def view_blacklisted():
    """View blacklisted folders or folder contents"""
    folder_name = request.args.get('folder')
    
    conn = sqlite3.connect("blacklist.db")
    
    # Get column names first
    cursor = conn.execute("PRAGMA table_info(blacklist)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Build query based on available columns
    if 'email' in columns and 'notes' in columns and 'status' in columns:
        rows = conn.execute(
            "SELECT name, phone, email, position, reason, date_added, added_by, notes, status, id FROM blacklist ORDER BY date_added DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name, phone, position, reason, date_added, added_by, id FROM blacklist ORDER BY date_added DESC"
        ).fetchall()
        rows = [list(row) + ['', 'active', row[-1]] for row in rows]
    
    total = conn.execute("SELECT COUNT(*) FROM blacklist").fetchone()[0]
    conn.close()
    
    clean_folders, blacklisted_folders = get_folder_structure()
    clean_files_count, blacklisted_files_count = get_file_count()
    
    current_blacklisted_files = []
    current_blacklisted_folder = None
    
    if folder_name:
        folder_path = os.path.join(BLACKLISTED_FOLDER, folder_name)
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            current_blacklisted_folder = folder_name
            for f in os.listdir(folder_path):
                file_path = os.path.join(folder_path, f)
                if os.path.isfile(file_path):
                    size = f"{os.path.getsize(file_path) / 1024:.1f} KB"
                    mtime = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M')
                    current_blacklisted_files.append({
                        'name': f, 
                        'size': size, 
                        'date': mtime,
                        'matched_name': 'Unknown'
                    })
    
    html = render_template_string(
        HTML,
        rows=rows,
        total=total,
        clean_files_count=clean_files_count,
        blacklisted_files_count=blacklisted_files_count,
        clean_folders=clean_folders,
        blacklisted_folders=blacklisted_folders,
        current_clean_folder=None,
        current_clean_files=[],
        current_blacklisted_folder=current_blacklisted_folder,
        current_blacklisted_files=current_blacklisted_files,
        scan_results=None,
        datetime=datetime
    )
    
    return html

@app.route("/add", methods=["POST"])
def add():
    reason = request.form["reason"]
    if reason == "Other" and request.form.get("other_reason"):
        reason = request.form["other_reason"]
    
    conn = sqlite3.connect("blacklist.db")
    
    # Get column names
    cursor = conn.execute("PRAGMA table_info(blacklist)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Build insert query based on available columns
    if 'email' in columns and 'notes' in columns and 'status' in columns:
        conn.execute(
            "INSERT INTO blacklist (name, phone, email, position, reason, date_added, added_by, notes, status) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                request.form["name"],
                request.form.get("phone", ""),
                request.form.get("email", ""),
                request.form.get("position", ""),
                reason,
                datetime.now().strftime("%Y-%m-%d"),
                request.form.get("added_by", "HR"),
                request.form.get("notes", ""),
                "active"
            )
        )
    else:
        conn.execute(
            "INSERT INTO blacklist (name, phone, position, reason, date_added, added_by) VALUES (?,?,?,?,?,?)",
            (
                request.form["name"],
                request.form.get("phone", ""),
                request.form.get("position", ""),
                reason,
                datetime.now().strftime("%Y-%m-%d"),
                request.form.get("added_by", "HR")
            )
        )
    
    conn.commit()
    conn.close()
    flash("✅ Added to blacklist successfully", "success")
    return redirect("/")

@app.route("/delete/<int:record_id>", methods=["POST"])
def delete(record_id):
    conn = sqlite3.connect("blacklist.db")
    conn.execute("DELETE FROM blacklist WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    flash("✅ Deleted successfully", "success")
    return redirect("/")

@app.route("/export")
def export():
    conn = sqlite3.connect("blacklist.db")
    
    # Get column names
    cursor = conn.execute("PRAGMA table_info(blacklist)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Build query based on available columns
    if 'email' in columns and 'notes' in columns and 'status' in columns:
        rows = conn.execute("SELECT name, phone, email, position, reason, date_added, added_by, notes, status FROM blacklist").fetchall()
        headers = ['Name', 'Phone', 'Email', 'Position', 'Reason', 'Date Added', 'Added By', 'Notes', 'Status']
    else:
        rows = conn.execute("SELECT name, phone, position, reason, date_added, added_by FROM blacklist").fetchall()
        headers = ['Name', 'Phone', 'Position', 'Reason', 'Date Added', 'Added By']
    
    conn.close()
    
    filename = f"blacklist_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    
    return send_file(filename, as_attachment=True, download_name=filename)

@app.route("/import", methods=["POST"])
def import_file():
    file = request.files['file']
    
    if not file:
        flash("❌ No file selected", "error")
        return redirect("/")
    
    filename = file.filename
    file.save(filename)
    
    count = 0
    
    try:
        conn = sqlite3.connect("blacklist.db")
        
        # Get column names
        cursor = conn.execute("PRAGMA table_info(blacklist)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if filename.endswith('.csv'):
            with open(filename, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
                start_idx = 1 if rows and rows[0] and rows[0][0].lower() in ['name', 'fullname'] else 0
                
                for row in rows[start_idx:]:
                    if row and len(row) >= 1 and row[0].strip():
                        name = row[0].strip()
                        phone = row[1].strip() if len(row) > 1 and row[1].strip() else ""
                        position = row[2].strip() if len(row) > 2 and row[2].strip() else ""
                        reason = row[3].strip() if len(row) > 3 and row[3].strip() else "Imported"
                        
                        if 'email' in columns and 'notes' in columns and 'status' in columns:
                            email = row[4].strip() if len(row) > 4 and row[4].strip() else ""
                            notes = row[5].strip() if len(row) > 5 and row[5].strip() else ""
                            status = row[6].strip() if len(row) > 6 and row[6].strip() else "active"
                            
                            conn.execute(
                                "INSERT INTO blacklist (name, phone, email, position, reason, date_added, added_by, notes, status) VALUES (?,?,?,?,?,?,?,?,?)",
                                (name, phone, email, position, reason, datetime.now().strftime('%Y-%m-%d'), 'Import', notes, status)
                            )
                        else:
                            conn.execute(
                                "INSERT INTO blacklist (name, phone, position, reason, date_added, added_by) VALUES (?,?,?,?,?,?)",
                                (name, phone, position, reason, datetime.now().strftime('%Y-%m-%d'), 'Import')
                            )
                        count += 1
        
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(filename)
            
            for _, row in df.iterrows():
                name = str(row.iloc[0]) if pd.notna(row.iloc[0]) else ""
                if not name:
                    continue
                    
                phone = str(row.iloc[1]) if len(row) > 1 and pd.notna(row.iloc[1]) else ""
                position = str(row.iloc[2]) if len(row) > 2 and pd.notna(row.iloc[2]) else ""
                reason = str(row.iloc[3]) if len(row) > 3 and pd.notna(row.iloc[3]) else "Imported"
                
                if 'email' in columns and 'notes' in columns and 'status' in columns:
                    email = str(row.iloc[4]) if len(row) > 4 and pd.notna(row.iloc[4]) else ""
                    notes = str(row.iloc[5]) if len(row) > 5 and pd.notna(row.iloc[5]) else ""
                    status = str(row.iloc[6]) if len(row) > 6 and pd.notna(row.iloc[6]) else "active"
                    
                    conn.execute(
                        "INSERT INTO blacklist (name, phone, email, position, reason, date_added, added_by, notes, status) VALUES (?,?,?,?,?,?,?,?,?)",
                        (name, phone, email, position, reason, datetime.now().strftime('%Y-%m-%d'), 'Import', notes, status)
                    )
                else:
                    conn.execute(
                        "INSERT INTO blacklist (name, phone, position, reason, date_added, added_by) VALUES (?,?,?,?,?,?)",
                        (name, phone, position, reason, datetime.now().strftime('%Y-%m-%d'), 'Import')
                    )
                count += 1
        
        else:
            flash("❌ Unsupported file format. Use CSV or Excel.", "error")
            os.remove(filename)
            return redirect("/")
        
        conn.commit()
        conn.close()
        os.remove(filename)
        
        flash(f"✅ Successfully imported {count} records!", "success")
        
    except Exception as e:
        flash(f"❌ Error importing file: {str(e)}", "error")
        if os.path.exists(filename):
            os.remove(filename)
    
    return redirect("/")

@app.route("/files/<folder_type>/<path:filepath>")
def view_nested_file(folder_type, filepath):
    """View a file inside a folder"""
    folder_map = {
        'clean': CLEAN_FOLDER,
        'blacklisted': BLACKLISTED_FOLDER
    }
    
    base_folder = folder_map.get(folder_type)
    if not base_folder:
        flash("❌ Invalid folder type", "error")
        return redirect("/")
    
    full_path = os.path.join(base_folder, filepath)
    
    if not os.path.exists(full_path):
        flash(f"❌ File not found", "error")
        return redirect("/")
    
    return send_file(full_path)

if __name__ == "__main__":
    print("="*60)
    print("🚀 OTIC CV SCANNER - FIXED VERSION")
    print("="*60)
    print("📊 Dashboard: http://127.0.0.1:5000")
    print("🎨 Company Colors: #02319A (Blue) & #FF0000 (Red)")
    print("✅ Database automatically updated with new columns")
    print("="*60)
    app.run(debug=True, host='0.0.0.0', port=5000)