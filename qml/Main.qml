// Dock Nova en QML — pilule (Réglages · bille · Styles) + bulle d'état + menu
// des Styles. Trois fenêtres frameless translucides toujours-au-dessus, pilotées
// par le pont Python `nova` (propriétés + slots). Animations natives (respiration
// de l'orbe, équaliseur, fondus). Aucune dépendance hors QtQuick.
import QtQuick
import QtQuick.Window

Window {
    id: pill
    // — pilule —
    property int pad: 8
    width: row.implicitWidth + 20
    height: 56
    visible: nova.pillShown
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
           | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint
    color: "transparent"
    opacity: nova.dockOpacity

    // accent de l'orbe selon l'état (ou couleur choisie par l'utilisateur)
    function accentFor(s) {
        if (nova.orbColor && nova.orbColor.length === 7) return nova.orbColor;
        switch (s) {
            case "listening": return "#8FB4FF";
            case "thinking":  return "#B6A8E6";
            case "ok":        return "#8FCFB2";
            case "error":     return "#E0A890";
            default:          return "#9DB0DD";
        }
    }

    // — placement (bas-centre par défaut), lu depuis nova.dockPosition —
    property int margin: 16
    function place() {
        var aw = Screen.desktopAvailableWidth, ah = Screen.desktopAvailableHeight;
        var sx = Screen.virtualX, sy = Screen.virtualY;
        var p = ("" + nova.dockPosition).split("-");
        var vert = p[0], horiz = p[1];
        pill.x = (horiz === "left") ? sx + margin
               : (horiz === "right") ? sx + aw - pill.width - margin
               : sx + (aw - pill.width) / 2;
        pill.y = (vert === "top") ? sy + margin
               : sy + ah - pill.height - margin;
    }
    onWidthChanged: place()
    Component.onCompleted: place()
    Connections { target: nova; function onDockPositionChanged() { pill.place() } }

    // — capsule —
    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: "#212127"
        border.color: "#34343C"; border.width: 1
        // lueur intérieure haute (verre)
        Rectangle {
            anchors { top: parent.top; topMargin: 1; horizontalCenter: parent.horizontalCenter }
            width: parent.width - 22; height: parent.height/2; radius: 26
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#26262E" }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 0

        // roue dentée (Réglages)
        Item {
            width: 54; height: 48
            Canvas { anchors.fill: parent; onPaint: {
                var c=getContext("2d"); c.reset(); var cx=width/2, cy=height/2, r=8;
                c.strokeStyle=gearMA.containsMouse?"#F2F2F4":"#AEB2BC";
                c.fillStyle=c.strokeStyle; c.lineWidth=2; c.lineCap="round";
                for (var a=0;a<360;a+=45){var dx=Math.cos(a*Math.PI/180),dy=Math.sin(a*Math.PI/180);
                    c.beginPath(); c.moveTo(cx+dx*r,cy+dy*r); c.lineTo(cx+dx*(r+3.5),cy+dy*(r+3.5)); c.stroke();}
                c.beginPath(); c.arc(cx,cy,r,0,Math.PI*2); c.stroke();
                c.beginPath(); c.arc(cx,cy,2.6,0,Math.PI*2); c.fill();
            } Connections { target: gearMA; function onContainsMouseChanged(){ parent.requestPaint() } } }
            MouseArea { id: gearMA; anchors.fill: parent; hoverEnabled: true
                cursorShape: Qt.PointingHandCursor; onClicked: nova.gear() }
        }
        Rectangle { width:1; height:26; color:"#37373F"; anchors.verticalCenter: parent.verticalCenter }

        // bille de verre
        Item {
            width: 76; height: 48
            Orb { anchors.centerIn: parent; width: 38; height: 38
                  level: nova.level; accent: pill.accentFor(nova.state)
                  animate: nova.pillShown }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                onClicked: nova.star() }
        }

        Rectangle { width:1; height:26; color:"#37373F"; anchors.verticalCenter: parent.verticalCenter }
        // étoile (Styles)
        Item {
            width: 54; height: 48
            Canvas { anchors.fill: parent; onPaint: {
                var c=getContext("2d"); c.reset(); var cx=width/2, cy=height/2, r=9;
                c.strokeStyle=starMA.containsMouse?"#F2F2F4":"#AEB2BC"; c.lineWidth=2; c.lineJoin="round";
                c.beginPath();
                for (var k=0;k<10;k++){var rad=(k%2)?r*0.42:r; var a=(-90+k*36)*Math.PI/180;
                    var px=cx+Math.cos(a)*rad, py=cy+Math.sin(a)*rad; if(k===0)c.moveTo(px,py); else c.lineTo(px,py);}
                c.closePath(); c.stroke();
            } Connections { target: starMA; function onContainsMouseChanged(){ parent.requestPaint() } } }
            MouseArea { id: starMA; anchors.fill: parent; hoverEnabled: true
                cursorShape: Qt.PointingHandCursor; onClicked: nova.star() }
        }
    }

    // ===================== bulle d'état (au-dessus de la pilule) =============
    Window {
        id: bubble
        flags: pill.flags
        color: "transparent"
        visible: nova.bubbleShown && nova.pillShown
        width: Math.max(190, bubbleRow.implicitWidth + 40)
        height: 46
        // placement IMPÉRATIF (pas de binding x↔width → aucune boucle de liaison)
        function place() { x = pill.x + (pill.width - width) / 2; y = pill.y - height - 10 }
        onWidthChanged: place()
        onVisibleChanged: place()
        Connections { target: pill
            function onXChanged() { bubble.place() }
            function onYChanged() { bubble.place() }
            function onWidthChanged() { bubble.place() } }
        opacity: nova.bubbleShown ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }

        Rectangle {
            anchors.fill: parent; radius: 15
            color: "#1A1B20"
            border.width: 1
            border.color: nova.state === "listening" ? "#2B517E"
                        : nova.state === "ok" ? "#2C6743"
                        : nova.state === "error" ? "#7A4438" : "#3A3D46"
        }
        Row {
            id: bubbleRow
            anchors.verticalCenter: parent.verticalCenter
            x: 16; spacing: 10
            // équaliseur animé (écoute)
            Row {
                spacing: 3; visible: nova.state === "listening"
                anchors.verticalCenter: parent.verticalCenter
                Repeater {
                    model: 11
                    Rectangle {
                        width: 3; radius: 2; color: index % 2 ? "#9CC8F0" : "#AEBEEC"
                        anchors.verticalCenter: parent.verticalCenter
                        height: 6
                        SequentialAnimation on height {
                            running: nova.state === "listening"; loops: Animation.Infinite
                            NumberAnimation { to: 6 + (index % 5) * 4 + 8; duration: 220 + index*17; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 5; duration: 240 + index*13; easing.type: Easing.InOutSine }
                        }
                    }
                }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: nova.bubbleText
                color: nova.state === "ok" ? "#BFE9D2" : nova.state === "error" ? "#F0C8B4" : "#ECEFF7"
                font.family: "SF Pro Text, Segoe UI, sans-serif"; font.pixelSize: 14; font.weight: Font.DemiBold
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: nova.bubbleSub; visible: nova.bubbleSub.length > 0
                color: "#7C8398"; font.family: "SF Pro Text, Segoe UI, sans-serif"; font.pixelSize: 12
            }
        }
    }

    // ===================== menu des Styles ===================================
    Window {
        id: menu
        flags: pill.flags
        color: "transparent"
        visible: nova.menuShown && nova.pillShown
        width: 264
        height: menuCol.implicitHeight + 12
        function place() { x = pill.x + (pill.width - width) / 2; y = pill.y - height - 10 }
        onHeightChanged: place()
        onVisibleChanged: place()
        Connections { target: pill
            function onXChanged() { menu.place() }
            function onYChanged() { menu.place() }
            function onWidthChanged() { menu.place() } }
        opacity: nova.menuShown ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 140 } }

        Rectangle { anchors.fill: parent; radius: 18; color: "#1A1B20"; border.color: "#3A3D46"; border.width: 1 }
        Column {
            id: menuCol
            anchors { fill: parent; margins: 6 }
            spacing: 2
            Repeater {
                model: JSON.parse(nova.modesJson || "[]")
                Rectangle {
                    width: parent.width; height: 40; radius: 10
                    property bool active: modelData.id === nova.currentMode
                    color: active ? "#1E3556" : rowMA.containsMouse && modelData.allowed ? "#26262E" : "transparent"
                    Text {
                        x: 12; anchors.verticalCenter: parent.verticalCenter
                        text: modelData.label
                        color: modelData.allowed ? "#F2F2F4" : "#7C8398"
                        font.family: "SF Pro Text, Segoe UI, sans-serif"; font.pixelSize: 13
                    }
                    Text {
                        visible: !modelData.allowed && modelData.lock
                        anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                        text: modelData.lock; color: "#C9B6F0"; font.pixelSize: 8; font.weight: Font.DemiBold
                    }
                    Canvas {
                        visible: active
                        anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                        width: 16; height: 16
                        onPaint: { var c=getContext("2d"); c.reset(); c.strokeStyle="#0A84FF"; c.lineWidth=2;
                            c.lineCap="round"; c.lineJoin="round"; c.beginPath();
                            c.moveTo(3,8); c.lineTo(7,12); c.lineTo(13,4); c.stroke(); }
                    }
                    MouseArea {
                        id: rowMA; anchors.fill: parent; hoverEnabled: true
                        cursorShape: modelData.allowed ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: if (modelData.allowed) nova.pick(modelData.id)
                    }
                }
            }
        }
    }
}
