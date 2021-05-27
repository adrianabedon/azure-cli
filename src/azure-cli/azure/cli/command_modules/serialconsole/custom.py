# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from knack.util import CLIError
import requests
import json
import websocket
import threading
import subprocess


def on_open(ws):
    print("### OPENING ###")
    import ctypes
    from ctypes import wintypes 

    #intialize variables to get characters from memory
    kernel32 = ctypes.windll.kernel32
    STD_INPUT_HANDLE = -10
    hIn = kernel32.GetStdHandle(STD_INPUT_HANDLE)
    lpBuffer = ctypes.create_string_buffer(1)
    lpNumberOfCharsRead = wintypes.DWORD()
    nNumberOfCharsToRead = wintypes.DWORD()
    nNumberOfCharsToRead.value = 1

    #listen for user input
    def listenForKeys():
        while(True):
            r = kernel32.ReadConsoleW(hIn, lpBuffer, nNumberOfCharsToRead, ctypes.byref(lpNumberOfCharsRead), None)
            if(lpBuffer.raw == b'\x1d'):
                r2 = kernel32.ReadConsoleW(hIn, lpBuffer, nNumberOfCharsToRead, ctypes.byref(lpNumberOfCharsRead), None)
                if(lpBuffer.raw == b'\x1d'):
                    ws.send(lpBuffer.raw)
                else:
                    print("\n### CLOSING1 ###")
                    ws.close()
                    break
            try:
                ws.send(lpBuffer.raw)
            except:
                print("\n### CONNECTION CLOSED BY HOST ###")
                quit()
    threading.Thread(target=listenForKeys, args=()).start()

def on_message(ws, message):
    print(message, end='', flush=True)

def on_error(ws, error):
    print("### ERROR ###", error)

def on_close(ws):
    print("### CLOSING2 ###")

def enableVirtualTerminal():
    import ctypes
    from ctypes import wintypes 
    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
    ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200

    ENABLE_ECHO_INPUT = 0x0004
    ENABLE_LINE_INPUT = 0x0002
    ENABLE_PROCESSED_INPUT = 0x0001

    disable = ~(ENABLE_ECHO_INPUT | ENABLE_LINE_INPUT | ENABLE_PROCESSED_INPUT)
    
    STD_OUTPUT_HANDLE = -11
    STD_INPUT_HANDLE = -10
    kernel32 = ctypes.windll.kernel32
    hOut = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
    hIn = kernel32.GetStdHandle(STD_INPUT_HANDLE)
    dwOriginalOutMode = wintypes.DWORD()
    kernel32.GetConsoleMode(hOut, ctypes.byref(dwOriginalOutMode))
    dwOriginalInMode = wintypes.DWORD()
    kernel32.GetConsoleMode(hIn, ctypes.byref(dwOriginalInMode))
    dwOutMode = dwOriginalOutMode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
    dwInMode = (dwOriginalInMode.value | ENABLE_VIRTUAL_TERMINAL_INPUT) & disable
    kernel32.SetConsoleMode(hOut, dwOutMode)
    kernel32.SetConsoleMode(hIn, dwInMode)

def connect_serialconsole(cmd, resource_group_name, vm_name):
    from azure.cli.core.commands.client_factory import get_subscription_id
    from msrestazure.tools import is_valid_resource_id, resource_id
    from azure.cli.core._profile import Profile
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

    enableVirtualTerminal()

    result = requests.post(connectionUrl, headers = headers)
    websocketURL = json.loads(result.text)["connectionString"]
    print(websocketURL)
    
    ws = websocket.WebSocketApp(websocketURL + "?authorization=" + accessToken,
                                on_open = on_open,
                                on_message = on_message,
                                on_error = on_error,
                                on_close = on_close)

    ws.run_forever()




    # raise CLIError('TODO: Implement `serialconsole create`')


# def list_serialconsole(cmd, resource_group_name=None):
#     raise CLIError('TODO: Implement `serialconsole list`')


# def update_serialconsole(cmd, instance, tags=None):
#     with cmd.update_context(instance) as c:
#         c.set_param('tags', tags)
#     return instance