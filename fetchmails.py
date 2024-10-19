from simplegmail import Gmail

# Authenticate and create a Gmail instance
gmail = Gmail()

# Get unread messages in your inbox
unread_messages = gmail.get_unread_inbox()

# Extract relevant information from each message
message_data = []
for message in unread_messages:
    message_data.append({
        "subject": message.subject,
        "date": message.date,
        "body": message.plain  # or message.html for HTML content
    })

# export message data to a csv file
import csv

with open("message_data.csv", "w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["Subject", "Date", "Body"])
    for message in message_data:
        writer.writerow([message["subject"], message["date"], message["body"]])
