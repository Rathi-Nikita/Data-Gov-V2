#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Apr 29 02:25:04 2025

@author: nikita
"""

from flask import Flask, render_template, request, redirect, session, url_for, jsonify, send_from_directory
from backend import *
import os
from werkzeug.utils import secure_filename

# Initialize Flask App
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Needed for session management

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ================================
# 🔐 Login Route
# ================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        success, user_obj = authenticate_web_user(username, password)
        if success:
            session['username'] = username
            session['role'] = user_obj['role']
            return redirect(url_for('chat'))
        else:
            return render_template('login.html', error="❌ Invalid credentials. Please try again.")

    return render_template('login.html')

# ================================
# 💬 Chatbot Route
# ================================
@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        if 'file' in request.files:
            # Handle uploaded PDF
            file = request.files['file']
            if file.filename == '':
                return jsonify({"response": "❌ No file selected."})

            filename = secure_filename(file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(file_path)

            # Call summarize_pdf_web with uploaded file path
            summarize_pdf_web(file_path)
            return jsonify({"response": get_conversation_response()})

        # Normal text chat input
        user_message = request.json.get('message')
        response_text = chatbot_handler(user_message)
        return jsonify({"response": response_text})

    return render_template('chat.html')

# ================================
# 📥 Download Summary Files
# ================================
@app.route('/download/<filename>')
def download_file(filename):
    uploads = os.path.join(app.root_path, UPLOAD_FOLDER)
    return send_from_directory(uploads, filename, as_attachment=True)

# ================================
# 🚪 Logout
# ================================
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ================================
# 🚀 Run Flask App
# ================================
if __name__ == '__main__':
    app.run(debug=True)
