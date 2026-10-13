import QtQuick 2.6
import Sailfish.Silica 1.0
import Nemo.DBus 2.0
import io.thp.pyotherside 1.5
import "pages"
import "cover"

ApplicationWindow {
    id: app
    
    // Antippen der Meldung: lipstick ruft diese Methode. Der Name ist der
    // einzige, den die App unter Sailjail besitzen darf --
    // <OrganizationName>.<ApplicationName> aus der .desktop-Datei.
    DBusAdaptor {
        id: oberflaeche
        service: "harbour-teams.harbour-teams"
        path: "/"
        iface: "harbour.teams.Gui"
        
        function openChat(faden) {
            app.activate()
            app.gespraechOeffnen(faden)
        }
    }
    
    // Zum Dienst hin: beim Oeffnen eines Gespraechs die Meldung wegnehmen.
    DBusInterface {
        id: dienst
        service: "harbour.teams.dienst"
        path: "/"
        iface: "harbour.teams.Dienst"
    }
    
    function gelesen(faden) {
        if (faden) {
            dienst.call("Gelesen", [faden])
        }
    }
    
    function gespraechOeffnen(faden) {
        if (!faden) {
            return
        }
        // Erst wenn die App ueberhaupt angemeldet ist, hat eine
        // Gespraechsseite einen Sinn.
        if (!authenticated) {
            return
        }
        pageStack.pop(pageStack.find(function(seite) {
            return seite.objectName === "MainPage"
        }), PageStackAction.Immediate)
        pageStack.push(Qt.resolvedUrl("pages/ConversationPage.qml"),
                       { conversationId: faden })
        gelesen(faden)
    }
    
    property bool authenticated: false
    property bool initializing: true
    
    initialPage: Component { LoginPage {} }
    cover: Component { CoverPage {} }
    
    // Switch pages based on auth state
    onAuthenticatedChanged: {
        if (authenticated && !initializing) {
            pageStack.replace(Qt.resolvedUrl("pages/MainPage.qml"))
        } else if (!authenticated && !initializing) {
            pageStack.replace(Qt.resolvedUrl("pages/LoginPage.qml"))
        }
    }
    
    onInitializingChanged: {
        if (!initializing && authenticated) {
            pageStack.replace(Qt.resolvedUrl("pages/MainPage.qml"))
        }
    }
    
    // Python backend
    Python {
        id: python
        
        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('..'))
            
            // Set up signal handlers
            setHandler('authStateChanged', function(authenticated) {
                app.authenticated = authenticated
                app.initializing = false
            })
            
            setHandler('loginComplete', function(success, error) {
                if (success) {
                    app.authenticated = true
                } else {
                    loginError(error)
                }
            })
            
            setHandler('chatsLoaded', function(chats) {
                chatsModel.clear()
                for (var i = 0; i < chats.length; i++) {
                    chatsModel.append(chats[i])
                }
                chatsLoading = false
            })
            
            setHandler('chatsError', function(error) {
                chatsLoading = false
            })
            
            setHandler('teamsLoaded', function(teams) {
                teamsModel.clear()
                for (var i = 0; i < teams.length; i++) {
                    teamsModel.append(teams[i])
                }
                teamsLoading = false
            })
            
            setHandler('teamsError', function(error) {
                teamsLoading = false
            })
            
            setHandler('messagesLoaded', function(convId, messages) {
                messagesReceived(convId, messages)
            })
            
            setHandler('messageSent', function(convId, success, error) {
                messageSentResult(convId, success, error || '')
            })
            
            setHandler('avatarPathLoaded', function(userMri, avatarPath) {
                if (avatarPath) {
                    avatarLoaded(userMri, avatarPath)
                }
            })
            
            setHandler('conversationAvatarLoaded', function(convId, avatarPath) {
                if (avatarPath) {
                    conversationAvatarLoaded(convId, avatarPath)
                }
            })
            
            setHandler('fileDownloadComplete', function(fileName, success, result) {
                fileDownloadComplete(fileName, success, result)
            })
            
            setHandler('imageUploadComplete', function(convId, success, error, imageInfo) {
                imageUploadComplete(convId, success, error, imageInfo || {})
            })
            
            setHandler('searchResults', function(results) {
                searchResults(results)
            })
            
            setHandler('chatCreated', function(success, convId, displayName, error) {
                chatCreated(success, convId, displayName, error || '')
            })
            
            setHandler('messageDeleted', function(convId, success, error) {
                messageDeleted(convId, success, error || '')
            })
            
            // Import and initialize
            importModule('teams_bridge', function() {
                call('teams_bridge.init', [], function(result) {
                    // Initialization complete
                })
            })
        }
        
        onError: {
            console.log("Python error:", traceback)
        }
    }
    
    // Signals for message passing
    signal loginError(string error)
    signal messagesReceived(string convId, var messages)
    signal messageSentResult(string convId, bool success, string error)
    signal avatarLoaded(string userMri, string avatarPath)
    signal conversationAvatarLoaded(string convId, string avatarPath)
    signal fileDownloadComplete(string fileName, bool success, string result)
    signal imageUploadComplete(string convId, bool success, string error, var imageInfo)
    signal searchResults(var results)
    signal chatCreated(bool success, string conversationId, string displayName, string error)
    signal messageDeleted(string convId, bool success, string error)
    
    // Global data models
    property bool chatsLoading: false
    property bool teamsLoading: false
    
    ListModel {
        id: chatsModel
    }
    
    ListModel {
        id: teamsModel
    }
    
    // Helper functions
    function startLogin(modus) {
        python.call('teams_bridge.start_login', [modus || 'arbeit'], function(result) {
            if (result.success) {
                pageStack.push(Qt.resolvedUrl("pages/DeviceCodePage.qml"), {
                    userCode: result.user_code,
                    verificationUrl: result.verification_url,
                    deviceCode: result.device_code,
                    message: result.message
                })
            } else {
                loginError(result.error)
            }
        })
    }
    
    function pollLogin(deviceCode) {
        python.call('teams_bridge.poll_login', [deviceCode])
    }
    
    function loadChats() {
        chatsLoading = true
        python.call('teams_bridge.get_chats', [])
    }
    
    function loadTeams() {
        teamsLoading = true
        python.call('teams_bridge.get_teams', [])
    }
    
    function loadMessages(conversationId) {
        python.call('teams_bridge.get_messages', [conversationId])
    }
    
    function sendMessage(conversationId, content) {
        python.call('teams_bridge.send_message', [conversationId, content])
    }
    
    function loadAvatar(userMri) {
        python.call('teams_bridge.get_avatar_path', [userMri])
    }
    
    function loadConversationAvatar(conversationId, groupId) {
        python.call('teams_bridge.get_conversation_avatar_path', [conversationId, groupId || ""])
    }
    
    function downloadFile(shareUrl, fileName, fileUrl) {
        python.call('teams_bridge.download_file', [shareUrl, fileName, fileUrl || ""])
    }
    
    function uploadFile(conversationId, filePath) {
        python.call('teams_bridge.upload_file', [conversationId, filePath])
    }
    
    function sendMessageWithFile(conversationId, content, fileInfo) {
        python.call('teams_bridge.send_message_with_file', [conversationId, content, fileInfo])
    }
    
    function logout() {
        python.call('teams_bridge.logout', [])
    }
    
    function searchPeople(query) {
        python.call('teams_bridge.search_people', [query])
    }
    
    function createChat(userMri, displayName) {
        python.call('teams_bridge.create_chat', [userMri, displayName])
    }
    
    function deleteMessage(conversationId, messageId) {
        python.call('teams_bridge.delete_message', [conversationId, messageId])
    }
}
