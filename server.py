from flask import Flask, request, jsonify
from fetch_mails import create_service
import base64
import time
from datetime import datetime

app = Flask(__name__)

# Gmail API setup
client_secret_file = 'client_secret.json'
API_SERVICE_NAME = 'gmail'
API_VERSION = 'v1'
SCOPES = ['https://mail.google.com/']
service = create_service(client_secret_file, API_SERVICE_NAME, API_VERSION, SCOPES)

def get_unread_messages():
    try:
        # Get unread messages from inbox
        results = service.users().messages().list(
            userId='me',
            labelIds=['INBOX', 'UNREAD']
        ).execute()
        
        messages = results.get('messages', [])
        
        if messages:
            for message in messages:
                msg = service.users().messages().get(
                    userId='me', 
                    id=message['id']
                ).execute()
                
                # Get email subject and body
                subject = ''
                body = ''
                
                for header in msg['payload']['headers']:
                    if header['name'] == 'Subject':
                        subject = header['value']
                
                if 'parts' in msg['payload']:
                    body = base64.urlsafe_b64decode(
                        msg['payload']['parts'][0]['body']['data']
                    ).decode('utf-8')
                else:
                    body = base64.urlsafe_b64decode(
                        msg['payload']['body']['data']
                    ).decode('utf-8')
                
                print(f"\nNew email received at {datetime.now()}")
                print(f"Subject: {subject}")
                
                # Mark message as read
                # service.users().messages().modify(
                #     userId='me',
                #     id=message['id'],
                #     body={'removeLabelIds': ['UNREAD']}
                # ).execute()
                
    except Exception as e:
        print(f"Error: {str(e)}")

@app.route('/webhook', methods=['POST'])
def webhook():
    get_unread_messages()
    return jsonify({'status': 'success'}), 200

def check_emails_periodically():
    while True:
        get_unread_messages()
        time.sleep(10)  # Check every 10 seconds

if __name__ == '__main__':
    # Start email checking in a separate thread
    import threading
    email_thread = threading.Thread(target=check_emails_periodically)
    email_thread.daemon = True
    email_thread.start()
    
    # Start Flask server
    app.run(port=5000, debug=True)
