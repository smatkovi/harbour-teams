"""
Sailfish Secrets integration for secure credential storage.
Uses D-Bus to communicate with the Sailfish Secrets daemon via P2P socket.

Architecture:
1. Discovery Service on Session Bus gives us the P2P socket address
2. We connect directly to the P2P socket to talk to the real daemon
3. We use call_blocking for P2P D-Bus (no bus name needed)
"""

import json

try:
    import dbus
    import dbus.connection
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False

# Collection and secret names
# v6: New collection name
COLLECTION_NAME = "TeamsWallet7"
SECRET_TOKENS = "teams-tokens"

# Default encrypted storage plugin (full name required!)
DEFAULT_PLUGIN = "org.sailfishos.secrets.plugin.encryptedstorage.sqlcipher"

# UserInteractionMode enum values
USER_INTERACTION_PREVENT = 0  # No UI - use if device is unlocked
USER_INTERACTION_SYSTEM = 2   # System UI for authentication

# Use SystemInteraction to allow system UI for authentication
USER_INTERACTION_MODE = USER_INTERACTION_SYSTEM

# DeviceLockUnlockSemantic enum
DEVICE_LOCK_KEEP_UNLOCKED = 0  # Stay unlocked after device unlock

# AccessControlMode enum  
ACCESS_CONTROL_OWNER_ONLY = 0

# Error codes from Sailfish Secrets
ERROR_COLLECTION_ALREADY_EXISTS = 3
ERROR_COLLECTION_ALREADY_EXISTS_2 = 46  # Alternative error code
ERROR_COLLECTION_OWNED_BY_OTHER = 10


def log(msg):
    """Log helper"""
    print(f"[Secrets] {msg}")
    try:
        import pyotherside
        pyotherside.send('log', f'[Secrets] {msg}')
    except:
        pass


class SailfishSecrets:
    """Interface to Sailfish Secrets via P2P D-Bus socket"""
    
    def __init__(self):
        self.available = False
        self.p2p_connection = None
        self.plugin_name = DEFAULT_PLUGIN
        self._collection_verified = False
        self._init_connection()
    
    def _init_connection(self):
        """Initialize connection to Sailfish Secrets daemon"""
        if not HAS_DBUS:
            log("D-Bus module not available")
            return
        
        try:
            # Step 1: Get P2P socket address from Discovery Service
            session_bus = dbus.SessionBus()
            
            discovery_obj = session_bus.get_object(
                'org.sailfishos.secrets.daemon.discovery',
                '/Sailfish/Secrets/Discovery'
            )
            discovery_iface = dbus.Interface(
                discovery_obj,
                'org.sailfishos.secrets.daemon.discovery'
            )
            
            # Get the P2P socket address
            p2p_address = str(discovery_iface.peerToPeerAddress())
            log(f"P2P socket: {p2p_address}")
            
            # Step 2: Connect to P2P socket using low-level connection
            self.p2p_connection = dbus.connection.Connection(p2p_address)
            log("Connected to P2P socket")
            
            # Test connection and get plugins
            self._get_plugins()
            
            self.available = True
            log("Sailfish Secrets ready!")
            
        except dbus.exceptions.DBusException as e:
            log(f"D-Bus error: {e}")
            self.available = False
        except Exception as e:
            log(f"Error: {e}")
            import traceback
            log(traceback.format_exc())
            self.available = False
    
    def _call(self, method, signature, *args):
        """Make a D-Bus call on the P2P connection"""
        return self.p2p_connection.call_blocking(
            None,  # bus_name - None for P2P
            '/Sailfish/Secrets',  # object_path
            'org.sailfishos.secrets',  # interface
            method,  # method name
            signature,  # signature
            args  # arguments as tuple
        )
    
    def _get_plugins(self):
        """Get available plugins and select best one"""
        try:
            result = self._call('getPluginInfo', '')
            result_tuple = result[0]
            encrypted_storage_plugins = result[3]
            
            log(f"getPluginInfo result: code={result_tuple[0]}")
            
            if encrypted_storage_plugins:
                for plugin in encrypted_storage_plugins:
                    plugin_name = str(plugin[0])
                    log(f"Available plugin: {plugin_name}")
                    if 'sqlcipher' in plugin_name.lower() and '.' in plugin_name:
                        self.plugin_name = plugin_name
                        log(f"Selected plugin: {plugin_name}")
                        break
            
            if '.' not in self.plugin_name:
                log(f"Plugin name '{self.plugin_name}' is not fully qualified, using default")
                self.plugin_name = DEFAULT_PLUGIN
            
            log(f"Using plugin: {self.plugin_name}")
            
        except Exception as e:
            log(f"getPluginInfo error: {e}")
    
    def _ensure_collection(self):
        """Ensure our collection exists and we own it"""
        if not self.available:
            return False
        
        if self._collection_verified:
            return True
        
        try:
            log(f"Creating collection '{COLLECTION_NAME}'...")
            result = self._call(
                'createCollection',
                'sss(i)(i)',
                COLLECTION_NAME,
                self.plugin_name,
                self.plugin_name,
                (DEVICE_LOCK_KEEP_UNLOCKED,),
                (ACCESS_CONTROL_OWNER_ONLY,)
            )
            
            code = int(result[0])
            error_code = int(result[1])
            message = str(result[2])
            
            log(f"createCollection result: code={code}, error={error_code}, msg={message}")
            
            if code == 0:
                log(f"Collection '{COLLECTION_NAME}' created successfully")
                self._collection_verified = True
                return True
            elif error_code in (ERROR_COLLECTION_ALREADY_EXISTS, ERROR_COLLECTION_ALREADY_EXISTS_2):
                # Collection exists - but do we own it?
                # Try a dummy operation to verify ownership
                log("Collection exists, verifying ownership...")
                if self._verify_ownership():
                    self._collection_verified = True
                    return True
                else:
                    log("We don't own this collection!")
                    return False
            elif error_code == ERROR_COLLECTION_OWNED_BY_OTHER:
                log("Collection owned by different application")
                return False
            else:
                log(f"createCollection failed: code={code}, error={error_code}, msg={message}")
                return False
                
        except dbus.exceptions.DBusException as e:
            log(f"createCollection error: {e}")
            return False
    
    def _verify_ownership(self):
        """Verify we can access the collection by trying to get collection info"""
        try:
            # Try to get a non-existent secret - if we get "secret not found" we own it
            # If we get "owned by different app" we don't
            result = self._call(
                'getSecret',
                '(sss)(i)s',
                ("__ownership_test__", COLLECTION_NAME, self.plugin_name),
                (USER_INTERACTION_MODE,),
                ""
            )
            
            result_tuple = result[0]
            code = int(result_tuple[0])
            error_code = int(result_tuple[1])
            message = str(result_tuple[2])
            
            log(f"Ownership test: code={code}, error={error_code}, msg={message}")
            
            if error_code == ERROR_COLLECTION_OWNED_BY_OTHER:
                return False
            # Any other error (including "secret not found") means we have access
            return True
            
        except Exception as e:
            log(f"Ownership verification error: {e}")
            return False
    
    def store_secret(self, name: str, data: dict) -> bool:
        """Store a secret securely. Deletes existing secret first if it exists."""
        if not self.available:
            log("Secrets not available")
            return False
        
        if not self._ensure_collection():
            log("Cannot ensure collection ownership")
            return False
        
        # Delete existing secret first (ignore errors if it doesn't exist)
        log(f"Deleting existing secret '{name}' if present...")
        self._delete_secret_silent(name)
        
        log("Encoding data...")
        json_data = json.dumps(data).encode('utf-8')
        log(f"Data encoded, {len(json_data)} bytes")
        
        try:
            log(f"Calling setSecret for '{name}'...")
            
            secret = (
                (name, COLLECTION_NAME, self.plugin_name),
                json_data,
                {}
            )
            
            ui_params = (
                "", "", "", "",
                (0,), "",
                {},
                (0,), (0,)
            )
            
            result = self._call(
                'setSecret',
                '((sss)aya{sv})(ssss(i)sa{is}(i)(i))(i)s',
                secret,
                ui_params,
                (USER_INTERACTION_MODE,),
                ""
            )
            
            code = int(result[0])
            error_code = int(result[1])
            message = str(result[2])
            
            log(f"setSecret result: code={code}, error={error_code}, msg={message}")
            
            if code == 0:
                log(f"Stored secret '{name}'")
                return True
            else:
                log(f"setSecret failed: code={code}, error={error_code}, msg={message}")
                self._collection_verified = False
                return False
                
        except dbus.exceptions.DBusException as e:
            log(f"Store error: {e}")
            self._collection_verified = False
            return False
    
    def _delete_secret_silent(self, name: str):
        """Delete a secret without logging errors (used before overwrite)"""
        try:
            self._call(
                'deleteSecret',
                '(sss)(i)s',
                (name, COLLECTION_NAME, self.plugin_name),
                (USER_INTERACTION_MODE,),
                ""
            )
            log(f"Deleted existing secret '{name}'")
        except:
            pass  # Ignore errors - secret might not exist
    
    def retrieve_secret(self, name: str) -> dict:
        """Retrieve a secret"""
        if not self.available:
            log("Secrets not available")
            return None
        
        try:
            log(f"Retrieving secret '{name}'...")
            
            result = self._call(
                'getSecret',
                '(sss)(i)s',
                (name, COLLECTION_NAME, self.plugin_name),
                (USER_INTERACTION_MODE,),
                ""
            )
            
            result_tuple = result[0]
            code = int(result_tuple[0])
            error_code = int(result_tuple[1])
            message = str(result_tuple[2])
            
            if code == 0:
                secret = result[1]
                data_bytes = bytes(secret[1])
                json_data = data_bytes.decode('utf-8')
                log(f"Retrieved secret '{name}'")
                return json.loads(json_data)
            else:
                log(f"getSecret failed: code={code}, error={error_code}, msg={message}")
                return None
                
        except dbus.exceptions.DBusException as e:
            log(f"Retrieve error: {e}")
            return None
    
    def delete_secret(self, name: str) -> bool:
        """Delete a secret"""
        if not self.available:
            log("Secrets not available")
            return False
        
        try:
            result = self._call(
                'deleteSecret',
                '(sss)(i)s',
                (name, COLLECTION_NAME, self.plugin_name),
                (USER_INTERACTION_MODE,),
                ""
            )
            
            code = int(result[0])
            if code == 0:
                log(f"Deleted secret '{name}'")
                return True
            else:
                log(f"deleteSecret failed: code={code}")
                return False
                
        except dbus.exceptions.DBusException as e:
            log(f"Delete error: {e}")
            return False


# Global instance
_secrets = None

def get_secrets() -> SailfishSecrets:
    """Get the global secrets instance"""
    global _secrets
    if _secrets is None:
        _secrets = SailfishSecrets()
    return _secrets


def is_secrets_available() -> bool:
    """Check if Sailfish Secrets is available"""
    return get_secrets().available


def save_tokens(tokens: dict) -> bool:
    """Save tokens securely"""
    return get_secrets().store_secret(SECRET_TOKENS, tokens)


def load_tokens() -> dict:
    """Load tokens"""
    return get_secrets().retrieve_secret(SECRET_TOKENS)


def delete_tokens() -> bool:
    """Delete tokens"""
    return get_secrets().delete_secret(SECRET_TOKENS)
