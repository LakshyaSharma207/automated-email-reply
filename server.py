from flask import Flask, request, jsonify, render_template
from authentication import create_service
import base64
import time
from datetime import datetime
import chromadb
import os
import requests
import atexit
import signal

# initialize LLM
from langchain_huggingface import HuggingFaceEndpoint
repo_id = "mistralai/Mistral-7B-Instruct-v0.3"
llm = HuggingFaceEndpoint(repo_id=repo_id, max_new_tokens=155, temperature=0.7)
audio_url = 'https://api-inference.huggingface.co/models/openai/whisper-large-v3-turbo'

app = Flask(__name__)

"""
Transcribes audio from the given file path using a remote API.

Args:
    audio_file_path (str): The path to the audio file to be transcribed.

Returns:
    str: The transcribed text if successful, None otherwise.
"""
def transcribe_audio(audio_file_path):
    with open(audio_file_path, 'rb') as audio_file:
        audio_data = audio_file.read()

    response = requests.post(audio_url, headers=headers, files={'file': audio_data})

    if response.status_code == 200:
        transcription = response.json()
        return transcription['text']
    else:
        print(f"Error: {response.status_code}, {response.text}")
        return None

"""
Fetches unread messages from the user's inbox and extracts relevant information.

Returns:
    dict: A dictionary containing the subject, from_email, to_email, body, images, and audios of the email.
"""
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
                    'body': '',
                    'images': [],
                    'audios': []
                }

                for header in msg['payload']['headers']:
                    if header['name'] == 'Subject':
                        new_email['subject'] = header['value']

                    if header['name'] == 'From':
                        new_email['from_email'] = header['value']
                    
                    if header['name'] == 'To':
                        new_email['to_email'] = header['value']
                
                if 'parts' in msg['payload']:
                    for part in msg['payload']['parts']:
                        if part['mimeType'].startswith('image/'):
                            attachment_id = part['body']['attachmentId']
                            response = service.users().messages().attachments().get(
                                userId='me',
                                messageId=message['id'],
                                id=attachment_id
                            ).execute()

                            file_data = base64.urlsafe_b64decode(response.get('data').encode('UTF-8'))
                            # save attachments
                            attachments_dir = os.path.join(os.getcwd(), 'image_attachments')
                            if not os.path.exists(attachments_dir):
                                os.makedirs(attachments_dir)
                            save_location = os.path.join(attachments_dir, part['filename'])
                            with open(save_location, 'wb') as f:
                                f.write(file_data)
                            new_email['images'].append(save_location)

                        if part['mimeType'].startswith('audio/'):
                            attachment_id = part['body']['attachmentId']
                            response = service.users().messages().attachments().get(
                                userId='me',
                                messageId=message['id'],
                                id=attachment_id
                            ).execute()

                            file_data = base64.urlsafe_b64decode(response.get('data').encode('UTF-8'))
                            # save audio attachments
                            audio_dir = os.path.join(os.getcwd(), 'audio_attachments')
                            if not os.path.exists(audio_dir):
                                os.makedirs(audio_dir)
                            save_location = os.path.join(audio_dir, part['filename'])
                            with open(save_location, 'wb') as f:
                                f.write(file_data)
                            new_email['audios'].append(save_location)

                            # Transcribe the audio and add the transcription to the email
                            transcription = transcribe_audio(save_location)
                            if transcription:
                                new_email['body'] += f"\n\nTranscription of audio: {transcription}. "

                        # get text body
                        if 'parts' in part:
                            for subpart in part['parts']:
                                if subpart['mimeType'] == 'text/plain':
                                    if 'data' in subpart['body']:
                                        new_email['body'] += base64.urlsafe_b64decode(subpart['body']['data']).decode('UTF-8')
                                    else:
                                        print("No data found in the subpart body.")
                        elif part['mimeType'] == 'text/plain':
                            if 'data' in part['body']:
                                new_email['body'] += base64.urlsafe_b64decode(part['body']['data']).decode('UTF-8')
                            else:
                                print("No data found in the part body.")

                # print(f"new email received: {new_email['body']}, {new_email['attachments']}")
                return new_email
                
    except Exception as e:
        print(f"Error: {str(e)}")

@app.route('/', methods=['GET', 'POST'])
def home():
    emails = []
    if request.method == 'POST':
        # Fetch unread emails when the button is clicked
        email = get_unread_messages()
        if email:
            emails.append(email)

    # Render the template with the emails
    return render_template('index.html', emails=emails)

"""
Updates the email collection from the Chroma database.

Returns:
    Collection: The updated email collection.
"""
def update_collection():
    chroma_client = chromadb.PersistentClient(path="vectordb")
    old_collection = chroma_client.get_collection(name="email_data")

    return old_collection

"""
Drafts a reply email based on the original email and relevant context from the database.

Args:
    email (dict): The original email data.
    old_collection: The collection of email data for context.

Returns:
    dict: A dictionary containing the subject and body of the drafted reply email.
"""
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

"""
Periodically checks for unread emails every 10 seconds.
This function runs in an infinite loop.
"""
def check_emails_periodically():
    while True:
        get_unread_messages()
        time.sleep(10)  # Check every 10 seconds

"""
Handles the reply_all route for the Flask application.

Returns:
    JSON response containing the status and replies to the fetched emails.
"""
@app.route('/reply_all', methods=['POST'])
def reply_all():
    emails = []
    # Fetch unread emails
    email = get_unread_messages()
    if email:
        emails.append(email)
    
    replies = []
    a_collection = update_collection()
    for email in emails:
        reply_email = draftEmail(email, a_collection)
        replies.append(reply_email)

    # print(replies)
    return jsonify({'status': 'success', 'replies': replies}), 200

"""
Cleans up resources before the application shuts down.
"""
def cleanup():
    print("Cleaning up resources...")

atexit.register(cleanup)

"""
Handles termination signals to gracefully shut down the application.

Args:
    sig: The signal number.
    frame: The current stack frame.
"""
def signal_handler(sig, frame):
    print("Signal received, shutting down...")
    cleanup()  # Call cleanup explicitly if needed
    exit(0)

signal.signal(signal.SIGINT, signal_handler)

if __name__ == '__main__':
    # Gmail API setup
    client_secret_file = 'client_secret.json'
    API_SERVICE_NAME = 'gmail'
    API_VERSION = 'v1'
    SCOPES = ['https://mail.google.com/']
    service = create_service(client_secret_file, API_SERVICE_NAME, API_VERSION, SCOPES)
    sec_key = os.environ.get('HF_TOKEN')
    headers = {
        'Authorization': f'Bearer {sec_key}',
        'Content-Type': 'application/json'
    }

    # Start email checking in a separate thread
    import threading
    email_thread = threading.Thread(target=check_emails_periodically)
    email_thread.daemon = True
    email_thread.start()
    
    # Start Flask server
    try:
       app.run(port=5000, debug=True)
    except KeyboardInterrupt:
       print("Shutting down....")
