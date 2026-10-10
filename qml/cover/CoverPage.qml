import QtQuick 2.6
import Sailfish.Silica 1.0

CoverBackground {
    
    Column {
        anchors.centerIn: parent
        spacing: Theme.paddingMedium
        
        // Teams logo
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: Theme.iconSizeLarge
            height: width
            radius: Theme.paddingSmall
            color: "#464EB8"
            
            Label {
                anchors.centerIn: parent
                text: "T"
                font.pixelSize: Theme.fontSizeHuge
                font.bold: true
                color: "white"
            }
        }
        
        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Teams"
            color: Theme.primaryColor
        }
    }
    
    CoverActionList {
        id: coverAction
        
        CoverAction {
            iconSource: "image://theme/icon-cover-refresh"
            onTriggered: {
                app.loadChats()
            }
        }
    }
}
