import os
import json
import logging
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import time
import random

logger = logging.getLogger(__name__)

# Paths and configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
USER_OAUTH_FILE = os.path.join(SCRIPT_DIR, "user_oauth2.json")
SERVICE_ACCOUNT_FILE = os.path.join(SCRIPT_DIR, "service_account.json")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Caching objects to reduce API calls (Read/Write requests)
_gspread_client = None
_spreadsheets = {}
_worksheets = {}

def retry_on_429(func, *args, max_retries=3, backoff_factor=2, **kwargs):
    """
    Executes a function and retries with exponential backoff if a 429 error occurs.
    """
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            err_msg = str(e)
            is_429 = False
            
            # Check for APIError, status code, or text indicating quota limits
            if "429" in err_msg or "quota" in err_msg.lower() or "limit" in err_msg.lower():
                is_429 = True
                
            if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                if e.response.status_code == 429:
                    is_429 = True
            elif hasattr(e, 'code'):
                if e.code == 429:
                    is_429 = True
                    
            if is_429 and attempt < max_retries - 1:
                sleep_time = (backoff_factor ** attempt) + random.uniform(1.5, 4.0)
                logger.warning(
                    f"⚠️ Google API 429/Quota limit hit in {func.__name__ if hasattr(func, '__name__') else 'API call'}. "
                    f"Retrying in {sleep_time:.2f}s... (Attempt {attempt+1}/{max_retries})"
                )
                time.sleep(sleep_time)
            else:
                raise

def patch_gspread_methods():
    """
    Monkeypatches key gspread methods to automatically retry on 429 quota errors.
    """
    def wrap_method(original_method):
        def wrapper(*args, **kwargs):
            return retry_on_429(original_method, *args, **kwargs)
        return wrapper

    # Worksheet methods
    ws_methods = ['get_all_values', 'row_values', 'update_cell', 'update_cells', 'update', 'batch_get']
    for method_name in ws_methods:
        if hasattr(gspread.Worksheet, method_name):
            original = getattr(gspread.Worksheet, method_name)
            if not getattr(original, '_wrapped_429', False):
                wrapped = wrap_method(original)
                wrapped._wrapped_429 = True
                setattr(gspread.Worksheet, method_name, wrapped)

    # Spreadsheet methods
    ss_methods = ['worksheet', 'values_batch_get']
    for method_name in ss_methods:
        if hasattr(gspread.Spreadsheet, method_name):
            original = getattr(gspread.Spreadsheet, method_name)
            if not getattr(original, '_wrapped_429', False):
                wrapped = wrap_method(original)
                wrapped._wrapped_429 = True
                setattr(gspread.Spreadsheet, method_name, wrapped)

    # Client methods
    if hasattr(gspread.Client, 'open_by_key'):
        original = getattr(gspread.Client, 'open_by_key')
        if not getattr(original, '_wrapped_429', False):
            wrapped = wrap_method(original)
            wrapped._wrapped_429 = True
            setattr(gspread.Client, 'open_by_key', wrapped)

# Apply patch when the module is loaded
patch_gspread_methods()

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
    global _gspread_client
    if _gspread_client is None:
        creds = get_sheets_credentials()
        _gspread_client = gspread.authorize(creds)
    return _gspread_client

def get_drive_service():
    creds = get_drive_credentials()
    return build('drive', 'v3', credentials=creds)

def get_spreadsheet(spreadsheet_id):
    global _spreadsheets
    if spreadsheet_id not in _spreadsheets:
        gc = get_gspread_client()
        _spreadsheets[spreadsheet_id] = gc.open_by_key(spreadsheet_id)
    return _spreadsheets[spreadsheet_id]

def get_worksheet(spreadsheet_id, sheet_name):
    cache_key = (spreadsheet_id, sheet_name)
    global _worksheets
    if cache_key not in _worksheets:
        sh = get_spreadsheet(spreadsheet_id)
        _worksheets[cache_key] = sh.worksheet(sheet_name)
    return _worksheets[cache_key]

def create_drive_folder(folder_name, parent_id):
    """
    Creates a folder in Google Drive.
    """
    def _run():
        service = get_drive_service()
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id] if parent_id else []
        }
        folder = service.files().create(body=file_metadata, fields='id').execute()
        folder_id = folder.get('id')
        folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
        logger.info(f"Created Google Drive folder '{folder_name}' with ID: {folder_id}")
        return folder_id, folder_url
    return retry_on_429(_run)

def upload_file_to_drive(local_path, filename, folder_id, mime_type=None):
    """
    Uploads a local file to a Google Drive folder.
    Returns (file_id, web_view_link)
    """
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Local file not found: {local_path}")
        
    def _run():
        service = get_drive_service()
        file_metadata = {
            'name': filename,
            'parents': [folder_id] if folder_id else []
        }
        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        logger.info(f"Uploaded file '{filename}' to folder '{folder_id}'. File ID: {file.get('id')}")
        return file.get('id'), file.get('webViewLink')
    return retry_on_429(_run)

def download_file_from_drive(file_id, local_path):
    """
    Downloads a file from Google Drive to a local path.
    """
    def _run():
        service = get_drive_service()
        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(local_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        logger.info(f"Downloaded file ID '{file_id}' to local path '{local_path}'")
        return True
    return retry_on_429(_run)

def list_files_in_folder(folder_id):
    """
    Lists files in a specific Google Drive folder.
    """
    def _run():
        service = get_drive_service()
        query = f"'{folder_id}' in parents and trashed = false"
        results = []
        page_token = None
        while True:
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
        return results
    return retry_on_429(_run)

def update_sheet_cells_batch(sheet, row, updates_dict, headers=None):
    """
    Updates cells in a specific row. Accepts optional headers to avoid extra read request.
    """
    if headers is None:
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
