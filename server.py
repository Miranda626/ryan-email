import os
import json
import base64
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
                body = base64.urlsafe_b64decode(
                    payload["body"]["data"]
                ).decode("utf-8")
            
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
        
        service = get_gmail_service()
        
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        result = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        
        return jsonify({"status": "sent", "id": result["id"]})
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
            body = base64.urlsafe_b64decode(
                payload["body"]["data"]
            ).decode("utf-8")
        
        return jsonify({
            "from": sender,
            "subject": subject,
            "date": date,
            "body": body
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
