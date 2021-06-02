# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
# pylint: disable=line-too-long

from knack.arguments import CLIArgumentType


vm_name_arg_type = CLIArgumentType(options_list=('--vm-name'), metavar='VMNAME', help='Provide the name of the machine')

def load_arguments(self, _):

    from azure.cli.core.commands.parameters import resource_group_name_type
    from azure.cli.core.commands.validators import get_default_location_from_resource_group

    # serialconsole_name_type = CLIArgumentType(options_list='--serialconsole-name-name', help='Name of the Serialconsole.', id_part='name')

    with self.argument_context('serialconsole') as c:
        c.argument('resource_group_name', arg_type = resource_group_name_type)
        c.argument('vm_name', arg_type=vm_name_arg_type)
        # c.argument('subscription', arg_type = subscription_arg_type)
        # c.argument('location', validator=get_default_location_from_resource_group)
        # c.argument('serialconsole_name', serialconsole_name_type, options_list=['--name', '-n'])

    # with self.argument_context('serialconsole list') as c:
    #     # c.argument('serialconsole_name', serialconsole_name_type, id_part=None)
    #     pass
