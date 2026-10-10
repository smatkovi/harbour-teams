#!/usr/bin/env python3
"""
Microsoft Teams API Client for Sailfish OS
"""

import json
import time
import requests
import base64
import hashlib
import os
from urllib.parse import quote
from pathlib import Path

# Import Sailfish Secrets once at module level (like WebUntis does)
try:
    import sailfish_secrets
    HAS_SECRETS = True
except ImportError:
    HAS_SECRETS = False
    print("[Teams] Sailfish Secrets not available")


class TeamsAuth:
    """Handles Teams authentication via device code flow."""
    
    # Azure CLI public client - allows device code flow
    CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
    RESOURCE = "https://api.spaces.skype.com"
    AUTHORITY = "https://login.microsoftonline.com/common"
    
    def __init__(self):
        self.access_token = None
        self.refresh_token = None
        self.skype_token = None
        self.region = None
        self.chat_service = None
        self.middle_tier = None
        self.user_id = None
        self.user_name = None
        
    def start_device_code_flow(self):
        """Start device code flow. Returns dict with user_code and verification_url."""
        response = requests.post(
            f"{self.AUTHORITY}/oauth2/devicecode",
            data={
                "client_id": self.CLIENT_ID,
                "resource": self.RESOURCE,
            }
        )
        response.raise_for_status()
        return response.json()
    
    def poll_for_token(self, device_code, interval=5, timeout=900):
        """Poll for token after user authenticates. Returns True on success."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            time.sleep(interval)
            
            response = requests.post(
                f"{self.AUTHORITY}/oauth2/token",
                data={
                    "client_id": self.CLIENT_ID,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "code": device_code,
                }
            )
            
            result = response.json()
            
            if "access_token" in result:
                self.access_token = result["access_token"]
                self.refresh_token = result.get("refresh_token")
                return True
            
            error = result.get("error")
            if error == "authorization_pending":
                continue
            elif error == "slow_down":
                interval += 5
                continue
            elif error in ["expired_token", "bad_verification_code"]:
                return False
                
        return False
    
    def refresh_access_token(self):
        """Refresh the access token using refresh token."""
        if not self.refresh_token:
            return False
            
        response = requests.post(
            f"{self.AUTHORITY}/oauth2/token",
            data={
                "client_id": self.CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "resource": self.RESOURCE,
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            self.access_token = result["access_token"]
            if "refresh_token" in result:
                self.refresh_token = result["refresh_token"]
            return True
        return False
    
    def get_teams_authorization(self):
        """Get Teams authorization including Skype token."""
        if not self.access_token:
            return False
            
        response = requests.post(
            "https://teams.microsoft.com/api/authsvc/v1.0/authz",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract tokens
            tokens = data.get("tokens", {})
            self.skype_token = tokens.get("skypeToken")
            
            # Extract region info
            self.region = data.get("region", "emea")
            
            region_gtms = data.get("regionGtms", {})
            self.chat_service = region_gtms.get("chatService", "https://emea.ng.msg.teams.microsoft.com")
            self.middle_tier = region_gtms.get("middleTier", "https://teams.microsoft.com/api/mt/emea")
            
            return True
        return False
    
    def save_tokens(self):
        """Save tokens using Sailfish Secrets or fallback to file."""
        tokens = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "skype_token": self.skype_token,
            "region": self.region,
            "chat_service": self.chat_service,
            "middle_tier": self.middle_tier,
        }
        
        # Try Sailfish Secrets first
        if HAS_SECRETS:
            print(f"sailfish_secrets available={sailfish_secrets.is_secrets_available()}")
            if sailfish_secrets.is_secrets_available():
                if sailfish_secrets.save_tokens(tokens):
                    print("Tokens saved to Sailfish Secrets")
                    # Remove any old plaintext file
                    old_file = Path.home() / ".local" / "share" / "harbour-teams" / "tokens.json"
                    if old_file.exists():
                        old_file.unlink()
                        print("Removed old plaintext token file")
                    return
                else:
                    print("sailfish_secrets.save_tokens() returned False")
        
        # Fallback to file - use .local/share for Sailjail compatibility
        print("Warning: Saving tokens to plaintext file (Sailfish Secrets not available)")
        config_dir = Path.home() / ".local" / "share" / "harbour-teams"
        config_dir.mkdir(parents=True, exist_ok=True)
        token_file = config_dir / "tokens.json"
        with open(token_file, "w") as f:
            json.dump(tokens, f)
        print(f"Tokens saved to {token_file}")
    
    def load_tokens(self):
        """Load tokens from Sailfish Secrets or fallback file."""
        tokens = None
        
        # Try Sailfish Secrets first
        if HAS_SECRETS:
            print(f"sailfish_secrets available={sailfish_secrets.is_secrets_available()}")
            if sailfish_secrets.is_secrets_available():
                tokens = sailfish_secrets.load_tokens()
                if tokens:
                    print("Tokens loaded from Sailfish Secrets")
        
        # Fallback to file if not found in Secrets
        if not tokens:
            # Try new location first (.local/share), then old location (.config)
            config_file = Path.home() / ".local" / "share" / "harbour-teams" / "tokens.json"
            if not config_file.exists():
                # Try old location for migration
                old_config = Path.home() / ".config" / "harbour-teams" / "tokens.json"
                if old_config.exists():
                    print(f"Migrating tokens from {old_config}")
                    config_file = old_config
            
            if config_file.exists():
                print(f"Loading tokens from {config_file}")
                with open(config_file) as f:
                    tokens = json.load(f)
                
                # Migrate to Sailfish Secrets if available
                if HAS_SECRETS and sailfish_secrets.is_secrets_available():
                    print("Migrating tokens to Sailfish Secrets...")
                    if sailfish_secrets.save_tokens(tokens):
                        config_file.unlink()
                        print("Migration complete, removed plaintext file")
                    else:
                        print("Migration failed: save_tokens returned False")
        
        if tokens:
            self.access_token = tokens.get("access_token")
            self.refresh_token = tokens.get("refresh_token")
            self.skype_token = tokens.get("skype_token")
            self.region = tokens.get("region", "emea")
            self.chat_service = tokens.get("chat_service")
            self.middle_tier = tokens.get("middle_tier")
            return True
        return False
    
    def is_authenticated(self):
        """Check if we have valid tokens."""
        return self.skype_token is not None
    
    def get_sharepoint_token(self, sharepoint_host):
        """
        Get a SharePoint access token.
        First tries refresh token, then falls back to cached token.
        
        Args:
            sharepoint_host: e.g., "polgargym-my.sharepoint.com"
        
        Returns:
            Access token for SharePoint or None
        """
        if not self.refresh_token:
            return None
        
        # Try with the sharepoint host URL as resource
        resource = f"https://{sharepoint_host}"
        
        try:
            response = requests.post(
                f"{self.AUTHORITY}/oauth2/token",
                data={
                    "client_id": self.CLIENT_ID,
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "resource": resource,
                }
            )
            
            print(f"SharePoint token response: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                token = result.get("access_token")
                if token:
                    print("Got SharePoint token successfully")
                    return token
            else:
                print(f"SharePoint token error: {response.status_code}")
                error_data = response.json() if response.text else {}
                error_desc = error_data.get("error_description", response.text[:300])
                print(f"Error: {error_desc}")
                
        except Exception as e:
            print(f"SharePoint token exception: {e}")
        
        return None
    
    def get_graph_token(self):
        """
        Get a Microsoft Graph access token.
        
        Returns:
            Access token for Graph API or None
        """
        if not self.refresh_token:
            return None
        
        try:
            response = requests.post(
                f"{self.AUTHORITY}/oauth2/token",
                data={
                    "client_id": self.CLIENT_ID,
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "resource": "https://graph.microsoft.com",
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("access_token")
            else:
                print(f"Graph token error: {response.status_code}")
                print(f"Response: {response.text[:300]}")
        except Exception as e:
            print(f"Graph token exception: {e}")
        
        return None


class TeamsClient:
    """Teams API client for chats, messages, and teams."""
    
    def __init__(self, auth: TeamsAuth):
        self.auth = auth
        self._avatar_cache_dir = Path.home() / ".cache" / "harbour-teams" / "avatars"
        self._avatar_cache_dir.mkdir(parents=True, exist_ok=True)
        
    def _headers(self):
        """Get headers for chat service API."""
        return {
            "Authentication": f"skypetoken={self.auth.skype_token}",
            "Content-Type": "application/json",
            "BehaviorOverride": "redirectAs404",
        }
    
    def _mt_headers(self):
        """Get headers for middle tier API."""
        return {
            "Authorization": f"Bearer {self.auth.access_token}",
            "Content-Type": "application/json",
        }
    
    def get_conversations(self, page_size=50):
        """Get list of conversations (chats)."""
        proxy_url = f"https://teams.microsoft.com/api/chatsvc/{self.auth.region}/v1/users/ME/conversations"
        
        print(f"get_conversations: region={self.auth.region}")
        print(f"URL: {proxy_url}")
        
        response = requests.get(
            proxy_url,
            headers=self._headers(),
            params={
                "view": "msnp24Equivalent|supportsMessageProperties",
                "pageSize": page_size,
            }
        )
        
        print(f"get_conversations response: {response.status_code}")
        
        if response.status_code == 200:
            convs = response.json().get("conversations", [])
            print(f"Got {len(convs)} conversations")
            return convs
        else:
            print(f"Error response: {response.text[:300]}")
        return []
    
    def get_conversation_messages(self, conversation_id, page_size=30):
        """Get messages from a conversation."""
        encoded_id = quote(conversation_id, safe='')
        
        proxy_url = f"https://teams.microsoft.com/api/chatsvc/{self.auth.region}/v1/users/ME/conversations/{encoded_id}/messages"
        
        response = requests.get(
            proxy_url,
            headers=self._headers(),
            params={
                "startTime": 0,
                "pageSize": page_size,
                "view": "msnp24Equivalent|supportsMessageProperties",
            }
        )
        
        if response.status_code == 200:
            return response.json().get("messages", [])
        return []
    
    def send_message(self, conversation_id, content, message_type="Text"):
        """Send a message to a conversation."""
        encoded_id = quote(conversation_id, safe='')
        client_msg_id = str(int(time.time() * 1000))
        
        payload = {
            "content": content,
            "messagetype": message_type,
            "contenttype": "text" if message_type == "Text" else "text/html",
            "amsreferences": [],
            "clientmessageid": client_msg_id,
            "properties": {
                "importance": "",
                "subject": None,
            }
        }
        
        proxy_url = f"https://teams.microsoft.com/api/chatsvc/{self.auth.region}/v1/users/ME/conversations/{encoded_id}/messages"
        
        response = requests.post(
            proxy_url,
            headers=self._headers(),
            json=payload
        )
        
        return response.status_code in [200, 201]
    
    def delete_message(self, conversation_id, message_id):
        """Delete a message from a conversation."""
        try:
            encoded_conv_id = quote(conversation_id, safe='')
            
            # Teams API endpoint for deleting messages
            proxy_url = f"https://teams.microsoft.com/api/chatsvc/{self.auth.region}/v1/users/ME/conversations/{encoded_conv_id}/messages/{message_id}"
            
            response = requests.delete(
                proxy_url,
                headers=self._headers()
            )
            
            print(f"Delete message response: {response.status_code}")
            
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"Delete message error: {e}")
            return False
    
    def search_people(self, query):
        """Search for people by name or email using Microsoft Graph API."""
        try:
            graph_token = self._get_graph_token()
            if graph_token:
                results = self._search_people_graph(query, graph_token)
                if results:
                    return results
            results = self._search_people_teams(query)
            if results:
                return results
            print("No search results from any API")
            return []
        except Exception as e:
            print(f"search_people exception: {e}")
            import traceback
            traceback.print_exc()
        return []
    
    def _get_graph_token(self):
        """Get a token for Microsoft Graph API."""
        if not self.auth.refresh_token:
            return None
        try:
            response = requests.post(
                f"{self.auth.AUTHORITY}/oauth2/token",
                data={
                    "client_id": self.auth.CLIENT_ID,
                    "grant_type": "refresh_token",
                    "refresh_token": self.auth.refresh_token,
                    "resource": "https://graph.microsoft.com",
                }
            )
            if response.status_code == 200:
                result = response.json()
                return result.get("access_token")
        except Exception as e:
            print(f"Graph token error: {e}")
        return None
    
    def _search_people_graph(self, query, graph_token):
        """Search people using Microsoft Graph API."""
        try:
            url = f"https://graph.microsoft.com/v1.0/users?$filter=startswith(displayName,'{query}') or startswith(mail,'{query}')&$top=20"
            headers = {
                "Authorization": f"Bearer {graph_token}",
                "Content-Type": "application/json",
            }
            response = requests.get(url, headers=headers)
            print(f"Graph people search response: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                users = data.get("value", [])
                results = []
                for user in users:
                    user_id = user.get("id", "")
                    results.append({
                        "id": user_id,
                        "displayName": user.get("displayName", "Unknown"),
                        "email": user.get("mail", "") or user.get("userPrincipalName", ""),
                        "mri": f"8:orgid:{user_id}",
                        "jobTitle": user.get("jobTitle", ""),
                        "department": user.get("department", ""),
                    })
                print(f"Graph found {len(results)} people")
                return results
            else:
                print(f"Graph search error: {response.text[:200]}")
        except Exception as e:
            print(f"Graph search exception: {e}")
        return []
    
    def _search_people_teams(self, query):
        """Search people using Teams middle tier API."""
        try:
            url = f"{self.auth.middle_tier}/beta/users/searchV2"
            headers = self._mt_headers()
            payload = {"query": query, "top": 20, "querySource": "Input"}
            response = requests.post(url, headers=headers, json=payload)
            print(f"Teams people search response: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                users = data.get("value", []) if isinstance(data, dict) else data
                results = []
                for user in users:
                    user_id = user.get("objectId", user.get("id", ""))
                    mri = user.get("mri", f"8:orgid:{user_id}")
                    results.append({
                        "id": user_id,
                        "displayName": user.get("displayName", "Unknown"),
                        "email": user.get("email", "") or user.get("mail", "") or user.get("userPrincipalName", ""),
                        "mri": mri,
                        "jobTitle": user.get("jobTitle", ""),
                        "department": user.get("department", ""),
                    })
                print(f"Teams found {len(results)} people")
                return results
            else:
                print(f"Teams search error: {response.text[:200]}")
        except Exception as e:
            print(f"Teams search exception: {e}")
        return []
    
    def create_chat(self, user_mri):
        """Create a new 1:1 chat with a user."""
        try:
            my_mri = None
            if self.auth.skype_token:
                try:
                    parts = self.auth.skype_token.split('.')
                    if len(parts) >= 2:
                        payload = parts[1]
                        padding = 4 - len(payload) % 4
                        if padding != 4:
                            payload += '=' * padding
                        decoded = base64.urlsafe_b64decode(payload)
                        token_data = json.loads(decoded)
                        skype_id = token_data.get("skypeid", "")
                        if skype_id:
                            my_mri = f"8:{skype_id}"
                except:
                    pass
            if not my_mri:
                print("Could not determine own MRI")
                return None
            print(f"Creating chat: {my_mri} <-> {user_mri}")
            url = f"{self.auth.chat_service}/v1/threads"
            headers = {
                "Authentication": f"skypetoken={self.auth.skype_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "members": [
                    {"id": my_mri, "role": "Admin"},
                    {"id": user_mri, "role": "Admin"}
                ],
                "properties": {
                    "threadType": "chat",
                    "chatFilesIndexId": "2",
                    "uniquerosterthread": "true",
                    "fixedRoster": "true"
                }
            }
            response = requests.post(url, headers=headers, json=payload)
            print(f"create_chat response: {response.status_code}")
            if response.status_code in [200, 201]:
                my_uuid = my_mri.split(":")[-1]
                other_uuid = user_mri.split(":")[-1]
                if my_uuid < other_uuid:
                    conv_id = f"19:{my_uuid}_{other_uuid}@unq.gbl.spaces"
                else:
                    conv_id = f"19:{other_uuid}_{my_uuid}@unq.gbl.spaces"
                print(f"Created chat: {conv_id}")
                return conv_id
            else:
                print(f"create_chat error: {response.text[:300]}")
        except Exception as e:
            print(f"create_chat exception: {e}")
            import traceback
            traceback.print_exc()
        return None
    
    def get_user_profile(self, user_mri):
        """Get user profile by MRI (e.g., 8:orgid:uuid)."""
        response = requests.get(
            f"{self.auth.middle_tier}/beta/users/{quote(user_mri, safe='')}/",
            headers=self._mt_headers()
        )
        
        if response.status_code == 200:
            return response.json()
        return None
    
    def get_user_profiles_batch(self, user_mris):
        """Get multiple user profiles in batch."""
        response = requests.post(
            f"{self.auth.middle_tier}/beta/users/fetchShortProfile",
            headers=self._mt_headers(),
            params={
                "isMailAddress": "false",
                "enableGuest": "true",
            },
            json=user_mris
        )
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return data.get("value", [])
        return []
    
    def get_user_avatar(self, user_mri, size="HR64x64"):
        """
        Get user avatar image.
        Returns local file path to cached avatar, or None if not available.
        
        Args:
            user_mri: User MRI (e.g., "8:orgid:uuid")
            size: Avatar size (HR64x64, HR96x96, HR128x128, etc.)
        """
        # Create cache filename from MRI hash
        mri_hash = hashlib.md5(user_mri.encode()).hexdigest()
        
        # Check for any existing cached file (any extension)
        for ext in ['.jpg', '.jpeg', '.png', '.gif']:
            cache_file = self._avatar_cache_dir / f"{mri_hash}_{size}{ext}"
            if cache_file.exists():
                age = time.time() - cache_file.stat().st_mtime
                if age < 86400:  # 24 hours
                    return str(cache_file)
        
        # Fetch avatar from Teams API
        try:
            url = f"{self.auth.middle_tier}/beta/users/{quote(user_mri, safe='')}/profilepicturev2"
            
            response = requests.get(
                url,
                headers=self._mt_headers(),
                params={"size": size},
                timeout=10
            )
            
            if response.status_code == 200 and len(response.content) > 100:
                # Detect image format from content
                content = response.content
                if content[:3] == b'\xff\xd8\xff':
                    ext = '.jpg'
                elif content[:8] == b'\x89PNG\r\n\x1a\n':
                    ext = '.png'
                elif content[:6] in (b'GIF87a', b'GIF89a'):
                    ext = '.gif'
                else:
                    # Default to jpg as Teams usually returns JPEG
                    ext = '.jpg'
                
                cache_file = self._avatar_cache_dir / f"{mri_hash}_{size}{ext}"
                with open(cache_file, "wb") as f:
                    f.write(content)
                return str(cache_file)
        except Exception:
            pass
        
        return None
    
    def get_user_avatar_base64(self, user_mri, size="HR64x64"):
        """
        Get user avatar as base64 encoded string for QML Image source.
        Returns data URI string or empty string if not available.
        """
        avatar_path = self.get_user_avatar(user_mri, size)
        if avatar_path and os.path.exists(avatar_path):
            try:
                with open(avatar_path, "rb") as f:
                    data = f.read()
                b64 = base64.b64encode(data).decode('utf-8')
                return f"data:image/png;base64,{b64}"
            except Exception:
                pass
        return ""
    
    def get_conversation_avatar(self, conversation_id, picture_url=None, group_id=None, size="HR64x64"):
        """
        Get avatar for a conversation (group chat, channel, team).
        Returns local file path to cached avatar, or None if not available.
        
        Args:
            conversation_id: The conversation ID (used for caching)
            picture_url: Optional explicit picture URL from threadProperties
            group_id: Optional group ID for Teams (to fetch team photo)
            size: Avatar size
        """
        # Create cache filename from conversation ID hash
        conv_hash = hashlib.md5(conversation_id.encode()).hexdigest()
        
        # Check for existing cached file
        for ext in ['.jpg', '.jpeg', '.png', '.gif']:
            cache_file = self._avatar_cache_dir / f"conv_{conv_hash}_{size}{ext}"
            if cache_file.exists():
                age = time.time() - cache_file.stat().st_mtime
                if age < 86400:  # 24 hours
                    return str(cache_file)
        
        # Try to fetch from provided picture URL
        if picture_url:
            try:
                headers = {}
                if "teams.microsoft.com" in picture_url or "graph.microsoft.com" in picture_url:
                    headers = {"Authorization": f"Bearer {self.auth.access_token}"}
                elif "skype.com" in picture_url:
                    headers = {"Authorization": f"skype_token {self.auth.skype_token}"}
                
                response = requests.get(picture_url, headers=headers, timeout=10)
                
                if response.status_code == 200 and len(response.content) > 100:
                    content = response.content
                    if content[:3] == b'\xff\xd8\xff':
                        ext = '.jpg'
                    elif content[:8] == b'\x89PNG\r\n\x1a\n':
                        ext = '.png'
                    elif content[:6] in (b'GIF87a', b'GIF89a'):
                        ext = '.gif'
                    else:
                        ext = '.jpg'
                    
                    cache_file = self._avatar_cache_dir / f"conv_{conv_hash}_{size}{ext}"
                    with open(cache_file, "wb") as f:
                        f.write(content)
                    return str(cache_file)
            except Exception as e:
                print(f"Failed to fetch conversation avatar from URL: {e}")
        
        # Try Graph API for group photo if we have a groupId
        if group_id:
            try:
                graph_token = self.auth.get_graph_token()
                if graph_token:
                    # Try to get group photo from Graph API
                    url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/photo/$value"
                    
                    response = requests.get(
                        url,
                        headers={"Authorization": f"Bearer {graph_token}"},
                        timeout=10
                    )
                    
                    if response.status_code == 200 and len(response.content) > 100:
                        content = response.content
                        if content[:3] == b'\xff\xd8\xff':
                            ext = '.jpg'
                        elif content[:8] == b'\x89PNG\r\n\x1a\n':
                            ext = '.png'
                        elif content[:6] in (b'GIF87a', b'GIF89a'):
                            ext = '.gif'
                        else:
                            ext = '.jpg'
                        
                        cache_file = self._avatar_cache_dir / f"conv_{conv_hash}_{size}{ext}"
                        with open(cache_file, "wb") as f:
                            f.write(content)
                        return str(cache_file)
            except Exception as e:
                print(f"Failed to fetch group photo from Graph: {e}")
        
        return None
    
    def get_file_download_url(self, share_url, file_info=None):
        """
        Get a direct download URL from a SharePoint share URL.
        Tries multiple methods.
        """
        try:
            print(f"get_file_download_url: {share_url}")
            
            # Extract host from share URL
            import re
            match = re.search(r'https://([^/]+)', share_url)
            if not match:
                print("Could not extract host from URL")
                return None
            
            host = match.group(1)
            print(f"host: {host}")
            
            # Get SharePoint-specific token
            sp_token = self.auth.get_sharepoint_token(host)
            if not sp_token:
                print("Could not get SharePoint token")
                return None
            
            # Method 1: Try shares API
            share_token = base64.urlsafe_b64encode(share_url.encode()).decode().rstrip('=')
            share_id = f"u!{share_token}"
            
            url = f"https://{host}/_api/v2.0/shares/{share_id}/driveItem"
            print(f"Trying shares API: {url}")
            
            response = requests.get(
                url,
                headers={
                    "Authorization": f"Bearer {sp_token}",
                    "Accept": "application/json",
                    "Prefer": "redeemSharingLink,getShortLivedDownloadUrl",
                },
                params={
                    "select": "@microsoft.graph.downloadUrl,file,id,name"
                },
                timeout=30
            )
            
            print(f"Shares API response: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                download_url = data.get("@microsoft.graph.downloadUrl")
                if download_url:
                    print(f"Got download URL from shares API")
                    return download_url
            
            # Method 2: Try direct file URL with download.aspx
            # Parse the share URL to extract file info
            if file_info and file_info.get('fileUrl'):
                file_url = file_info['fileUrl']
                print(f"Trying direct file URL approach: {file_url}")
                
                # Convert to download URL format
                # e.g. /personal/user/Documents/file.zip -> /_layouts/15/download.aspx?SourceUrl=/personal/user/Documents/file.zip
                from urllib.parse import urlparse, quote
                parsed = urlparse(file_url)
                path = parsed.path
                
                download_url = f"https://{host}/_layouts/15/download.aspx?SourceUrl={quote(path)}"
                print(f"Direct download URL: {download_url}")
                return download_url
                
            print("No download URL found")
            return None
            
        except Exception as e:
            print(f"get_file_download_url error: {e}")
            import traceback
            traceback.print_exc()
        return None
    
    def download_file(self, download_url, save_path, sharepoint_host=None):
        """
        Download a file from the given URL to save_path.
        Returns True on success.
        """
        try:
            headers = {}
            
            # If it's a SharePoint URL that needs auth
            if sharepoint_host and "/_layouts/" in download_url:
                sp_token = self.auth.get_sharepoint_token(sharepoint_host)
                if sp_token:
                    headers["Authorization"] = f"Bearer {sp_token}"
            
            response = requests.get(
                download_url,
                headers=headers,
                stream=True,
                timeout=60,
                allow_redirects=True
            )
            
            print(f"Download response status: {response.status_code}")
            
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"Downloaded {save_path}")
                return True
            else:
                print(f"Download failed: {response.status_code}")
                print(f"Response: {response.text[:300] if response.text else 'empty'}")
        except Exception as e:
            print(f"Download exception: {e}")
        return False
    
    def upload_file(self, conversation_id, file_path):
        """
        Upload a file to a conversation via Teams AsyncGW.
        
        Args:
            conversation_id: The conversation/thread ID
            file_path: Local path to the file
            
        Returns:
            dict with object_id and preview_url on success, None on failure
        """
        try:
            import os
            import mimetypes
            import uuid
            
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"
            
            # Teams uses pish/image for images, pish/file for others
            if mime_type.startswith("image/"):
                teams_type = "pish/image"
            else:
                teams_type = "pish/file"
            
            # Get asyncgw base URL from region
            region = self.auth.region or "emea"
            asyncgw_base = f"https://eu-prod.asyncgw.teams.microsoft.com"
            
            # Generate session and request IDs like Teams client
            session_id = str(uuid.uuid4())
            request_id = session_id.replace("-", "") + "_1"
            
            # Full Teams Desktop headers from mitmproxy capture
            headers = {
                "authorization": f"skype_token {self.auth.skype_token}",
                "content-type": "application/json",
                "accept": "application/json",
                "x-ms-client-type": "desktop",
                "x-ms-client-version": "41/1.0.0.2025070703",
                "x-ms-session-id": session_id,
                "x-ms-scenario-id": "1520",
                "x-ms-user-type": "null",
                "x-ms-client-env": "pds-prod-cosmic-linux-euwe",
                "x-ms-request-id": request_id,
                "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) MicrosoftTeams-Preview/1.5.00.23861 Chrome/85.0.4183.121 Electron/10.4.7 Safari/537.36",
                "origin": "https://teams.microsoft.com",
                "referer": "https://teams.microsoft.com/_",
            }
            
            # Step 1: Create object
            create_payload = {
                "type": teams_type,
                "permissions": {
                    conversation_id: ["read"]
                },
                "filename": filename
            }
            
            print(f"Creating object for {filename} (type: {teams_type})")
            response = requests.post(
                f"{asyncgw_base}/v1/objects/",
                headers=headers,
                json=create_payload
            )
            
            print(f"Create response: {response.status_code}")
            
            if response.status_code != 201:
                print(f"Create failed: {response.text[:500]}")
                return None
            
            # Get object ID from response or location header
            object_id = None
            if response.text:
                try:
                    data = response.json()
                    object_id = data.get("id")
                except:
                    pass
            
            if not object_id:
                location = response.headers.get("location", "")
                if "/objects/" in location:
                    object_id = location.split("/objects/")[-1].rstrip("/")
            
            if not object_id:
                print("Could not get object ID")
                return None
            
            print(f"Object ID: {object_id}")
            
            # Step 2: Upload content
            with open(file_path, "rb") as f:
                file_data = f.read()
            
            upload_headers = {
                "authorization": f"skype_token {self.auth.skype_token}",
                "content-type": "application/octet-stream",
                "accept": "*/*",
                "x-ms-client-type": "desktop",
                "x-ms-client-version": "41/1.0.0.2025070703",
                "x-ms-session-id": session_id,
                "x-ms-scenario-id": "1520",
                "x-ms-user-type": "null",
                "x-ms-client-env": "pds-prod-cosmic-linux-euwe",
                "x-ms-request-id": request_id + "2",
                "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) MicrosoftTeams-Preview/1.5.00.23861 Chrome/85.0.4183.121 Electron/10.4.7 Safari/537.36",
                "origin": "https://teams.microsoft.com",
                "referer": "https://teams.microsoft.com/_",
            }
            
            # Use imgpsh for images, original for other files
            content_path = "imgpsh" if teams_type == "pish/image" else "original"
            
            print(f"Uploading {len(file_data)} bytes to /content/{content_path}")
            response = requests.put(
                f"{asyncgw_base}/v1/objects/{object_id}/content/{content_path}",
                headers=upload_headers,
                data=file_data
            )
            
            print(f"Upload response: {response.status_code}")
            
            if response.status_code not in [200, 201]:
                print(f"Upload failed: {response.text[:500]}")
                return None
            
            # Step 3: Set permissions
            perm_headers = {
                "authorization": f"skype_token {self.auth.skype_token}",
                "content-type": "application/json",
                "accept": "application/json",
                "x-ms-client-type": "desktop",
                "x-ms-client-version": "41/1.0.0.2025070703",
                "x-ms-session-id": session_id,
                "x-ms-scenario-id": "1520",
                "x-ms-user-type": "null",
                "x-ms-client-env": "pds-prod-cosmic-linux-euwe",
                "x-ms-request-id": request_id + "3",
                "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) MicrosoftTeams-Preview/1.5.00.23861 Chrome/85.0.4183.121 Electron/10.4.7 Safari/537.36",
                "origin": "https://teams.microsoft.com",
                "referer": "https://teams.microsoft.com/_",
            }
            
            perm_payload = {
                conversation_id: ["read"]
            }
            
            print("Setting permissions")
            response = requests.put(
                f"{asyncgw_base}/v1/objects/{object_id}/permissions",
                headers=perm_headers,
                json=perm_payload
            )
            
            print(f"Permissions response: {response.status_code}")
            
            if response.status_code not in [200, 204]:
                print(f"Permissions failed: {response.text[:300]}")
                # Continue anyway, upload might still work
            
            # Return result
            if teams_type == "pish/image":
                preview_url = f"https://eu-api.asm.skype.com/v1/objects/{object_id}/views/imgo"
            else:
                preview_url = f"https://eu-api.asm.skype.com/v1/objects/{object_id}/views/original"
            
            # Get file extension for type
            file_ext = os.path.splitext(filename)[1].lstrip('.').lower() or "file"
            
            return {
                "object_id": object_id,
                "preview_url": preview_url,
                "filename": filename,
                "file_type": file_ext,
                "mime_type": mime_type,
                "is_image": teams_type == "pish/image"
            }
            
        except Exception as e:
            print(f"Upload exception: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def send_message_with_file(self, conversation_id, content, file_info):
        """
        Send a message with an uploaded file attachment.
        
        Args:
            conversation_id: The conversation/thread ID
            content: Text content of the message
            file_info: dict from upload_file with object_id, preview_url, etc.
            
        Returns:
            True on success, False on failure
        """
        try:
            import json
            
            encoded_id = quote(conversation_id, safe='')
            client_msg_id = str(int(time.time() * 1000))
            
            object_id = file_info.get("object_id", "")
            preview_url = file_info.get("preview_url", "")
            filename = file_info.get("filename", "file")
            is_image = file_info.get("is_image", False)
            file_type = file_info.get("file_type", "file")
            
            # Build message content based on file type
            if is_image:
                # For images, create an img tag
                img_tag = f'<img alt="{filename}" src="{preview_url}" itemscope="http://schema.skype.com/AMSImage" style="vertical-align:bottom;width:250px;height:auto"></img>'
                if content:
                    message_content = f"{content}<p>{img_tag}</p>"
                else:
                    message_content = img_tag
            else:
                # For files (PDF, etc.), create a file attachment link
                file_tag = f'<a href="{preview_url}" itemscope="http://schema.skype.com/File" itemtype="http://schema.skype.com/File" itemid="{object_id}">{filename}</a>'
                if content:
                    message_content = f"{content}<p>{file_tag}</p>"
                else:
                    message_content = file_tag
            
            # Build file attachment reference
            file_ref = {
                "@type": "http://schema.skype.com/File",
                "version": 2,
                "id": object_id,
                "type": file_type,
                "title": filename,
                "state": "active",
                "objectUrl": preview_url,
                "filePreview": {
                    "previewUrl": preview_url
                }
            }
            
            payload = {
                "content": message_content,
                "messagetype": "RichText/Html",
                "contenttype": "text",
                "amsreferences": [object_id],
                "clientmessageid": client_msg_id,
                "properties": {
                    "importance": "",
                    "subject": None,
                    "files": json.dumps([file_ref])
                }
            }
            
            proxy_url = f"https://teams.microsoft.com/api/chatsvc/{self.auth.region}/v1/users/ME/conversations/{encoded_id}/messages"
            
            response = requests.post(
                proxy_url,
                headers=self._headers(),
                json=payload
            )
            
            print(f"Send with file response: {response.status_code}")
            
            if response.status_code not in [200, 201]:
                print(f"Send failed: {response.text[:300]}")
            
            return response.status_code in [200, 201]
            
        except Exception as e:
            print(f"Send with file exception: {e}")
            return False
    
    def get_teams(self):
        """Get list of teams the user is member of."""
        response = requests.get(
            f"{self.auth.middle_tier}/beta/teams/usergroups",
            headers=self._mt_headers()
        )
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return data.get("value", [])
        return []
    
    def get_team_channels(self, team_id):
        """Get channels for a team."""
        response = requests.get(
            f"{self.auth.middle_tier}/beta/teams/{team_id}/channels",
            headers=self._mt_headers()
        )
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return data.get("value", [])
        return []


class ChatInfo:
    """Processed chat information for display."""
    
    def __init__(self, conversation_id, display_name, last_message="", last_time=None, 
                 chat_type="chat", avatar_url="", user_mri="", group_id=""):
        self.conversation_id = conversation_id
        self.display_name = display_name
        self.last_message = last_message
        self.last_time = last_time
        self.chat_type = chat_type
        self.avatar_url = avatar_url
        self.user_mri = user_mri
        self.group_id = group_id


class TeamsDataManager:
    """Manages Teams data and provides processed info for UI."""
    
    def __init__(self, auth: TeamsAuth):
        self.auth = auth
        self.client = TeamsClient(auth)
        self._user_cache = {}  # Cache user profiles: mri -> {name, avatar}
        self._my_user_id = None
        
    def _extract_user_id_from_mri(self, mri):
        """Extract user GUID from MRI like '8:orgid:uuid'."""
        if mri and ':' in mri:
            parts = mri.split(':')
            if len(parts) >= 3:
                return parts[2]
        return mri
    
    def _get_my_user_id(self):
        """Get current user's ID."""
        if self._my_user_id:
            return self._my_user_id
        
        # Method 1: Try to get user ID from /me endpoint
        try:
            response = requests.get(
                f"{self.auth.middle_tier}/beta/users/ME",
                headers={
                    "Authorization": f"Bearer {self.auth.access_token}",
                    "Content-Type": "application/json",
                }
            )
            if response.status_code == 200:
                data = response.json()
                # MRI format is like "8:orgid:uuid"
                mri = data.get("mri", "")
                if mri:
                    user_id = self._extract_user_id_from_mri(mri)
                    if user_id:
                        self._my_user_id = user_id
                        return user_id
                # Also try objectId or id
                obj_id = data.get("objectId") or data.get("id")
                if obj_id:
                    self._my_user_id = obj_id
                    return obj_id
        except Exception:
            pass
        
        # Method 2: Extract from skype token (it contains user info)
        try:
            import base64
            import json
            if self.auth.skype_token:
                # JWT format: header.payload.signature
                parts = self.auth.skype_token.split('.')
                if len(parts) >= 2:
                    # Add padding if needed
                    payload = parts[1]
                    padding = 4 - len(payload) % 4
                    if padding != 4:
                        payload += '=' * padding
                    decoded = base64.urlsafe_b64decode(payload)
                    token_data = json.loads(decoded)
                    # skypeid format: "orgid:uuid"
                    skype_id = token_data.get("skypeid", "")
                    if ":" in skype_id:
                        user_id = skype_id.split(":")[-1]
                        self._my_user_id = user_id
                        return user_id
        except Exception:
            pass
        
        return None
    
    def get_user_info(self, user_mri):
        """Get display name and avatar for a user MRI."""
        if user_mri in self._user_cache:
            return self._user_cache[user_mri]
        
        profile = self.client.get_user_profile(user_mri)
        info = {"name": "Unknown", "avatar": ""}
        
        if profile:
            info["name"] = profile.get("displayName", "Unknown")
            # Avatar will be fetched separately by QML
        
        self._user_cache[user_mri] = info
        return info
    
    def get_chats(self):
        """Get processed chat list with display names and avatars."""
        conversations = self.client.get_conversations()
        chats = []
        my_id = self._get_my_user_id()
        
        # Collect user MRIs to batch fetch
        user_mris = set()
        
        for conv in conversations:
            conv_id = conv.get("id", "")
            
            # Skip system conversations
            if conv_id.startswith("48:"):
                continue
            
            # Determine chat type
            if "@thread.tacv2" in conv_id:
                chat_type = "channel"
            elif "@unq.gbl" in conv_id:
                chat_type = "chat"
            elif "@thread.v2" in conv_id:
                chat_type = "group"
            else:
                continue
            
            # Get last message preview
            last_msg = conv.get("lastMessage", {})
            last_content = last_msg.get("content", "")
            if "<" in last_content:
                import re
                last_content = re.sub(r'<[^>]+>', '', last_content)
            last_content = last_content[:50]
            
            last_time = last_msg.get("composetime")
            
            # Get thread properties for name
            thread_props = conv.get("threadProperties", {})
            # Teams uses different fields for topic depending on type
            topic = thread_props.get("topic", "") or thread_props.get("spaceThreadTopic", "")
            # Get groupId for Teams channels (used to fetch team photo)
            group_id = thread_props.get("groupId", "")
            
            # For 1:1 chats, get the other person's MRI
            other_mri = ""
            if chat_type == "chat":
                # Extract user IDs from conversation ID like 19:uuid1_uuid2@unq.gbl.spaces
                parts = conv_id.replace("19:", "").split("@")[0].split("_")
                other_id = None
                for p in parts:
                    if p != my_id:
                        other_id = p
                        break
                
                # If we couldn't find the other user (maybe my_id not in parts), try differently
                if not other_id and len(parts) == 2:
                    other_id = parts[0] if parts[0] else parts[1]
                
                if other_id:
                    other_mri = f"8:orgid:{other_id}"
                    user_mris.add(other_mri)
            
            chats.append({
                "id": conv_id,
                "type": chat_type,
                "last_message": last_content,
                "last_time": last_time,
                "members": conv.get("members", []),
                "other_mri": other_mri,
                "topic": topic,
                "group_id": group_id,
            })
        
        # Batch fetch user profiles
        if user_mris:
            profiles = self.client.get_user_profiles_batch(list(user_mris))
            for p in profiles:
                mri = p.get("mri", "")
                name = p.get("displayName", "Unknown")
                self._user_cache[mri] = {"name": name, "avatar": ""}
        
        # Build final chat list with names
        result = []
        for chat in chats:
            user_mri = ""
            if chat["type"] == "chat":
                user_mri = chat["other_mri"]
                cached = self._user_cache.get(user_mri, {})
                display_name = cached.get("name", "Unknown")
            elif chat["type"] == "channel":
                # Use topic if available, otherwise generic name
                display_name = chat.get("topic") or "Channel"
            else:
                # Group chat - use topic or list member names
                topic = chat.get("topic", "")
                if topic:
                    display_name = topic
                else:
                    # Try to build name from members
                    members = chat.get("members", [])
                    member_names = []
                    for m in members[:4]:  # Limit to 4 names
                        mri = m.get("id", "")
                        if mri in self._user_cache:
                            member_names.append(self._user_cache[mri].get("name", ""))
                    if member_names:
                        display_name = ", ".join(n for n in member_names if n)[:40]
                    else:
                        display_name = "Group Chat"
            
            result.append(ChatInfo(
                conversation_id=chat["id"],
                display_name=display_name,
                last_message=chat["last_message"],
                last_time=chat["last_time"],
                chat_type=chat["type"],
                user_mri=user_mri,
                group_id=chat.get("group_id", "")
            ))
        
        return result
    
    def get_teams_list(self):
        """Get list of teams with channels."""
        try:
            teams = self.client.get_teams()
            result = []
            
            if not isinstance(teams, list):
                return []
            
            for team in teams:
                if not isinstance(team, dict):
                    continue
                    
                team_info = {
                    "id": team.get("id", ""),
                    "name": team.get("displayName", "Unknown Team"),
                    "description": team.get("description", ""),
                    "channels": []
                }
                
                # Get channels for this team
                try:
                    team_id = team.get("id")
                    if team_id:
                        channels = self.client.get_team_channels(team_id)
                        if isinstance(channels, list):
                            for ch in channels:
                                if isinstance(ch, dict):
                                    team_info["channels"].append({
                                        "id": ch.get("id", ""),
                                        "name": ch.get("displayName", "Unknown Channel"),
                                        "description": ch.get("description", ""),
                                    })
                except Exception:
                    pass
                
                result.append(team_info)
            
            return result
        except Exception:
            return []
