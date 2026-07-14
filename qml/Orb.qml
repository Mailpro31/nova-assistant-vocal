// Bille de verre « Nova » — halo par dégradé radial réel (Canvas), respiration
// douce + réaction au niveau audio. Aucune dépendance hors QtQuick.
import QtQuick

Item {
    id: root
    property real level: 0.0            // 0..1 posé par le fil audio (via nova.level)
    property string accent: "#8AA0EA"   // accent de l'orbe selon l'état
    property bool animate: true         // respiration active (repos/écoute)
    width: 40; height: 40

    // respiration : échelle 0.94..1.0 en boucle, + enflement avec le son
    property real breath: 1.0
    SequentialAnimation on breath {
        running: root.animate; loops: Animation.Infinite
        NumberAnimation { to: 1.0;  duration: 1400; easing.type: Easing.InOutSine }
        NumberAnimation { to: 0.94; duration: 1400; easing.type: Easing.InOutSine }
    }
    scale: breath * (1.0 + 0.16 * level)
    Behavior on scale { NumberAnimation { duration: 90 } }

    Canvas {
        id: cv
        anchors.fill: parent
        property real glow: 0.35 + 0.65 * root.level
        onGlowChanged: requestPaint()
        function rgba(hex, alpha) {
            hex = ("" + hex).replace("#", "");
            var r = parseInt(hex.substr(0, 2), 16),
                g = parseInt(hex.substr(2, 2), 16),
                b = parseInt(hex.substr(4, 2), 16);
            return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
        }
        function darker(hex, f) {
            hex = ("" + hex).replace("#", "");
            var r = Math.round(parseInt(hex.substr(0, 2), 16) / f),
                g = Math.round(parseInt(hex.substr(2, 2), 16) / f),
                b = Math.round(parseInt(hex.substr(4, 2), 16) / f);
            return "rgb(" + r + "," + g + "," + b + ")";
        }
        onPaint: {
            var c = getContext("2d"); c.reset();
            var cx = width/2, cy = height/2, R = Math.min(cx, cy);
            var a = root.accent;
            // halo
            var g = c.createRadialGradient(cx, cy, 1, cx, cy, R);
            g.addColorStop(0.0, "rgba(255,255,255," + (0.95*glow) + ")");
            g.addColorStop(0.42, rgba(a, 0.55*glow));
            g.addColorStop(1.0, rgba(a, 0.0));
            c.fillStyle = g; c.beginPath(); c.arc(cx, cy, R, 0, Math.PI*2); c.fill();
            // bille
            var b = c.createRadialGradient(cx-R*0.3, cy-R*0.34, 1, cx, cy, R*0.62);
            b.addColorStop(0.0, "#FFFFFF");
            b.addColorStop(0.45, a);
            b.addColorStop(1.0, darker(a, 1.7));
            c.fillStyle = b; c.beginPath(); c.arc(cx, cy, R*0.6, 0, Math.PI*2); c.fill();
            // reflet
            c.fillStyle = "rgba(255,255,255,0.9)";
            c.beginPath(); c.arc(cx-R*0.26, cy-R*0.3, R*0.15, 0, Math.PI*2); c.fill();
        }
        Component.onCompleted: requestPaint()
    }
    onAccentChanged: cv.requestPaint()
}
