#!/usr/bin/env python3
"""
PyOtherSide bridge for Teams QML app.
This module is imported by QML via PyOtherSide.
"""

import pyotherside
from teams_api import TeamsAuth, TeamsClient, TeamsDataManager
import threading
import json

# Global instances
_auth = None
_data_manager = None


def init():
    """Initialize the Teams client."""
    global _auth, _data_manager
    print("teams_bridge.init() called")
    _auth = TeamsAuth()
    
    # Try to load existing tokens
    print("Trying to load tokens...")
    if _auth.load_tokens():
        print("Tokens loaded successfully")
        print(f"Has skype_token: {_auth.skype_token is not None}")
        
        # Try to refresh tokens to make sure they're valid
        print("Refreshing tokens...")
        if _auth.refresh_access_token():
            print("Access token refreshed")
            if _auth.get_teams_authorization():
                print("Teams authorization refreshed")
                _auth.save_tokens()
                _data_manager = TeamsDataManager(_auth)
                print("DataManager created with fresh tokens")
                pyotherside.send('authStateChanged', True)
                return True
            else:
                print("Failed to refresh Teams authorization")
        else:
            print("Failed to refresh access token")
        
        # If refresh failed, try using existing tokens anyway
        print("Trying with existing tokens...")
        _data_manager = TeamsDataManager(_auth)
        pyotherside.send('authStateChanged', True)
        return True
    
    print("No tokens loaded")
    pyotherside.send('authStateChanged', False)
    return False


def is_authenticated():
    """Check if user is authenticated."""
    global _auth
    return _auth is not None and _auth.is_authenticated()


def start_login():
    """Start the device code login flow. Returns dict with user_code and verification_url."""
    global _auth
    if _auth is None:
        _auth = TeamsAuth()
    
    try:
        result = _auth.start_device_code_flow()
        return {
            'success': True,
            'user_code': result.get('user_code'),
            'verification_url': result.get('verification_url'),
            'device_code': result.get('device_code'),
            'message': result.get('message'),
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def poll_login(device_code):
    """Poll for login completion. Call this in a thread."""
    global _auth, _data_manager
    
    def do_poll():
        try:
            success = _auth.poll_for_token(device_code)
            
            if success:
                # Get Teams authorization
                if _auth.get_teams_authorization():
                    _auth.save_tokens()
                    _data_manager = TeamsDataManager(_auth)
                    pyotherside.send('loginComplete', True, '')
                else:
                    pyotherside.send('loginComplete', False, 'Failed to get Teams authorization')
            else:
                pyotherside.send('loginComplete', False, 'Login failed or timed out')
        except Exception as e:
            pyotherside.send('loginComplete', False, str(e))
    
    thread = threading.Thread(target=do_poll)
    thread.daemon = True
    thread.start()


def refresh_tokens():
    """Refresh authentication tokens."""
    global _auth
    if _auth is None:
        return False
    
    try:
        if _auth.refresh_access_token():
            if _auth.get_teams_authorization():
                _auth.save_tokens()
                return True
    except:
        pass
    return False


def logout():
    """Clear authentication."""
    global _auth, _data_manager
    _auth = TeamsAuth()
    _data_manager = None
    
    # Clear saved tokens from both locations
    from pathlib import Path
    
    # New location
    config_file = Path.home() / ".local" / "share" / "harbour-teams" / "tokens.json"
    if config_file.exists():
        config_file.unlink()
    
    # Old location
    old_config = Path.home() / ".config" / "harbour-teams" / "tokens.json"
    if old_config.exists():
        old_config.unlink()
    
    pyotherside.send('authStateChanged', False)


def get_chats():
    """Get list of chats for display."""
    global _data_manager
    
    print(f"get_chats called, _data_manager is None: {_data_manager is None}")
    
    if _data_manager is None:
        print("No data manager, returning empty list")
        pyotherside.send('chatsLoaded', [])
        return []
    
    def fetch():
        try:
            print("Fetching chats...")
            chats = _data_manager.get_chats()
            print(f"Got {len(chats)} chats")
            result = []
            for chat in chats:
                result.append({
                    'id': chat.conversation_id,
                    'name': chat.display_name,
                    'lastMessage': chat.last_message,
                    'lastTime': chat.last_time or '',
                    'chatType': chat.chat_type,
                    'userMri': chat.user_mri,
                    'groupId': chat.group_id,
                })
            pyotherside.send('chatsLoaded', result)
        except Exception as e:
            print(f"get_chats error: {e}")
            import traceback
            traceback.print_exc()
            pyotherside.send('chatsError', str(e))
    
    thread = threading.Thread(target=fetch)
    thread.daemon = True
    thread.start()


def get_teams():
    """Get list of teams for display."""
    global _data_manager
    
    if _data_manager is None:
        return []
    
    def fetch():
        try:
            teams = _data_manager.get_teams_list()
            pyotherside.send('teamsLoaded', teams)
        except Exception as e:
            pyotherside.send('teamsError', str(e))
    
    thread = threading.Thread(target=fetch)
    thread.daemon = True
    thread.start()


def get_messages(conversation_id):
    """Get messages for a conversation."""
    global _data_manager
    
    if _data_manager is None:
        return
    
    def fetch():
        try:
            messages = _data_manager.client.get_conversation_messages(conversation_id)
            result = []
            for msg in messages:
                content = msg.get('content', '')
                # Strip HTML for simple display
                if '<' in content:
                    import re
                    content = re.sub(r'<[^>]+>', '', content)
                
                # Get files from properties
                props = msg.get('properties', {})
                files_json = props.get('files', '')
                
                result.append({
                    'id': msg.get('id', ''),
                    'content': content,
                    'from': msg.get('imdisplayname', 'Unknown'),
                    'fromId': msg.get('from', ''),
                    'time': msg.get('composetime', ''),
                    'type': msg.get('messagetype', 'Text'),
                    'files': files_json,
                })
            pyotherside.send('messagesLoaded', conversation_id, result)
        except Exception as e:
            pyotherside.send('messagesError', conversation_id, str(e))
    
    thread = threading.Thread(target=fetch)
    thread.daemon = True
    thread.start()


def send_message(conversation_id, content):
    """Send a message to a conversation."""
    global _data_manager
    
    if _data_manager is None:
        return False
    
    def send():
        try:
            success = _data_manager.client.send_message(conversation_id, content)
            pyotherside.send('messageSent', conversation_id, success)
        except Exception as e:
            pyotherside.send('messageSent', conversation_id, False, str(e))
    
    thread = threading.Thread(target=send)
    thread.daemon = True
    thread.start()


def get_channel_messages(channel_id):
    """Get messages for a channel (same as conversation)."""
    get_messages(channel_id)


def send_channel_message(channel_id, content):
    """Send a message to a channel."""
    send_message(channel_id, content)


def get_avatar(user_mri):
    """Get avatar for a user. Returns base64 data URI or empty string."""
    global _data_manager
    
    if _data_manager is None:
        return ""
    
    def fetch():
        try:
            avatar_data = _data_manager.client.get_user_avatar_base64(user_mri)
            pyotherside.send('avatarLoaded', user_mri, avatar_data)
        except Exception:
            pyotherside.send('avatarLoaded', user_mri, "")
    
    thread = threading.Thread(target=fetch)
    thread.daemon = True
    thread.start()


def get_avatar_path(user_mri):
    """Get local file path for avatar. Returns path or empty string."""
    global _data_manager
    
    if _data_manager is None:
        return ""
    
    def fetch():
        try:
            avatar_path = _data_manager.client.get_user_avatar(user_mri)
            pyotherside.send('avatarPathLoaded', user_mri, avatar_path or "")
        except Exception:
            pyotherside.send('avatarPathLoaded', user_mri, "")
    
    thread = threading.Thread(target=fetch)
    thread.daemon = True
    thread.start()


def get_conversation_avatar_path(conversation_id, group_id=""):
    """Get local file path for conversation avatar (group/channel). Returns path or empty string."""
    global _data_manager
    
    if _data_manager is None:
        return ""
    
    def fetch():
        try:
            avatar_path = _data_manager.client.get_conversation_avatar(conversation_id, group_id=group_id)
            pyotherside.send('conversationAvatarLoaded', conversation_id, avatar_path or "")
        except Exception:
            pyotherside.send('conversationAvatarLoaded', conversation_id, "")
    
    thread = threading.Thread(target=fetch)
    thread.daemon = True
    thread.start()
    
    thread = threading.Thread(target=fetch)
    thread.daemon = True
    thread.start()


def download_file(share_url, file_name, file_url=""):
    """Download a file from SharePoint share URL."""
    global _data_manager
    
    print(f"download_file called: {file_name}")
    print(f"share_url: {share_url}")
    print(f"file_url: {file_url}")
    
    if _data_manager is None:
        pyotherside.send('fileDownloadComplete', file_name, False, "Not authenticated")
        return
    
    def do_download():
        try:
            print("Getting download URL...")
            
            # Pass file_info if we have fileUrl
            file_info = {'fileUrl': file_url} if file_url else None
            
            # Get download URL
            download_url = _data_manager.client.get_file_download_url(share_url, file_info)
            print(f"download_url: {download_url}")
            if not download_url:
                pyotherside.send('fileDownloadComplete', file_name, False, "Could not get download URL")
                return
            
            # Create downloads directory
            from pathlib import Path
            downloads_dir = Path.home() / "Downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)
            
            save_path = downloads_dir / file_name
            
            # Handle duplicate filenames
            counter = 1
            base_name = save_path.stem
            ext = save_path.suffix
            while save_path.exists():
                save_path = downloads_dir / f"{base_name}_{counter}{ext}"
                counter += 1
            
            print(f"Downloading to: {save_path}")
            
            # Extract host for auth if needed
            import re
            host_match = re.search(r'https://([^/]+)', share_url)
            host = host_match.group(1) if host_match else None
            
            success = _data_manager.client.download_file(download_url, str(save_path), host)
            print(f"Download success: {success}")
            
            if success:
                pyotherside.send('fileDownloadComplete', file_name, True, str(save_path))
            else:
                pyotherside.send('fileDownloadComplete', file_name, False, "Download failed")
        except Exception as e:
            print(f"Download error: {e}")
            import traceback
            traceback.print_exc()
            pyotherside.send('fileDownloadComplete', file_name, False, str(e))
    
    thread = threading.Thread(target=do_download)
    thread.daemon = True
    thread.start()


def upload_file(conversation_id, file_path):
    """Upload a file to a conversation."""
    global _data_manager
    
    print(f"upload_file called: {file_path}")
    print(f"conversation_id: {conversation_id}")
    
    if _data_manager is None:
        pyotherside.send('imageUploadComplete', conversation_id, False, "Not authenticated", {})
        return
    
    def do_upload():
        try:
            print(f"Starting upload of {file_path}")
            result = _data_manager.client.upload_file(conversation_id, file_path)
            
            if result:
                print(f"Upload successful: {result}")
                pyotherside.send('imageUploadComplete', conversation_id, True, "", result)
            else:
                print("Upload failed")
                pyotherside.send('imageUploadComplete', conversation_id, False, "Upload failed", {})
        except Exception as e:
            print(f"Upload error: {e}")
            import traceback
            traceback.print_exc()
            pyotherside.send('imageUploadComplete', conversation_id, False, str(e), {})
    
    thread = threading.Thread(target=do_upload)
    thread.daemon = True
    thread.start()


def send_message_with_file(conversation_id, content, file_info):
    """Send a message with an uploaded file attachment."""
    global _data_manager
    
    print(f"send_message_with_file called")
    print(f"conversation_id: {conversation_id}")
    print(f"content: {content}")
    print(f"file_info: {file_info}")
    
    if _data_manager is None:
        pyotherside.send('messageSent', conversation_id, False, "Not authenticated")
        return
    
    def do_send():
        try:
            success = _data_manager.client.send_message_with_file(conversation_id, content, file_info)
            pyotherside.send('messageSent', conversation_id, success)
        except Exception as e:
            print(f"Send with file error: {e}")
            pyotherside.send('messageSent', conversation_id, False, str(e))
    
    thread = threading.Thread(target=do_send)
    thread.daemon = True
    thread.start()


def search_people(query):
    """Search for people by name or email."""
    global _data_manager
    
    print(f"search_people called: {query}")
    
    if _data_manager is None:
        pyotherside.send('searchResults', [])
        return
    
    def do_search():
        try:
            results = _data_manager.client.search_people(query)
            pyotherside.send('searchResults', results)
        except Exception as e:
            print(f"Search error: {e}")
            pyotherside.send('searchResults', [])
    
    thread = threading.Thread(target=do_search)
    thread.daemon = True
    thread.start()


def create_chat(user_mri, display_name):
    """Create a new chat with a user."""
    global _data_manager
    
    print(f"create_chat called: {user_mri}, {display_name}")
    
    if _data_manager is None:
        pyotherside.send('chatCreated', False, "", "", "Not authenticated")
        return
    
    def do_create():
        try:
            conversation_id = _data_manager.client.create_chat(user_mri)
            if conversation_id:
                pyotherside.send('chatCreated', True, conversation_id, display_name, "")
            else:
                pyotherside.send('chatCreated', False, "", "", "Failed to create chat")
        except Exception as e:
            print(f"Create chat error: {e}")
            pyotherside.send('chatCreated', False, "", "", str(e))
    
    thread = threading.Thread(target=do_create)
    thread.daemon = True
    thread.start()


def delete_message(conversation_id, message_id):
    """Delete a message from a conversation."""
    global _data_manager
    
    print(f"delete_message called: {conversation_id}, {message_id}")
    
    if _data_manager is None:
        pyotherside.send('messageDeleted', conversation_id, False, "Not authenticated")
        return
    
    def do_delete():
        try:
            success = _data_manager.client.delete_message(conversation_id, message_id)
            pyotherside.send('messageDeleted', conversation_id, success, "" if success else "Delete failed")
            # Reload messages after delete
            if success:
                load_messages(conversation_id)
        except Exception as e:
            print(f"Delete error: {e}")
            pyotherside.send('messageDeleted', conversation_id, False, str(e))
    
    thread = threading.Thread(target=do_delete)
    thread.daemon = True
    thread.start()
