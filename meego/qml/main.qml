/**
 * Microsoft Teams Client for MeeGo Harmattan
 * Version 0.9.22 - Larger headers with back buttons
 */

import QtQuick 1.1
import com.nokia.meego 1.0

PageStackWindow {
    id: app
    
    showStatusBar: true
    showToolBar: true
    initialPage: loginPage
    
    // === MeeGo Harmattan UI Constants (from messaging-ui) ===
    property int headerHeight: inPortrait ? 84 : 72
    property int headerTopPadding: 12  // Extra padding for status bar area
    property int listItemHeight: 80
    property int avatarSize: 56
    property int indentDefault: 16
    property int marginSmall: 4
    property int marginDouble: 8
    property int marginLarge: 12
    property int paddingXLarge: 16
    property int inputAreaHeight: 52
    property int bubbleRadius: 10
    property int fontSizeTitle: 26
    property int fontSizeSubtitle: 22
    property int fontSizeBody: 18
    property int fontSizeSmall: 16
    property int fontSizeXSmall: 14
    
    // Use system properties for bottom margin
    property bool inPortrait: screen.currentOrientation === Screen.Portrait || screen.currentOrientation === Screen.PortraitInverted
    
    // Colors
    property color colorAccent: "#4FC3F7"
    property color colorHeader: "#1a1a1a"
    property color colorSeparator: "#333333"
    property color colorSecondary: "#888888"
    property color colorBubbleMine: "#306080"
    property color colorBubbleOther: "#2a2a2a"
    
    
    Rectangle {
        anchors.fill: parent
        color: "#000000"
        z: -1
    }
    
    // ==================== State ====================
    
    property variant conversationsList: []
    property variant messagesList: []
    property int messagesVersion: 0
    property variant searchResultsList: []
    property int searchResultsVersion: 0
    property variant currentConv: null
    property variant avatarCache: ({})
    property int conversationsVersion: 0  // Change counter to force rebind
    
    // Message cache: { convId: { messages: [...], lastMessageId: "..." } }
    property variant messagesCache: ({})
    
    // ==================== Startup ====================
    
    Component.onCompleted: {
        console.log("=== Teams 0.9.6 QML Starting ===")
        TeamsAPI.checkAuth()
    }
    
    // ==================== API Connections ====================
    
    Connections {
        target: TeamsAPI
        
        onAuthReady: {
            console.log("Auth ready: " + TeamsAPI.authenticated)
            if (TeamsAPI.authenticated) {
                pageStack.replace(chatsPage)
                // 1. Load cached conversations instantly (no network wait)
                TeamsAPI.loadCachedConversations()
                // 2. Then refresh from network for new chats (background)
                TeamsAPI.loadConversations()
            }
        }
        
        onDeviceCodeReady: {
            console.log("Device code: " + TeamsAPI.userCode)
        }
        
        onLoginReady: {
            console.log("Login complete")
            if (TeamsAPI.authenticated) {
                pageStack.replace(chatsPage)
                // First login - no cache yet, must load from network
                TeamsAPI.loadConversations()
            }
        }
        
        onConversationsReady: {
            try {
                var parsed = JSON.parse(TeamsAPI.conversations)
                console.log("Parsed " + parsed.length + " conversations")
                
                // Force rebind: first clear, then set
                conversationsList = []
                conversationsList = parsed
                conversationsVersion++  // Increment to force ListView update
                
                console.log("conversationsList now has " + conversationsList.length + " items, version=" + conversationsVersion)
                
                // Stop loading indicator
                if (chatsPage.isLoading) chatsPage.isLoading = false
                
                // Pre-populate avatar cache from API response and only fetch missing ones
                var newCache = avatarCache
                var needsLoading = []
                for (var i = 0; i < conversationsList.length && i < 20; i++) {
                    var conv = conversationsList[i]
                    if (conv.chatType === "chat" && conv.userMri) {
                        // If avatarPath is provided in response, use it directly
                        if (conv.avatarPath && conv.avatarPath.length > 0) {
                            newCache[conv.userMri] = conv.avatarPath
                        } else if (!newCache[conv.userMri]) {
                            // Need to fetch this one
                            needsLoading.push(conv.userMri)
                        }
                    }
                }
                avatarCache = newCache
                
                // Only fetch avatars that are not in disk cache
                for (var j = 0; j < needsLoading.length; j++) {
                    TeamsAPI.loadAvatar(needsLoading[j])
                }
                
                if (needsLoading.length > 0) {
                    console.log("Loading " + needsLoading.length + " avatars from API")
                } else {
                    console.log("All avatars loaded from disk cache")
                }
            } catch (e) {
                console.log("Parse error: " + e)
                conversationsList = []
                if (chatsPage.isLoading) chatsPage.isLoading = false
            }
        }
        
        onMessagesReady: {
            try {
                var newMessages = JSON.parse(TeamsAPI.messages)
                console.log("Loaded " + newMessages.length + " messages")
                
                // Cache messages for current conversation
                if (currentConv && currentConv.id) {
                    var cache = messagesCache
                    cache[currentConv.id] = {
                        messages: newMessages,
                        timestamp: Date.now()
                    }
                    messagesCache = cache
                }
                
                messagesList = newMessages
                messagesVersion = messagesVersion + 1
                // Force ListView to update
                msgList.model = newMessages
                
                // Stop loading indicator
                if (messagesPage.isLoading) messagesPage.isLoading = false
            } catch (e) {
                console.log("Messages parse error: " + e)
                messagesList = []
                msgList.model = []
                if (messagesPage.isLoading) messagesPage.isLoading = false
            }
        }
        
        onMessageSentReady: {
            if (TeamsAPI.sendSuccess && currentConv) {
                TeamsAPI.refreshMessages(currentConv.id)
            }
        }
        
        onAvatarReady: {
            var mri = TeamsAPI.avatarMri
            var path = TeamsAPI.avatarPath
            if (mri && path) {
                var cache = avatarCache
                cache[mri] = path
                avatarCache = cache
                console.log("Avatar cached: " + mri + " -> " + path)
            }
        }
        
        onSearchReady: {
            try {
                var data = JSON.parse(TeamsAPI.searchResults)
                console.log("Search results raw: " + TeamsAPI.searchResults)
                // API returns array directly
                var results = data.results || data || []
                searchResultsList = results
                searchResultsVersion = searchResultsVersion + 1
                // Force ListView to update by setting model explicitly
                searchList.model = results
                console.log("Parsed " + results.length + " search results, version=" + searchResultsVersion)
            } catch (e) {
                console.log("Search parse error: " + e)
                searchResultsList = []
                searchList.model = []
                searchResultsVersion = searchResultsVersion + 1
            }
        }
        
        onChatCreated: {
            var chatId = TeamsAPI.createdChatId
            console.log("Chat created: " + chatId)
            if (chatId) {
                currentConv = {"id": chatId, "name": "New Chat", "chatType": "chat"}
                messagesList = []
                msgList.model = []
                // Pop search page first, then push messages page
                pageStack.pop()  // Remove search page
                pageStack.push(messagesPage)
                TeamsAPI.loadMessages(chatId)
                TeamsAPI.loadConversations()
            }
        }
        
        onDownloadReady: {
            if (TeamsAPI.downloadSuccess) {
                var path = TeamsAPI.downloadPath
                if (path.indexOf("asm.skype.com") >= 0) {
                    // This was an upload
                    console.log("Upload complete: " + path)
                    downloadNotification.text = "Image uploaded!"
                    // Refresh messages to show the uploaded image
                    if (currentConv) {
                        TeamsAPI.refreshMessages(currentConv.id)
                    }
                } else {
                    // This was a download
                    console.log("Download complete: " + path)
                    downloadNotification.text = "Downloaded to ~/MyDocs/Downloads"
                }
                downloadNotification.visible = true
                downloadTimer.restart()
            } else {
                console.log("Operation failed")
                downloadNotification.text = "Operation failed"
                downloadNotification.visible = true
                downloadTimer.restart()
            }
        }
        
        onErrorOccurred: {
            console.log("Error: " + TeamsAPI.errorMessage)
        }
    }
    
    // ==================== Helper Functions ====================
    
    function avatarColor(name, isChannel) {
        if (isChannel) return "#464EB8"
        var colors = ["#E91E63", "#9C27B0", "#673AB7", "#3F51B5", "#2196F3",
                      "#009688", "#4CAF50", "#FF9800", "#FF5722", "#795548"]
        var hash = 0
        for (var i = 0; i < name.length; i++) {
            hash = name.charCodeAt(i) + ((hash << 5) - hash)
        }
        return colors[Math.abs(hash) % colors.length]
    }
    
    function getInitials(name) {
        if (!name) return "?"
        var parts = name.split(" ")
        if (parts.length >= 2) {
            return (parts[0][0] + parts[1][0]).toUpperCase()
        }
        return name.substring(0, 2).toUpperCase()
    }
    
    function formatTime(timeStr) {
        if (!timeStr || timeStr === "") return ""
        try {
            var date = new Date(timeStr)
            // Check if date is valid
            if (isNaN(date.getTime())) return ""
            var hours = date.getHours()
            var mins = date.getMinutes()
            return (hours < 10 ? "0" : "") + hours + ":" + (mins < 10 ? "0" : "") + mins
        } catch (e) {
            return ""
        }
    }
    
    // ==================== Login Page ====================
    
    Page {
        id: loginPage
        orientationLock: PageOrientation.Automatic
        tools: null

        
        property bool showCode: false
        
        Rectangle {
            anchors.fill: parent
            color: "#000000"
        }
        
        Column {
            anchors.centerIn: parent
            spacing: 24
            width: parent.width - 48
            
            // Logo
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 80; height: 80; radius: 16
                color: "#464EB8"
                
                Text {
                    anchors.centerIn: parent
                    text: "T"
                    font.pixelSize: 48
                    font.bold: true
                    color: "white"
                }
            }
            
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Microsoft Teams"
                font.pixelSize: 28
                font.bold: true
                color: "white"
            }
            
            // Zwei Tore, keine gemeinsame Station: ein Arbeits- oder
            // Schulkonto meldet sich unter /common an und holt den
            // Skypetoken von teams.microsoft.com, ein privates Konto (also
            // auch ein Skype-Konto) unter /consumers und von teams.live.com.
            // Rateversuche kosten nur Zeit, deshalb fragen.
            Rectangle {
                id: arbeitKnopf
                visible: !loginPage.showCode
                anchors.horizontalCenter: parent.horizontalCenter
                width: 300; height: 50; radius: 25
                color: "#464EB8"

                Text {
                    anchors.centerIn: parent
                    text: "Work or school account"
                    font.pixelSize: 17
                    color: "white"
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        loginPage.showCode = true
                        TeamsAPI.startDeviceFlow("arbeit")
                    }
                }
            }

            Rectangle {
                visible: !loginPage.showCode
                anchors.horizontalCenter: parent.horizontalCenter
                width: 300; height: 50; radius: 25
                color: "#464EB8"

                Text {
                    anchors.centerIn: parent
                    text: "Personal or Skype account"
                    font.pixelSize: 17
                    color: "white"
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        loginPage.showCode = true
                        TeamsAPI.startDeviceFlow("privat")
                    }
                }
            }

            Text {
                visible: !loginPage.showCode
                anchors.horizontalCenter: parent.horizontalCenter
                width: parent.width - 48
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                font.pixelSize: 14
                color: "#b0b0b0"
                text: "A personal account has chats, but no teams, channels or profile pictures."
            }
            
            // Device code display
            Column {
                visible: loginPage.showCode
                width: parent.width
                spacing: 16
                
                Text {
                    width: parent.width
                    text: "Go to:"
                    font.pixelSize: 16
                    color: "#aaa"
                    horizontalAlignment: Text.AlignHCenter
                }
                
                Text {
                    width: parent.width
                    text: TeamsAPI.verificationUrl || "microsoft.com/devicelogin"
                    font.pixelSize: 16
                    font.bold: true
                    color: "#4FC3F7"
                    horizontalAlignment: Text.AlignHCenter
                }
                
                Text {
                    width: parent.width
                    text: "Enter code:"
                    font.pixelSize: 16
                    color: "#aaa"
                    horizontalAlignment: Text.AlignHCenter
                }
                
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 200; height: 60; radius: 8
                    color: "#333"
                    
                    Text {
                        anchors.centerIn: parent
                        text: TeamsAPI.userCode || "..."
                        font.pixelSize: 28
                        font.bold: true
                        color: "white"
                    }
                }
                
                // Poll button
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 200; height: 44; radius: 22
                    color: "#464EB8"
                    
                    Text {
                        anchors.centerIn: parent
                        text: "I've entered the code"
                        font.pixelSize: 14
                        color: "white"
                    }
                    
                    MouseArea {
                        anchors.fill: parent
                        onClicked: TeamsAPI.pollToken()
                    }
                }
                
                // Cancel
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Cancel"
                    font.pixelSize: 14
                    color: "#888"
                    
                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -10
                        onClicked: loginPage.showCode = false
                    }
                }
            }
        }
    }
    
    // ==================== Chats Page ====================
    
    Page {
        id: chatsPage
        orientationLock: PageOrientation.Automatic
        tools: ToolBarLayout {
            ToolIcon {
                iconId: "toolbar-refresh"
                onClicked: TeamsAPI.loadConversations()
            }
            ToolIcon {
                iconId: "toolbar-add"
                onClicked: {
                    searchResultsList = []
                    searchResultsVersion++
                    pageStack.push(searchPage)
                }
            }
            ToolIcon {
                iconId: "toolbar-view-menu"
                onClicked: logoutDialog.open()
            }
        }

        
        property bool isLoading: false
        
        Rectangle {
            anchors.fill: parent
            color: "#000000"
        }
        
        // Loading indicator
        Rectangle {
            anchors.centerIn: parent
            width: 200
            height: 60
            radius: 10
            color: "#222"
            visible: chatsPage.isLoading && conversationsList.length === 0
            z: 50
            
            Text {
                anchors.centerIn: parent
                text: "Loading..."
                color: "white"
                font.pixelSize: 18
            }
        }
        
        // Header
        Rectangle {
            id: chatsHeader
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: headerHeight
            color: colorHeader
            
            Text {
                anchors.left: parent.left
                anchors.leftMargin: indentDefault
                anchors.top: parent.top
                anchors.topMargin: headerTopPadding + (headerHeight - headerTopPadding - height) / 2
                text: "Teams"
                font.pixelSize: fontSizeTitle
                font.weight: Font.Light
                color: "white"
            }
            
            Row {
                anchors.right: parent.right
                anchors.rightMargin: marginDouble
                anchors.top: parent.top
                anchors.topMargin: headerTopPadding + (headerHeight - headerTopPadding - height) / 2
                spacing: marginSmall
                
                // Refresh button
                Rectangle {
                    width: 48; height: 48; radius: marginDouble
                    color: refreshMouse.pressed ? "#333" : "transparent"
                    
                    Text {
                        anchors.centerIn: parent
                        text: "↻"
                        font.pixelSize: 24
                        color: chatsPage.isLoading ? colorAccent : "white"
                        rotation: chatsPage.isLoading ? refreshAnim.angle : 0
                    }
                    
                    NumberAnimation {
                        id: refreshAnim
                        property real angle: 0
                        target: refreshAnim
                        property: "angle"
                        from: 0
                        to: 360
                        duration: 1000
                        loops: Animation.Infinite
                        running: chatsPage.isLoading
                    }
                    
                    MouseArea {
                        id: refreshMouse
                        anchors.fill: parent
                        onClicked: {
                            chatsPage.isLoading = true
                            TeamsAPI.loadConversations()
                        }
                    }
                }
                
                // New chat
                Rectangle {
                    width: 48; height: 48; radius: marginDouble
                    color: newChatMouse.pressed ? "#333" : "transparent"
                    
                    Text {
                        anchors.centerIn: parent
                        text: "+"
                        font.pixelSize: 28
                        color: colorAccent
                    }
                    
                    MouseArea {
                        id: newChatMouse
                        anchors.fill: parent
                        onClicked: pageStack.push(searchPage)
                    }
                }
                
                // Menu button
                Rectangle {
                    width: 48; height: 48; radius: marginDouble
                    color: logoutMouse.pressed ? "#333" : "transparent"
                    
                    Text {
                        anchors.centerIn: parent
                        text: "⋮"
                        font.pixelSize: 28
                        color: "white"
                    }
                    
                    MouseArea {
                        id: logoutMouse
                        anchors.fill: parent
                        onClicked: logoutDialog.visible = true
                    }
                }
            }
        }
        
        // Logout confirmation dialog
        Rectangle {
            id: logoutDialog
            visible: false
            anchors.fill: parent
            color: "#80000000"
            z: 100
            
            MouseArea {
                anchors.fill: parent
                onClicked: logoutDialog.visible = false
            }
            
            Rectangle {
                anchors.centerIn: parent
                width: 280
                height: 150
                radius: 12
                color: "#222"
                
                Column {
                    anchors.centerIn: parent
                    spacing: 20
                    
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Sign out?"
                        font.pixelSize: 20
                        font.bold: true
                        color: "white"
                    }
                    
                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 20
                        
                        Rectangle {
                            width: 100; height: 40; radius: 20
                            color: "#444"
                            Text { anchors.centerIn: parent; text: "Cancel"; color: "white"; font.pixelSize: 16 }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: logoutDialog.visible = false
                            }
                        }
                        
                        Rectangle {
                            width: 100; height: 40; radius: 20
                            color: "#ff4444"
                            Text { anchors.centerIn: parent; text: "Sign Out"; color: "white"; font.pixelSize: 16 }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    logoutDialog.visible = false
                                    TeamsAPI.logout()
                                    pageStack.replace(loginPage)
                                }
                            }
                        }
                    }
                }
            }
        }
        
        // Conversations list
        ListView {
            id: chatsList
            anchors.top: chatsHeader.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            clip: true
            
            // Model depends on version to force rebind
            model: conversationsVersion >= 0 ? conversationsList : []
            
            delegate: Rectangle {
                width: chatsList.width
                height: listItemHeight
                color: convMouse.pressed ? colorHeader : "#000000"
                
                // Defensive property extraction
                property string convId: modelData ? (modelData.id || "") : ""
                property string convName: modelData ? (modelData.name || "Chat") : "Chat"
                property string convType: modelData ? (modelData.chatType || "chat") : "chat"
                property string convLastMsg: modelData ? (modelData.lastMessage || "") : ""
                property string convLastTime: modelData ? (modelData.lastTime || "") : ""
                property string convUserMri: modelData ? (modelData.userMri || "") : ""
                property bool isChannel: convType === "channel"
                // Avatar - try modelData first (from API response), then cache
                property string avatarFromData: modelData ? (modelData.avatarPath || "") : ""
                property string avatarFromCache: (convUserMri && avatarCache && avatarCache[convUserMri]) ? avatarCache[convUserMri] : ""
                property string avatarPath: avatarFromData || avatarFromCache
                property bool hasAvatar: avatarPath.length > 0
                
                Component.onCompleted: {
                    if (index < 5) {
                        console.log("Conv " + index + ": name=" + convName + ", type=" + convType + ", userMri=" + convUserMri)
                    }
                }
                
                Row {
                    anchors.fill: parent
                    anchors.leftMargin: indentDefault
                    anchors.rightMargin: indentDefault
                    anchors.topMargin: marginLarge
                    anchors.bottomMargin: marginLarge
                    spacing: marginLarge
                    
                    // Avatar
                    Rectangle {
                        width: avatarSize; height: avatarSize
                        radius: isChannel ? marginDouble : avatarSize / 2
                        color: avatarColor(convName, isChannel)
                        
                        Image {
                            anchors.fill: parent
                            visible: hasAvatar
                            source: hasAvatar ? "file://" + avatarPath : ""
                            fillMode: Image.PreserveAspectCrop
                            smooth: true
                        }
                        
                        Text {
                            anchors.centerIn: parent
                            visible: !hasAvatar
                            text: isChannel ? "#" : getInitials(convName)
                            font.pixelSize: fontSizeSubtitle
                            font.weight: Font.Light
                            color: "white"
                        }
                    }
                    
                    // Text
                    Column {
                        width: parent.width - avatarSize - marginLarge - indentDefault * 2
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: marginSmall
                        
                        Row {
                            width: parent.width
                            
                            Text {
                                width: parent.width - timeText.width - marginDouble
                                text: convName
                                font.pixelSize: fontSizeSubtitle
                                font.weight: Font.Light
                                color: "white"
                                elide: Text.ElideRight
                            }
                            
                            Text {
                                id: timeText
                                text: formatTime(convLastTime)
                                font.pixelSize: fontSizeXSmall
                                color: colorSecondary
                            }
                        }
                        
                        Text {
                            width: parent.width
                            text: convLastMsg
                            font.pixelSize: fontSizeBody
                            font.weight: Font.Light
                            color: colorSecondary
                            elide: Text.ElideRight
                        }
                    }
                }
                
                // Separator line
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: indentDefault + avatarSize + marginLarge
                    height: 1
                    color: colorHeader
                }
                
                MouseArea {
                    id: convMouse
                    anchors.fill: parent
                    onClicked: {
                        currentConv = modelData
                        
                        // Check in-memory cache first
                        var cached = messagesCache[convId]
                        if (cached && cached.messages && cached.messages.length > 0) {
                            messagesList = cached.messages
                            msgList.model = cached.messages
                            console.log("Loaded " + messagesList.length + " messages from memory cache")
                        } else {
                            messagesList = []
                            msgList.model = []
                            // Try disk cache first (fast)
                            TeamsAPI.loadCachedMessages(convId)
                        }
                        
                        pageStack.push(messagesPage)
                        // Always load fresh/new messages in background (incremental)
                        TeamsAPI.loadMessages(convId)
                    }
                }
                
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: 72
                    height: 1
                    color: "#333"
                }
            }
        }
        
        // Empty state
        Column {
            anchors.centerIn: parent
            visible: conversationsList.length === 0
            spacing: 16
            
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "No conversations"
                font.pixelSize: 18
                color: "#666"
            }
            
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 120; height: 40; radius: 20
                color: "#464EB8"
                Text { anchors.centerIn: parent; text: "Refresh"; font.pixelSize: 16; color: "white" }
                MouseArea { anchors.fill: parent; onClicked: TeamsAPI.loadConversations() }
            }
        }
    }
    
    // ==================== Messages Page ====================
    
    Page {
        id: messagesPage
        objectName: "messagesPage"
        tools: ToolBarLayout {
            ToolIcon {
                iconId: "toolbar-back"
                onClicked: pageStack.pop()
            }
            ToolIcon {
                iconId: "toolbar-refresh"
                onClicked: {
                    if (currentConv) TeamsAPI.loadMessages(currentConv.id)
                }
            }
        }
        orientationLock: PageOrientation.Automatic

        
        property bool isLoading: false
        
        Rectangle {
            anchors.fill: parent
            color: "#000000"
        }
        
        // Header
        Rectangle {
            id: msgHeader
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: headerHeight
            color: colorHeader
            
            // Back button
            Rectangle {
                id: backButton
                anchors.left: parent.left
                anchors.leftMargin: marginDouble
                anchors.top: parent.top
                anchors.topMargin: headerTopPadding + (headerHeight - headerTopPadding - height) / 2
                width: 48
                height: 48
                radius: 8
                color: backMouse.pressed ? "#333" : "transparent"
                
                Text {
                    anchors.centerIn: parent
                    text: "◀"
                    font.pixelSize: 22
                    color: "white"
                }
                
                MouseArea {
                    id: backMouse
                    anchors.fill: parent
                    onClicked: pageStack.pop()
                }
            }
            
            // Title
            Text {
                anchors.left: backButton.right
                anchors.leftMargin: marginDouble
                anchors.right: parent.right
                anchors.rightMargin: indentDefault
                anchors.top: parent.top
                anchors.topMargin: headerTopPadding + (headerHeight - headerTopPadding - height) / 2
                text: currentConv ? (currentConv.name || "Chat") : "Chat"
                font.pixelSize: fontSizeSubtitle
                font.weight: Font.Light
                color: "white"
                elide: Text.ElideRight
            }
        }
        
        // Messages list
        ListView {
            id: msgList
            anchors.top: msgHeader.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: inputRow.top
            anchors.margins: 8
            clip: true
            model: []  // Set explicitly in handlers
            spacing: 4
            
            delegate: Item {
                width: msgList.width
                height: msgCol.height + 8
                
                // Defensive property extraction - check both true and "true"
                property bool isMe: modelData ? (modelData.isMe === true || modelData.isMe === "true") : false
                property string msgContent: modelData ? (modelData.content || "") : ""
                property string msgSender: modelData ? (modelData.sender || "Unknown") : "Unknown"
                property string msgTime: modelData ? (modelData.time || "") : ""
                property variant msgAttachments: modelData ? (modelData.attachments || []) : []
                // Show sender name for all messages that are not mine
                property bool showSender: !isMe
                
                Component.onCompleted: {
                    if (index < 3) {
                        console.log("Message " + index + ": isMe=" + isMe + ", sender=" + msgSender + ", raw isMe=" + (modelData ? modelData.isMe : "no data"))
                    }
                }
                
                Column {
                    id: msgCol
                    anchors.left: isMe ? undefined : parent.left
                    anchors.right: isMe ? parent.right : undefined
                    spacing: 2
                    
                    Text {
                        visible: showSender
                        text: msgSender
                        font.pixelSize: 12
                        font.bold: true
                        color: avatarColor(msgSender, false)
                    }
                    
                    Rectangle {
                        width: Math.min(Math.max(msgText.implicitWidth, attachCol.width) + 24, msgList.width * 0.8)
                        height: msgTextCol.height + 24
                        radius: 16
                        color: isMe ? "#464EB8" : "#333"
                        
                        Column {
                            id: msgTextCol
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 12
                            spacing: 8
                            
                            Text {
                                id: msgText
                                width: parent.width
                                text: msgContent
                                font.pixelSize: 15
                                color: "white"
                                wrapMode: Text.WordWrap
                                visible: msgContent.length > 0
                            }
                            
                            // Attachments column
                            Column {
                                id: attachCol
                                width: parent.width
                                spacing: 4
                                visible: msgAttachments.length > 0
                                
                                Repeater {
                                    model: msgAttachments
                                    
                                    Rectangle {
                                        width: attachCol.width
                                        height: 36
                                        radius: 8
                                        color: "#222"
                                        
                                        Row {
                                            anchors.fill: parent
                                            anchors.margins: 8
                                            spacing: 8
                                            
                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: "📎"
                                                font.pixelSize: 14
                                            }
                                            
                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: parent.width - 60
                                                text: modelData.name || "File"
                                                font.pixelSize: 13
                                                color: "#4FC3F7"
                                                elide: Text.ElideMiddle
                                            }
                                        }
                                        
                                        MouseArea {
                                            anchors.fill: parent
                                            onClicked: {
                                                // SharePoint download not possible on MeeGo (browser too old)
                                                downloadNotification.text = "Download not supported"
                                                downloadNotification.visible = true
                                                downloadTimer.restart()
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    
                    Text {
                        anchors.right: isMe ? parent.right : undefined
                        text: formatTime(msgTime)
                        font.pixelSize: 11
                        color: "#666"
                    }
                }
            }
            
            onCountChanged: positionViewAtEnd()
        }
        
        // Input - messaging-ui style
        Rectangle {
            id: inputRow
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 0
            height: inputAreaHeight + paddingXLarge * 2
            color: colorHeader
            
            // Top separator
            Rectangle {
                anchors.top: parent.top
                width: parent.width
                height: 1
                color: colorSeparator
            }
            
            Row {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.leftMargin: indentDefault
                anchors.rightMargin: indentDefault
                anchors.topMargin: paddingXLarge
                height: inputAreaHeight
                spacing: marginDouble
                
                // Attach button
                Rectangle {
                    id: attachBtn
                    width: inputAreaHeight; height: inputAreaHeight
                    radius: marginDouble
                    color: attachMouse.pressed ? "#333" : "transparent"
                    
                    Text {
                        anchors.centerIn: parent
                        text: "+"
                        font.pixelSize: 28
                        color: colorAccent
                    }
                    
                    MouseArea {
                        id: attachMouse
                        anchors.fill: parent
                        onClicked: imagePickerDialog.open()
                    }
                }
                
                // Text input field
                Rectangle {
                    width: parent.width - sendBtn.width - attachBtn.width - marginDouble * 2
                    height: inputAreaHeight
                    radius: bubbleRadius
                    color: colorBubbleOther
                    border.width: 1
                    border.color: msgInput.activeFocus ? colorAccent : colorSeparator
                    
                    TextInput {
                        id: msgInput
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: paddingXLarge
                        anchors.rightMargin: paddingXLarge
                        color: "white"
                        font.pixelSize: fontSizeBody
                        font.weight: Font.Light
                        clip: true
                        
                        Text {
                            anchors.fill: parent
                            visible: !msgInput.text && !msgInput.activeFocus
                            text: "Type a message..."
                            color: "#666"
                            font.pixelSize: fontSizeBody
                            font.weight: Font.Light
                        }
                    }
                }
                
                // Send button
                Rectangle {
                    id: sendBtn
                    width: inputAreaHeight; height: inputAreaHeight
                    radius: marginDouble
                    color: msgInput.text ? colorAccent : "transparent"
                    
                    Text {
                        anchors.centerIn: parent
                        text: "›"
                        font.pixelSize: 32
                        color: msgInput.text ? "white" : "#666"
                    }
                    
                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            if (msgInput.text && currentConv) {
                                TeamsAPI.sendMessage(currentConv.id, msgInput.text)
                                msgInput.text = ""
                            }
                        }
                    }
                }
            }
        }
        
        // Image picker dialog
        Rectangle {
            id: imagePickerDialog
            anchors.fill: parent
            color: "#000000"
            visible: false
            z: 100
            
            property string currentPath: "/home/user/MyDocs"
            
            function open() {
                imagePickerDialog.visible = true
                TeamsAPI.listDir(currentPath)
            }
            
            function close() {
                imagePickerDialog.visible = false
            }
            
            function navigateTo(path) {
                currentPath = path
                TeamsAPI.listDir(path)
            }
            
            Connections {
                target: TeamsAPI
                onDirListReady: {
                    try {
                        var items = JSON.parse(TeamsAPI.dirList)
                        fileModel.clear()
                        for (var i = 0; i < items.length; i++) {
                            fileModel.append(items[i])
                        }
                        imagePickerDialog.currentPath = TeamsAPI.dirPath
                    } catch (e) {
                        console.log("Dir list error: " + e)
                    }
                }
            }
            
            ListModel {
                id: fileModel
            }
            
            // Header
            Rectangle {
                id: pickerHeader
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                height: 72
                color: "#111111"
                z: 1
                
                Rectangle {
                    anchors.left: parent.left
                    anchors.leftMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    width: 44; height: 44; radius: 22
                    color: pickerBackMouse.pressed ? "#444" : "transparent"
                    Text { anchors.centerIn: parent; text: "X"; font.pixelSize: 20; color: "white" }
                    MouseArea {
                        id: pickerBackMouse
                        anchors.fill: parent
                        onClicked: imagePickerDialog.close()
                    }
                }
                
                Column {
                    anchors.centerIn: parent
                    spacing: 2
                    
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Select Image"
                        font.pixelSize: 18
                        font.bold: true
                        color: "white"
                    }
                    
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "(Only images can be uploaded)"
                        font.pixelSize: 11
                        color: "#888"
                    }
                }
            }
            
            // Current path display
            Rectangle {
                id: pathBar
                anchors.top: pickerHeader.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 36
                color: "#222"
                
                Text {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 12
                    text: imagePickerDialog.currentPath
                    font.pixelSize: 12
                    color: "#aaa"
                    elide: Text.ElideMiddle
                }
            }
            
            // Quick access buttons
            Row {
                id: quickAccess
                anchors.top: pathBar.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 44
                spacing: 0
                
                Repeater {
                    model: [
                        {"name": "DCIM", "path": "/home/user/MyDocs/DCIM"},
                        {"name": "Pictures", "path": "/home/user/MyDocs/Pictures"},
                        {"name": "MyDocs", "path": "/home/user/MyDocs"}
                    ]
                    
                    Rectangle {
                        width: quickAccess.width / 3
                        height: 44
                        color: quickMouse.pressed ? "#444" : "#333"
                        border.width: 1
                        border.color: "#222"
                        
                        Text {
                            anchors.centerIn: parent
                            text: modelData.name
                            font.pixelSize: 13
                            color: "#4FC3F7"
                        }
                        
                        MouseArea {
                            id: quickMouse
                            anchors.fill: parent
                            onClicked: imagePickerDialog.navigateTo(modelData.path)
                        }
                    }
                }
            }
            
            // File list
            ListView {
                id: fileList
                anchors.top: quickAccess.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 8
                clip: true
                model: fileModel
                spacing: 4
                
                delegate: Rectangle {
                    width: fileList.width
                    height: 56
                    radius: 8
                    color: fileMouse.pressed ? "#444" : "#222"
                    
                    Row {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 12
                        
                        // Icon
                        Rectangle {
                            width: 32; height: 32
                            radius: 4
                            anchors.verticalCenter: parent.verticalCenter
                            color: model.isDir ? "#4FC3F7" : (model.isImage ? "#8BC34A" : "#666")
                            
                            Text {
                                anchors.centerIn: parent
                                text: model.isDir ? "📁" : (model.isImage ? "🖼" : "📄")
                                font.pixelSize: 16
                            }
                        }
                        
                        // Name
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 60
                            text: model.name
                            font.pixelSize: 15
                            color: model.isDir ? "#4FC3F7" : "white"
                            elide: Text.ElideMiddle
                        }
                    }
                    
                    MouseArea {
                        id: fileMouse
                        anchors.fill: parent
                        onClicked: {
                            if (model.isDir) {
                                imagePickerDialog.navigateTo(model.path)
                            } else if (model.isImage) {
                                console.log("Uploading: " + model.path)
                                TeamsAPI.uploadImage(currentConv.id, model.path, "")
                                imagePickerDialog.close()
                            }
                        }
                    }
                }
            }
            
            // Empty state
            Text {
                anchors.centerIn: fileList
                visible: fileModel.count === 0
                text: "No images found\n\nTry DCIM or Pictures folder"
                color: "#666"
                font.pixelSize: 14
                horizontalAlignment: Text.AlignHCenter
            }
        }
        
        // Download notification
        Rectangle {
            id: downloadNotification
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: inputRow.top
            anchors.bottomMargin: 8
            width: downloadText.width + 32
            height: 40
            radius: 20
            color: "#333"
            visible: false
            
            property alias text: downloadText.text
            
            Text {
                id: downloadText
                anchors.centerIn: parent
                color: "#4FC3F7"
                font.pixelSize: 14
            }
            
            Timer {
                id: downloadTimer
                interval: 3000
                onTriggered: downloadNotification.visible = false
            }
        }
    }
    
    // ==================== Search Page ====================
    
    Page {
        id: searchPage
        orientationLock: PageOrientation.Automatic
        tools: ToolBarLayout {
            ToolIcon {
                iconId: "toolbar-back"
                onClicked: pageStack.pop()
            }
        }

        
        Rectangle {
            anchors.fill: parent
            color: "#000000"
        }
        
        // Header
        Rectangle {
            id: searchHeader
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: headerHeight
            color: "#111111"
            
            // Back button
            Rectangle {
                id: searchBackButton
                anchors.left: parent.left
                anchors.leftMargin: marginDouble
                anchors.top: parent.top
                anchors.topMargin: headerTopPadding + (headerHeight - headerTopPadding - height) / 2
                width: 48
                height: 48
                radius: 8
                color: searchBackMouse.pressed ? "#333" : "transparent"
                
                Text {
                    anchors.centerIn: parent
                    text: "◀"
                    font.pixelSize: 22
                    color: "white"
                }
                
                MouseArea {
                    id: searchBackMouse
                    anchors.fill: parent
                    onClicked: pageStack.pop()
                }
            }
            
            Text {
                anchors.left: searchBackButton.right
                anchors.leftMargin: marginDouble
                anchors.top: parent.top
                anchors.topMargin: headerTopPadding + (headerHeight - headerTopPadding - height) / 2
                text: "New Chat"
                font.pixelSize: fontSizeTitle
                color: "white"
            }
        }
        
        // Search input
        Rectangle {
            id: searchInputRow
            anchors.top: searchHeader.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            height: 60
            color: "#111111"
            
            Row {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 8
                
                Rectangle {
                    width: parent.width - searchGoBtn.width - 8
                    height: 44
                    radius: 22
                    color: "#333"
                    
                    TextInput {
                        id: searchInput
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 16
                        anchors.rightMargin: 16
                        color: "white"
                        font.pixelSize: 15
                        
                        Text {
                            anchors.fill: parent
                            visible: !searchInput.text
                            text: "Search people..."
                            color: "#666"
                            font.pixelSize: 15
                        }
                    }
                }
                
                Rectangle {
                    id: searchGoBtn
                    width: 44; height: 44; radius: 22
                    color: "#464EB8"
                    Text { anchors.centerIn: parent; text: "?"; font.pixelSize: 20; font.bold: true; color: "white" }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            if (searchInput.text.length >= 2) {
                                console.log("Searching for: " + searchInput.text)
                                TeamsAPI.searchPeople(searchInput.text)
                            }
                        }
                    }
                }
            }
        }
        
        // Results
        ListView {
            id: searchList
            anchors.top: searchInputRow.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            clip: true
            model: []  // Set explicitly in onSearchReady
            
            Component.onCompleted: {
                console.log("Search list initialized")
            }
            
            onCountChanged: {
                console.log("Search results count: " + count)
            }
            
            delegate: Rectangle {
                width: searchList.width
                height: 64
                color: searchItemMouse.pressed ? "#333" : "transparent"
                
                Row {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 12
                    
                    Rectangle {
                        width: 40; height: 40; radius: 20
                        color: avatarColor(modelData.displayName || "", false)
                        Text {
                            anchors.centerIn: parent
                            text: getInitials(modelData.displayName || "")
                            font.pixelSize: 14
                            font.bold: true
                            color: "white"
                        }
                    }
                    
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        
                        Text {
                            text: modelData.displayName || ""
                            font.pixelSize: 16
                            font.bold: true
                            color: "white"
                        }
                        
                        Text {
                            text: modelData.email || ""
                            font.pixelSize: 13
                            color: "#888"
                        }
                    }
                }
                
                MouseArea {
                    id: searchItemMouse
                    anchors.fill: parent
                    onClicked: TeamsAPI.createChat(modelData.mri)
                }
                
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: 64
                    height: 1
                    color: "#333"
                }
            }
        }
    }
    
}
