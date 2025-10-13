const clientList = document.getElementById("clientList")
const pingForm = document.getElementById("pingForm");

let userData;
getUserData()

let connectedClients = []

async function getClients() {
    let json = await (await fetch("/clients")).json()
    return json
}

function getUserData() {
    let userdatastring = localStorage.getItem("userdata")
    if (!userdatastring) {
        userData = {
            username: generateName(),
            uid: guidGenerator()
        }
        saveUserData(userData)
        return userData
    }

    userData = JSON.parse(userdatastring)
    return userData
}

function saveUserData(userdata) {
    localStorage.setItem("userdata", JSON.stringify(userdata))
}

function addClient(name) {
    let clientDiv = document.getElementById("client-" + name)
    if (clientDiv) return

    clientDiv = document.createElement("div")
    clientDiv.id = "client-" + name

    let clientName = document.createElement("name")
    clientName.textContent = name
    clientDiv.appendChild(clientName)

    clientList.appendChild(clientDiv)
}

function removeClient(name) {
    let clientDiv = document.getElementById("client-" + name)
    clientDiv.remove()
}


async function updateClientList(clients) {
    console.log(clients)
    connectedClients.forEach(client=>{
        if (!clients.includes(client)) removeClient(client)
    })
    connectedClients = clients
    clients.forEach(name => {
        addClient(name)
    });
}

pingForm.addEventListener("submit", (e) => {
    e.preventDefault();
    let username = document.getElementById("username");
    if (!username) return

    pingClient(username.value)
})