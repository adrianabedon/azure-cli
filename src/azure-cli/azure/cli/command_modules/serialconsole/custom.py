# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

# from knack.util import CLIError
import requests
import json
import websocket
import threading
import sys
import uuid
import time


class GlobalVariables:
    def __init__(self):
        self.webSocket = None
        self.terminalInstance = None
        self.serialConsoleInstance = None
        self.terminatingApp = False
        self.loading = True
        self.firstMessage = True


GV = GlobalVariables()


def quitapp(fromWebsocket=False, message=""):
    print("\x1b[31m" + message + "\x1b[0m", end="\r\n", flush=True)
    GV.terminatingApp = True
    GV.loading = False
    if GV.terminalInstance:
        GV.terminalInstance.revertTerminal()
        GV.terminalInstance = None
    if not fromWebsocket and GV.webSocket:
        GV.webSocket.close()
        GV.webSocket = None
    sys.exit()


class _Getch:
    def __init__(self):
        if sys.platform.startswith('win'):
            import ctypes
            from ctypes import wintypes
            STD_INPUT_HANDLE = -10
            self.hIn = ctypes.windll.kernel32.GetStdHandle(STD_INPUT_HANDLE)
            self.lpBuffer = ctypes.create_string_buffer(1)
            self.lpNumberOfCharsRead = wintypes.DWORD()
            self.nNumberOfCharsToRead = wintypes.DWORD()
            self.nNumberOfCharsToRead.value = 1
            self.impl = self._getchWindows
        else:
            self.impl = self._getchUnix

    def __call__(self):
        return self.impl()

    def _getchUnix(self):
        return sys.stdin.read(1).encode()

    def _getchWindows(self):
        import ctypes
        status = ctypes.windll.kernel32.ReadConsoleW(self.hIn,
                                                     self.lpBuffer,
                                                     self.nNumberOfCharsToRead,
                                                     ctypes.byref(
                                                         self.lpNumberOfCharsRead),
                                                     None)
        if status == 0:
            quitapp()
        return chr(self.lpBuffer.raw[0]).encode()


class Terminal:
    def __init__(self):
        self.winOriginalOutMode = None
        self.winOriginalInMode = None
        self.winOut = None
        self.winIn = None
        self.unixOriginalMode = None

    def configureTerminal(self):
        if sys.platform.startswith('win'):
            import ctypes
            from ctypes import wintypes
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
            ENABLE_ECHO_INPUT = 0x0004
            ENABLE_LINE_INPUT = 0x0002
            ENABLE_PROCESSED_INPUT = 0x0001
            STD_OUTPUT_HANDLE = -11
            STD_INPUT_HANDLE = -10
            DISABLE = ~(ENABLE_ECHO_INPUT | ENABLE_LINE_INPUT |
                        ENABLE_PROCESSED_INPUT)

            kernel32 = ctypes.windll.kernel32
            dwOriginalOutMode = wintypes.DWORD()
            dwOriginalInMode = wintypes.DWORD()
            self.winOut = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            self.winIn = kernel32.GetStdHandle(STD_INPUT_HANDLE)
            errorMessage = "Error configuring terminal: Make sure that app in running in a Windows 10 console."

            if not kernel32.GetConsoleMode(self.winOut, ctypes.byref(dwOriginalOutMode)):
                quitapp(message=errorMessage)
            if not kernel32.GetConsoleMode(self.winIn, ctypes.byref(dwOriginalInMode)):
                quitapp(message=errorMessage)

            self.winOriginalOutMode = dwOriginalOutMode.value
            self.winOriginalInMode = dwOriginalInMode.value

            dwOutMode = self.winOriginalOutMode | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            dwInMode = (self.winOriginalInMode |
                        ENABLE_VIRTUAL_TERMINAL_INPUT) & DISABLE

            if not kernel32.SetConsoleMode(self.winOut, dwOutMode):
                quitapp(message=errorMessage)
            if not kernel32.SetConsoleMode(self.winIn, dwInMode):
                quitapp(message=errorMessage)
        else:
            import tty
            import termios
            errorMessage = "Error configuring terminal: Make sure that app in running in a terminal."
            try:
                fd = sys.stdin.fileno()
            except ValueError:
                quitapp(message=errorMessage)
            self.unixOriginalMode = termios.tcgetattr(fd)
            tty.setraw(fd)

    def revertTerminal(self):
        if sys.platform.startswith('win'):
            import ctypes
            kernel32 = ctypes.windll.kernel32
            if self.winOriginalOutMode:
                kernel32.SetConsoleMode(self.winOut, self.winOriginalOutMode)
            if self.winOriginalInMode:
                kernel32.SetConsoleMode(self.winIn, self.winOriginalInMode)
        else:
            import termios
            if self.unixOriginalMode:
                try:
                    fd = sys.stdin.fileno()
                except ValueError:
                    return
                termios.tcsetattr(fd, termios.TCSADRAIN, self.unixOriginalMode)


def listenForKeys():
    getch = _Getch()
    while True:
        c = getch()
        if GV.webSocket:
            if c == b'\x1d':
                c = getch()
                if c == b'n':
                    GV.serialConsoleInstance.sendNMI()
                    continue
                if c == b'r':
                    GV.serialConsoleInstance.sendReset()
                    continue
                if c == b's':
                    c = getch()
                    GV.serialConsoleInstance.sendSysRq(c.decode())
                    continue
                if c == b'q':
                    quitapp()
                    return
                if c != b'\x1d':
                    continue
            try:
                if GV.webSocket:
                    GV.webSocket.send(c)
            except (AttributeError, websocket.WebSocketConnectionClosedException):
                pass
        else:
            if c == b'\r':
                GV.serialConsoleInstance.connect()
            elif c == b'\x1d':
                c = getch()
                if c == b'q':
                    quitapp()
                    return


class SerialConsole:
    def __init__(self, cmd, resource_group_name, vm_vmss_name, vmss_instanceid):
        from azure.cli.core.commands.client_factory import get_subscription_id
        armEndpoint = "https://management.azure.com"
        RP_PROVIDER = "Microsoft.SerialConsole"
        subscriptionId = get_subscription_id(cmd.cli_ctx)
        vmPath = f"virtualMachineScaleSets/{vm_vmss_name}/virtualMachines/{vmss_instanceid}" if vmss_instanceid else f"virtualMachines/{vm_vmss_name}"
        self.connectionUrl = (f"{armEndpoint}/subscriptions/{subscriptionId}/resourcegroups/{resource_group_name}"
                              f"/providers/Microsoft.Compute/{vmPath}"
                              f"/providers/{RP_PROVIDER}/serialPorts/0"
                              f"/connect?api-version=2018-05-01")
        self.websocketURL = None
        self.accessToken = None

    # Returns True if successful, False otherwise
    def loadWebSocketURL(self):
        from azure.cli.core._profile import Profile
        tokenInfo, _, _ = Profile().get_raw_token()
        self.accessToken = tokenInfo[1]
        applicationJsonFormat = "application/json"
        headers = {'authorization': "Bearer " + self.accessToken,
                   'accept': applicationJsonFormat,
                   'content-type': applicationJsonFormat}
        result = requests.post(self.connectionUrl, headers=headers)
        jsonResults = json.loads(result.text)
        if result.status_code == 200 and "connectionString" in jsonResults:
            self.websocketURL = jsonResults["connectionString"]
            return True

        return False

    def connect(self):
        def on_open(_):
            pass

        def on_message(_, message):
            if GV.firstMessage:
                print("\x1b[2J\x1b[0;0H", end='', flush=True)
            GV.firstMessage = False
            GV.loading = False
            print(message, end='', flush=True)

        def on_error(*_):
            pass

        def on_close(_):
            GV.loading = False
            if not GV.terminatingApp:
                print(
                    "\r\n\x1b[31m### Connection Closed: Press Enter to reconnect...\x1b[0m", end="\r\n")
                GV.webSocket = None

        def connectThread():
            if self.loadWebSocketURL():
                GV.webSocket = websocket.WebSocketApp(self.websocketURL + "?authorization=" + self.accessToken,
                                                      on_open=on_open,
                                                      on_message=on_message,
                                                      on_error=on_error,
                                                      on_close=on_close)
                GV.webSocket.run_forever()
            else:
                GV.loading = False
                print(
                    "\r\n\x1b[31m### Could not establish connection to VM or VMSS. Make sure that input parameters are correct or press Enter to try again...\x1b[0m", end="\r\n")

        def loadingMessage():
            dots = 0
            while GV.loading:
                print("\x1b[2J\x1b[0;0H\x1b[36m### Opening" + "." * dots + "\x1b[0m", end="", flush=True)
                dots = (dots + 1) % 4
                time.sleep(0.5)
        GV.loading = True
        GV.firstMessage = True

        th1 = threading.Thread(target=loadingMessage, args=())
        th1.daemon = True
        th1.start()

        th2 = threading.Thread(target=connectThread, args=())
        th2.daemon = True
        th2.start()

    def sendAdminCommand(self, command, commandParameters):
        if self.websocketURL and self.accessToken:
            url = self.websocketURL.replace("wss", "https").replace(
                "ws", "http").replace("/client", "/adminCommand/" + command)
            headers = {'accept': "application/json",
                       'authorization': "Bearer " + self.accessToken,
                       'accept-language': "en",
                       'content-type': "application/json"}
            data = {'command': command,
                    'requestId': str(uuid.uuid4()),
                    'commandParameters': commandParameters}
            requests.post(url, headers=headers, data=json.dumps(data))

    def sendNMI(self):
        self.sendAdminCommand("nmi", {})

    def sendReset(self):
        self.sendAdminCommand("reset", {})

    def sendSysRq(self, key):
        self.sendAdminCommand("sysrq", {"SysRqCommand": key})


def connect_serialconsole(cmd, resource_group_name, vm_vmss_name, vmss_instanceid=None):
    GV.terminalInstance = Terminal()
    GV.terminalInstance.configureTerminal()

    th = threading.Thread(target=listenForKeys, args=())
    th.daemon = True
    th.start()

    GV.serialConsoleInstance = SerialConsole(cmd, resource_group_name, vm_vmss_name, vmss_instanceid)
    GV.serialConsoleInstance.connect()

    th.join()
