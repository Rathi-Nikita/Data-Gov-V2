#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Apr 29 01:08:56 2025

@author: nikita
"""

# backend.py

# ==========================
# 📦 Imports
# ==========================
import os
import re
import textwrap
import fitz
import torch
import pprint
import nltk
from sentence_transformers import SentenceTransformer, util
from transformers import pipeline
from nltk.corpus import stopwords

# Custom imports (your databases)
import dg_users_db
import dg_applications_db
import dg_app_links
import dg_db
import dg_field_mapping
import dg_field_table_mapping
import dg_tasks_db
import pprint  # Make sure you import pprint at the top if not done already
import time

# ==========================
# 🧠 Model Initialization
# ==========================
nltk.download("stopwords", quiet=True)
stop_words = set(stopwords.words("english"))
sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")

# Make sure current_user_role is defined at the top as a global
current_user_role = None


# ==========================
# 📋 Conversation History Manager
# ==========================
conversation_history = []

def input_manager(prompt_text):
    conversation_history.append({"type": "prompt", "text": prompt_text})
    return "__awaiting_user_response__"

def output_manager(message):
    conversation_history.append({"type": "bot", "text": message})

# ==========================
# 🛠 Helpers
# ==========================
def extract_keywords(text):
    custom_stopwords = {"please", "i", "want", "need", "can", "could", "would", "like", "give", "me", "access", "download"}
    combined_stopwords = stop_words.union(custom_stopwords)
    words = re.findall(r'\w+', text.lower())
    keywords = [word for word in words if word not in combined_stopwords]
    return keywords

def extract_pdf_text(pdf_path):
    try:
        text = ""
        with fitz.open(pdf_path) as doc:
            for page in doc:
                page_text = page.get_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except Exception as e:
        output_manager(f"❌ Error extracting text: {e}")
        return None

def clean_text(text):
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if re.match(r'^\s*page\s*\d+|^\d+$|^running head:', line, re.IGNORECASE):
            continue
        if len(line) < 2:
            continue
        cleaned_lines.append(line)
    cleaned_text = ' '.join(cleaned_lines)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    return cleaned_text.strip()

def generate_summary(text, output_func, max_chunk_tokens=900, save_to_file=True, output_path="summary_output.txt"):
    import logging
    logging.getLogger("transformers").setLevel(logging.ERROR)

    summaries = []
    words = text.split()
    chunk = []

    for word in words:
        chunk.append(word)
        if len(chunk) >= max_chunk_tokens:
            chunk_text = ' '.join(chunk)
            try:
                summary = summarizer(chunk_text, max_length=150, min_length=40, do_sample=False)[0]['summary_text']
                summaries.append(summary)
            except Exception as e:
                output_func(f"⚠️ Error summarizing a chunk: {e}")
            chunk = []

    if chunk:
        chunk_text = ' '.join(chunk)
        try:
            summary = summarizer(chunk_text, max_length=150, min_length=40, do_sample=False)[0]['summary_text']
            summaries.append(summary)
        except Exception as e:
            output_func(f"⚠️ Error summarizing final chunk: {e}")

    final_summary = "\n\n".join(summaries)

    if save_to_file:
        try:
            output_dir = os.path.dirname(os.path.abspath(output_path))
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_summary)
            output_func(f"✅ Summary saved: {output_path}")
            output_func(f"📂 Location: {output_dir}")
        except Exception as e:
            output_func(f"❌ Error saving summary: {e}")

    return final_summary

# ==========================
# 🔥 Task Functions (Download, Summarize, Field Mapping, Access DB)
# ==========================


# ==========================
# 🔥 Task Functions (Download)
# ==========================


# conversation_context is global and stores session details
conversation_context = {
    "stage": 0,  # 0 = waiting for app name or category, 1 = waiting for app inside category
    "waiting_for_category_yesno": False,
    "selected_category": None,
    "available_categories": [],
    "available_apps": [],
}

# 🔵 Reset Download Context
def reset_download_context():
    conversation_context["stage"] = 0
    conversation_context["waiting_for_category_yesno"] = False
    conversation_context["selected_category"] = None
    conversation_context["available_categories"] = []
    conversation_context["available_apps"] = []

# 🔵 Download Apps Web
def download_apps_web(user_message=None):
    role = current_user_role
    role_apps = dg_applications_db.applications_db.get(role, {})

    if not role_apps:
        output_manager("❌ No applications available for your role.")
        reset_download_context()
        return

    all_categories = list(role_apps.keys())
    all_apps = [app for apps in role_apps.values() for app in apps]

    conversation_context["available_categories"] = all_categories

    # 1️⃣ First time asking
    if user_message is None:
        output_manager("💬 Which app would you like to download? (or type 'exit' to cancel)")
        return "__awaiting_user_response__"

    user_input = user_message.strip().lower()

    # 2️⃣ If waiting for yes/no to show categories
    if conversation_context.get("waiting_for_category_yesno", False):
        if user_input in ['yes', 'y']:
            output_manager("\n📂 Available Categories:")
            for idx, category in enumerate(all_categories, 1):
                output_manager(f"  {idx}. {category.replace('_', ' ').title()}")
            output_manager("\n👉 Enter category name or number to explore (or 'exit'):")
            conversation_context["waiting_for_category_yesno"] = False
            conversation_context["stage"] = 2  # Stage 2: Choosing category manually
            return "__awaiting_user_response__"
        else:
            output_manager("👋 Exiting download task.")
            reset_download_context()
            return

    # 3️⃣ If waiting for app selection after selecting a category
    if conversation_context["stage"] == 1:
        apps_in_category = conversation_context.get("available_apps", [])

        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(apps_in_category):
                matched_app = apps_in_category[idx]
            else:
                output_manager("❌ Invalid app selection. Try again.")
                return "__awaiting_user_response__"
        else:
            matched_app = None
            for kw in extract_keywords(user_input):
                matched_app = next((app for app in apps_in_category if kw == app.lower() or (kw in app.lower() and len(kw) >= 3)), None)
                if matched_app:
                    break

        if matched_app:
            link = dg_app_links.download_applinks.get(matched_app, "[No link available]")
            output_manager(f"\n📥 {matched_app}: {link}")
            reset_download_context()
            return
        else:
            output_manager("❌ App not found inside the selected category. Try again.")
            return "__awaiting_user_response__"

    # 4️⃣ If waiting for category selection manually
    if conversation_context["stage"] == 2:
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(all_categories):
                matched_category = all_categories[idx]
            else:
                output_manager("❌ Invalid category selection. Try again.")
                return "__awaiting_user_response__"
        else:
            matched_category = None
            for kw in extract_keywords(user_input):
                matched_category = next((cat for cat in all_categories if kw == cat.lower() or (kw in cat.lower() and len(kw) >= 3)), None)
                if matched_category:
                    break

        if matched_category:
            apps_in_category = role_apps[matched_category]
            conversation_context["stage"] = 1
            conversation_context["selected_category"] = matched_category
            conversation_context["available_apps"] = apps_in_category

            output_manager(f"\n📦 Apps under {matched_category.replace('_', ' ').title()}:\n")
            for idx, app in enumerate(apps_in_category, 1):
                output_manager(f"  {idx}. {app}")

            output_manager("\n👉 Enter app name or number:")
            return "__awaiting_user_response__"
        else:
            output_manager("❌ Couldn't find category. Try again.")
            return "__awaiting_user_response__"

    # 5️⃣ Normal first match - Check direct app match first
    keywords = extract_keywords(user_input)
    matched_app = None
    for app in all_apps:
        app_lower = app.lower()
        for kw in keywords:
            if (kw == app_lower) or (kw in app_lower and len(kw) >= 3):
                matched_app = app
                break
        if matched_app:
            break

    if matched_app:
        link = dg_app_links.download_applinks.get(matched_app, "[No link available]")
        output_manager(f"\n📥 {matched_app}: {link}")
        reset_download_context()
        return

    # 6️⃣ If not matched app, try matching category
    matched_category = None
    for category in all_categories:
        category_lower = category.lower()
        for kw in keywords:
            if (kw == category_lower) or (kw in category_lower and len(kw) >= 3):
                matched_category = category
                break
        if matched_category:
            break

    if matched_category:
        apps_in_category = role_apps[matched_category]
        conversation_context["stage"] = 1
        conversation_context["selected_category"] = matched_category
        conversation_context["available_apps"] = apps_in_category

        output_manager(f"\n🤔 It seems you meant the category '{matched_category.replace('_', ' ').title()}'.")
        output_manager(f"Here are the apps available inside {matched_category.replace('_', ' ').title()}:\n")
        for idx, app in enumerate(apps_in_category, 1):
            output_manager(f"  {idx}. {app}")

        output_manager("\n👉 Enter app name or number:")
        return "__awaiting_user_response__"

    # 7️⃣ If neither app nor category matched
    output_manager("❓ App not found. Would you like to see available categories? (yes/no)")
    conversation_context["waiting_for_category_yesno"] = True
    return "__awaiting_user_response__"


# ==========================
# 🔥 Task Functions (Database Access)
# ==========================

conversation_context_access = {
    "stage": 0,
    "matched_db": None,
    "available_dbs": [],
}


# 🔵 Reset function
def reset_access_context():
    conversation_context_access["stage"] = 0
    conversation_context_access["matched_db"] = None
    conversation_context_access["available_dbs"] = []

# 🔵 Access Database Web function
def access_database_web(user_message=None):
    role = current_user_role
    dbs = dg_db.role_based_db.get(role, {})

    if not dbs:
        output_manager("❌ No database access available for your role.")
        reset_access_context()
        return

    available_dbs = list(dbs.keys())
    conversation_context_access["available_dbs"] = available_dbs

    # 1️⃣ First time asking
    if user_message is None:
        output_manager("🔍 Enter the database name you want access to:")
        return "__awaiting_user_response__"

    user_input = user_message.strip().lower()

    # 2️⃣ Handle stages
    if conversation_context_access["stage"] == 1:
        if user_input in ['yes', 'y']:
            output_manager(f"✏️ Why do you need access to '{conversation_context_access['matched_db']}'? (or type 'exit' to cancel)")
            conversation_context_access["stage"] = 2
            return "__awaiting_user_response__"
        else:
            output_manager("❓ Couldn't confidently match. Would you like to see the list of databases you can access? (yes/no)")
            conversation_context_access["stage"] = 3
            return "__awaiting_user_response__"

    if conversation_context_access["stage"] == 2:
        reason = user_input
        if reason in ['exit', 'cancel']:
            output_manager("👋 Access request cancelled. Returning to main menu.")
            reset_access_context()
            return

        db_selected = conversation_context_access["matched_db"]
        spoc_email = dbs.get(db_selected, "[No SPOC email available]")

        output_manager(f"📨 Request sent to {spoc_email} for access to '{db_selected}' with reason: {reason}")
        reset_access_context()
        return

    if conversation_context_access["stage"] == 3:
        if user_input in ['no', 'n']:
            output_manager("👋 Returning to the main menu.")
            reset_access_context()
            return

        if user_input in ['yes', 'y']:
            output_manager("\n📂 Available Databases:")
            for idx, db in enumerate(available_dbs, 1):
                output_manager(f"  {idx}. {db}")
            output_manager("\n👉 Enter the number of the database you want access to:")
            conversation_context_access["stage"] = 4
            return "__awaiting_user_response__"

    if conversation_context_access["stage"] == 4:
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(available_dbs):
                db_selected = available_dbs[idx]
                conversation_context_access["matched_db"] = db_selected
                output_manager(f"✏️ Why do you need access to '{db_selected}'? (or type 'exit' to cancel)")
                conversation_context_access["stage"] = 2
                return "__awaiting_user_response__"
            else:
                output_manager("❌ Invalid selection. Please try again.")
                return "__awaiting_user_response__"

    # 3️⃣ Normal stage 0 - matching database name
    keywords = extract_keywords(user_input)

    matched_db = None
    for kw in keywords:
        matched_db = next((db for db in available_dbs if kw in db.lower()), None)
        if matched_db:
            break

    if matched_db:
        conversation_context_access["matched_db"] = matched_db
        output_manager(f"❓ Did you mean '{matched_db}' database? (yes/no)")
        conversation_context_access["stage"] = 1
        return "__awaiting_user_response__"

    output_manager("❓ Couldn't confidently match. Would you like to see the list of databases you can access? (yes/no)")
    conversation_context_access["stage"] = 3
    return "__awaiting_user_response__"


# ==========================
# 🔥 Task Functions (Field Mapping)
# ==========================


def reset_field_mapping_context():
    conversation_context_field_mapping["stage"] = 0
    conversation_context_field_mapping["predicted_field"] = None
    conversation_context_field_mapping["predicted_table"] = None
    conversation_context_field_mapping["user_input_field"] = None



# Global context for Field Mapping task
conversation_context_field_mapping = {
    "stage": 0,  # 0 = waiting for field name, 1 = waiting for yes/no/exit, 2 = waiting for corrected field name
    "predicted_field": None,
    "predicted_table": None,
    "user_input_field": None
}

def field_mapping_web(user_message=None):
    field_table = dg_field_table_mapping.dg_field_table.copy()
    synonyms = dg_field_mapping.dg_field_synonyms

    # 🛑 First Call: Ask for field name
    if user_message is None:
        output_manager("\n🔍 You are trying to find relevant field names for your data.")
        output_manager("Please provide the field name you want to find:")
        conversation_context_field_mapping["stage"] = 0
        return "__awaiting_user_response__"

    # ✅ Stage 0: Waiting for user to type field name
    if conversation_context_field_mapping["stage"] == 0:
        field_name = user_message.strip().lower()
        conversation_context_field_mapping["user_input_field"] = field_name

        matched_field = None

        # Step 1: Exact match
        if field_name in synonyms:
            matched_field = field_name
        else:
            # Step 2: Check synonyms
            for field, syns in synonyms.items():
                if field_name in syns:
                    matched_field = field
                    break

        # Step 3: If no exact or synonym, use BERT
        if not matched_field:
            all_fields = list(field_table.keys())
            user_emb = sentence_model.encode(field_name, convert_to_tensor=True)
            field_embs = sentence_model.encode(all_fields, convert_to_tensor=True)
            scores = util.cos_sim(user_emb, field_embs)[0]
            top_idx = int(torch.argmax(scores))
            matched_field = all_fields[top_idx]

        matched_table = field_table.get(matched_field)

        # Save into context
        conversation_context_field_mapping["predicted_field"] = matched_field
        conversation_context_field_mapping["predicted_table"] = matched_table

        # Show bot's guess
        output_manager(f"🤖 Closest match I could find is: Field = '{matched_field}', located in Table = '{matched_table}'.")
        output_manager("\n❓ Was this match correct? (yes/no/exit)")

        conversation_context_field_mapping["stage"] = 1
        return "__awaiting_user_response__"

    # ✅ Stage 1: Waiting for user to say yes/no/exit
    if conversation_context_field_mapping["stage"] == 1:
        feedback = user_message.strip().lower()

        if feedback in ["yes", "y"]:
            output_manager("✅ Field mapping task complete.")
            reset_field_mapping_context()
            return

        elif feedback in ["no", "n"]:
            output_manager("\n✏️ Please provide the correct field name:")
            conversation_context_field_mapping["stage"] = 2
            return "__awaiting_user_response__"

        elif feedback in ["exit", "cancel"]:
            output_manager("👋 Exiting field mapping task.")
            reset_field_mapping_context()
            return

        else:
            output_manager("❌ Invalid response. Please reply with 'yes', 'no', or 'exit'.")
            return "__awaiting_user_response__"

    # ✅ Stage 2: Waiting for user to give corrected field name
    if conversation_context_field_mapping["stage"] == 2:
        correct_field = user_message.strip().lower()

        # Update synonyms
        if correct_field not in synonyms:
            synonyms[correct_field] = [conversation_context_field_mapping["user_input_field"]]
        else:
            if conversation_context_field_mapping["user_input_field"] not in synonyms[correct_field]:
                synonyms[correct_field].append(conversation_context_field_mapping["user_input_field"])

        # Optional: Save synonyms to file (if required in your project)
        try:
            with open("dg_field_mapping.py", "w", encoding="utf-8") as f:
                f.write("dg_field_synonyms = ")
                f.write(pprint.pformat(synonyms))
            output_manager("✅ Synonyms updated successfully.")
        except Exception as e:
            output_manager(f"❌ Error updating synonyms file: {e}")

        output_manager("✅ Field mapping task complete.")
        reset_field_mapping_context()
        return


# ==========================
# 🔥 Task Functions (Summarize Context)
# ==========================


conversation_context_summarize = {
    "waiting_for_pdf": False,
}

def reset_summarize_context():
    conversation_context_summarize["waiting_for_pdf"] = False


def summarize_pdf_web(file_path=None):
    if file_path is None:
        output_manager("📄 Please upload your PDF file now (through Upload button).")
        conversation_context_summarize["waiting_for_pdf"] = True
        return "__awaiting_file_upload__"

    if conversation_context_summarize["waiting_for_pdf"]:
        if not os.path.isfile(file_path):
            output_manager("❌ Uploaded file path is invalid. Please try uploading again.")
            reset_summarize_context()
            return

        try:
            raw_text = extract_pdf_text(file_path)
            if not raw_text:
                output_manager("❌ Couldn't extract text from the uploaded PDF. Try another file.")
                reset_summarize_context()
                return

            cleaned_text = clean_text(raw_text)
            summary = generate_summary(cleaned_text, output_manager, save_to_file=False)

            # 📂 Now save summary file under /uploads/ with unique name
            timestamp = int(time.time())
            summary_filename = f"summary_output_{timestamp}.txt"
            summary_path = os.path.join('uploads', summary_filename)

            os.makedirs('uploads', exist_ok=True)

            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(summary)

            output_manager("\n📄 Here is the summary of your PDF:\n")
            output_manager(textwrap.fill(summary, width=100))

            # 🛎️ New: tell user that summary file is saved
            download_link = f"/download/{summary_filename}"
            output_manager(f"\n✅ Summary successfully saved! [Click here to download]({download_link})")

            reset_summarize_context()
            return

        except Exception as e:
            output_manager(f"❌ Something went wrong while processing the uploaded PDF: {e}")
            reset_summarize_context()
            return

    output_manager("❌ Unexpected error in summarizing. Please restart task.")
    reset_summarize_context()
    return


# ==========================
# 🧠 Task Handler
# ==========================


def task_handler(selected_task, user_message=None):
    """
    Handles user tasks for Flask Web chatbot.
    """

    if selected_task == "download":
        return download_apps_web(user_message)

    elif selected_task == "field_mapping":
        return field_mapping_web(user_message)

    elif selected_task == "summarize":
        return summarize_pdf_web(user_message)

    elif selected_task == "access":
        return access_database_web(user_message)

    else:
        output_manager("❌ Task not recognized.")
        return



# ==========================
# 🧠 Authenticate
# ==========================


def authenticate_web_user(username, password):
    user = dg_users_db.users.get(username)

    if user and user['password'] == password:
        global current_user_role
        current_user_role = user['role']
        return True, user
    else:
        return False, None


# ==========================
# 🎯 Chatbot Handler (Main Controller)
# ==========================

# Global to track current task
current_selected_task = None
waiting_for_task_selection = True  # Initially True

def chatbot_handler(user_message):
    global current_selected_task, waiting_for_task_selection

    if not user_message:
        output_manager("❌ Empty input. Please type something.")
        return get_conversation_response()

    user_message = user_message.strip()

    # 🚩 If we are waiting for task selection
    if waiting_for_task_selection:
        task_keys = list(dg_tasks_db.tasks_db.keys())
        available_tasks = {str(idx + 1): task for idx, task in enumerate(task_keys)}
        available_tasks["0"] = "exit"

        if user_message not in available_tasks:
            output_manager("\n📋 Please select a task:")
            for number, task_key in available_tasks.items():
                if task_key != "exit":
                    description = dg_tasks_db.tasks_db.get(task_key, {}).get("description", "")
                    output_manager(f"  {number}. {task_key.replace('_', ' ').title()} - {description}")
            output_manager("  0. Exit")
            return get_conversation_response()

        if user_message == "0":
            output_manager("👋 Goodbye!")
            return get_conversation_response()

        # ✅ User selected a valid task
        current_selected_task = available_tasks[user_message]
        waiting_for_task_selection = False  # Now ready for actual task execution

        output_manager(f"\n✅ You selected: {current_selected_task.replace('_', ' ').title()}.")

        # Immediately start first step of selected task
        task_handler(current_selected_task, None)
        return get_conversation_response()

    # 🚩 If task is already selected and working
    else:
        message = task_handler(current_selected_task, user_message)

        if message == "__task_complete__":
            # 🎯 Task completed - Ask if user wants to continue same task
            friendly_task_name = current_selected_task.replace('_', ' ').title()
            output_manager(f"\n🔄 Would you like to continue with '{friendly_task_name}'? (yes/no):")
            waiting_for_task_selection = False  # Still waiting for user answer
            return get_conversation_response()

        if user_message.lower() in ['yes', 'y']:
            # ✅ Continue with the same task
            task_handler(current_selected_task, None)
            return get_conversation_response()

        if user_message.lower() in ['no', 'n']:
            # ❌ User wants to switch task
            current_selected_task = None
            waiting_for_task_selection = True
            output_manager("\n📋 Please select a new task:")
            task_keys = list(dg_tasks_db.tasks_db.keys())
            available_tasks = {str(idx + 1): task for idx, task in enumerate(task_keys)}
            available_tasks["0"] = "exit"
            for number, task_key in available_tasks.items():
                if task_key != "exit":
                    description = dg_tasks_db.tasks_db.get(task_key, {}).get("description", "")
                    output_manager(f"  {number}. {task_key.replace('_', ' ').title()} - {description}")
            output_manager("  0. Exit")
            return get_conversation_response()

        return get_conversation_response()

def get_conversation_response():
    messages = [msg["text"] for msg in conversation_history]
    conversation_history.clear()
    return "\n".join(messages)
