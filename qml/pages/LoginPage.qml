import QtQuick 2.6
import Sailfish.Silica 1.0

Page {
    id: loginPage
    
    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height + Theme.paddingLarge * 2
        
        Column {
            id: column
            width: parent.width
            spacing: Theme.paddingLarge
            
            PageHeader {
                title: qsTr("Microsoft Teams")
            }
            
            Item {
                width: parent.width
                height: Theme.paddingLarge * 2
            }
            
            // Teams logo placeholder
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: Theme.itemSizeExtraLarge * 2
                height: width
                radius: Theme.paddingMedium
                color: "#464EB8"  // Teams purple
                
                Label {
                    anchors.centerIn: parent
                    text: "T"
                    font.pixelSize: Theme.fontSizeHuge * 2
                    font.bold: true
                    color: "white"
                }
            }
            
            Item {
                width: parent.width
                height: Theme.paddingLarge
            }
            
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                width: parent.width - Theme.paddingLarge * 2
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                color: Theme.highlightColor
                text: qsTr("Sign in with your Microsoft account to access Teams chats and channels.")
            }
            
            Item {
                width: parent.width
                height: Theme.paddingLarge * 2
            }
            
            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                text: qsTr("Sign In")
                onClicked: {
                    app.startLogin()
                }
            }
        }
    }
    
    Connections {
        target: app
        onLoginError: {
            errorLabel.text = error
            errorLabel.visible = true
        }
    }
    
    Label {
        id: errorLabel
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.paddingLarge
        anchors.horizontalCenter: parent.horizontalCenter
        width: parent.width - Theme.paddingLarge * 2
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        color: Theme.errorColor
        visible: false
    }
}
