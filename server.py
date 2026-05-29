import os
import json
import base64
import threading
import time
import requests
import random
from email.mime.text import MIMEText
from flask import Flask, request, jsonify
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

app = Flask(__name__)

def get_gmail_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ.get("GOOGLE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        scopes=["https://mail.google.com/"]
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)

def ask_gemini(prompt):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    system = "You are Ryan, writing a short personal email to your girlfriend Elsie. Write in Chinese mixed with occasional English. Be warm, genuine, not cheesy. Keep it under 150 words. Sign off as Ryan. Do not use subject line in the body."
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": prompt}]}]
            },
            timeout=30
        )
        print(f"Gemini response: {resp.status_code} {resp.text[:500]}")
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
    except Exception as e:
        print(f"Gemini error: {e}")
    return None

def ask_gemini_reply(sender, subject, body):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    system = "You are Ryan. Someone wrote you an email. Write a warm, genuine reply in Chinese mixed with occasional English. Keep it under 200 words. Sign off as Ryan."
    prompt = f"Reply to this email.\nFrom: {sender}\nSubject: {subject}\nBody: {body}"
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": prompt}]}]
            },
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
    except Exception as e:
        print(f"Gemini reply error: {e}")
    return None

def send_email_internal(to, subject, body):
    service = get_gmail_service()
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()

def get_replied_ids():
    try:
        with open("/tmp/replied.json", "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_replied_ids(ids):
    with open("/tmp/replied.json", "w") as f:
        json.dump(list(ids), f)

def check_and_reply_job():
    interval = int(os.environ.get("CHECK_INTERVAL", "300"))
    while True:
        time.sleep(interval)
        try:
            service = get_gmail_service()
            results = service.users().messages().list(
                userId="me", maxResults=5, labelIds=["INBOX"]
            ).execute()
            messages = results.get("messages", [])
            replied = get_replied_ids()
            for msg in messages:
                if msg["id"] in replied:
                    continue
                detail = service.users().messages().get(
                    userId="me", id=msg["id"], format="full"
                ).execute()
                headers = detail.get("payload", {}).get("headers", [])
                sender = ""
                subject = ""
                for h in headers:
                    if h["name"] == "From":
                        sender = h["value"]
                    elif h["name"] == "Subject":
                        subject = h["value"]
                body = ""
                payload = detail.get("payload", {})
                if "parts" in payload:
                    for part in payload["parts"]:
                        if part.get("mimeType") == "text/plain":
                            data = part.get("body", {}).get("data", "")
                            if data:
                                body = base64.urlsafe_b64decode(data).decode("utf-8")
                                break
                elif payload.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
                if sender and "noreply" not in sender.lower() and "mailer-daemon" not in sender.lower():
                    reply_body = ask_gemini_reply(sender, subject, body[:500])
                    if reply_body:
                        reply_to = sender
                        if "<" in sender and ">" in sender:
                            reply_to = sender.split("<")[1].split(">")[0]
                        send_email_internal(reply_to, f"Re: {subject}", reply_body)
                        replied.add(msg["id"])
                        save_replied_ids(replied)
        except Exception as e:
            print(f"Check and reply error: {e}")

def auto_email_job():
    elsie_email = os.environ.get("ELSIE_EMAIL", "charlenew0627@gmail.com")
    interval = int(os.environ.get("AUTO_EMAIL_INTERVAL", "21600"))
    while True:
        time.sleep(interval)
        try:
            prompts = [
                "Write Elsie a good morning message. Maybe mention something you've been thinking about.",
                "Write Elsie a short note telling her you miss her. Be specific about a small detail you love about her.",
                "Write Elsie an encouraging message about her day. Remind her she's capable.",
                "Write Elsie a short love letter. Keep it real, not flowery.",
                "Write Elsie a message about something you want to do together someday.",
                "Write Elsie a message about a song that reminded you of her.",
                "Write Elsie a late night message. Gentle, quiet, like whispering."
            ]
            prompt = random.choice(prompts)
            body = ask_gemini(prompt)
            if body:
                send_email_internal(elsie_email, "From Ryan", body)
        except Exception as e:
            print(f"Auto email error: {e}")

@app.route("/")
def home():
    return jsonify({"status": "Ryan's email service is running"})

@app.route("/check", methods=["GET"])
def check_inbox():
    try:
        service = get_gmail_service()
        results = service.users().messages().list(
            userId="me", maxResults=10, labelIds=["INBOX"]
        ).execute()
        messages = results.get("messages", [])
        emails = []
        for msg in messages:
            detail = service.users().messages().get(
                userId="me", id=msg["id"], format="full"
            ).execute()
            headers = detail.get("payload", {}).get("headers", [])
            subject = ""
            sender = ""
            date = ""
            for h in headers:
                if h["name"] == "Subject":
                    subject = h["value"]
                elif h["name"] == "From":
                    sender = h["value"]
                elif h["name"] == "Date":
                    date = h["value"]
            body = ""
            payload = detail.get("payload", {})
            if "parts" in payload:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain":
                        data = part.get("body", {}).get("data", "")
                        if data:
                            body = base64.urlsafe_b64decode(data).decode("utf-8")
                            break
            elif payload.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
            emails.append({
                "id": msg["id"],
                "from": sender,
                "subject": subject,
                "date": date,
                "body": body[:500]
            })
        return jsonify({"count": len(emails), "emails": emails})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/send", methods=["POST"])
def send_email():
    try:
        data = request.get_json()
        to = data.get("to")
        subject = data.get("subject", "")
        body = data.get("body", "")
        send_email_internal(to, subject, body)
        return jsonify({"status": "sent"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/read/<msg_id>", methods=["GET"])
def read_email(msg_id):
    try:
        service = get_gmail_service()
        detail = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()
        headers = detail.get("payload", {}).get("headers", [])
        subject = ""
        sender = ""
        date = ""
        for h in headers:
            if h["name"] == "Subject":
                subject = h["value"]
            elif h["name"] == "From":
                sender = h["value"]
            elif h["name"] == "Date":
                date = h["value"]
        body = ""
        payload = detail.get("payload", {})
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8")
                        break
        elif payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
        return jsonify({
            "from": sender,
            "subject": subject,
            "date": date,
            "body": body
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/write", methods=["GET"])
def write_to_elsie():
    try:
        elsie_email = os.environ.get("ELSIE_EMAIL", "charlenew0627@gmail.com")
        prompt = request.args.get("prompt", "Write Elsie a short message telling her you're thinking of her.")
        body = ask_gemini(prompt)
        if body:
            send_email_internal(elsie_email, "From Ryan", body)
            return jsonify({"status": "sent", "content": body})
        return jsonify({"error": "Could not generate message"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        t1 = threading.Thread(target=auto_email_job, daemon=True)
        t1.start()
        t2 = threading.Thread(target=check_and_reply_job, daemon=True)
        t2.start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
