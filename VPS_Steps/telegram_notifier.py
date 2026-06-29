import os
import requests
import logging
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8984558925:AAHjRpUWbxoi9hvFoZKevoIKaLklCP1hQ-o")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1004392602002")       # Group ID for replies/general updates
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "-1003911765158")    # Channel ID for original ideas

TOPIC_NAME_MAPPING = {
    "hanzidegushi": "Lê Lê kể chữ",
    "idiom": "Thành ngữ thực chiến",
    "vs_series": "Tiếng Trung thực chiến",
    "dialogue": "Hội thoại thực chiến",
    "slang": "Tiếng Trung lóng"
}

def send_channel_post(category: str, character: str, idea: str, row_num: int, drive_folder_url: str) -> int:
    """
    Sends the initial idea post to the Telegram Channel.
    Returns the message_id (PostID) of the posted channel message.
    """
    topic_name = TOPIC_NAME_MAPPING.get(category, category)
    text = (
        f"Topic: {topic_name}\n\n"
        f"Idea: <code>{character}</code>\n"
        f"<code>{idea}</code>\n"
        f"(dòng số: {row_num})\n\n"
        f"GDrive <a href=\"{drive_folder_url}\">link</a>"
    )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True}
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        post_id = data["result"]["message_id"]
        logger.info(f"Telegram channel post successful. Message ID: {post_id}")
        return post_id
    except Exception as e:
        logger.error(f"Failed to post to Telegram channel: {e}")
        if 'response' in locals():
            logger.error(f"Response content: {response.text}")
        return None

def get_group_message_id(channel_message_id: int) -> int:
    """
    Polls the Bot API getUpdates endpoint to find the group's message ID
    for the automatically forwarded channel post.
    """
    import time
    updates_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    for attempt in range(6):
        try:
            logger.info(f"Querying getUpdates to resolve group message ID for channel post {channel_message_id} (attempt {attempt+1}/6)...")
            response = requests.get(updates_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            for update in data.get("result", []):
                if "message" in update:
                    msg = update["message"]
                    chat = msg.get("chat", {})
                    # Ensure it's in the linked group
                    if str(chat.get("id")) == str(CHAT_ID):
                        fwd_chat = msg.get("forward_from_chat", {})
                        # Match original channel ID and original message ID
                        if str(fwd_chat.get("id")) == str(CHANNEL_ID):
                            fwd_msg_id = msg.get("forward_from_message_id")
                            if fwd_msg_id == int(channel_message_id):
                                group_msg_id = msg.get("message_id")
                                logger.info(f"Resolved Channel PostID {channel_message_id} -> Group MessageID {group_msg_id}")
                                return group_msg_id
        except Exception as e:
            logger.error(f"Error querying getUpdates: {e}")
        time.sleep(2.0)
    logger.warning(f"Could not resolve Group MessageID for Channel PostID {channel_message_id}")
    return None

def get_reply_parameters(reply_to_post_id: str) -> dict:
    if not reply_to_post_id:
        return None
        
    reply_to_post_id_str = str(reply_to_post_id).strip()
    if not reply_to_post_id_str or reply_to_post_id_str.lower() in ["none", "null", "n/a", ""]:
        return None
        
    channel_post_id = reply_to_post_id_str
    group_msg_id = None
    
    if "," in reply_to_post_id_str:
        parts = reply_to_post_id_str.split(",")
        channel_post_id = parts[0].strip()
        if len(parts) > 1 and parts[1].strip():
            group_msg_id = parts[1].strip()
            
    if not group_msg_id:
        # Try to resolve dynamically via getUpdates
        try:
            resolved_id = get_group_message_id(int(channel_post_id))
            if resolved_id:
                group_msg_id = str(resolved_id)
        except Exception:
            pass
            
    if group_msg_id:
        logger.info(f"Using Group MessageID {group_msg_id} for comment reply.")
        return {
            "message_id": int(group_msg_id),
            "chat_id": CHAT_ID
        }
    else:
        logger.info(f"Using Channel PostID {channel_post_id} as fallback channel reply.")
        return {
            "message_id": int(channel_post_id),
            "chat_id": CHANNEL_ID
        }

def send_message(text: str, reply_to_post_id: str = None) -> bool:
    """
    Sends a text message to the Telegram group, optionally replying to a message inside the group.
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True}
    }
    reply_params = get_reply_parameters(reply_to_post_id)
    if reply_params:
        payload["reply_parameters"] = reply_params
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        logger.info("Telegram message sent successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        if 'response' in locals():
            logger.error(f"Response content: {response.text}")
        return False

def send_photo(photo_path: str, caption: str = "", reply_to_post_id: str = None) -> bool:
    """
    Sends a photo to the Telegram group, optionally replying to a message inside the group.
    """
    if not os.path.exists(photo_path):
        logger.error(f"Photo path does not exist: {photo_path}")
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    data = {
        "chat_id": CHAT_ID,
        "caption": caption,
        "parse_mode": "HTML"
    }
    reply_params = get_reply_parameters(reply_to_post_id)
    if reply_params:
        data["reply_parameters"] = json.dumps(reply_params)
    try:
        with open(photo_path, 'rb') as photo_file:
            files = {'photo': photo_file}
            response = requests.post(url, data=data, files=files, timeout=30)
            response.raise_for_status()
            logger.info(f"Telegram photo {photo_path} sent successfully.")
            return True
    except Exception as e:
        logger.error(f"Failed to send Telegram photo: {e}")
        if 'response' in locals():
            logger.error(f"Response content: {response.text}")
        return False

def send_document(doc_path: str, caption: str = "", reply_to_post_id: str = None) -> bool:
    """
    Sends a document to the Telegram group, optionally replying to a message inside the group.
    """
    if not os.path.exists(doc_path):
        logger.error(f"Document path does not exist: {doc_path}")
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    data = {
        "chat_id": CHAT_ID,
        "caption": caption,
        "parse_mode": "HTML"
    }
    try:
        import json
        reply_params = get_reply_parameters(reply_to_post_id)
        if reply_params:
            data["reply_parameters"] = json.dumps(reply_params)
        with open(doc_path, 'rb') as doc_file:
            files = {'document': doc_file}
            response = requests.post(url, data=data, files=files, timeout=60)
            response.raise_for_status()
            logger.info(f"Telegram document {doc_path} sent successfully.")
            return True
    except Exception as e:
        logger.error(f"Failed to send Telegram document: {e}")
        if 'response' in locals():
            logger.error(f"Response content: {response.text}")
        return False

def send_video(video_path: str, caption: str = "", reply_to_post_id: str = None) -> bool:
    """
    Sends a video to the Telegram group, optionally replying to a message inside the group.
    """
    if not os.path.exists(video_path):
        logger.error(f"Video path does not exist: {video_path}")
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    data = {
        "chat_id": CHAT_ID,
        "caption": caption,
        "parse_mode": "HTML"
    }
    try:
        import json
        reply_params = get_reply_parameters(reply_to_post_id)
        if reply_params:
            data["reply_parameters"] = json.dumps(reply_params)
        with open(video_path, 'rb') as video_file:
            files = {'video': video_file}
            response = requests.post(url, data=data, files=files, timeout=120)
            response.raise_for_status()
            logger.info(f"Telegram video {video_path} sent successfully.")
            return True
    except Exception as e:
        logger.error(f"Failed to send Telegram video: {e}")
        if 'response' in locals():
            logger.error(f"Response content: {response.text}")
        return False
def send_telegram_notification(text: str, reply_to_post_id: str = None) -> bool:
    """
    Backward-compatible alias for send_message.
    """
    return send_message(text, reply_to_post_id=reply_to_post_id)

if __name__ == "__main__":
    # Test sending a message
    send_message("<b>[Test]</b> Hệ thống thông báo Telegram Bot cho lelehoctiengtrung đã hoạt động!")

