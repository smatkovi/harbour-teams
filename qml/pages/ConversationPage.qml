import QtQuick 2.6
import Sailfish.Silica 1.0
import Sailfish.Pickers 1.0
import Nemo.Notifications 1.0

Page {
    id: conversationPage
    
    property string conversationId: ""
    property string conversationName: ""
    property bool isChannel: false
    property bool loading: true
    property bool uploading: false
    property var pendingImageInfo: null
    
    ListModel {
        id: messagesModel
    }
    
    Component.onCompleted: {
        console.log("ConversationPage opened, conversationId:", conversationId)
        app.loadMessages(conversationId)
    }
    
    Connections {
        target: app
        
        onMessagesReceived: {
            console.log("Messages received for:", convId, "count:", messages.length)
            console.log("Our conversationId:", conversationPage.conversationId)
            if (convId === conversationPage.conversationId) {
                console.log("IDs match, loading messages")
                messagesModel.clear()
                for (var i = messages.length - 1; i >= 0; i--) {
                    messagesModel.append(messages[i])
                }
                console.log("Model now has", messagesModel.count, "messages")
                loading = false
                messagesList.positionViewAtEnd()
            }
        }
        
        onMessageSentResult: {
            if (convId === conversationPage.conversationId) {
                if (success) {
                    app.loadMessages(conversationPage.conversationId)
                    messageInput.text = ""
                    pendingImageInfo = null
                } else {
                    console.log("Send failed:", error)
                }
                sendButton.enabled = true
                uploading = false
            }
        }
        
        onImageUploadComplete: {
            console.log("File upload complete:", convId, success, error)
            if (convId === conversationPage.conversationId) {
                uploading = false
                if (success) {
                    // Store file info and send message with it
                    pendingImageInfo = imageInfo
                    console.log("File uploaded, sending message with attachment")
                    app.sendMessageWithFile(conversationId, messageInput.text.trim() || "", imageInfo)
                } else {
                    console.log("Upload failed:", error)
                    notification.previewBody = qsTr("Upload failed: ") + error
                    notification.publish()
                }
            }
        }
    }
    
    Notification {
        id: notification
        appName: "Teams"
        previewSummary: qsTr("Teams")
    }
    
    SilicaFlickable {
        anchors.fill: parent
        
        PullDownMenu {
            MenuItem {
                text: qsTr("Refresh")
                onClicked: {
                    loading = true
                    app.loadMessages(conversationId)
                }
            }
        }
        
        contentHeight: parent.height
        
        Column {
            anchors.fill: parent
            
            PageHeader {
                id: header
                title: conversationName || qsTr("Conversation")
                description: isChannel ? qsTr("Channel") : qsTr("Chat")
            }
            
            // Messages list
            SilicaListView {
                id: messagesList
                width: parent.width
                height: parent.height - header.height - inputRow.height
                model: messagesModel
                clip: true
                verticalLayoutDirection: ListView.TopToBottom
                
                delegate: ListItem {
                    id: messageItem
                    width: parent.width
                    contentHeight: messageColumn.height + Theme.paddingMedium
                    
                    property var filesList: parseFiles(model.files)
                    property string messageId: model.id || ""
                    
                    menu: ContextMenu {
                        MenuItem {
                            text: qsTr("Delete")
                            onClicked: {
                                messageItem.remorseAction(qsTr("Deleting"), function() {
                                    app.deleteMessage(conversationId, messageId)
                                })
                            }
                        }
                    }
                    
                    Column {
                        id: messageColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: Theme.horizontalPageMargin
                        anchors.rightMargin: Theme.horizontalPageMargin
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.paddingSmall / 2
                        
                        // Sender name
                        Label {
                            text: model.from || qsTr("Unknown")
                            color: Theme.highlightColor
                            font.pixelSize: Theme.fontSizeSmall
                            font.bold: true
                        }
                        
                        // Message content
                        Label {
                            width: parent.width
                            text: model.content || ""
                            color: Theme.primaryColor
                            wrapMode: Text.Wrap
                            visible: (model.content || "").length > 0
                        }
                        
                        // File attachments
                        Repeater {
                            model: filesList
                            
                            BackgroundItem {
                                width: messageColumn.width
                                height: fileRow.height + Theme.paddingSmall * 2
                                
                                Row {
                                    id: fileRow
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: Theme.paddingMedium
                                    
                                    Image {
                                        anchors.verticalCenter: parent.verticalCenter
                                        source: "image://theme/icon-m-file-document"
                                        width: Theme.iconSizeMedium
                                        height: width
                                    }
                                    
                                    Column {
                                        anchors.verticalCenter: parent.verticalCenter
                                        
                                        Label {
                                            text: modelData.fileName || qsTr("File")
                                            color: Theme.primaryColor
                                            font.pixelSize: Theme.fontSizeSmall
                                        }
                                        
                                        Label {
                                            text: qsTr("Tap to open in browser")
                                            color: Theme.secondaryColor
                                            font.pixelSize: Theme.fontSizeExtraSmall
                                        }
                                    }
                                }
                                
                                onClicked: {
                                    // Open share URL in browser for download
                                    var url = modelData.shareUrl || modelData.fileUrl
                                    if (url) {
                                        Qt.openUrlExternally(url)
                                    }
                                }
                            }
                        }
                        
                        // Time
                        Label {
                            text: formatTime(model.time)
                            color: Theme.secondaryColor
                            font.pixelSize: Theme.fontSizeExtraSmall
                        }
                    }
                }
                
                ViewPlaceholder {
                    enabled: messagesModel.count === 0 && !loading
                    text: qsTr("No messages")
                }
                
                BusyIndicator {
                    anchors.centerIn: parent
                    size: BusyIndicatorSize.Large
                    running: loading
                    visible: loading
                }
                
                VerticalScrollDecorator {}
            }
            
            // Input row
            Row {
                id: inputRow
                width: parent.width
                height: Theme.itemSizeMedium
                spacing: Theme.paddingSmall
                
                IconButton {
                    id: attachButton
                    width: Theme.itemSizeMedium
                    height: Theme.itemSizeMedium
                    icon.source: "image://theme/icon-m-attach"
                    enabled: !uploading
                    
                    onClicked: {
                        pageStack.push(filePickerPage)
                    }
                }
                
                Rectangle {
                    width: parent.width - attachButton.width - sendButton.width - Theme.paddingSmall * 2
                    height: parent.height
                    color: Theme.rgba(Theme.highlightBackgroundColor, 0.1)
                    
                    TextField {
                        id: messageInput
                        anchors.fill: parent
                        anchors.margins: Theme.paddingSmall
                        placeholderText: uploading ? qsTr("Uploading...") : qsTr("Type a message...")
                        labelVisible: false
                        backgroundStyle: TextEditor.NoBackground
                        enabled: !uploading
                        
                        EnterKey.enabled: text.trim().length > 0 && !uploading
                        EnterKey.iconSource: "image://theme/icon-m-enter-accept"
                        EnterKey.onClicked: sendMessage()
                    }
                }
                
                IconButton {
                    id: sendButton
                    width: Theme.itemSizeMedium
                    height: Theme.itemSizeMedium
                    icon.source: uploading ? "" : "image://theme/icon-m-send"
                    enabled: messageInput.text.trim().length > 0 && !uploading
                    
                    BusyIndicator {
                        anchors.centerIn: parent
                        size: BusyIndicatorSize.Small
                        running: uploading
                        visible: uploading
                    }
                    
                    onClicked: sendMessage()
                }
            }
        }
    }
    
    Component {
        id: filePickerPage
        
        ImagePickerPage {
            onSelectedContentPropertiesChanged: {
                console.log("Selected image:", selectedContentProperties.filePath)
                var filePath = selectedContentProperties.filePath
                if (filePath) {
                    uploading = true
                    app.uploadFile(conversationId, filePath)
                }
            }
        }
    }
    
    function sendMessage() {
        var content = messageInput.text.trim()
        if (content.length > 0) {
            sendButton.enabled = false
            app.sendMessage(conversationId, content)
        }
    }
    
    function formatTime(timeStr) {
        if (!timeStr) return ""
        try {
            var date = new Date(timeStr)
            return Qt.formatDateTime(date, "hh:mm")
        } catch (e) {
            return timeStr
        }
    }
    
    function parseFiles(filesJson) {
        if (!filesJson) return []
        try {
            var files = JSON.parse(filesJson)
            var result = []
            for (var i = 0; i < files.length; i++) {
                var f = files[i]
                result.push({
                    fileName: f.fileName || f.title || "File",
                    fileType: f.fileType || f.type || "",
                    fileUrl: (f.fileInfo && f.fileInfo.fileUrl) || f.objectUrl || "",
                    shareUrl: (f.fileInfo && f.fileInfo.shareUrl) || ""
                })
            }
            return result
        } catch (e) {
            return []
        }
    }
}
