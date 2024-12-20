# Required imports for Google API authentication and service creation
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

def create_service(client_secret_file, api_name, api_version, *scopes, prefix=''):
    """
    Creates and returns an authenticated Google API service instance.
    
    Args:
        client_secret_file (str): Path to the client secret JSON file
        api_name (str): Name of the Google API service (e.g. 'gmail')
        api_version (str): Version of the API to use (e.g. 'v1')
        scopes (list): OAuth scopes required for the API
        prefix (str): Optional prefix for the token file name
    
    Returns:
        service: Authenticated Google API service instance or None if creation fails
    """
    # Store parameters in constants
    CLIENT_SECRET_FILE = client_secret_file
    API_SERVICE_NAME = api_name
    API_VERSION = api_version
    SCOPES = [scope for scope in scopes[0]]

    creds = None    
    working_dir = os.getcwd()
    token_dir = 'token files'
    token_file = f'token_{API_SERVICE_NAME}_{API_VERSION}{prefix}.json'

    # Create token directory if it doesn't exist
    if not os.path.exists(os.path.join(working_dir, token_dir)):
        os.mkdir(os.path.join(working_dir, token_dir))

    # Load existing credentials if available
    if os.path.exists(os.path.join(working_dir, token_dir, token_file)):
        # print("EXISTS")
        creds = Credentials.from_authorized_user_file(os.path.join(working_dir, token_dir, token_file), SCOPES)
    
    # Refresh or create new credentials if needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Start OAuth2 flow for new credentials
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for future use
        with open(os.path.join(working_dir, token_dir, token_file), 'w') as token:
            token.write(creds.to_json())
    try:
        # Create and return the service instance
        service = build(API_SERVICE_NAME, API_VERSION, credentials=creds, static_discovery=False)
        print(API_SERVICE_NAME, API_VERSION, 'service created successfully')
        return service

    except Exception as e:
        # Handle service creation failure
        print (e)
        print(f'Failed to create service instance for {API_SERVICE_NAME}')
        os.remove(os.path.join(working_dir, token_dir, token_file))
        return None