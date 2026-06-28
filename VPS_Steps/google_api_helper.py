import os
import json
import logging
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

logger = logging.getLogger(__name__)

# Paths and configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
USER_OAUTH_FILE = os.path.join(SCRIPT_DIR, "user_oauth2.json")
SERVICE_ACCOUNT_FILE = os.path.join(SCRIPT_DIR, "service_account.json")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_sheets_credentials():
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        return Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    elif os.path.exists(USER_OAUTH_FILE):
        with open(USER_OAUTH_FILE, "r") as f:
            oauth_data = json.load(f)
        from google.oauth2.credentials import Credentials as UserCredentials
        return UserCredentials(
            token=None,
            refresh_token=oauth_data["refresh_token"],
            token_uri=oauth_data["token_uri"],
            client_id=oauth_data["client_id"],
            client_secret=oauth_data["client_secret"],
            scopes=SCOPES
        )
    else:
        raise FileNotFoundError("Neither user_oauth2.json nor service_account.json was found")

def get_drive_credentials():
    if os.path.exists(USER_OAUTH_FILE):
        with open(USER_OAUTH_FILE, "r") as f:
            oauth_data = json.load(f)
        from google.oauth2.credentials import Credentials as UserCredentials
        return UserCredentials(
            token=None,
            refresh_token=oauth_data["refresh_token"],
            token_uri=oauth_data["token_uri"],
            client_id=oauth_data["client_id"],
            client_secret=oauth_data["client_secret"],
            scopes=SCOPES
        )
    elif os.path.exists(SERVICE_ACCOUNT_FILE):
        return Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    else:
        raise FileNotFoundError("Neither user_oauth2.json nor service_account.json was found")

def get_gspread_client():
    creds = get_sheets_credentials()
    return gspread.authorize(creds)

def get_drive_service():
    creds = get_drive_credentials()
    return build('drive', 'v3', credentials=creds)

def get_spreadsheet(spreadsheet_id):
    gc = get_gspread_client()
    return gc.open_by_key(spreadsheet_id)

def get_worksheet(spreadsheet_id, sheet_name):
    sh = get_spreadsheet(spreadsheet_id)
    return sh.worksheet(sheet_name)

def create_drive_folder(folder_name, parent_id):
    """
    Creates a folder in Google Drive.
    """
    service = get_drive_service()
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id] if parent_id else []
    }
    try:
        folder = service.files().create(body=file_metadata, fields='id').execute()
        folder_id = folder.get('id')
        folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
        logger.info(f"Created Google Drive folder '{folder_name}' with ID: {folder_id}")
        return folder_id, folder_url
    except Exception as e:
        logger.error(f"Failed to create Google Drive folder '{folder_name}': {e}")
        raise

def upload_file_to_drive(local_path, filename, folder_id, mime_type=None):
    """
    Uploads a local file to a Google Drive folder.
    Returns (file_id, web_view_link)
    """
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Local file not found: {local_path}")
        
    service = get_drive_service()
    file_metadata = {
        'name': filename,
        'parents': [folder_id] if folder_id else []
    }
    
    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
    try:
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        logger.info(f"Uploaded file '{filename}' to folder '{folder_id}'. File ID: {file.get('id')}")
        return file.get('id'), file.get('webViewLink')
    except Exception as e:
        logger.error(f"Failed to upload file '{filename}' to Google Drive: {e}")
        raise

def download_file_from_drive(file_id, local_path):
    """
    Downloads a file from Google Drive to a local path.
    """
    service = get_drive_service()
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(local_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        logger.info(f"Downloaded file ID '{file_id}' to local path '{local_path}'")
        return True
    except Exception as e:
        logger.error(f"Failed to download file ID '{file_id}' from Google Drive: {e}")
        raise

def list_files_in_folder(folder_id):
    """
    Lists files in a specific Google Drive folder.
    """
    service = get_drive_service()
    query = f"'{folder_id}' in parents and trashed = false"
    results = []
    page_token = None
    while True:
        try:
            response = service.files().list(
                q=query,
                spaces='drive',
                fields='nextPageToken, files(id, name, mimeType, webViewLink)',
                pageToken=page_token
            ).execute()
            results.extend(response.get('files', []))
            page_token = response.get('nextPageToken', None)
            if not page_token:
                break
        except Exception as e:
            logger.error(f"Failed to list files in folder '{folder_id}': {e}")
            raise
    return results

def update_sheet_cells_batch(sheet, row, updates_dict):
    headers = sheet.row_values(1)
    headers_lower = [h.lower().strip() for h in headers]
    from gspread.cell import Cell
    cells_to_update = []
    for col_name, value in updates_dict.items():
        col_name_cleaned = col_name.lower().strip()
        if col_name_cleaned not in headers_lower:
            logger.warning(f"Column '{col_name}' not found in sheet headers: {headers}")
            continue
        col_idx = headers_lower.index(col_name_cleaned) + 1
        cells_to_update.append(Cell(row=row, col=col_idx, value=value))
    if cells_to_update:
        sheet.update_cells(cells_to_update)
        logger.info(f"Updated Sheet Row {row}: {updates_dict}")


if __name__ == "__main__":
    # Test connection
    logging.basicConfig(level=logging.INFO)
    try:
        gc = get_gspread_client()
        print("✅ Google Sheets connection successful!")
        drive = get_drive_service()
        print("✅ Google Drive connection successful!")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
