from flask import Flask, render_template_string, request, redirect, url_for, flash, send_file
import sqlite3
from datetime import datetime
import csv
import os
import shutil
from pathlib import Path
import PyPDF2
import docx
import pandas as pd

app = Flask(__name__)
app.secret_key = "otic-blacklist-secret"

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
    conn.execute("""
    CREATE TABLE IF NOT EXISTS blacklist(
        id INTEGER PRIMARY KEY,
        name TEXT,
        phone TEXT,
        position TEXT,
        reason TEXT,
        date_added TEXT,
        added_by TEXT
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
                text += page.extract_text()
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
    # Extract text based on file type
    ext = os.path.splitext(filepath)[1].lower()
    
    if ext == '.pdf':
        text = extract_text_from_pdf(filepath)
    elif ext == '.docx':
        text = extract_text_from_docx(filepath)
    elif ext == '.txt':
        text = extract_text_from_txt(filepath)
    else:
        return None
    
    # Check for each blacklisted name
    for name in blacklisted_names:
        if name.lower() in text:
            return name
    return None

def get_file_count():
    """Get total file counts in clean and blacklisted folders"""
    clean_files_count = 0
    blacklisted_files_count = 0
    
    # Count files in clean_cvs folders
    if os.path.exists(CLEAN_FOLDER):
        for root, dirs, files in os.walk(CLEAN_FOLDER):
            clean_files_count += len(files)
    
    # Count files in blacklisted_cvs folders
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
<html>
<head>
    <title>OTIC CV Scanner</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        
        body {
            background: #f3f4f6;
        }
        
        .layout {
            display: flex;
            min-height: 100vh;
        }
        
        /* SIDEBAR */
        .sidebar {
            width: 260px;
            background: #111827;
            color: white;
            position: fixed;
            height: 100vh;
            overflow-y: auto;
        }
        
        .logo-area {
            padding: 28px 24px;
            border-bottom: 1px solid #1f2937;
        }
        
        .logo-area h2 {
            font-size: 20px;
            font-weight: 500;
            letter-spacing: 0.3px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .nav-menu {
            padding: 24px 16px;
        }
        
        .nav-item {
            padding: 12px 16px;
            margin: 4px 0;
            border-radius: 8px;
            color: #9ca3af;
            cursor: pointer;
            font-size: 15px;
            display: flex;
            align-items: center;
            gap: 12px;
            transition: all 0.2s;
        }
        
        .nav-item i {
            width: 20px;
            font-size: 16px;
        }
        
        .nav-item:hover {
            background: #1f2937;
            color: white;
        }
        
        .nav-item.active {
            background: #ef4444;
            color: white;
        }
        
        /* MAIN CONTENT */
        .main {
            flex: 1;
            margin-left: 260px;
            padding: 32px 48px;
            max-width: 1400px;
        }
        
        .page {
            display: none;
        }
        
        .page.active-page {
            display: block;
        }
        
        /* STATS CARDS */
        .stats-row {
            display: flex;
            gap: 24px;
            margin-bottom: 32px;
        }
        
        .stat-card {
            flex: 1;
            padding: 24px;
            border-radius: 12px;
            color: white;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            transition: transform 0.2s;
        }
        
        .stat-card:hover {
            transform: translateY(-2px);
        }
        
        .stat-card.red {
            background: #dc2626;
        }
        
        .stat-card.green {
            background: #16a34a;
        }
        
        .stat-card.orange {
            background: #ea580c;
        }
        
        .stat-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        
        .stat-label {
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            opacity: 0.9;
        }
        
        .stat-number {
            font-size: 42px;
            font-weight: 700;
        }
        
        .add-icon {
            width: 32px;
            height: 32px;
            background: rgba(255,255,255,0.2);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .add-icon:hover {
            background: rgba(255,255,255,0.3);
            transform: scale(1.1);
        }
        
        /* UPLOAD SECTION */
        .upload-section {
            background: #ffffff;
            border-radius: 16px;
            padding: 32px;
            margin-bottom: 24px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            border: 1px solid #e5e7eb;
        }
        
        .upload-section h3 {
            color: #111827;
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .folder-name-input {
            margin-bottom: 24px;
            background: #f9fafb;
            padding: 20px;
            border-radius: 12px;
            border: 1px solid #e5e7eb;
        }
        
        .folder-name-input label {
            display: block;
            margin-bottom: 10px;
            font-weight: 600;
            color: #374151;
            font-size: 15px;
        }
        
        .folder-name-input label i {
            color: #ef4444;
            margin-right: 8px;
        }
        
        .folder-input-group {
            display: flex;
            gap: 12px;
        }
        
        .folder-name-input input {
            flex: 1;
            padding: 14px 18px;
            border: 2px solid #e5e7eb;
            border-radius: 10px;
            font-size: 15px;
            transition: all 0.2s;
            background: white;
        }
        
        .folder-name-input input:focus {
            outline: none;
            border-color: #ef4444;
            box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
        }
        
        .save-folder-btn {
            padding: 14px 28px;
            background: #16a34a;
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .save-folder-btn:hover {
            background: #15803d;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(22, 163, 74, 0.3);
        }
        
        .upload-area {
            border: 2px dashed #d1d5db;
            border-radius: 12px;
            padding: 40px;
            background: #f9fafb;
            cursor: pointer;
            transition: all 0.3s;
            text-align: center;
        }
        
        .upload-area:hover {
            border-color: #ef4444;
            background: #fef2f2;
        }
        
        .upload-area i {
            font-size: 48px;
            color: #9ca3af;
            margin-bottom: 16px;
        }
        
        .upload-area p {
            color: #6b7280;
            font-size: 14px;
        }
        
        .scan-btn {
            margin-top: 24px;
            padding: 16px 32px;
            background: #ef4444;
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        
        .scan-btn:hover {
            background: #dc2626;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
        }
        
        .scan-btn i {
            font-size: 18px;
        }
        
        /* SCAN RESULTS */
        .results-section {
            background: #ffffff;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            border: 1px solid #e5e7eb;
        }
        
        .results-header {
            font-size: 20px;
            font-weight: 700;
            color: #111827;
            margin-bottom: 20px;
        }
        
        .results-grid {
            display: flex;
            gap: 24px;
            margin-bottom: 24px;
        }
        
        .result-card {
            flex: 1;
            padding: 24px;
            border-radius: 12px;
            text-align: center;
        }
        
        .result-card.clean {
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
        }
        
        .result-card.blacklisted {
            background: #fef2f2;
            border: 1px solid #fecaca;
        }
        
        .result-number {
            font-size: 48px;
            font-weight: 700;
            margin-bottom: 8px;
        }
        
        .result-card.clean .result-number {
            color: #16a34a;
        }
        
        .result-card.blacklisted .result-number {
            color: #dc2626;
        }
        
        .result-label {
            font-size: 16px;
            font-weight: 500;
        }
        
        .blacklisted-names {
            margin-top: 20px;
            padding: 20px;
            background: #fef2f2;
            border-radius: 8px;
        }
        
        .blacklisted-names h4 {
            color: #991b1b;
            margin-bottom: 16px;
            font-size: 16px;
        }
        
        .name-tag {
            display: inline-block;
            background: white;
            padding: 8px 16px;
            border-radius: 20px;
            margin: 4px;
            border: 1px solid #fecaca;
            color: #991b1b;
            font-size: 14px;
            font-weight: 500;
        }
        
        .folder-actions {
            display: flex;
            gap: 16px;
            margin-top: 20px;
        }
        
        .folder-btn {
            flex: 1;
            padding: 16px;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            background: white;
            cursor: pointer;
            transition: all 0.2s;
            text-align: center;
        }
        
        .folder-btn:hover {
            background: #f9fafb;
            border-color: #ef4444;
        }
        
        .folder-btn i {
            font-size: 24px;
            color: #6b7280;
            margin-bottom: 8px;
        }
        
        /* FOLDERS GRID */
        .folders-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .folder-card {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 24px;
            cursor: pointer;
            transition: all 0.2s;
            text-align: center;
        }
        
        .folder-card:hover {
            border-color: #ef4444;
            box-shadow: 0 8px 20px rgba(0,0,0,0.1);
            transform: translateY(-2px);
        }
        
        .folder-card.clean:hover {
            border-color: #16a34a;
        }
        
        .folder-card.blacklisted:hover {
            border-color: #dc2626;
        }
        
        .folder-card i {
            font-size: 48px;
            color: #6b7280;
            margin-bottom: 16px;
        }
        
        .folder-card.clean i {
            color: #16a34a;
        }
        
        .folder-card.blacklisted i {
            color: #dc2626;
        }
        
        .folder-card h4 {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 8px;
            color: #111827;
        }
        
        .folder-card p {
            color: #6b7280;
            font-size: 14px;
        }
        
        .folder-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
        }
        
        .folder-header h3 {
            font-size: 20px;
            font-weight: 600;
            color: #111827;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .back-btn {
            padding: 10px 20px;
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s;
        }
        
        .back-btn:hover {
            background: #f9fafb;
            border-color: #d1d5db;
        }
        
        .back-btn i {
            font-size: 14px;
        }
        
        /* FILES TABLE */
        .files-section {
            background: white;
            border-radius: 12px;
            border: 1px solid #e5e7eb;
            overflow: hidden;
        }
        
        .files-header {
            padding: 20px 24px;
            border-bottom: 1px solid #e5e7eb;
            background: #f9fafb;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .files-header h4 {
            font-size: 16px;
            font-weight: 600;
            color: #111827;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .files-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }
        
        .files-table th {
            background: #f9fafb;
            padding: 16px 20px;
            text-align: left;
            font-weight: 600;
            color: #374151;
            font-size: 13px;
            letter-spacing: 0.3px;
            border-bottom: 1px solid #e5e7eb;
        }
        
        .files-table td {
            padding: 16px 20px;
            border-bottom: 1px solid #e5e7eb;
            color: #1f2937;
        }
        
        .files-table tr:hover td {
            background: #f9fafb;
        }
        
        .view-btn {
            background: none;
            border: none;
            color: #3b82f6;
            cursor: pointer;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 14px;
        }
        
        .view-btn:hover {
            background: #dbeafe;
        }
        
        .matched-badge {
            background: #fee2e2;
            color: #991b1b;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            display: inline-block;
        }
        
        /* FOLDERS LIST */
        .folders-section {
            background: #ffffff;
            border-radius: 12px;
            padding: 24px;
            border: 1px solid #e5e7eb;
            margin-bottom: 24px;
        }
        
        .folders-section h3 {
            color: #111827;
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 16px;
        }
        
        .folder-item {
            display: flex;
            align-items: center;
            padding: 16px;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            margin-bottom: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .folder-item:hover {
            background: #f9fafb;
            border-color: #ef4444;
        }
        
        .folder-item:last-child {
            margin-bottom: 0;
        }
        
        .folder-icon {
            width: 48px;
            height: 48px;
            background: #f3f4f6;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 16px;
        }
        
        .folder-icon i {
            font-size: 24px;
            color: #ef4444;
        }
        
        .folder-info {
            flex: 1;
        }
        
        .folder-name {
            font-weight: 600;
            color: #111827;
            font-size: 16px;
            margin-bottom: 4px;
        }
        
        .folder-count {
            color: #6b7280;
            font-size: 13px;
        }
        
        /* TABLE */
        .table-container {
            background: white;
            border-radius: 12px;
            border: 1px solid #e5e7eb;
            overflow: hidden;
            margin-top: 24px;
        }
        
        .table-header {
            padding: 16px 20px;
            border-bottom: 1px solid #e5e7eb;
            background: #f9fafb;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .table-header h4 {
            font-size: 15px;
            font-weight: 600;
            color: #111827;
        }
        
        .table-header span {
            color: #6b7280;
            font-size: 13px;
            background: #f3f4f6;
            padding: 4px 10px;
            border-radius: 16px;
        }
        
        .table-wrapper {
            max-height: 400px;
            overflow-y: auto;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }
        
        th {
            background: #f9fafb;
            padding: 14px 16px;
            text-align: left;
            font-weight: 600;
            color: #374151;
            font-size: 13px;
            letter-spacing: 0.3px;
            border-bottom: 1px solid #e5e7eb;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        
        td {
            padding: 14px 16px;
            border-bottom: 1px solid #e5e7eb;
            color: #1f2937;
        }
        
        tr:hover td {
            background: #f9fafb;
        }
        
        .delete-btn {
            background: none;
            border: none;
            color: #9ca3af;
            cursor: pointer;
            padding: 6px 10px;
            border-radius: 6px;
            transition: all 0.2s;
        }
        
        .delete-btn:hover {
            color: #dc2626;
            background: #fee2e2;
        }
        
        /* MODAL */
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
            backdrop-filter: blur(4px);
        }
        
        .modal-content {
            background: white;
            width: 520px;
            border-radius: 16px;
            padding: 32px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            animation: slideIn 0.3s ease;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-20px);
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
            margin-bottom: 24px;
        }
        
        .modal-header h3 {
            font-size: 22px;
            font-weight: 700;
            color: #111827;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .modal-header h3 i {
            color: #ef4444;
            font-size: 24px;
        }
        
        .close-modal {
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: #9ca3af;
            transition: color 0.2s;
        }
        
        .close-modal:hover {
            color: #ef4444;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #374151;
            font-size: 14px;
        }
        
        .form-group input,
        .form-group select {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 14px;
            transition: all 0.2s;
            background: #f9fafb;
        }
        
        .form-group input:focus,
        .form-group select:focus {
            outline: none;
            border-color: #ef4444;
            background: white;
            box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.1);
        }
        
        .modal-actions {
            display: flex;
            gap: 12px;
            margin-top: 32px;
        }
        
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            flex: 1;
        }
        
        .btn-primary {
            background: #16a34a;
            color: white;
        }
        
        .btn-primary:hover {
            background: #15803d;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(22, 163, 74, 0.3);
        }
        
        .btn-outline {
            background: white;
            border: 2px solid #e5e7eb;
            color: #374151;
        }
        
        .btn-outline:hover {
            background: #f9fafb;
            border-color: #d1d5db;
        }
        
        /* FLASH MESSAGES */
        .flash-message {
            padding: 14px 18px;
            margin-bottom: 24px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 10px;
            animation: slideIn 0.3s;
        }
        
        .flash-success {
            background: #f0fdf4;
            color: #166534;
            border: 1px solid #bbf7d0;
        }
        
        .flash-error {
            background: #fef2f2;
            color: #991b1b;
            border: 1px solid #fecaca;
        }
        
        /* Loading */
        .loading {
            display: none;
            text-align: center;
            padding: 40px;
        }
        
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #ef4444;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        /* Scrollbar */
        .table-wrapper::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        
        .table-wrapper::-webkit-scrollbar-track {
            background: #f1f1f1;
        }
        
        .table-wrapper::-webkit-scrollbar-thumb {
            background: #c1c1c1;
            border-radius: 4px;
        }
        
        .table-wrapper::-webkit-scrollbar-thumb:hover {
            background: #a1a1a1;
        }
    </style>
</head>
<body>
    <div class="layout">
        <!-- Sidebar -->
        <div class="sidebar">
            <div class="logo-area">
                <h2 style="display: flex; align-items: center; gap: 12px;">
                    <img src="/static/otic-logo.png" alt="OTIC" style="height: 32px; width: auto;">
                    <span style="color: white;">OTIC</span>
                </h2>
            </div>
            
            <div class="nav-menu">
                <div class="nav-item active" onclick="showPage('dashboard')">
                    <i class="fas fa-home"></i>
                    Dashboard
                </div>
                <div class="nav-item" onclick="showPage('scan')">
                    <i class="fas fa-search"></i>
                    Scan CVs
                </div>
                <div class="nav-item" onclick="showPage('blacklist')">
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
        <div class="main">
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
                <div class="stats-row">
                    <div class="stat-card red">
                        <div class="stat-header">
                            <span class="stat-label">Blacklisted Names</span>
                            <div class="add-icon" onclick="showAddModal()">
                                <i class="fas fa-plus"></i>
                            </div>
                        </div>
                        <div class="stat-number">{{ total }}</div>
                    </div>
                    
                    <div class="stat-card green">
                        <div class="stat-header">
                            <span class="stat-label">Clean CV Files</span>
                        </div>
                        <div class="stat-number">{{ clean_files_count }}</div>
                    </div>
                    
                    <div class="stat-card orange">
                        <div class="stat-header">
                            <span class="stat-label">Blacklisted Files</span>
                        </div>
                        <div class="stat-number">{{ blacklisted_files_count }}</div>
                    </div>
                </div>
                
                <div class="folders-section">
                    <h3>Quick Access Folders</h3>
                    
                    <div class="folder-item" onclick="window.location.href='/clean'">
                        <div class="folder-icon">
                            <i class="fas fa-folder-open"></i>
                        </div>
                        <div class="folder-info">
                            <div class="folder-name">Clean CVs</div>
                            <div class="folder-count">{{ clean_folders|length }} folders</div>
                        </div>
                    </div>
                    
                    <div class="folder-item" onclick="window.location.href='/blacklisted-files'">
                        <div class="folder-icon">
                            <i class="fas fa-folder-open"></i>
                        </div>
                        <div class="folder-info">
                            <div class="folder-name">Blacklisted CVs</div>
                            <div class="folder-count">{{ blacklisted_folders|length }} folders</div>
                        </div>
                    </div>
                </div>
                
                <div class="table-container">
                    <div class="table-header">
                        <h4>Recent Blacklisted Names</h4>
                        <span>{{ total }} total</span>
                    </div>
                    <div class="table-wrapper">
                        <table>
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Phone</th>
                                    <th>Reason</th>
                                    <th>Date</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for row in rows[:5] %}
                                <tr>
                                    <td><strong>{{ row[0] }}</strong></td>
                                    <td>{{ row[1] or '-' }}</td>
                                    <td>{{ row[3] }}</td>
                                    <td>{{ row[4] }}</td>
                                    <td>
                                        <form method="POST" action="/delete/{{ row[6] }}" style="display:inline;" onsubmit="return confirm('Delete this name?')">
                                            <button class="delete-btn">
                                                <i class="fas fa-trash-alt"></i>
                                            </button>
                                        </form>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <!-- Scan Page -->
            <div id="page-scan" class="page">
                <div class="upload-section">
                    <h3><i class="fas fa-cloud-upload-alt" style="color: #ef4444;"></i> Upload CV Folder</h3>
                    
                    <form method="POST" action="/scan" enctype="multipart/form-data" id="scanForm">
                        <div class="folder-name-input">
                            <label><i class="fas fa-folder-plus"></i> Folder Name (e.g., Operations, Accounts, Marketing)</label>
                            <div class="folder-input-group">
                                <input type="text" name="folder_name" id="folderName" placeholder="Enter folder name..." required>
                                <button type="button" class="save-folder-btn" onclick="document.getElementById('folderInput').click()">
                                    <i class="fas fa-save"></i> Save & Upload
                                </button>
                            </div>
                        </div>
                        
                        <div class="upload-area" onclick="document.getElementById('folderInput').click()">
                            <i class="fas fa-cloud-upload-alt"></i>
                            <p>Click to select folder containing CVs</p>
                            <p style="font-size: 12px; margin-top: 8px;">Supports: PDF, DOCX, DOC, TXT</p>
                        </div>
                        
                        <input type="file" name="folder" id="folderInput" webkitdirectory directory multiple style="display: none;" required>
                        
                        <button type="submit" class="scan-btn" onclick="return validateAndShowLoading()">
                            <i class="fas fa-search"></i> Start Scanning
                        </button>
                    </form>
                    
                    <div id="loading" class="loading">
                        <div class="spinner"></div>
                        <p>Scanning CVs... This may take a few moments.</p>
                    </div>
                </div>
                
                {% if scan_results %}
                <div class="results-section">
                    <div class="results-header">Scan Complete: {{ scan_results.folder_name }}</div>
                    
                    <div class="results-grid">
                        <div class="result-card clean">
                            <div class="result-number">{{ scan_results.clean }}</div>
                            <div class="result-label">Clean CVs</div>
                        </div>
                        
                        <div class="result-card blacklisted">
                            <div class="result-number">{{ scan_results.blacklisted }}</div>
                            <div class="result-label">Blacklisted CVs</div>
                        </div>
                    </div>
                    
                    {% if scan_results.found_names %}
                    <div class="blacklisted-names">
                        <h4><i class="fas fa-exclamation-triangle"></i> Blacklisted Names Found:</h4>
                        {% for name in scan_results.found_names %}
                            <span class="name-tag">{{ name }}</span>
                        {% endfor %}
                    </div>
                    {% endif %}
                </div>
                {% endif %}
            </div>
            
            <!-- Blacklist Management Page -->
            <div id="page-blacklist" class="page">
                <div style="margin-bottom: 24px; display: flex; gap: 16px;">
                    <button class="action-btn green" onclick="showAddModal()" style="padding: 12px 24px; background: #16a34a; color: white; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        <i class="fas fa-plus"></i> Add to Blacklist
                    </button>
                    <button class="action-btn" onclick="showImportModal()" style="padding: 12px 24px; background: white; border: 2px solid #16a34a; color: #16a34a; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer;">
                        <i class="fas fa-upload"></i> Import from File
                    </button>
                </div>
                
                <div class="table-container">
                    <div class="table-header">
                        <h4>All Blacklisted Names</h4>
                        <span>{{ total }} names</span>
                    </div>
                    <div class="table-wrapper" style="max-height: 600px;">
                        <table>
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Phone</th>
                                    <th>Position</th>
                                    <th>Reason</th>
                                    <th>Date</th>
                                    <th>Added By</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for row in rows %}
                                <tr>
                                    <td><strong>{{ row[0] }}</strong></td>
                                    <td>{{ row[1] or '-' }}</td>
                                    <td>{{ row[2] or '-' }}</td>
                                    <td>{{ row[3] }}</td>
                                    <td>{{ row[4] }}</td>
                                    <td>{{ row[5] or 'Import' }}</td>
                                    <td>
                                        <form method="POST" action="/delete/{{ row[6] }}" style="display:inline;" onsubmit="return confirm('Delete this name?')">
                                            <button class="delete-btn">
                                                <i class="fas fa-trash-alt"></i>
                                            </button>
                                        </form>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <!-- Clean CVs Page -->
            <div id="page-clean" class="page">
                <div class="folder-header">
                    <h3><i class="fas fa-check-circle" style="color: #16a34a;"></i> Clean CV Folders</h3>
                </div>
                
                {% if current_clean_folder %}
                    <div style="margin-bottom: 20px;">
                        <button class="back-btn" onclick="window.location.href='/clean'">
                            <i class="fas fa-arrow-left"></i> Back to Folders
                        </button>
                    </div>
                    
                    <div class="files-section">
                        <div class="files-header">
                            <h4><i class="fas fa-folder-open" style="color: #16a34a;"></i> {{ current_clean_folder }}</h4>
                            <span>{{ current_clean_files|length }} files</span>
                        </div>
                        <table class="files-table">
                            <thead>
                                <tr>
                                    <th>Filename</th>
                                    <th>Size</th>
                                    <th>Date</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for file in current_clean_files %}
                                <tr>
                                    <td>{{ file.name }}</td>
                                    <td>{{ file.size }}</td>
                                    <td>{{ file.date }}</td>
                                    <td>
                                        <a href="/files/clean/{{ current_clean_folder }}/{{ file.name }}" target="_blank">
                                            <button class="view-btn">
                                                <i class="fas fa-eye"></i> View
                                            </button>
                                        </a>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                {% else %}
                    <div class="folders-grid">
                        {% for folder in clean_folders %}
                        <div class="folder-card clean" onclick="window.location.href='/clean?folder={{ folder.name }}'">
                            <i class="fas fa-folder"></i>
                            <h4>{{ folder.name }}</h4>
                            <p>{{ folder.count }} files</p>
                        </div>
                        {% endfor %}
                    </div>
                {% endif %}
            </div>
            
            <!-- Blacklisted Files Page -->
            <div id="page-blacklisted-files" class="page">
                <div class="folder-header">
                    <h3><i class="fas fa-exclamation-triangle" style="color: #dc2626;"></i> Blacklisted CV Folders</h3>
                </div>
                
                {% if current_blacklisted_folder %}
                    <div style="margin-bottom: 20px;">
                        <button class="back-btn" onclick="window.location.href='/blacklisted-files'">
                            <i class="fas fa-arrow-left"></i> Back to Folders
                        </button>
                    </div>
                    
                    <div class="files-section">
                        <div class="files-header">
                            <h4><i class="fas fa-folder-open" style="color: #dc2626;"></i> {{ current_blacklisted_folder }}</h4>
                            <span>{{ current_blacklisted_files|length }} files</span>
                        </div>
                        <table class="files-table">
                            <thead>
                                <tr>
                                    <th>Filename</th>
                                    <th>Size</th>
                                    <th>Matched Name</th>
                                    <th>Date</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for file in current_blacklisted_files %}
                                <tr>
                                    <td>{{ file.name }}</td>
                                    <td>{{ file.size }}</td>
                                    <td><span class="matched-badge">{{ file.matched_name }}</span></td>
                                    <td>{{ file.date }}</td>
                                    <td>
                                        <a href="/files/blacklisted/{{ current_blacklisted_folder }}/{{ file.name }}" target="_blank">
                                            <button class="view-btn">
                                                <i class="fas fa-eye"></i> View
                                            </button>
                                        </a>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                {% else %}
                    <div class="folders-grid">
                        {% for folder in blacklisted_folders %}
                        <div class="folder-card blacklisted" onclick="window.location.href='/blacklisted-files?folder={{ folder.name }}'">
                            <i class="fas fa-folder"></i>
                            <h4>{{ folder.name }}</h4>
                            <p>{{ folder.count }} files</p>
                        </div>
                        {% endfor %}
                    </div>
                {% endif %}
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
                    <label>Full Name <span style="color: #ef4444;">*</span></label>
                    <input type="text" name="name" placeholder="e.g., John Doe" required>
                </div>
                
                <div class="form-group">
                    <label>Phone Number</label>
                    <input type="text" name="phone" placeholder="e.g., 08012345678">
                </div>
                
                <div class="form-group">
                    <label>Position</label>
                    <input type="text" name="position" placeholder="e.g., Software Developer">
                </div>
                
                <div class="form-group">
                    <label>Reason <span style="color: #ef4444;">*</span></label>
                    <select name="reason" id="reasonSelect" onchange="toggleOtherReason()" required>
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
                    <label>Please specify reason:</label>
                    <input type="text" name="other_reason" id="otherReason" placeholder="Enter custom reason..." style="width: 100%; padding: 12px 16px; border: 2px solid #e5e7eb; border-radius: 8px; margin-top: 8px;">
                </div>
                
                <div class="form-group">
                    <label>Added By</label>
                    <input type="text" name="added_by" placeholder="e.g., HR Department">
                </div>
                
                <div class="modal-actions">
                    <button type="submit" class="btn btn-primary">
                        <i class="fas fa-save"></i> Save
                    </button>
                    <button type="button" class="btn btn-outline" onclick="hideAddModal()">
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
                    Import Blacklist
                </h3>
                <button class="close-modal" onclick="hideImportModal()">&times;</button>
            </div>
            
            <form method="POST" action="/import" enctype="multipart/form-data">
                <div class="form-group">
                    <label>Select File <span style="color: #ef4444;">*</span></label>
                    <input type="file" name="file" accept=".csv, .xlsx, .xls" required style="padding: 10px; border: 2px dashed #d1d5db; width: 100%;">
                    <p style="font-size: 12px; color: #6b7280; margin-top: 8px;">
                        <i class="fas fa-info-circle"></i> 
                        Supported: CSV, Excel (.xlsx, .xls)<br>
                        Columns: Name, Phone, Position, Reason
                    </p>
                </div>
                
                <div class="modal-actions">
                    <button type="submit" class="btn btn-primary">
                        <i class="fas fa-check"></i> Import
                    </button>
                    <button type="button" class="btn btn-outline" onclick="hideImportModal()">
                        Cancel
                    </button>
                </div>
            </form>
        </div>
    </div>
    
    <script>
        function showPage(page) {
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active-page'));
            document.getElementById('page-' + page).classList.add('active-page');
            
            document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
            event.target.classList.add('active');
        }
        
        function showAddModal() {
            document.getElementById('addModal').style.display = 'flex';
            document.getElementById('reasonSelect').value = '';
            document.getElementById('otherReasonDiv').style.display = 'none';
            document.getElementById('otherReason').value = '';
        }
        
        function hideAddModal() {
            document.getElementById('addModal').style.display = 'none';
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
        
        window.onclick = function(event) {
            if (event.target.classList.contains('modal')) {
                event.target.style.display = 'none';
            }
        }
    </script>
</body>
</html>
"""

@app.route("/")
def home():
    conn = sqlite3.connect("blacklist.db")
    
    rows = conn.execute(
        "SELECT name, phone, position, reason, date_added, added_by, id FROM blacklist ORDER BY date_added DESC"
    ).fetchall()
    
    total = conn.execute("SELECT COUNT(*) FROM blacklist").fetchone()[0]
    
    # Get folder stats
    clean_folders, blacklisted_folders = get_folder_structure()
    clean_files_count, blacklisted_files_count = get_file_count()
    
    conn.close()
    
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
        scan_results=scan_results
    )

@app.route("/scan", methods=["POST"])
def scan_folder():
    """Scan uploaded folder for CVs"""
    files = request.files.getlist('folder')
    folder_name = request.form.get('folder_name', '').strip()
    
    if not files:
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
    conn.close()
    
    # Create target folders
    clean_target = os.path.join(CLEAN_FOLDER, folder_name)
    blacklisted_target = os.path.join(BLACKLISTED_FOLDER, folder_name)
    
    os.makedirs(clean_target, exist_ok=True)
    os.makedirs(blacklisted_target, exist_ok=True)
    
    clean_count = 0
    blacklisted_count = 0
    found_names = set()
    
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
    
    flash(f"✅ Scan complete! Clean: {clean_count}, Blacklisted: {blacklisted_count}", "success")
    
    # Redirect with results
    return redirect(f"/?scan_results=1&clean={clean_count}&blacklisted={blacklisted_count}&folder={folder_name}&names={','.join(found_names)}")

@app.route("/clean")
def view_clean():
    """View clean folders or folder contents"""
    folder_name = request.args.get('folder')
    
    conn = sqlite3.connect("blacklist.db")
    rows = conn.execute(
        "SELECT name, phone, position, reason, date_added, added_by, id FROM blacklist ORDER BY date_added DESC"
    ).fetchall()
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
    
    # Force the clean page to be active
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
        scan_results=None
    )
    
    # Add a script to activate the clean page
    html = html.replace('active-page', '')    # Add a script to activate the clean page
    html = html.replace('id="page-clean" class="page"', 'id="page-clean" class="page active-page"')
    
    return html

@app.route("/blacklisted-files")
def view_blacklisted():
    """View blacklisted folders or folder contents"""
    folder_name = request.args.get('folder')
    
    conn = sqlite3.connect("blacklist.db")
    rows = conn.execute(
        "SELECT name, phone, position, reason, date_added, added_by, id FROM blacklist ORDER BY date_added DESC"
    ).fetchall()
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
                        'matched_name': 'Unknown'  # You can enhance this later
                    })
    
    # Force the blacklisted page to be active
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
        scan_results=None
    )
    
    # Add a script to activate the blacklisted page
    html = html.replace('id="page-blacklisted-files" class="page"', 'id="page-blacklisted-files" class="page active-page"')
    
    return html

@app.route("/add", methods=["POST"])
def add():
    reason = request.form["reason"]
    if reason == "Other" and request.form.get("other_reason"):
        reason = request.form["other_reason"]
    
    conn = sqlite3.connect("blacklist.db")
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
    rows = conn.execute("SELECT name, phone, position, reason, date_added, added_by FROM blacklist").fetchall()
    conn.close()
    
    filename = f"blacklist_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Name', 'Phone', 'Position', 'Reason', 'Date', 'Added By'])
        writer.writerows(rows)
    
    return send_file(filename, as_attachment=True)

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
    print("="*50)
    print("OTIC CV SCANNER - FIXED VERSION")
    print("="*50)
    print("🚀 Server running at: http://127.0.0.1:5000")
    print("📁 Clean CVs count: Files in folders")
    print("🚫 Blacklisted CVs count: Files in folders")
    print("="*50)
    app.run(debug=True, host='0.0.0.0', port=5000)