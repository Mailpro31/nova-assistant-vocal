// Fenêtre Réglages en QML — barre latérale à catégories + panneaux animés.
// Racine = Item (rendue par un QQuickView côté Python : fenêtre réelle ET
// prévisualisable offscreen). Pilotée par le pont `settings`. Style macOS
// (CLAUDE.md) : listes groupées arrondies, interrupteurs macOS, accent #0A84FF.
import QtQuick

Item {
    id: root
    width: 760; height: 540

    property int panel: 1                 // 0 Apparence · 1 Moteur · 2 Licence
    readonly property string font1: "SF Pro Text, Segoe UI, sans-serif"

    // ---- composants réutilisables ----
    component Switch : Item {
        id: sw
        property bool on: false
        signal toggled(bool value)
        width: 42; height: 25
        Rectangle {
            anchors.fill: parent; radius: height / 2
            color: sw.on ? "#0A84FF" : "#3A3A3E"
            Behavior on color { ColorAnimation { duration: 140 } }
            Rectangle {
                width: 21; height: 21; radius: 11; color: "white"; y: 2
                x: sw.on ? parent.width - width - 2 : 2
                Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
            }
        }
        // « contrôlé » : ne bascule PAS localement — il reflète `on` (lié à la
        // config) et demande le changement ; si refusé (palier), il revient seul.
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
            onClicked: sw.toggled(!sw.on) }
    }
    component SecLabel : Text {
        color: "#98989F"; font.family: root.font1; font.pixelSize: 11
        font.weight: Font.DemiBold; font.capitalization: Font.AllUppercase
        font.letterSpacing: 0.6; topPadding: 14; bottomPadding: 6
    }
    component Group : Rectangle { color: "#2C2C30"; radius: 10; width: parent.width }
    component Hair : Rectangle { height: 1; color: "#3A3A3E"; x: 14; width: parent.width - 28 }

    Rectangle { anchors.fill: parent; color: "#1F1F22"; radius: 13 }

    Row {
        anchors.fill: parent
        // -------- barre latérale --------
        Rectangle {
            width: 210; height: parent.height; color: "#28282C"
            topLeftRadius: 13; bottomLeftRadius: 13
            Column {
                x: 12; y: 20; width: parent.width - 24; spacing: 4
                // en-tête = poignée de déplacement (fenêtre frameless). La zone de
                // drag est sur l'Item (pas dans le Row → pas d'anchors interdits).
                Item {
                    width: parent.width; height: 34
                    MouseArea { anchors.fill: parent; onPressed: settings.startDrag() }
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10
                        Item { width: 30; height: 30
                            Orb { anchors.centerIn: parent; width: 28; height: 28; animate: false } }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            Text { text: "Nova"; color: "#F2F2F4"; font.family: root.font1; font.pixelSize: 15; font.weight: Font.DemiBold }
                            Text { text: "Réglages"; color: "#98989F"; font.family: root.font1; font.pixelSize: 12 }
                        }
                    }
                }
                Item { width: 1; height: 12 }
                Repeater {
                    model: [ {n: "Apparence", c: "#FF9F0A"},
                             {n: "Moteur & dictée", c: "#0A84FF"},
                             {n: "Licence", c: "#C9B6F0"} ]
                    Rectangle {
                        width: parent.width; height: 34; radius: 7
                        color: root.panel === index ? "#3A3A40"
                             : catMA.containsMouse ? "#303036" : "transparent"
                        Behavior on color { ColorAnimation { duration: 120 } }
                        Row {
                            anchors.verticalCenter: parent.verticalCenter; x: 8; spacing: 9
                            Rectangle { width: 20; height: 20; radius: 5; color: modelData.c; anchors.verticalCenter: parent.verticalCenter }
                            Text { text: modelData.n; color: "#F2F2F4"; font.family: root.font1; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                        }
                        MouseArea { id: catMA; anchors.fill: parent; hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor; onClicked: root.panel = index }
                    }
                }
            }
        }

        // -------- contenu (panneaux empilés, animés) --------
        Item {
            id: content
            width: parent.width - 210; height: parent.height
            clip: true

            // fabrique un panneau qui glisse/fond selon root.panel
            component Panel : Item {
                property int index: 0
                anchors.fill: parent
                visible: opacity > 0.01
                opacity: root.panel === index ? 1 : 0
                x: root.panel === index ? 0 : (root.panel > index ? -24 : 24)
                Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                Behavior on x { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
            }

            // ---- Apparence ----
            Panel {
                index: 0
                Column {
                    x: 24; y: 24; width: parent.width - 48; spacing: 6
                    Text { text: "Apparence"; color: "#F2F2F4"; font.family: root.font1; font.pixelSize: 20; font.weight: Font.Bold }
                    SecLabel { text: "Couleur de l'orbe" }
                    Row {
                        spacing: 12
                        Repeater {
                            model: ["", "#0A84FF", "#30D158", "#FF9F0A", "#C9B6F0", "#FF453A"]
                            Rectangle {
                                width: 34; height: 34; radius: 17
                                color: modelData === "" ? "#3A3A3E" : modelData
                                border.width: settings.orbColor === modelData ? 3 : 0
                                border.color: "#FFFFFF"
                                Text { visible: modelData === ""; anchors.centerIn: parent; text: "A"; color: "#98989F"; font.pixelSize: 12 }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                    onClicked: settings.setOrbColor(modelData) }
                            }
                        }
                    }
                    SecLabel { text: "Position du dock" }
                    Group { height: posCol.height
                        Column { id: posCol; width: parent.width
                            Repeater {
                                model: [ {id: "bottom-center", n: "En bas au centre"},
                                         {id: "bottom-right", n: "En bas à droite"},
                                         {id: "bottom-left", n: "En bas à gauche"},
                                         {id: "top-center", n: "En haut au centre"} ]
                                Column { width: parent.width
                                    Item { width: parent.width; height: 44
                                        Text { x: 14; anchors.verticalCenter: parent.verticalCenter; text: modelData.n; color: "#F2F2F4"; font.family: root.font1; font.pixelSize: 13 }
                                        Canvas { visible: settings.dockPosition === modelData.id
                                            anchors { right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                                            width: 16; height: 16
                                            onPaint: { var c=getContext("2d"); c.reset(); c.strokeStyle="#0A84FF"; c.lineWidth=2; c.lineCap="round"; c.lineJoin="round"; c.beginPath(); c.moveTo(3,8); c.lineTo(7,12); c.lineTo(13,4); c.stroke(); } }
                                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: settings.setDockPosition(modelData.id) }
                                    }
                                    Hair { visible: index < 3 }
                                }
                            }
                        }
                    }
                }
            }

            // ---- Moteur & dictée ----
            Panel {
                index: 1
                Column {
                    x: 24; y: 24; width: parent.width - 48; spacing: 6
                    Text { text: "Moteur & dictée"; color: "#F2F2F4"; font.family: root.font1; font.pixelSize: 20; font.weight: Font.Bold }
                    SecLabel { text: "Transcription" }
                    Group { height: engCol.height
                        Column { id: engCol; width: parent.width
                            Item { width: parent.width; height: 46
                                Text { x: 14; anchors.verticalCenter: parent.verticalCenter
                                    text: "Turbo (plus rapide, via le réseau)" + (settings.canTurbo ? "" : "   — NÉCESSITE NOVA ULTRA")
                                    color: settings.canTurbo ? "#F2F2F4" : "#7C8398"; font.family: root.font1; font.pixelSize: 13 }
                                Switch { on: settings.cloudOn; anchors { right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                                    enabled: settings.canTurbo; opacity: settings.canTurbo ? 1 : 0.4
                                    onToggled: function(v) { settings.setCloud(v) } }
                            }
                            Hair {}
                            Item { width: parent.width; height: 46
                                Text { x: 14; anchors.verticalCenter: parent.verticalCenter; text: "Reformulation hors ligne"; color: "#F2F2F4"; font.family: root.font1; font.pixelSize: 13 }
                                Text { text: settings.offlineState; color: settings.offlineColor
                                    anchors { right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                                    font.family: root.font1; font.pixelSize: 12 }
                            }
                        }
                    }
                    SecLabel { text: "Profil de puissance" }
                    Row {
                        spacing: 10; width: parent.width
                        Repeater {
                            model: JSON.parse(settings.profilesJson || "[]")
                            Rectangle {
                                width: (parent.width - 20) / 3; height: 74; radius: 10
                                color: settings.profileId === modelData.id ? "#1E3556" : "#2C2C30"
                                border.width: settings.profileId === modelData.id ? 1 : 0; border.color: "#0A84FF"
                                Behavior on color { ColorAnimation { duration: 140 } }
                                Column { anchors.centerIn: parent; spacing: 3
                                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.label; color: "#F2F2F4"; font.family: root.font1; font.pixelSize: 13; font.weight: Font.DemiBold }
                                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.hint; color: "#98989F"; font.family: root.font1; font.pixelSize: 11 }
                                }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: settings.setProfile(modelData.id) }
                            }
                        }
                    }
                    SecLabel { text: "Vitesse de transcription" }
                    Group { height: 46
                        Item { width: parent.width; height: 46
                            Text { x: 14; anchors.verticalCenter: parent.verticalCenter; text: "Latence minimale"; color: "#F2F2F4"; font.family: root.font1; font.pixelSize: 13 }
                            Switch { on: settings.latencyMin; anchors { right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                                onToggled: function(v) { settings.setLatency(v) } }
                        }
                    }
                }
            }

            // ---- Licence ----
            Panel {
                index: 2
                Column {
                    x: 24; y: 24; width: parent.width - 48; spacing: 6
                    Text { text: "Licence"; color: "#F2F2F4"; font.family: root.font1; font.pixelSize: 20; font.weight: Font.Bold }
                    SecLabel { text: "État" }
                    Text { text: settings.licText; color: settings.licColor; font.family: root.font1; font.pixelSize: 13; width: parent.width; wrapMode: Text.WordWrap }
                    SecLabel { text: "Activer une clé" }
                    Row {
                        spacing: 10; width: parent.width
                        Rectangle {
                            width: parent.width - 130; height: 34; radius: 6; color: "#1A1A1D"; border.color: "#3A3A3E"; border.width: 1
                            TextInput { id: keyInput; anchors.fill: parent; anchors.margins: 9; color: "#F2F2F4"; font.family: root.font1; font.pixelSize: 13; verticalAlignment: TextInput.AlignVCenter; clip: true }
                            Text { visible: keyInput.text.length === 0; x: 10; anchors.verticalCenter: parent.verticalCenter; text: "NOVA-XXXX-XXXX-XXXX"; color: "#6A6A72"; font.family: root.font1; font.pixelSize: 13 }
                        }
                        Rectangle { width: 110; height: 34; radius: 8; color: "#0A84FF"
                            Text { anchors.centerIn: parent; text: "Activer"; color: "white"; font.family: root.font1; font.pixelSize: 13; font.weight: Font.DemiBold }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: settings.activate(keyInput.text) }
                        }
                    }
                    Item { height: 10; width: 1 }
                    Rectangle { width: 170; height: 36; radius: 8; color: "#0A84FF"
                        Text { anchors.centerIn: parent; text: "Passer à Nova Ultra"; color: "white"; font.family: root.font1; font.pixelSize: 13; font.weight: Font.DemiBold }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: settings.upgrade() }
                    }
                }
            }

            // bouton Fermer (coin bas-droit)
            Rectangle {
                anchors { right: parent.right; bottom: parent.bottom; margins: 20 }
                width: 96; height: 34; radius: 8; color: closeMA.containsMouse ? "#34343A" : "#2C2C30"
                border.color: "#3A3A3E"; border.width: 1
                Text { anchors.centerIn: parent; text: "Fermer"; color: "#F2F2F4"; font.family: root.font1; font.pixelSize: 13 }
                MouseArea { id: closeMA; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: settings.close() }
            }
        }
    }
}
