# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

# pylint: disable=line-too-long
from azure.cli.core.commands import CliCommandType
from azure.cli.command_modules.serialconsole._client_factory import cf_serialconsole


def load_command_table(self, _):

    # TODO: Add command type here
    # serialconsole_sdk = CliCommandType(
    #    operations_tmpl='<PATH>.operations#.{}',
    #    client_factory=cf_serialconsole)


    with self.command_group('serialconsole') as g:
        g.custom_command('connect', 'connect_serialconsole')
        # g.custom_command('list', 'list_serialconsole')
        # g.show_command('show', 'get')
        # g.generic_update_command('update', setter_name='update', custom_func_name='update_serialconsole')


    with self.command_group('serialconsole', is_preview=True):
        pass

