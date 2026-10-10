import QtQuick 2.6
import Sailfish.Silica 1.0

Page {
    id: deviceCodePage
    
    property string userCode: ""
    property string verificationUrl: ""
    property string deviceCode: ""
    property string message: ""
    property bool waiting: false
    
    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height + Theme.paddingLarge * 2
        
        Column {
            id: column
            width: parent.width
            spacing: Theme.paddingLarge
            
            PageHeader {
                title: qsTr("Sign In")
            }
            
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                width: parent.width - Theme.paddingLarge * 2
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                color: Theme.highlightColor
                text: qsTr("To sign in, open a web browser and go to:")
            }
            
            // URL display - clickable
            BackgroundItem {
                anchors.horizontalCenter: parent.horizontalCenter
                width: urlLabel.width + Theme.paddingLarge * 2
                height: urlLabel.height + Theme.paddingMedium * 2
                
                Rectangle {
                    anchors.fill: parent
                    color: Theme.rgba(Theme.highlightBackgroundColor, 0.2)
                    radius: Theme.paddingSmall
                }
                
                Label {
                    id: urlLabel
                    anchors.centerIn: parent
                    text: verificationUrl
                    font.pixelSize: Theme.fontSizeMedium
                    color: highlighted ? Theme.highlightColor : Theme.primaryColor
                    font.underline: true
                }
                
                onClicked: {
                    Qt.openUrlExternally(verificationUrl)
                }
            }
            
            Item {
                width: parent.width
                height: Theme.paddingMedium
            }
            
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                width: parent.width - Theme.paddingLarge * 2
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                color: Theme.highlightColor
                text: qsTr("Then enter this code:")
            }
            
            // Code display - tap to copy
            BackgroundItem {
                anchors.horizontalCenter: parent.horizontalCenter
                width: codeColumn.width + Theme.paddingLarge * 2
                height: codeColumn.height + Theme.paddingMedium * 2
                
                Rectangle {
                    anchors.fill: parent
                    color: Theme.rgba(Theme.highlightBackgroundColor, 0.3)
                    radius: Theme.paddingSmall
                }
                
                Column {
                    id: codeColumn
                    anchors.centerIn: parent
                    spacing: Theme.paddingSmall
                    
                    Label {
                        id: codeLabel
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: userCode
                        font.pixelSize: Theme.fontSizeExtraLarge
                        font.bold: true
                        color: parent.parent.highlighted ? Theme.highlightColor : Theme.primaryColor
                        font.family: "monospace"
                    }
                    
                    Label {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: qsTr("Tap to copy")
                        font.pixelSize: Theme.fontSizeExtraSmall
                        color: Theme.secondaryColor
                    }
                }
                
                onClicked: {
                    Clipboard.text = userCode
                    clipboardNotice.show()
                }
            }
            
            // Clipboard notification
            Label {
                id: clipboardNotice
                anchors.horizontalCenter: parent.horizontalCenter
                text: qsTr("Code copied to clipboard")
                color: Theme.highlightColor
                font.pixelSize: Theme.fontSizeSmall
                opacity: 0
                
                function show() {
                    opacity = 1
                    hideTimer.restart()
                }
                
                Timer {
                    id: hideTimer
                    interval: 2000
                    onTriggered: clipboardNotice.opacity = 0
                }
                
                Behavior on opacity {
                    FadeAnimator { duration: 200 }
                }
            }
            
            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                text: waiting ? qsTr("Waiting...") : qsTr("I've entered the code")
                enabled: !waiting
                onClicked: {
                    waiting = true
                    app.pollLogin(deviceCode)
                }
            }
            
            BusyIndicator {
                anchors.horizontalCenter: parent.horizontalCenter
                size: BusyIndicatorSize.Medium
                running: waiting
                visible: waiting
            }
            
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                width: parent.width - Theme.paddingLarge * 2
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeSmall
                visible: waiting
                text: qsTr("Waiting for you to sign in with your browser. This may take a moment...")
            }
        }
    }
    
    Connections {
        target: app
        onLoginError: {
            waiting = false
            // Show error
            pageStack.push(Qt.resolvedUrl("ErrorPage.qml"), {errorText: error})
        }
    }
    
    // When login is complete, the app will automatically switch to MainPage
}
