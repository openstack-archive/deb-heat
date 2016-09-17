#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import json

from heat_integrationtests.common import exceptions
from heat_integrationtests.scenario import scenario_base


class ServerSignalIntegrationTest(scenario_base.ScenarioTestsBase):
    """Test a server in a created network can signal to heat."""

    def test_server_signal(self):
        """Check a server in a created network can signal to heat."""
        parameters = {
            'key_name': self.keypair_name,
            'flavor': self.conf.instance_type,
            'image': self.conf.image_ref,
            'timeout': self.conf.build_timeout,
        }

        # Launch stack
        sid = self.launch_stack(
            template_name="test_server_signal.yaml",
            parameters=parameters,
            expected_status=None
        )

        # Check status of all resources
        for res in ('sg', 'floating_ip', 'network', 'router', 'subnet',
                    'router_interface', 'wait_handle', 'server',
                    'server_floating_ip_assoc'):
            self._wait_for_resource_status(
                sid, res, 'CREATE_COMPLETE')

        server_resource = self.client.resources.get(sid, 'server')
        server_id = server_resource.physical_resource_id
        server = self.compute_client.servers.get(server_id)

        try:
            self._wait_for_resource_status(
                sid, 'wait_condition', 'CREATE_COMPLETE')
        except (exceptions.StackResourceBuildErrorException,
                exceptions.TimeoutException):
            raise
        finally:
            # attempt to log the server console regardless of WaitCondition
            # going to complete. This allows successful and failed cloud-init
            # logs to be compared
            self._log_console_output(servers=[server])

        stack = self.client.stacks.get(sid)

        wc_data = json.loads(
            self._stack_output(stack, 'wc_data'))
        self.assertEqual({'1': 'test complete'}, wc_data)

        server_ip = self._stack_output(stack, 'server_ip')

        # Check that created server is reachable
        if not self._ping_ip_address(server_ip):
            self._log_console_output(servers=[server])
            self.fail(
                "Timed out waiting for %s to become reachable" % server_ip)
