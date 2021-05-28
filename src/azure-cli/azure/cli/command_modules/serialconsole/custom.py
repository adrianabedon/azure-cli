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


webSocket = None
terminalInstance = None

def quitapp(fromWebsocket = False):
    if terminalInstance:
        terminalInstance.revertTerminal()
    if not fromWebsocket and webSocket:
        webSocket.close()
    quit()

class Terminal:
    def __init__(self):
        self.winOriginalOutMode = None
        self.winOriginalInMode = None
        self.winOut = None
        self.winIn = None
        self.unixOriginalMode = None
        
    def configureTerminal(self):
        import sys
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
            DISABLE = ~(ENABLE_ECHO_INPUT | ENABLE_LINE_INPUT | ENABLE_PROCESSED_INPUT)
        
            kernel32 = ctypes.windll.kernel32
            dwOriginalOutMode = wintypes.DWORD()
            dwOriginalInMode = wintypes.DWORD()
            self.winOut = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            self.winIn = kernel32.GetStdHandle(STD_INPUT_HANDLE)


            if(not kernel32.GetConsoleMode(self.winOut, ctypes.byref(dwOriginalOutMode))):
                quitapp()
            if(not kernel32.GetConsoleMode(self.winIn, ctypes.byref(dwOriginalInMode))):
                quitapp()

            self.winOriginalOutMode = dwOriginalOutMode.value
            self.winOriginalInMode = dwOriginalInMode.value

            dwOutMode = self.winOriginalOutMode | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            dwInMode = (self.winOriginalInMode | ENABLE_VIRTUAL_TERMINAL_INPUT) & DISABLE
            
            if(not kernel32.SetConsoleMode(self.winOut, dwOutMode)):
                quitapp()
            if(not kernel32.SetConsoleMode(self.winIn, dwInMode)):
                quitapp()
        else:
            import sys, tty, termios
            fd = sys.stdin.fileno()
            self.unixOriginalMode = termios.tcgetattr(fd)
            tty.setraw(fd)
    def revertTerminal(self):
        import sys
        if sys.platform.startswith('win'):
            import ctypes
            kernel32 = ctypes.windll.kernel32
            if self.winOriginalOutMode:
                kernel32.SetConsoleMode(self.winOut, self.winOriginalOutMode)
            if self.winOriginalInMode:
                kernel32.SetConsoleMode(self.winIn, self.winOriginalInMode)
        else:
            import sys, termios
            fd = sys.stdin.fileno()
            if self.unixOriginalMode:
                termios.tcsetattr(fd, termios.TCSADRAIN, self.unixOriginalMode)
class _Getch:
    def __init__(self):
        import sys
        if sys.platform.startswith('win'):
            self.impl = _GetchWindows()
        else:
            self.impl = _GetchUnix()
    def __call__(self): return self.impl()

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
        ctypes.windll.kernel32.ReadConsoleW(self.hIn, self.lpBuffer, self.nNumberOfCharsToRead, ctypes.byref(self.lpNumberOfCharsRead), None)
        return chr(self.lpBuffer.raw[0]).encode()

class _GetchUnix:
    def __init__(self):
        pass
    def __call__(self):
        import sys
        return sys.stdin.read(1).encode()

def on_open(ws):
    print("### OPENING ###", end = "\r\n")
    getch = _Getch()

    #listen for user input
    def listenForKeys():
        while(True):
            c = getch()
            if(c == b'\x1d'):
                c = getch()
                if(c == b'\x1d'):
                    ws.send(c)
                else:
                    quitapp()
            try:
                ws.send(c)
            except:
                print("\r\n### CONNECTION CLOSED BY HOST ###")
                quitapp()
    threading.Thread(target=listenForKeys, args=()).start()

def on_message(ws, message):
    print(message, end='', flush=True)

def on_error(ws, error):
    print("### ERROR ###", error)

def on_close(ws):
    if terminalInstance:
        terminalInstance.revertTerminal()
    print("\r\n### CLOSING ###")
    quit()

def connect_serialconsole(cmd, resource_group_name, vm_name):
    from azure.cli.core.commands.client_factory import get_subscription_id
    from azure.cli.core._profile import Profile
    global webSocket, terminalInstance

    armEndpoint = "https://management.azure.com"
    RP_PROVIDER = "Microsoft.SerialConsole"
    subscriptionId=get_subscription_id(cmd.cli_ctx)
    tokenInfo,_,_ = Profile().get_raw_token()
    tokenType = tokenInfo[0]
    accessToken = tokenInfo[1]
    applicationJsonFormat = "application/json"
    serialConsoleUxProdUrl = "https://portal.serialconsole.azure.com"

    connectionUrl = "%s/subscriptions/%s/resourcegroups/%s/providers/Microsoft.Compute/virtualMachines/%s/providers/%s/serialPorts/0/connect?api-version=2018-05-01" % (armEndpoint, subscriptionId, resource_group_name, vm_name, RP_PROVIDER)
    headers = {'authorization' : tokenType + " " + accessToken, 'accept' : applicationJsonFormat, 'origin' : serialConsoleUxProdUrl, 'content-type' : applicationJsonFormat, 'content-length' : "0"}

    terminalInstance = Terminal()
    terminalInstance.configureTerminal()

    result = requests.post(connectionUrl, headers = headers)
    websocketURL = json.loads(result.text)["connectionString"]
    print(websocketURL, end = "\r\n")
    
    webSocket = websocket.WebSocketApp(websocketURL + "?authorization=" + accessToken,
                                on_open = on_open,
                                on_message = on_message,
                                on_error = on_error,
                                on_close = on_close)

    webSocket.run_forever()




    # raise CLIError('TODO: Implement `serialconsole create`')


# def list_serialconsole(cmd, resource_group_name=None):
#     raise CLIError('TODO: Implement `serialconsole list`')


# def update_serialconsole(cmd, instance, tags=None):
#     with cmd.update_context(instance) as c:
#         c.set_param('tags', tags)
#     return instance