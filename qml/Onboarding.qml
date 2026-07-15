// Assistant de premier lancement en QML — carrousel de 6 étapes qui glissent,
// piloté par le pont `onb`. Racine = Item (fenêtre frameless translucide côté
// Python). Style macOS, mêmes polices/teintes que le reste.
import QtQuick

Item {
    id: root
    width: 700; height: 560
    readonly property string font1: "SF Pro Text, Segoe UI, sans-serif"
    readonly property string fontD: "SF Pro Display, SF Pro Text, Segoe UI, sans-serif"

    Rectangle { anchors.fill: parent; radius: 16; color: "#1F1F22" }

    // en-tête = poignée de déplacement
    MouseArea { anchors { left: parent.left; right: parent.right; top: parent.top }
        height: 54; onPressed: onb.startDrag() }

    // fonction d'aide : carte de choix arrondie
    component Choice : Rectangle {
        property bool sel: false
        property string title: ""
        property string sub: ""
        property bool locked: false
        radius: 12
        color: sel ? "#1E3556" : "#2C2C30"
        border.width: sel ? 1 : 0; border.color: "#0A84FF"
        Behavior on color { ColorAnimation { duration: 130 } }
        Column {
            anchors.centerIn: parent; spacing: 4; width: parent.width - 24
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: title
                color: locked ? "#7C8398" : "#F2F2F4"; font.family: root.font1; font.pixelSize: 14; font.weight: Font.DemiBold }
            Text { visible: sub.length > 0; anchors.horizontalCenter: parent.horizontalCenter; text: sub
                color: "#98989F"; font.family: root.font1; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; width: parent.width; wrapMode: Text.WordWrap }
            Text { visible: locked; anchors.horizontalCenter: parent.horizontalCenter; text: "NÉCESSITE NOVA ULTRA"
                color: "#C9B6F0"; font.family: root.font1; font.pixelSize: 8; font.weight: Font.DemiBold }
        }
    }

    // ---- carrousel ----
    Item {
        id: view
        anchors { left: parent.left; right: parent.right; top: parent.top; topMargin: 20 }
        height: root.height - 130
        clip: true
        Row {
            id: strip
            height: parent.height
            x: -onb.step * root.width
            Behavior on x { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }

            // 0 — Bienvenue
            Item { width: root.width; height: view.height
                Column { anchors.centerIn: parent; spacing: 16; width: parent.width - 120
                    Orb { anchors.horizontalCenter: parent.horizontalCenter; width: 84; height: 84; animate: onb.step === 0 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Bienvenue sur Nova"; color: "#F2F2F4"; font.family: root.fontD; font.pixelSize: 26; font.weight: Font.Bold }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                        text: "Votre assistant de dictée vocale. Maintenez une touche, parlez, relâchez : le texte s'écrit au curseur, reformulé selon le Style."
                        color: "#98989F"; font.family: root.font1; font.pixelSize: 13 }
                }
            }

            // 1 — Touche
            Item { width: root.width; height: view.height
                Column { anchors.centerIn: parent; spacing: 18; width: parent.width - 120
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Votre touche pour parler"; color: "#F2F2F4"; font.family: root.fontD; font.pixelSize: 21; font.weight: Font.Bold }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Maintenez-la pour dicter. Modifiable plus tard dans les Réglages."; color: "#98989F"; font.family: root.font1; font.pixelSize: 12 }
                    Row { anchors.horizontalCenter: parent.horizontalCenter; spacing: 12
                        Repeater { model: ["f9", "f8", "f10"]
                            Choice { width: 120; height: 64; title: modelData.toUpperCase()
                                sel: onb.pttKey === modelData.toUpperCase()
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: onb.setKey(modelData) } }
                        }
                    }
                }
            }

            // 2 — Profil de puissance
            Item { width: root.width; height: view.height
                Column { anchors.centerIn: parent; spacing: 18; width: parent.width - 90
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Profil de puissance"; color: "#F2F2F4"; font.family: root.fontD; font.pixelSize: 21; font.weight: Font.Bold }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Nova l'ajuste à votre machine ; vous pouvez le changer."; color: "#98989F"; font.family: root.font1; font.pixelSize: 12 }
                    Row { anchors.horizontalCenter: parent.horizontalCenter; spacing: 12
                        Repeater { model: JSON.parse(onb.profilesJson)
                            Choice { width: 168; height: 84; title: modelData.label; sub: modelData.hint
                                sel: onb.profileId === modelData.id
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: onb.setProfile(modelData.id) } }
                        }
                    }
                }
            }

            // 3 — Langue
            Item { width: root.width; height: view.height
                Column { anchors.centerIn: parent; spacing: 16; width: parent.width - 90
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Langue de la dictée"; color: "#F2F2F4"; font.family: root.fontD; font.pixelSize: 21; font.weight: Font.Bold }
                    Flow { width: parent.width; spacing: 8
                        Repeater { model: JSON.parse(onb.languagesJson)
                            Rectangle {
                                property bool sel: onb.language === modelData.code
                                radius: 999; height: 34; width: lbl.implicitWidth + 26
                                color: sel ? "#0A84FF" : "#2C2C30"
                                Behavior on color { ColorAnimation { duration: 120 } }
                                Text { id: lbl; anchors.centerIn: parent; text: modelData.label; color: sel ? "white" : "#F2F2F4"; font.family: root.font1; font.pixelSize: 12 }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: onb.setLanguage(modelData.code) }
                            }
                        }
                    }
                }
            }

            // 4 — Moteur
            Item { width: root.width; height: view.height
                Column { anchors.centerIn: parent; spacing: 18; width: parent.width - 120
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Moteur de transcription"; color: "#F2F2F4"; font.family: root.fontD; font.pixelSize: 21; font.weight: Font.Bold }
                    Row { anchors.horizontalCenter: parent.horizontalCenter; spacing: 14
                        Choice { width: 210; height: 104; title: "Intelligence privée"; sub: "100 % sur votre appareil, hors ligne"
                            sel: !onb.cloud
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: onb.setCloud(false) } }
                        Choice { width: 210; height: 104; title: "Turbo"; sub: "Plus rapide, via le réseau"; locked: !onb.canTurbo
                            sel: onb.cloud
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: onb.setCloud(true) } }
                    }
                }
            }

            // 5 — Prêt
            Item { width: root.width; height: view.height
                Column { anchors.centerIn: parent; spacing: 14; width: parent.width - 120
                    Orb { anchors.horizontalCenter: parent.horizontalCenter; width: 72; height: 72; accent: "#8FCFB2"; animate: onb.step === 5 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Tout est prêt"; color: "#F2F2F4"; font.family: root.fontD; font.pixelSize: 24; font.weight: Font.Bold }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                        text: "Maintenez " + onb.pttKey + " et parlez. Nova s'occupe du reste."
                        color: "#98989F"; font.family: root.font1; font.pixelSize: 13 }
                }
            }
        }
    }

    // ---- points de progression ----
    Row {
        anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 66 }
        spacing: 7
        Repeater { model: onb.nSteps
            Rectangle { width: 7; height: 7; radius: 4
                color: index === onb.step ? "#0A84FF" : "#3A3A3E"
                Behavior on color { ColorAnimation { duration: 150 } } }
        }
    }

    // ---- barre du bas ----
    Item {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: 54
        Rectangle {
            visible: onb.step > 0
            anchors { left: parent.left; leftMargin: 30; verticalCenter: parent.verticalCenter }
            width: 108; height: 36; radius: 8; color: prevMA.containsMouse ? "#34343A" : "#2C2C30"; border.color: "#3A3A3E"; border.width: 1
            Text { anchors.centerIn: parent; text: "Précédent"; color: "#F2F2F4"; font.family: root.font1; font.pixelSize: 13 }
            MouseArea { id: prevMA; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: onb.goPrev() }
        }
        Rectangle {
            anchors { right: parent.right; rightMargin: 30; verticalCenter: parent.verticalCenter }
            width: 150; height: 36; radius: 8; color: "#0A84FF"
            Text { anchors.centerIn: parent; text: onb.step === onb.nSteps - 1 ? "Terminer" : "Suivant"; color: "white"; font.family: root.font1; font.pixelSize: 13; font.weight: Font.DemiBold }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                onClicked: onb.step === onb.nSteps - 1 ? onb.finish() : onb.goNext() }
        }
    }
}
