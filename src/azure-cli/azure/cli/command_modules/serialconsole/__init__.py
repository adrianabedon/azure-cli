# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# test
# --------------------------------------------------------------------------------------------

from azure.cli.core import AzCommandsLoader

from azure.cli.command_modules.serialconsole._help import helps  # pylint: disable=unused-import


class SerialconsoleCommandsLoader(AzCommandsLoader):

    def __init__(self, cli_ctx=None):
        from azure.cli.core.commands import CliCommandType
        from azure.cli.command_modules.serialconsole._client_factory import cf_serialconsole
        serialconsole_custom = CliCommandType(
            operations_tmpl='azure.cli.command_modules.serialconsole.custom#{}',
            client_factory=cf_serialconsole)
        super(SerialconsoleCommandsLoader, self).__init__(cli_ctx=cli_ctx,
                                                  custom_command_type=serialconsole_custom)

    def load_command_table(self, args):
        from azure.cli.command_modules.serialconsole.commands import load_command_table
        load_command_table(self, args)
        return self.command_table

    def load_arguments(self, command):
        from azure.cli.command_modules.serialconsole._params import load_arguments
        load_arguments(self, command)


COMMAND_LOADER_CLS = SerialconsoleCommandsLoader
