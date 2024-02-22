let websocket = new WebSocket("ws://" + window.location.host + "/ws/reload");

websocket.onmessage = function(e) {
    if (e.data == "reload") {
        window.location.reload();
    }
}

websocket.onclose = function(e) {
    window.location.reload()
}