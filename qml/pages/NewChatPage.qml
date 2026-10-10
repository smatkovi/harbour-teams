import QtQuick 2.6
import Sailfish.Silica 1.0

Page {
    id: newChatPage
    
    property bool searching: false
    
    ListModel {
        id: searchResultsModel
    }
    
    Connections {
        target: app
        
        onSearchResults: {
            console.log("Search results received:", results.length)
            searchResultsModel.clear()
            searching = false
            
            for (var i = 0; i < results.length; i++) {
                searchResultsModel.append(results[i])
            }
        }
        
        onChatCreated: {
            console.log("Chat created:", success, conversationId, displayName)
            if (success) {
                pageStack.replace(Qt.resolvedUrl("ConversationPage.qml"), {
                    conversationId: conversationId,
                    conversationName: displayName
                })
            }
        }
    }
    
    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height + Theme.paddingLarge
        
        Column {
            id: column
            width: parent.width
            
            PageHeader {
                title: "New Chat"
            }
            
            SearchField {
                id: searchField
                width: parent.width
                placeholderText: "Search people..."
                
                EnterKey.enabled: text.length > 0
                EnterKey.iconSource: "image://theme/icon-m-search"
                EnterKey.onClicked: {
                    if (text.length > 0) {
                        searching = true
                        searchResultsModel.clear()
                        app.searchPeople(text)
                    }
                }
                
                onTextChanged: {
                    if (text.length >= 2) {
                        searchTimer.restart()
                    } else {
                        searchResultsModel.clear()
                    }
                }
            }
            
            Timer {
                id: searchTimer
                interval: 300
                onTriggered: {
                    if (searchField.text.length >= 2) {
                        searching = true
                        app.searchPeople(searchField.text)
                    }
                }
            }
            
            Item {
                width: parent.width
                height: Theme.paddingLarge
            }
            
            BusyIndicator {
                anchors.horizontalCenter: parent.horizontalCenter
                running: searching
                visible: searching
                size: BusyIndicatorSize.Medium
            }
            
            Label {
                width: parent.width - 2 * Theme.horizontalPageMargin
                x: Theme.horizontalPageMargin
                visible: !searching && searchField.text.length >= 2 && searchResultsModel.count === 0
                text: "No people found"
                color: Theme.secondaryHighlightColor
                horizontalAlignment: Text.AlignHCenter
            }
            
            Repeater {
                model: searchResultsModel
                
                delegate: BackgroundItem {
                    width: parent.width
                    height: Theme.itemSizeMedium
                    
                    onClicked: {
                        console.log("Creating chat with:", model.mri, model.displayName)
                        app.createChat(model.mri, model.displayName)
                    }
                    
                    Row {
                        anchors {
                            left: parent.left
                            leftMargin: Theme.horizontalPageMargin
                            right: parent.right
                            rightMargin: Theme.horizontalPageMargin
                            verticalCenter: parent.verticalCenter
                        }
                        spacing: Theme.paddingMedium
                        
                        Rectangle {
                            width: Theme.itemSizeSmall
                            height: Theme.itemSizeSmall
                            radius: width / 2
                            color: Theme.rgba(Theme.highlightColor, 0.3)
                            
                            Label {
                                anchors.centerIn: parent
                                text: model.displayName ? model.displayName.charAt(0).toUpperCase() : "?"
                                font.pixelSize: Theme.fontSizeLarge
                                color: Theme.highlightColor
                            }
                        }
                        
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - Theme.itemSizeSmall - Theme.paddingMedium
                            
                            Label {
                                width: parent.width
                                text: model.displayName || "Unknown"
                                truncationMode: TruncationMode.Fade
                                color: highlighted ? Theme.highlightColor : Theme.primaryColor
                            }
                            
                            Label {
                                width: parent.width
                                text: model.email || ""
                                font.pixelSize: Theme.fontSizeSmall
                                truncationMode: TruncationMode.Fade
                                color: Theme.secondaryColor
                                visible: text.length > 0
                            }
                        }
                    }
                }
            }
        }
        
        VerticalScrollDecorator {}
    }
}
