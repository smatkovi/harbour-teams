#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Microsoft Teams API Client for MeeGo Harmattan
Based on Sailfish OS harbour-teams implementation
Runs with Python 3.11, called via subprocess from Python 2.7 launcher
"""

import sys
import json
import time
import os
import hashlib
import base64
from pathlib import Path

# Use urllib for HTTP requests (no external dependencies)
import urllib.request
import urllib.parse
import urllib.error
import ssl

# Disable SSL verification for older systems
ssl._create_default_https_context = ssl._create_unverified_context

# Paths
CONFIG_DIR = Path.home() / ".config" / "teams"
TOKENS_FILE = CONFIG_DIR / "tokens.json"
AVATAR_CACHE_DIR = Path.home() / ".cache" / "teams" / "avatars"
MESSAGES_CACHE_DIR = Path.home() / ".cache" / "teams" / "messages"
CONVERSATIONS_CACHE_FILE = Path.home() / ".cache" / "teams" / "conversations.json"
PROFILES_CACHE_FILE = Path.home() / ".cache" / "teams" / "profiles.json"

# Cache expiry times (seconds)
CONVERSATIONS_CACHE_MAX_AGE = 300  # 5 minutes
PROFILES_CACHE_MAX_AGE = 86400  # 24 hours

# Azure CLI public client
CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
RESOURCE = "https://api.spaces.skype.com"
AUTHORITY = "https://login.microsoftonline.com/common"


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    MESSAGES_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def http_request(url, method="GET", headers=None, data=None, timeout=45):
    """Make HTTP request with gzip support for bandwidth efficiency."""
    import gzip
    
    headers = headers or {}
    
    # Add User-Agent if not set
    if "User-Agent" not in headers:
        headers["User-Agent"] = "Mozilla/5.0 (compatible; TeamsClient/1.0)"
    
    # Add gzip support for smaller responses (saves bandwidth on 2G)
    if "Accept-Encoding" not in headers:
        headers["Accept-Encoding"] = "gzip, deflate"
    
    if data and isinstance(data, dict):
        if headers.get("Content-Type") == "application/json":
            data = json.dumps(data).encode('utf-8')
        else:
            data = urllib.parse.urlencode(data).encode('utf-8')
    
    print(f"HTTP {method} {url}", file=sys.stderr)
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
            
            # Decompress gzip if needed
            if resp.getheader('Content-Encoding') == 'gzip':
                try:
                    content = gzip.decompress(content)
                except:
                    pass  # Not actually gzipped
            
            print(f"HTTP Response: {resp.status}", file=sys.stderr)
            try:
                parsed = json.loads(content.decode('utf-8'))
                # Ensure we always return a dict
                if isinstance(parsed, dict):
                    return parsed
                elif isinstance(parsed, list):
                    return {"data": parsed}
                else:
                    return {"value": parsed}
            except:
                return {"raw": content}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='ignore')
        print(f"HTTP Error {e.code}: {error_body[:500]}", file=sys.stderr)
        try:
            return {"error": True, "status": e.code, "body": json.loads(error_body)}
        except:
            return {"error": True, "status": e.code, "body": error_body}
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}", file=sys.stderr)
        return {"error": True, "message": str(e.reason)}
    except Exception as e:
        print(f"Request error: {e}", file=sys.stderr)
        return {"error": True, "message": str(e)}


class TeamsAuth:
    """Handles Teams authentication via device code flow."""
    
    def __init__(self):
        self.access_token = None
        self.refresh_token = None
        self.skype_token = None
        self.region = "emea"
        self.chat_service = None
        self.middle_tier = None
        self.my_mri = None
        self.display_name = None
    
    def start_device_code_flow(self):
        """Start device code flow. Returns dict with user_code and verification_url."""
        result = http_request(
            f"{AUTHORITY}/oauth2/devicecode",
            method="POST",
            data={
                "client_id": CLIENT_ID,
                "resource": RESOURCE,
            }
        )
        return result
    
    def poll_for_token(self, device_code, interval=5, timeout=900):
        """Poll for token after user authenticates. Returns True on success."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            time.sleep(interval)
            
            result = http_request(
                f"{AUTHORITY}/oauth2/token",
                method="POST",
                data={
                    "client_id": CLIENT_ID,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "code": device_code,
                }
            )
            
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
        
        result = http_request(
            f"{AUTHORITY}/oauth2/token",
            method="POST",
            data={
                "client_id": CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "resource": RESOURCE,
            }
        )
        
        if "access_token" in result:
            self.access_token = result["access_token"]
            if "refresh_token" in result:
                self.refresh_token = result["refresh_token"]
            return True
        return False
    
    def get_teams_authorization(self):
        """Get Teams authorization including Skype token."""
        if not self.access_token:
            return False
        
        result = http_request(
            "https://teams.microsoft.com/api/authsvc/v1.0/authz",
            method="POST",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
        )
        
        if result.get("error"):
            return False
        
        tokens = result.get("tokens", {})
        self.skype_token = tokens.get("skypeToken")
        self.region = result.get("region", "emea")
        
        region_gtms = result.get("regionGtms", {})
        self.chat_service = region_gtms.get("chatService", f"https://{self.region}.ng.msg.teams.microsoft.com")
        self.middle_tier = region_gtms.get("middleTier", f"https://teams.microsoft.com/api/mt/{self.region}")
        
        # Extract my MRI from skype token
        self._extract_my_mri()
        
        return self.skype_token is not None
    
    def _extract_my_mri(self):
        """Extract user MRI from Skype token (JWT)."""
        if not self.skype_token:
            return
        try:
            parts = self.skype_token.split('.')
            if len(parts) >= 2:
                payload = parts[1]
                # Add padding
                padding = 4 - len(payload) % 4
                if padding != 4:
                    payload += '=' * padding
                decoded = base64.urlsafe_b64decode(payload)
                data = json.loads(decoded)
                skype_id = data.get("skypeid", "")
                if skype_id:
                    self.my_mri = f"8:{skype_id}"
                self.display_name = data.get("name", "Teams User")
        except Exception as e:
            print(f"Error extracting MRI: {e}", file=sys.stderr)
    
    def save_tokens(self):
        """Save tokens to JSON file."""
        ensure_dirs()
        tokens = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "skype_token": self.skype_token,
            "region": self.region,
            "chat_service": self.chat_service,
            "middle_tier": self.middle_tier,
            "my_mri": self.my_mri,
            "display_name": self.display_name,
        }
        with open(TOKENS_FILE, 'w') as f:
            json.dump(tokens, f)
    
    def load_tokens(self):
        """Load tokens from JSON file."""
        if not TOKENS_FILE.exists():
            return False
        try:
            with open(TOKENS_FILE) as f:
                tokens = json.load(f)
            self.access_token = tokens.get("access_token")
            self.refresh_token = tokens.get("refresh_token")
            self.skype_token = tokens.get("skype_token")
            self.region = tokens.get("region", "emea")
            self.chat_service = tokens.get("chat_service")
            self.middle_tier = tokens.get("middle_tier")
            self.my_mri = tokens.get("my_mri")
            self.display_name = tokens.get("display_name", "Teams User")
            return self.skype_token is not None
        except Exception as e:
            print(f"Error loading tokens: {e}", file=sys.stderr)
            return False
    
    def clear_tokens(self):
        """Delete tokens file."""
        if TOKENS_FILE.exists():
            TOKENS_FILE.unlink()
    
    def is_authenticated(self):
        return self.skype_token is not None
    
    def get_graph_token(self):
        """Get a Microsoft Graph access token."""
        if not self.refresh_token:
            return None
        
        result = http_request(
            f"{AUTHORITY}/oauth2/token",
            method="POST",
            data={
                "client_id": CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "resource": "https://graph.microsoft.com",
            }
        )
        
        if "access_token" in result:
            return result["access_token"]
        return None


class TeamsClient:
    """Teams API client for chats, messages, etc."""
    
    def __init__(self, auth):
        self.auth = auth
        ensure_dirs()
    
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
        # Use proxy URL like SFOS does
        base_url = f"https://teams.microsoft.com/api/chatsvc/{self.auth.region}/v1/users/ME/conversations"
        
        # Build query string - view parameter needs proper encoding
        view_param = urllib.parse.quote("msnp24Equivalent|supportsMessageProperties", safe='')
        full_url = f"{base_url}?view={view_param}&pageSize={page_size}"
        
        print(f"get_conversations URL: {full_url}", file=sys.stderr)
        print(f"Using skype_token: {self.auth.skype_token[:50] if self.auth.skype_token else 'None'}...", file=sys.stderr)
        
        result = http_request(
            full_url,
            headers=self._headers(),
        )
        
        if result.get("error"):
            print(f"get_conversations error: {result}", file=sys.stderr)
            return []
        
        convs = result.get("conversations", [])
        print(f"Got {len(convs)} conversations", file=sys.stderr)
        return convs
    
    def get_conversation_messages(self, conversation_id, page_size=30, start_time=0):
        """Get messages from a conversation.
        
        Args:
            conversation_id: The conversation ID
            page_size: Number of messages to fetch
            start_time: Unix timestamp in milliseconds - only get messages after this time
        """
        encoded_id = urllib.parse.quote(conversation_id, safe='')
        base_url = f"https://teams.microsoft.com/api/chatsvc/{self.auth.region}/v1/users/ME/conversations/{encoded_id}/messages"
        
        view_param = urllib.parse.quote("msnp24Equivalent|supportsMessageProperties", safe='')
        full_url = f"{base_url}?startTime={start_time}&pageSize={page_size}&view={view_param}"
        
        result = http_request(
            full_url,
            headers=self._headers(),
        )
        
        if result.get("error"):
            print(f"get_messages error: {result}", file=sys.stderr)
            return []
        
        return result.get("messages", [])
    
    def send_message(self, conversation_id, content, message_type="Text"):
        """Send a message to a conversation."""
        encoded_id = urllib.parse.quote(conversation_id, safe='')
        client_msg_id = str(int(time.time() * 1000))
        
        payload = {
            "content": content,
            "messagetype": message_type,
            "contenttype": "text",
            "amsreferences": [],
            "clientmessageid": client_msg_id,
            "properties": {
                "importance": "",
                "subject": None,
            }
        }
        
        url = f"https://teams.microsoft.com/api/chatsvc/{self.auth.region}/v1/users/ME/conversations/{encoded_id}/messages"
        
        result = http_request(
            url,
            method="POST",
            headers=self._headers(),
            data=json.dumps(payload).encode('utf-8')
        )
        
        # Check if successful (no error key or status in 200s)
        if result.get("error"):
            return False
        return True
    
    def get_user_avatar(self, user_mri, size="HR64x64"):
        """Get user avatar. Returns local file path or None."""
        mri_hash = hashlib.md5(user_mri.encode()).hexdigest()
        
        # Check cache - permanent, no expiry
        for ext in ['.jpg', '.png', '.gif']:
            cache_file = AVATAR_CACHE_DIR / f"{mri_hash}_{size}{ext}"
            if cache_file.exists():
                return str(cache_file)
        
        # Fetch from API (not cached yet)
        print(f"Fetching new avatar: {user_mri[:30]}...", file=sys.stderr)
        try:
            url = f"{self.auth.middle_tier}/beta/users/{urllib.parse.quote(user_mri, safe='')}/profilepicturev2?size={size}"
            
            req = urllib.request.Request(url, headers=self._mt_headers())
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read()
                
                if len(content) > 100:
                    # Detect format
                    if content[:3] == b'\xff\xd8\xff':
                        ext = '.jpg'
                    elif content[:8] == b'\x89PNG\r\n\x1a\n':
                        ext = '.png'
                    else:
                        ext = '.jpg'
                    
                    cache_file = AVATAR_CACHE_DIR / f"{mri_hash}_{size}{ext}"
                    with open(cache_file, 'wb') as f:
                        f.write(content)
                    return str(cache_file)
        except Exception as e:
            print(f"Avatar error: {e}", file=sys.stderr)
        
        return None
    
    def search_people(self, query):
        """Search for people by name or email using Microsoft Graph API."""
        # Trim whitespace from query
        query = query.strip()
        if not query:
            return []
        
        try:
            # First try Graph API (more reliable)
            graph_token = self._get_graph_token()
            if graph_token:
                results = self._search_people_graph(query, graph_token)
                if results:
                    return results
            
            # Fallback to Teams API
            results = self._search_people_teams(query)
            if results:
                return results
                
            print("No search results from any API", file=sys.stderr)
            return []
        except Exception as e:
            print(f"search_people exception: {e}", file=sys.stderr)
            return []
    
    def _get_graph_token(self):
        """Get a token for Microsoft Graph API."""
        if not self.auth.refresh_token:
            print("No refresh token for Graph API", file=sys.stderr)
            return None
        try:
            url = f"{AUTHORITY}/oauth2/token"
            data = {
                "client_id": CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": self.auth.refresh_token,
                "resource": "https://graph.microsoft.com",
            }
            
            req = urllib.request.Request(url, 
                data=urllib.parse.urlencode(data).encode('utf-8'),
                headers={"Content-Type": "application/x-www-form-urlencoded"})
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                token = result.get("access_token")
                if token:
                    print("Got Graph API token", file=sys.stderr)
                return token
        except Exception as e:
            print(f"Graph token error: {e}", file=sys.stderr)
        return None
    
    def _search_people_graph(self, query, graph_token):
        """Search people using Microsoft Graph API."""
        try:
            # Build the OData filter - encode the whole query parameter properly
            filter_str = f"startswith(displayName,'{query}') or startswith(mail,'{query}')"
            # Use urlencode for proper query string encoding
            params = urllib.parse.urlencode({
                '$filter': filter_str,
                '$top': '20'
            })
            url = f"https://graph.microsoft.com/v1.0/users?{params}"
            
            headers = {
                "Authorization": f"Bearer {graph_token}",
                "Content-Type": "application/json",
            }
            
            print(f"Graph search: {query}", file=sys.stderr)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                users = data.get("value", [])
                results = []
                for user in users:
                    user_id = user.get("id", "")
                    results.append({
                        "id": user_id,
                        "displayName": user.get("displayName", "Unknown"),
                        "email": user.get("mail", "") or user.get("userPrincipalName", ""),
                        "mri": f"8:orgid:{user_id}",
                    })
                print(f"Graph found {len(results)} people", file=sys.stderr)
                return results
        except urllib.error.HTTPError as e:
            print(f"Graph search HTTP error: {e.code} - {e.read().decode()[:200]}", file=sys.stderr)
        except Exception as e:
            print(f"Graph search exception: {e}", file=sys.stderr)
        return []
    
    def _search_people_teams(self, query):
        """Search people using Teams middle tier API."""
        try:
            url = f"{self.auth.middle_tier}/beta/users/searchV2"
            payload = json.dumps({"query": query, "top": 20, "querySource": "Input"})
            
            print(f"Teams search payload: {payload}", file=sys.stderr)
            
            result = http_request(
                url,
                method="POST",
                headers=self._mt_headers(),
                data=payload.encode('utf-8')
            )
            
            print(f"Teams search raw result: {str(result)[:300]}", file=sys.stderr)
            
            if result.get("error"):
                print(f"Teams search error: {result.get('error')}", file=sys.stderr)
                return []
            
            # Try different response structures
            users = []
            if isinstance(result, dict):
                users = result.get("value", []) or result.get("results", []) or result.get("users", [])
            elif isinstance(result, list):
                users = result
            
            results = []
            for user in users:
                user_id = user.get("objectId", user.get("id", ""))
                mri = user.get("mri", f"8:orgid:{user_id}")
                results.append({
                    "id": user_id,
                    "displayName": user.get("displayName", "Unknown"),
                    "email": user.get("email", "") or user.get("mail", ""),
                    "mri": mri,
                })
            print(f"Teams found {len(results)} people", file=sys.stderr)
            return results
        except Exception as e:
            print(f"Teams search error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return []
    
    def create_chat(self, user_mri):
        """Create a new 1:1 chat with a user."""
        if not self.auth.my_mri:
            return None
        
        try:
            url = f"{self.auth.chat_service}/v1/threads"
            headers = {
                "Authentication": f"skypetoken={self.auth.skype_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "members": [
                    {"id": self.auth.my_mri, "role": "Admin"},
                    {"id": user_mri, "role": "Admin"}
                ],
                "properties": {
                    "threadType": "chat",
                    "uniquerosterthread": "true",
                    "fixedRoster": "true"
                }
            }
            
            result = http_request(url, method="POST", headers=headers, 
                                 data=json.dumps(payload).encode('utf-8'))
            
            if not result.get("error"):
                # Construct conversation ID
                my_uuid = self.auth.my_mri.split(":")[-1]
                other_uuid = user_mri.split(":")[-1]
                if my_uuid < other_uuid:
                    return f"19:{my_uuid}_{other_uuid}@unq.gbl.spaces"
                else:
                    return f"19:{other_uuid}_{my_uuid}@unq.gbl.spaces"
        except Exception as e:
            print(f"Create chat error: {e}", file=sys.stderr)
        
        return None


# ==================== Command Handler ====================

def handle_command(cmd, args):
    """Handle a command from the Python 2 launcher."""
    auth = TeamsAuth()
    
    if cmd == "CHECK_AUTH":
        if auth.load_tokens():
            return json.dumps({
                "authenticated": True,
                "displayName": auth.display_name,
                "myMri": auth.my_mri,
            })
        return json.dumps({"authenticated": False})
    
    elif cmd == "START_DEVICE_FLOW":
        result = auth.start_device_code_flow()
        return json.dumps(result)
    
    elif cmd == "POLL_TOKEN":
        device_code = args.get("device_code")
        if auth.poll_for_token(device_code):
            if auth.get_teams_authorization():
                auth.save_tokens()
                return json.dumps({
                    "success": True,
                    "displayName": auth.display_name,
                    "myMri": auth.my_mri,
                })
        return json.dumps({"success": False})
    
    elif cmd == "REFRESH_TOKEN":
        if auth.load_tokens() and auth.refresh_access_token():
            if auth.get_teams_authorization():
                auth.save_tokens()
                return json.dumps({"success": True})
        return json.dumps({"success": False})
    
    elif cmd == "LOGOUT":
        auth.clear_tokens()
        return json.dumps({"success": True})
    
    elif cmd == "GET_CACHED_CONVERSATIONS":
        # Load conversations from disk cache only (no network) - for fast startup
        if CONVERSATIONS_CACHE_FILE.exists():
            try:
                with open(CONVERSATIONS_CACHE_FILE, 'r') as f:
                    cached_data = json.load(f)
                    convs = cached_data.get("conversations", [])
                    timestamp = cached_data.get("timestamp", 0)
                    age = time.time() - timestamp
                    print(f"Loaded {len(convs)} conversations from disk cache (age: {int(age)}s)", file=sys.stderr)
                    return json.dumps({"conversations": convs, "fromCache": True, "age": age})
            except Exception as e:
                print(f"Failed to load conversations cache: {e}", file=sys.stderr)
        return json.dumps({"conversations": [], "fromCache": True})
    
    elif cmd == "UPDATE_CONVERSATION_CACHE":
        # Update a single conversation's lastTime in cache (after new messages)
        conv_id = args.get("conversation_id", "")
        last_time = args.get("last_time", "")
        last_message = args.get("last_message", "")
        
        if not conv_id or not CONVERSATIONS_CACHE_FILE.exists():
            return json.dumps({"success": False})
        
        try:
            with open(CONVERSATIONS_CACHE_FILE, 'r') as f:
                cached_data = json.load(f)
            
            convs = cached_data.get("conversations", [])
            updated = False
            
            for conv in convs:
                if conv.get("id") == conv_id:
                    if last_time:
                        conv["lastTime"] = last_time
                    if last_message:
                        conv["lastMessage"] = last_message[:50]
                    updated = True
                    break
            
            if updated:
                # Re-sort by lastTime
                convs.sort(key=lambda c: c.get("lastTime", ""), reverse=True)
                cached_data["conversations"] = convs
                cached_data["timestamp"] = time.time()
                
                with open(CONVERSATIONS_CACHE_FILE, 'w') as f:
                    json.dump(cached_data, f)
                
                print(f"Updated conversation {conv_id[:30]} in cache", file=sys.stderr)
                return json.dumps({"success": True, "conversations": convs})
            
            return json.dumps({"success": False})
        except Exception as e:
            print(f"Failed to update conversation cache: {e}", file=sys.stderr)
            return json.dumps({"success": False})
    
    elif cmd == "GET_CONVERSATIONS":
        if not auth.load_tokens():
            return json.dumps({"error": "Not authenticated"})
        
        print(f"GET_CONVERSATIONS: region={auth.region}, skype_token={auth.skype_token[:20] if auth.skype_token else 'None'}...", file=sys.stderr)
        
        client = TeamsClient(auth)
        convs = client.get_conversations()
        
        # If no conversations and we might have a stale token, try refreshing
        if len(convs) == 0:
            print("No conversations - trying token refresh...", file=sys.stderr)
            if auth.refresh_access_token() and auth.get_teams_authorization():
                auth.save_tokens()
                print("Token refreshed, retrying...", file=sys.stderr)
                client = TeamsClient(auth)
                convs = client.get_conversations()
        
        print(f"Raw conversations count: {len(convs)}", file=sys.stderr)
        
        # Get my user ID (uuid part from my_mri like "8:orgid:uuid")
        my_user_id = ""
        if auth.my_mri and ":" in auth.my_mri:
            parts = auth.my_mri.split(":")
            if len(parts) >= 3:
                my_user_id = parts[2]
            elif len(parts) >= 2:
                my_user_id = parts[-1]
        
        print(f"My user ID: {my_user_id}", file=sys.stderr)
        
        # First pass: categorize conversations and collect user MRIs
        chats = []
        user_mris_to_fetch = set()
        
        for conv in convs:
            if not isinstance(conv, dict):
                continue
            
            conv_id = conv.get("id", "")
            
            # Skip system conversations
            if conv_id.startswith("48:"):
                continue
            
            # Determine chat type from conversation ID
            if "@thread.tacv2" in conv_id:
                chat_type = "channel"
            elif "@unq.gbl" in conv_id:
                chat_type = "chat"
            elif "@thread.v2" in conv_id or "@thread.skype" in conv_id:
                chat_type = "group"
            else:
                continue
            
            # Get thread properties
            props = conv.get("threadProperties", {})
            if not isinstance(props, dict):
                props = {}
            
            topic = props.get("topic", "") or props.get("spaceThreadTopic", "")
            
            # Get last message info
            last_msg = ""
            last_time = ""
            last_msg_obj = conv.get("lastMessage", {})
            if isinstance(last_msg_obj, dict):
                last_msg = last_msg_obj.get("content", "")[:50]
                last_time = last_msg_obj.get("composetime", "")
                # Strip HTML
                if "<" in last_msg:
                    import re
                    last_msg = re.sub(r'<[^>]+>', '', last_msg)
            
            # Fallback for time
            if not last_time:
                last_time = conv.get("lastActivityTime", "")
            
            # For 1:1 chats, extract the other user's MRI
            other_mri = ""
            if chat_type == "chat" and my_user_id:
                # Extract user IDs from conversation ID like 19:uuid1_uuid2@unq.gbl.spaces
                try:
                    id_part = conv_id.replace("19:", "").split("@")[0]
                    parts = id_part.split("_")
                    other_id = None
                    for p in parts:
                        if p and p != my_user_id:
                            other_id = p
                            break
                    if other_id:
                        other_mri = f"8:orgid:{other_id}"
                        user_mris_to_fetch.add(other_mri)
                except:
                    pass
            
            chats.append({
                "id": conv_id,
                "type": chat_type,
                "topic": topic,
                "last_msg": last_msg,
                "last_time": last_time,
                "other_mri": other_mri,
                "members": conv.get("members", []),
            })
        
        # Batch fetch user profiles for 1:1 chats
        # Load cached profiles first (saves bandwidth on 2G)
        user_cache = {}
        profiles_changed = False
        
        if PROFILES_CACHE_FILE.exists():
            try:
                with open(PROFILES_CACHE_FILE, 'r') as f:
                    cached_profiles = json.load(f)
                    user_cache = cached_profiles.get("profiles", {})
                    print(f"Loaded {len(user_cache)} profiles from disk cache", file=sys.stderr)
            except:
                pass
        
        # Find which MRIs we still need to fetch
        mris_to_fetch = [m for m in user_mris_to_fetch if m not in user_cache]
        
        if mris_to_fetch:
            print(f"Fetching {len(mris_to_fetch)} new user profiles (cached: {len(user_cache)})...", file=sys.stderr)
            try:
                url = f"{auth.middle_tier}/beta/users/fetchShortProfile?isMailAddress=false&enableGuest=true"
                payload = json.dumps(list(mris_to_fetch))
                result = http_request(url, method="POST", headers={
                    "Authorization": f"Bearer {auth.access_token}",
                    "Content-Type": "application/json",
                }, data=payload.encode('utf-8'))
                
                profiles = []
                if isinstance(result, dict):
                    profiles = result.get("value", result.get("data", []))
                elif isinstance(result, list):
                    profiles = result
                
                for p in profiles:
                    if isinstance(p, dict):
                        mri = p.get("mri", "")
                        name = p.get("displayName", "Unknown")
                        user_cache[mri] = name
                        profiles_changed = True
                        print(f"  Profile: {mri} -> {name}", file=sys.stderr)
                
                # Save updated cache
                if profiles_changed:
                    try:
                        with open(PROFILES_CACHE_FILE, 'w') as f:
                            json.dump({"profiles": user_cache}, f)
                        print(f"Saved {len(user_cache)} profiles to disk cache", file=sys.stderr)
                    except:
                        pass
                        
            except Exception as e:
                print(f"Profile fetch error: {e}", file=sys.stderr)
        else:
            print(f"All {len(user_cache)} profiles loaded from cache", file=sys.stderr)
        
        # Build final result with cached avatar paths
        result = []
        for chat in chats:
            chat_type = chat["type"]
            other_mri = chat["other_mri"]
            
            if chat_type == "chat":
                # 1:1 chat - get name from user cache
                display_name = user_cache.get(other_mri, "Chat")
            elif chat_type == "channel":
                # Channel - use topic
                display_name = chat["topic"] or "Channel"
            else:
                # Group - use topic or "Group Chat"
                display_name = chat["topic"] or "Group Chat"
            
            # Check if avatar is in disk cache
            avatar_path = ""
            if other_mri:
                mri_hash = hashlib.md5(other_mri.encode()).hexdigest()
                for ext in ['.jpg', '.png', '.gif']:
                    cache_file = AVATAR_CACHE_DIR / f"{mri_hash}_HR64x64{ext}"
                    if cache_file.exists():
                        avatar_path = str(cache_file)
                        break
            
            result.append({
                "id": chat["id"],
                "name": display_name,
                "chatType": chat_type,
                "lastMessage": chat["last_msg"],
                "lastTime": chat["last_time"],
                "userMri": other_mri,
                "avatarPath": avatar_path,  # Pre-loaded from disk cache
            })
        
        # Sort by lastTime - newest first
        def sort_key(conv):
            t = conv.get("lastTime", "")
            if not t:
                return ""
            return t
        
        result.sort(key=sort_key, reverse=True)
        
        # Save to disk cache for faster startup
        try:
            with open(CONVERSATIONS_CACHE_FILE, 'w') as f:
                json.dump({
                    "conversations": result,
                    "timestamp": time.time()
                }, f)
            print(f"Saved {len(result)} conversations to disk cache", file=sys.stderr)
        except Exception as e:
            print(f"Failed to save conversations cache: {e}", file=sys.stderr)
        
        print(f"Returning {len(result)} conversations", file=sys.stderr)
        return json.dumps({"conversations": result})
    
    elif cmd == "GET_MESSAGES":
        if not auth.load_tokens():
            return json.dumps({"error": "Not authenticated"})
        
        # Ensure cache directory exists
        ensure_dirs()
        
        conv_id = args.get("conversation_id")
        use_cache_only = args.get("cache_only", False)
        force_refresh = args.get("refresh", False)
        
        # Create cache filename from conversation ID
        conv_hash = hashlib.md5(conv_id.encode()).hexdigest()
        cache_file = MESSAGES_CACHE_DIR / f"{conv_hash}.json"
        
        # Try to load from cache first
        cached_messages = []
        last_time_ms = 0
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                    cached_messages = cached_data.get("messages", [])
                    last_time_ms = cached_data.get("last_time_ms", 0)
                    print(f"Loaded {len(cached_messages)} messages from disk cache", file=sys.stderr)
            except:
                pass
        
        # If cache_only mode, return cached messages immediately
        if use_cache_only:
            if cached_messages:
                return json.dumps({"messages": cached_messages, "fromCache": True})
            else:
                return json.dumps({"messages": [], "fromCache": True})
        
        # Find the newest message time from cache to use as startTime
        if cached_messages and not last_time_ms:
            # Parse times from cached messages to find newest
            for msg in cached_messages:
                msg_time = msg.get("time", "")
                if msg_time:
                    try:
                        # Parse ISO format: 2024-01-15T10:30:00.000Z
                        from datetime import datetime
                        dt = datetime.fromisoformat(msg_time.replace('Z', '+00:00'))
                        ts_ms = int(dt.timestamp() * 1000)
                        if ts_ms > last_time_ms:
                            last_time_ms = ts_ms
                    except:
                        pass
        
        # Fetch from API - use startTime to only get new messages
        client = TeamsClient(auth)
        if last_time_ms > 0:
            # Add 1ms to avoid getting the same message again
            messages = client.get_conversation_messages(conv_id, start_time=last_time_ms + 1)
            print(f"Fetching messages after {last_time_ms} (incremental)", file=sys.stderr)
        else:
            messages = client.get_conversation_messages(conv_id)
            print(f"Fetching all messages (no cache)", file=sys.stderr)
        
        # Get my user ID for comparison
        my_mri = auth.my_mri or ""
        my_user_id = ""
        if my_mri and ":" in my_mri:
            my_user_id = my_mri.split(":")[-1]
        
        # Process new messages
        import re
        new_messages = []
        newest_time_ms = last_time_ms
        for msg in messages:
            msg_type = msg.get("messagetype", "")
            if msg_type not in ["Text", "RichText/Html"]:
                continue
            
            content = msg.get("content", "")
            content = re.sub(r'<[^>]+>', '', content)
            
            from_mri = msg.get("from", "")
            sender_name = msg.get("imdisplayname", "")
            
            is_me = False
            if from_mri:
                if from_mri == my_mri:
                    is_me = True
                elif my_user_id and my_user_id in from_mri:
                    is_me = True
            
            if is_me and not sender_name:
                sender_name = auth.display_name or "Me"
            elif not sender_name:
                sender_name = "Unknown"
            
            msg_time = msg.get("composetime", "")
            
            # Track newest time
            if msg_time:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(msg_time.replace('Z', '+00:00'))
                    ts_ms = int(dt.timestamp() * 1000)
                    if ts_ms > newest_time_ms:
                        newest_time_ms = ts_ms
                except:
                    pass
            
            # Parse attachments
            attachments = []
            props = msg.get("properties", {})
            files_raw = props.get("files", "")
            if files_raw:
                try:
                    files_data = json.loads(files_raw) if isinstance(files_raw, str) else files_raw
                    for f in files_data:
                        attachments.append({
                            "name": f.get("title", f.get("fileName", "File")),
                            "url": f.get("objectUrl", ""),
                            "type": f.get("fileType", ""),
                            "size": f.get("fileInfo", {}).get("fileSize", 0) if isinstance(f.get("fileInfo"), dict) else 0
                        })
                except:
                    pass
            
            # Check for inline images in amsreferences
            ams_refs = msg.get("amsreferences", [])
            for ref in ams_refs:
                if ref and ":" in ref:
                    attachments.append({
                        "name": "Image",
                        "url": ref,
                        "type": "image",
                        "amsRef": True
                    })
            
            new_messages.append({
                "id": msg.get("id", ""),
                "content": content,
                "sender": sender_name,
                "senderMri": from_mri,
                "isMe": is_me,
                "time": msg_time,
                "attachments": attachments,
            })
        
        print(f"Got {len(new_messages)} new messages from API", file=sys.stderr)
        
        # Merge with cached messages
        if cached_messages and new_messages:
            # Get existing message IDs to avoid duplicates
            existing_ids = {m.get("id") for m in cached_messages}
            for msg in new_messages:
                if msg.get("id") not in existing_ids:
                    cached_messages.append(msg)
            result = cached_messages
            # Sort by time
            result.sort(key=lambda m: m.get("time", ""))
            print(f"Merged to {len(result)} total messages", file=sys.stderr)
        elif cached_messages:
            result = cached_messages
        else:
            # No cache - reverse new messages (API returns newest first)
            new_messages.reverse()
            result = new_messages
        
        # Save to disk cache with newest time
        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    "messages": result,
                    "conv_id": conv_id,
                    "last_time_ms": newest_time_ms
                }, f)
            print(f"Saved {len(result)} messages to disk cache", file=sys.stderr)
        except Exception as e:
            print(f"Failed to save message cache: {e}", file=sys.stderr)
        
        return json.dumps({"messages": result})
    
    elif cmd == "SEND_MESSAGE":
        if not auth.load_tokens():
            return json.dumps({"error": "Not authenticated"})
        
        conv_id = args.get("conversation_id")
        content = args.get("content")
        
        client = TeamsClient(auth)
        success = client.send_message(conv_id, content)
        return json.dumps({"success": success})
    
    elif cmd == "GET_AVATAR":
        if not auth.load_tokens():
            return json.dumps({"path": ""})
        
        user_mri = args.get("user_mri")
        client = TeamsClient(auth)
        path = client.get_user_avatar(user_mri)
        return json.dumps({"path": path or ""})
    
    elif cmd == "SEARCH_PEOPLE":
        if not auth.load_tokens():
            return json.dumps({"results": []})
        
        query = args.get("query")
        print(f"SEARCH_PEOPLE: query='{query}'", file=sys.stderr)
        client = TeamsClient(auth)
        results = client.search_people(query)
        print(f"Search returned {len(results)} results", file=sys.stderr)
        for r in results[:3]:
            print(f"  - {r.get('displayName', 'N/A')}", file=sys.stderr)
        return json.dumps({"results": results})
    
    elif cmd == "CREATE_CHAT":
        if not auth.load_tokens():
            return json.dumps({"error": "Not authenticated"})
        
        user_mri = args.get("user_mri")
        client = TeamsClient(auth)
        conv_id = client.create_chat(user_mri)
        return json.dumps({"conversation_id": conv_id or ""})
    
    elif cmd == "DOWNLOAD_FILE":
        if not auth.load_tokens():
            return json.dumps({"error": "Not authenticated"})
        
        url = args.get("url", "")
        filename = args.get("filename", "download")
        
        # Download directory
        download_dir = Path.home() / "MyDocs" / "Downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # Clean filename
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
        if not safe_name:
            safe_name = "download"
        
        output_path = download_dir / safe_name
        
        # If file exists, add number
        counter = 1
        base_path = output_path
        while output_path.exists():
            stem = base_path.stem
            suffix = base_path.suffix
            output_path = download_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        
        try:
            # Download with auth headers
            headers = {
                "Authorization": f"Bearer {auth.access_token}",
                "User-Agent": "Mozilla/5.0"
            }
            
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(output_path, 'wb') as f:
                    f.write(resp.read())
            
            print(f"Downloaded to {output_path}", file=sys.stderr)
            return json.dumps({"success": True, "path": str(output_path)})
        except Exception as e:
            print(f"Download error: {e}", file=sys.stderr)
            return json.dumps({"error": str(e)})
    
    elif cmd == "LIST_DIR":
        # List directory contents - for image picker
        dir_path = args.get("path", str(Path.home() / "MyDocs"))
        images_only = args.get("images_only", True)
        
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}
        
        try:
            p = Path(dir_path)
            if not p.exists():
                return json.dumps({"error": "Directory not found", "path": dir_path})
            
            if not p.is_dir():
                return json.dumps({"error": "Not a directory", "path": dir_path})
            
            items = []
            
            # Add parent directory if not at root
            if str(p) != "/" and p.parent != p:
                items.append({
                    "name": "..",
                    "path": str(p.parent),
                    "isDir": True,
                    "isImage": False
                })
            
            # List contents
            for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if item.name.startswith('.'):
                    continue  # Skip hidden files
                
                is_dir = item.is_dir()
                is_image = item.suffix.lower() in image_extensions if not is_dir else False
                
                # If images_only, skip non-image files (but keep directories)
                if images_only and not is_dir and not is_image:
                    continue
                
                items.append({
                    "name": item.name,
                    "path": str(item),
                    "isDir": is_dir,
                    "isImage": is_image
                })
            
            return json.dumps({
                "path": str(p),
                "items": items
            })
        except Exception as e:
            print(f"LIST_DIR error: {e}", file=sys.stderr)
            return json.dumps({"error": str(e)})
    
    elif cmd == "UPLOAD_IMAGE":
        if not auth.load_tokens():
            return json.dumps({"error": "Not authenticated"})
        
        conv_id = args.get("conversation_id", "")
        image_path = args.get("image_path", "")
        message_text = args.get("message", "")
        
        if not conv_id or not image_path:
            return json.dumps({"error": "Missing conversation_id or image_path"})
        
        image_file = Path(image_path)
        if not image_file.exists():
            return json.dumps({"error": "Image file not found"})
        
        import uuid
        import mimetypes
        
        filename = image_file.name
        file_size = image_file.stat().st_size
        
        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(str(image_file))
        if not mime_type:
            mime_type = "image/jpeg"
        
        # Teams uses pish/image for images
        teams_type = "pish/image" if mime_type.startswith("image/") else "pish/file"
        
        # AsyncGW base URL
        asyncgw_base = "https://eu-prod.asyncgw.teams.microsoft.com"
        
        # Generate session and request IDs
        session_id = str(uuid.uuid4())
        request_id = session_id.replace("-", "") + "_1"
        
        base_headers = {
            "Authorization": f"skype_token {auth.skype_token}",
            "x-ms-client-type": "desktop",
            "x-ms-client-version": "41/1.0.0.2025070703",
            "x-ms-session-id": session_id,
            "x-ms-scenario-id": "1520",
            "x-ms-user-type": "null",
            "x-ms-client-env": "pds-prod-cosmic-linux-euwe",
            "x-ms-request-id": request_id,
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Teams/1.5.00",
            "Origin": "https://teams.microsoft.com",
            "Referer": "https://teams.microsoft.com/_",
        }
        
        try:
            # Step 1: Create object
            create_payload = json.dumps({
                "type": teams_type,
                "permissions": {conv_id: ["read"]},
                "filename": filename
            }).encode('utf-8')
            
            create_headers = dict(base_headers)
            create_headers["Content-Type"] = "application/json"
            create_headers["Accept"] = "application/json"
            
            print(f"Creating object for {filename}", file=sys.stderr)
            req = urllib.request.Request(
                f"{asyncgw_base}/v1/objects/",
                data=create_payload,
                headers=create_headers,
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.getcode()
                print(f"Create response: {status}", file=sys.stderr)
                
                if status != 201:
                    return json.dumps({"error": f"Create failed: {status}"})
                
                # Get object ID
                object_id = None
                try:
                    data = json.loads(resp.read().decode('utf-8'))
                    object_id = data.get("id")
                except:
                    pass
                
                if not object_id:
                    location = resp.getheader("location", "")
                    if "/objects/" in location:
                        object_id = location.split("/objects/")[-1].rstrip("/")
                
                if not object_id:
                    return json.dumps({"error": "Could not get object ID"})
            
            print(f"Object ID: {object_id}", file=sys.stderr)
            
            # Step 2: Upload content
            with open(image_file, 'rb') as f:
                file_data = f.read()
            
            upload_headers = dict(base_headers)
            upload_headers["Content-Type"] = "application/octet-stream"
            upload_headers["Accept"] = "*/*"
            upload_headers["x-ms-request-id"] = request_id + "2"
            
            content_path = "imgpsh" if teams_type == "pish/image" else "original"
            
            print(f"Uploading {len(file_data)} bytes", file=sys.stderr)
            req = urllib.request.Request(
                f"{asyncgw_base}/v1/objects/{object_id}/content/{content_path}",
                data=file_data,
                headers=upload_headers,
                method="PUT"
            )
            
            with urllib.request.urlopen(req, timeout=60) as resp:
                status = resp.getcode()
                print(f"Upload response: {status}", file=sys.stderr)
                
                if status not in [200, 201]:
                    return json.dumps({"error": f"Upload failed: {status}"})
            
            # Step 3: Set permissions
            perm_headers = dict(base_headers)
            perm_headers["Content-Type"] = "application/json"
            perm_headers["Accept"] = "application/json"
            perm_headers["x-ms-request-id"] = request_id + "3"
            
            perm_payload = json.dumps({conv_id: ["read"]}).encode('utf-8')
            
            print("Setting permissions", file=sys.stderr)
            req = urllib.request.Request(
                f"{asyncgw_base}/v1/objects/{object_id}/permissions",
                data=perm_payload,
                headers=perm_headers,
                method="PUT"
            )
            
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    print(f"Permissions response: {resp.getcode()}", file=sys.stderr)
            except:
                pass  # Continue even if permissions fail
            
            # Step 4: Send message with attachment
            if teams_type == "pish/image":
                preview_url = f"https://eu-api.asm.skype.com/v1/objects/{object_id}/views/imgo"
                img_tag = f'<img alt="{filename}" src="{preview_url}" itemscope="http://schema.skype.com/AMSImage" style="vertical-align:bottom;width:250px;height:auto"></img>'
                if message_text:
                    message_content = f"{message_text}<p>{img_tag}</p>"
                else:
                    message_content = img_tag
            else:
                preview_url = f"https://eu-api.asm.skype.com/v1/objects/{object_id}/views/original"
                file_tag = f'<a href="{preview_url}">{filename}</a>'
                if message_text:
                    message_content = f"{message_text}<p>{file_tag}</p>"
                else:
                    message_content = file_tag
            
            file_ext = image_file.suffix.lstrip('.').lower() or "file"
            file_ref = {
                "@type": "http://schema.skype.com/File",
                "version": 2,
                "id": object_id,
                "type": file_ext,
                "title": filename,
                "state": "active",
                "objectUrl": preview_url,
                "filePreview": {"previewUrl": preview_url}
            }
            
            client = TeamsClient(auth)
            encoded_id = urllib.parse.quote(conv_id, safe='')
            client_msg_id = str(int(time.time() * 1000))
            
            msg_payload = json.dumps({
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
            }).encode('utf-8')
            
            msg_url = f"https://teams.microsoft.com/api/chatsvc/{auth.region}/v1/users/ME/conversations/{encoded_id}/messages"
            
            result = http_request(
                msg_url,
                method="POST",
                headers=client._headers(),
                data=msg_payload
            )
            
            success = not result.get("error")
            print(f"Message with image sent: {success}", file=sys.stderr)
            
            return json.dumps({
                "success": success,
                "object_id": object_id,
                "preview_url": preview_url
            })
            
        except Exception as e:
            print(f"Upload error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return json.dumps({"error": str(e)})
    
    elif cmd == "DEBUG":
        # Show token info for debugging
        if auth.load_tokens():
            return json.dumps({
                "authenticated": True,
                "region": auth.region,
                "my_mri": auth.my_mri,
                "display_name": auth.display_name,
                "chat_service": auth.chat_service,
                "middle_tier": auth.middle_tier,
                "has_skype_token": auth.skype_token is not None,
                "skype_token_preview": auth.skype_token[:50] if auth.skype_token else None,
                "has_access_token": auth.access_token is not None,
            })
        return json.dumps({"authenticated": False})
    
    return json.dumps({"error": "Unknown command"})


if __name__ == "__main__":
    # Read command from stdin
    try:
        input_data = sys.stdin.read()
        request = json.loads(input_data)
        cmd = request.get("command", "")
        args = request.get("args", {})
        
        result = handle_command(cmd, args)
        print(result)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
