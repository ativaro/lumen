import QtQuick
Canvas {
    id: chart
    property var points: []
    property var keys: ['value']
    property var colors: ['#9be5d8']
    property var events: []
    property color gridColor: '#526d79'
    property real maximum: 100
    property int seconds: 60
    property bool grid: false
    onPointsChanged: requestPaint()
    onColorsChanged: requestPaint()
    onMaximumChanged: requestPaint()
    onSecondsChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        let ctx = getContext('2d'); ctx.reset()
        if (grid) {
            ctx.strokeStyle = Qt.alpha(gridColor,.28); ctx.lineWidth = 1
            for (let y of [.0,.5,1.0]) { ctx.beginPath(); ctx.moveTo(0, 2+y*(height-4)); ctx.lineTo(width,2+y*(height-4)); ctx.stroke() }
        }
        if (!points.length) return
        let end = points[points.length-1].time, start = end - seconds
        for (let k=0; k<keys.length; k++) {
            ctx.beginPath(); ctx.strokeStyle=colors[k % colors.length]; ctx.lineWidth=2; ctx.lineJoin='round'
            let open=false, lastTime=null
            for (let p of points) {
                let value=p[keys[k]]
                if (value === null || value === undefined) { open=false; continue }
                let x=Math.max(0,(p.time-start)/seconds*width), y=height-3-Math.min(1,Math.max(0,value/maximum))*(height-6)
                if (!open || (lastTime !== null && p.time-lastTime>8)) ctx.moveTo(x,y); else ctx.lineTo(x,y)
                open=true; lastTime=p.time
            }
            ctx.stroke()
        }
        if (grid) for (let event of events) {
            if (event.timestamp < start || event.timestamp > end) continue
            let x=(event.timestamp-start)/seconds*width
            ctx.strokeStyle=Qt.alpha(gridColor,.6); ctx.lineWidth=1; ctx.setLineDash([3,5])
            ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,height); ctx.stroke(); ctx.setLineDash([])
        }
    }
}
