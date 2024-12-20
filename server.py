from flask import Flask, request, jsonify
from authentication import create_service
import base64
import time
from datetime import datetime
import chromadb

# initialize LLM
from langchain_huggingface import HuggingFaceEndpoint

repo_id = "mistralai/Mistral-7B-Instruct-v0.3"
llm = HuggingFaceEndpoint(repo_id=repo_id, max_new_tokens=20, temperature=0.7)

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
            q='is:unread in:inbox'
        ).execute()
        messages = results.get('messages', [])
        
        if messages:
            for message in messages:
                msg = service.users().messages().get(
                    userId='me', 
                    id=message['id']
                ).execute()
                
                # Get email subject and body
                new_email = {
                    'subject': '',
                    'from_email': '',
                    'to_email': '',
                    'body': ''
                }

                for header in msg['payload']['headers']:
                    if header['name'] == 'Subject':
                        new_email['subject'] = header['value']

                    if header['name'] == 'From':
                        new_email['from_email'] = header['value']
                    
                    if header['name'] == 'To':
                        new_email['to_email'] = header['value']
                
                if 'parts' in msg['payload']:
                    new_email['body'] = base64.urlsafe_b64decode(
                        msg['payload']['parts'][0]['body']['data']
                    ).decode('utf-8')
                else:
                    new_email['body'] = base64.urlsafe_b64decode(
                        msg['payload']['body']['data']
                    ).decode('utf-8')

                # print(f"new email recieved: {new_email}")
                return new_email
                
    except Exception as e:
        print(f"Error: {str(e)}")



@app.route('/webhook', methods=['POST'])
def webhook():
    old_collection = update_collection()
    email = get_unread_messages()
    print('here')
    if email:
        print('got email')
        reply_email = draftEmail(email, old_collection)
        print(f"Reply email body: {reply_email['body']}")
        return jsonify({'status': 'success', 'reply': reply_email}), 200
    else:
        return jsonify({'status': 'no unread messages'}), 200
    
def update_collection():
    chroma_client = chromadb.PersistentClient(path="vectordb")
    old_collection = chroma_client.get_collection(name="email_data")

    return old_collection

    
def draftEmail(email, old_collection):
    # Perform a query search with the email body
    query_results = old_collection.query(
        query_texts=[email["body"]],
        n_results=4
    )
    context_chromadb = query_results["documents"]
    
    # reply for the mail
    reply_subject = f"Re: {email['subject']}"

    # Prompt for the email body
    body_prompt = f"Email Body:\n{email['body']}, Email Subject:\n{email['subject']}\n\nRelevant Context:\n{context_chromadb}\n\nDraft a reply to this email. Include only the body of the email:"
    reply_draft = llm.invoke(body_prompt)

    # Combine subject and body drafts into the final email format
    final_email = {
        "subject": reply_subject.strip(),
        "body": reply_draft.strip(),
        "from_email": email["to_email"],
        "to_email": email["from_email"]
    }

    return final_email

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
