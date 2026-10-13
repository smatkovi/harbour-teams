import QtQuick 2.6
import Sailfish.Silica 1.0

Page {
    id: mainPage
    objectName: "MainPage"
    
    property var avatarCache: ({})  // Cache for user avatar paths (keyed by userMri)
    property var convAvatarCache: ({})  // Cache for conversation avatar paths (keyed by convId)
    
    Component.onCompleted: {
        app.loadChats()
    }
    
    // Handle avatar loaded signal
    Connections {
        target: app
        onAvatarLoaded: {
            avatarCache[userMri] = avatarPath
            avatarCacheVersion++
        }
        onConversationAvatarLoaded: {
            convAvatarCache[convId] = avatarPath
            avatarCacheVersion++
        }
    }
    
    property int avatarCacheVersion: 0
    
    SilicaFlickable {
        anchors.fill: parent
        
        PullDownMenu {
            MenuItem {
                text: qsTr("Sign Out")
                onClicked: {
                    app.logout()
                }
            }
            MenuItem {
                text: qsTr("New Chat")
                onClicked: {
                    pageStack.push(Qt.resolvedUrl("NewChatPage.qml"))
                }
            }
            MenuItem {
                text: qsTr("Refresh")
                onClicked: {
                    app.loadChats()
                }
            }
        }
        
        contentHeight: parent.height
        
        Column {
            id: column
            width: parent.width
            height: parent.height
            
            PageHeader {
                title: qsTr("Teams")
            }
            
            // Content area
            Item {
                width: parent.width
                height: parent.height - Theme.itemSizeLarge
                
                // Chats list
                SilicaListView {
                    id: chatsList
                    anchors.fill: parent
                    model: chatsModel
                    
                    delegate: ListItem {
                        id: chatItem
                        contentHeight: Theme.itemSizeMedium
                        
                        property string convId: model.id || ""
                        property string userMri: model.userMri || ""
                        property string groupId: model.groupId || ""
                        property string chatType: model.chatType || "chat"
                        
                        // Get cached avatar based on chat type
                        property string cachedAvatar: {
                            var v = avatarCacheVersion
                            if (chatType === "chat" && userMri) {
                                return avatarCache[userMri] || ""
                            } else if (convId) {
                                return convAvatarCache[convId] || ""
                            }
                            return ""
                        }
                        
                        // Request avatar if not cached
                        Component.onCompleted: {
                            if (chatType === "chat") {
                                if (userMri && !avatarCache[userMri]) {
                                    app.loadAvatar(userMri)
                                }
                            } else {
                                // Group or channel - load conversation avatar using groupId
                                if (convId && !convAvatarCache[convId]) {
                                    app.loadConversationAvatar(convId, groupId)
                                }
                            }
                        }
                        
                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: Theme.horizontalPageMargin
                            anchors.rightMargin: Theme.horizontalPageMargin
                            spacing: Theme.paddingMedium
                            
                            // Avatar
                            Item {
                                anchors.verticalCenter: parent.verticalCenter
                                width: Theme.itemSizeSmall
                                height: width
                                
                                // Background/Fallback circle with initial or icon
                                Rectangle {
                                    id: avatarFallback
                                    anchors.fill: parent
                                    radius: chatItem.chatType === "chat" ? width / 2 : Theme.paddingSmall
                                    color: chatItem.chatType === "channel" ? "#464EB8" : Theme.rgba(Theme.highlightColor, 0.3)
                                    visible: avatarImage.status !== Image.Ready
                                    
                                    Label {
                                        anchors.centerIn: parent
                                        text: chatItem.chatType === "channel" ? "#" : (model.name ? model.name.charAt(0).toUpperCase() : "?")
                                        font.pixelSize: Theme.fontSizeLarge
                                        color: chatItem.chatType === "channel" ? "white" : Theme.highlightColor
                                    }
                                }
                                
                                // Circular/rounded clipping container
                                Rectangle {
                                    id: avatarClip
                                    anchors.fill: parent
                                    radius: chatItem.chatType === "chat" ? width / 2 : Theme.paddingSmall
                                    clip: true
                                    color: "transparent"
                                    visible: avatarImage.status === Image.Ready
                                    
                                    Image {
                                        id: avatarImage
                                        anchors.fill: parent
                                        source: chatItem.cachedAvatar ? "file://" + chatItem.cachedAvatar : ""
                                        fillMode: Image.PreserveAspectCrop
                                        asynchronous: true
                                    }
                                }
                            }
                            
                            Column {
                                id: textColumn
                                anchors.verticalCenter: parent.verticalCenter
                                width: chatItem.width - Theme.horizontalPageMargin * 2 - Theme.itemSizeSmall - Theme.paddingMedium
                                
                                Label {
                                    width: textColumn.width
                                    text: model.name || qsTr("Unknown")
                                    color: chatItem.highlighted ? Theme.highlightColor : Theme.primaryColor
                                    truncationMode: TruncationMode.Fade
                                }
                                
                                Label {
                                    width: textColumn.width
                                    text: model.lastMessage || ""
                                    color: Theme.secondaryColor
                                    font.pixelSize: Theme.fontSizeSmall
                                    truncationMode: TruncationMode.Fade
                                }
                            }
                        }
                        
                        onClicked: {
                            pageStack.push(Qt.resolvedUrl("ConversationPage.qml"), {
                                conversationId: model.id,
                                conversationName: model.name
                            })
                        }
                    }
                    
                    ViewPlaceholder {
                        enabled: chatsList.count === 0 && !app.chatsLoading
                        text: qsTr("No chats")
                        hintText: qsTr("Pull down to refresh")
                    }
                    
                    BusyIndicator {
                        anchors.centerIn: parent
                        size: BusyIndicatorSize.Large
                        running: app.chatsLoading
                        visible: app.chatsLoading
                    }
                    
                    VerticalScrollDecorator {}
                }
            }
        }
    }
}
