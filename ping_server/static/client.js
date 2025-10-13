let socket
let token

async function login(username, uid) {
    let json = await (await fetch("/login", {
        method: 'POST',
        headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, uid })
    })).json()
    return json
}

async function pingClient(to) {
    let json = await (await fetch("/ping", {
        method: 'POST',
        headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': "Bearer " + token
        },
        body: JSON.stringify({ to })
    })).json()
    return json
}

async function createWebsocket() {
    let { username, uid } = userData
    let loginData = await login(username, uid)
    token = loginData.token
    socket = new WebSocket("ws://" + location.host + "/ws?token=" + token);

    // Connection opened
    socket.addEventListener("open", (event) => {
        //socket.send("Hello Server!");
    });

    // Listen for messages
    socket.addEventListener("message", (event) => {
        console.log("Message from server ", event.data);
        let json = JSON.parse(event.data)
        switch (json.type) {
            case "clientlist":
                updateClientList(json.clients)
                break;

            default:
                break;
        }
    });
}