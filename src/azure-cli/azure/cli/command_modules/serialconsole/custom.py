# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from knack.util import CLIError
import requests
import json
import websocket
import threading
import sys
import uuid
import time


webSocket = None
terminalInstance = None
serialConsoleInstance = None
terminatingApp = False
loading = True


def quitapp(fromWebsocket=False):
    global terminalInstance, webSocket, terminatingApp, loading
    terminatingApp = True
    loading = True
    if terminalInstance:
        terminalInstance.revertTerminal()
        terminalInstance = None
    if not fromWebsocket and webSocket:
        webSocket.close()
        webSocket = None
    sys.exit()


class _Getch:
    class _GetchWindows:
        def __init__(self):
            import ctypes
            from ctypes import wintypes
            STD_INPUT_HANDLE = -10
            self.hIn = ctypes.windll.kernel32.GetStdHandle(STD_INPUT_HANDLE)
            self.lpBuffer = ctypes.create_string_buffer(1)
            self.lpNumberOfCharsRead = wintypes.DWORD()
            self.nNumberOfCharsToRead = wintypes.DWORD()
            self.nNumberOfCharsToRead.value = 1

        def __call__(self):
            import ctypes
            ctypes.windll.kernel32.ReadConsoleW(self.hIn,
                                                self.lpBuffer,
                                                self.nNumberOfCharsToRead,
                                                ctypes.byref(
                                                    self.lpNumberOfCharsRead),
                                                None)
            return chr(self.lpBuffer.raw[0]).encode()

    class _GetchUnix:
        def __init__(self):
            pass

        def __call__(self):
            return sys.stdin.read(1).encode()

    def __init__(self):
        if sys.platform.startswith('win'):
            self.impl = self._GetchWindows()
        else:
            self.impl = self._GetchUnix()

    def __call__(self):
        return self.impl()


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

            if not kernel32.GetConsoleMode(self.winOut, ctypes.byref(dwOriginalOutMode)):
                quitapp()
            if not kernel32.GetConsoleMode(self.winIn, ctypes.byref(dwOriginalInMode)):
                quitapp()

            self.winOriginalOutMode = dwOriginalOutMode.value
            self.winOriginalInMode = dwOriginalInMode.value

            dwOutMode = self.winOriginalOutMode | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            dwInMode = (self.winOriginalInMode |
                        ENABLE_VIRTUAL_TERMINAL_INPUT) & DISABLE

            if not kernel32.SetConsoleMode(self.winOut, dwOutMode):
                quitapp()
            if not kernel32.SetConsoleMode(self.winIn, dwInMode):
                quitapp()
        else:
            import tty
            import termios
            try:
                fd = sys.stdin.fileno()
            except:
                quitapp()
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
                except:
                    return
                termios.tcsetattr(fd, termios.TCSADRAIN, self.unixOriginalMode)


def listenForKeys():
    global webSocket, serialConsoleInstance
    getch = _Getch()
    while True:
        c = getch()
        if webSocket:
            if c == b'\x1d':
                c = getch()
                if c == b'n':
                    serialConsoleInstance.sendNMI()
                    continue
                elif c == b'r':
                    serialConsoleInstance.sendReset()
                    continue
                elif c == b's':
                    c = getch()
                    serialConsoleInstance.sendSysRq(c.decode())
                    continue
                elif c == b'q':
                    quitapp()
                    return
                elif c != b'\x1d':
                    continue
            try:
                webSocket.send(c)
            except:
                pass
        else:
            if c == b'\r':
                serialConsoleInstance.connect()
            elif c == b'\x1d':
                c = getch()
                if c == b'q':
                    quitapp()
                    return

class SerialConsole:
    def __init__(self, cmd, resource_group_name, vm_name):
        from azure.cli.core.commands.client_factory import get_subscription_id
        armEndpoint = "https://management.azure.com"
        RP_PROVIDER = "Microsoft.SerialConsole"
        subscriptionId = get_subscription_id(cmd.cli_ctx)
        self.connectionUrl = ("%s/subscriptions/%s/resourcegroups/%s"
                              "/providers/Microsoft.Compute/virtualMachines/%s"
                              "/providers/%s/serialPorts/0"
                              "/connect?api-version=2018-05-01"
                              ) % (armEndpoint, subscriptionId, resource_group_name, vm_name, RP_PROVIDER)
        self.websocketURL = None

    def connect(self):
        def on_open(ws):
            # print("### OPENING ###", end="\r\n")
            pass
        def on_message(ws, message):
            global loading
            loading = False
            print(message, end='', flush=True)
        def on_error(ws, error):
            pass
        def on_close(ws):
            global webSocket, terminatingApp, loading
            loading = False
            if not terminatingApp:
                print("\r\n### Connection Closed: Press Enter to reconnect... ###", end="\r\n")
                webSocket = None
        def connectThread():
            from azure.cli.core._profile import Profile
            global webSocket
            tokenInfo, _, _ = Profile().get_raw_token()
            tokenType = tokenInfo[0]
            accessToken = tokenInfo[1]
            applicationJsonFormat = "application/json"
            serialConsoleUxProdUrl = "https://portal.serialconsole.azure.com"
            headers = {'authorization': tokenType + " " + accessToken,
                       'accept': applicationJsonFormat,
                       'origin': serialConsoleUxProdUrl,
                       'content-type': applicationJsonFormat,
                       'content-length': "0"}
            result = requests.post(self.connectionUrl, headers=headers)
            self.websocketURL = json.loads(result.text)["connectionString"]
            webSocket = websocket.WebSocketApp(self.websocketURL + "?authorization=" + accessToken,
                                               on_open=on_open,
                                               on_message=on_message,
                                               on_error=on_error,
                                               on_close=on_close)
            webSocket.run_forever()
        def loadingMessage():
            dots = 0
            while loading:
                print("### Opening"+"."*(dots+1)+"   ", end="\r", flush=True)
                dots = (dots+1) % 3
                time.sleep(0.5)
        global loading
        loading = True

        th1 = threading.Thread(target=loadingMessage, args=())
        th1.daemon = True
        th1.start()

        th2 = threading.Thread(target=connectThread, args=())
        th2.daemon = True
        th2.start()

    def sendAdminCommand(self, command, commandParameters):
        from azure.cli.core._profile import Profile
        tokenInfo, _, _ = Profile().get_raw_token()
        tokenType = tokenInfo[0]
        accessToken = tokenInfo[1]
        url = self.websocketURL.replace("wss", "https").replace("ws", "http").replace("/client", "/adminCommand/" + command)
        headers = {'accept' : "application/json",
                   'authorization': tokenType + " " + accessToken,
                   'accept-language': "en",
                   'content-type' : "application/json"}
        data = {'command' : command,
                'requestId' : str(uuid.uuid4()),
                'commandParameters' : commandParameters}
        requests.post(url, headers=headers, data=json.dumps(data))
    
    def sendNMI(self):
        self.sendAdminCommand("nmi", {})
    
    def sendReset(self):
        self.sendAdminCommand("reset", {})
    
    def sendSysRq(self, key):
        self.sendAdminCommand("sysrq", {"SysRqCommand" : key})

def connect_serialconsole(cmd, resource_group_name, vm_name):
    global terminalInstance, serialConsoleInstance

    terminalInstance = Terminal()
    terminalInstance.configureTerminal()

    th = threading.Thread(target=listenForKeys, args=())
    th.daemon = True
    th.start()

    serialConsoleInstance = SerialConsole(cmd, resource_group_name, vm_name)
    serialConsoleInstance.connect()

    th.join()
