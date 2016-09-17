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

import mox

from neutronclient.common import exceptions as qe
from neutronclient.neutron import v2_0 as neutronV20
from neutronclient.v2_0 import client as neutronclient

from heat.common import exception
from heat.common import template_format
from heat.engine.clients.os import neutron
from heat.engine.resources.openstack.neutron import net
from heat.engine import rsrc_defn
from heat.engine import scheduler
from heat.tests import common
from heat.tests import utils


neutron_template = '''
heat_template_version: 2015-04-30
description: Template to test network Neutron resource
resources:
  network:
    type: OS::Neutron::Net
    properties:
      name: the_network
      tenant_id: c1210485b2424d48804aad5d39c61b8f
      shared: true
      dhcp_agent_ids:
        - 28c25a04-3f73-45a7-a2b4-59e183943ddc
      port_security_enabled: False
      dns_domain: openstack.org.

  subnet:
    type: OS::Neutron::Subnet
    properties:
      network: { get_resource: network }
      tenant_id: c1210485b2424d48804aad5d39c61b8f
      ip_version: 4
      cidr: 10.0.3.0/24
      allocation_pools:
        - start: 10.0.3.20
          end: 10.0.3.150
      host_routes:
        - destination: 10.0.4.0/24
          nexthop: 10.0.3.20
      dns_nameservers:
        - 8.8.8.8

  router:
    type: OS::Neutron::Router
    properties:
      l3_agent_ids:
        - 792ff887-6c85-4a56-b518-23f24fa65581

  router_interface:
    type: OS::Neutron::RouterInterface
    properties:
      router_id: {get_resource: router}
      subnet: {get_resource : subnet}

  gateway:
    type: OS::Neutron::RouterGateway
    properties:
      router_id: {get_resource: router}
      network: {get_resource : network}
'''


class NeutronNetTest(common.HeatTestCase):

    def setUp(self):
        super(NeutronNetTest, self).setUp()
        self.m.StubOutWithMock(neutronclient.Client, 'create_network')
        self.m.StubOutWithMock(neutronclient.Client, 'delete_network')
        self.m.StubOutWithMock(neutronclient.Client, 'show_network')
        self.m.StubOutWithMock(neutronclient.Client, 'update_network')
        self.m.StubOutWithMock(neutronclient.Client,
                               'add_network_to_dhcp_agent')
        self.m.StubOutWithMock(neutronclient.Client,
                               'remove_network_from_dhcp_agent')
        self.m.StubOutWithMock(neutronclient.Client,
                               'list_dhcp_agent_hosting_networks')
        self.m.StubOutWithMock(neutronV20, 'find_resourceid_by_name_or_id')
        self.patchobject(neutron.NeutronClientPlugin, 'has_extension',
                         return_value=True)

    def create_net(self, t, stack, resource_name):
        resource_defns = stack.t.resource_definitions(stack)
        rsrc = net.Net('test_net', resource_defns[resource_name], stack)
        scheduler.TaskRunner(rsrc.create)()
        self.assertEqual((rsrc.CREATE, rsrc.COMPLETE), rsrc.state)
        return rsrc

    def test_net(self):
        t = template_format.parse(neutron_template)
        stack = utils.parse_stack(t)

        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'router',
            '792ff887-6c85-4a56-b518-23f24fa65581',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('792ff887-6c85-4a56-b518-23f24fa65581')

        # Create script
        neutronclient.Client.create_network({
            'network': {
                'name': u'the_network',
                'admin_state_up': True,
                'tenant_id': 'c1210485b2424d48804aad5d39c61b8f',
                'port_security_enabled': False,
                'dns_domain': 'openstack.org.',
                'shared': True}
        }).AndReturn({"network": {
            "status": "BUILD",
            "subnets": [],
            "name": "name",
            "admin_state_up": True,
            "shared": True,
            "tenant_id": "c1210485b2424d48804aad5d39c61b8f",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766",
            "mtu": 0
        }})

        neutronclient.Client.list_dhcp_agent_hosting_networks(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({"agents": []})

        neutronclient.Client.add_network_to_dhcp_agent(
            '28c25a04-3f73-45a7-a2b4-59e183943ddc',
            {'network_id': u'fc68ea2c-b60b-4b4f-bd82-94ec81110766'}
        ).AndReturn(None)

        neutronclient.Client.show_network(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({"network": {
            "status": "BUILD",
            "subnets": [],
            "name": "name",
            "admin_state_up": True,
            "shared": True,
            "tenant_id": "c1210485b2424d48804aad5d39c61b8f",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766",
            "mtu": 0
        }})

        neutronclient.Client.show_network(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({"network": {
            "status": "ACTIVE",
            "subnets": [],
            "name": "name",
            "admin_state_up": True,
            "shared": True,
            "tenant_id": "c1210485b2424d48804aad5d39c61b8f",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766",
            "mtu": 0
        }})

        neutronclient.Client.show_network(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndRaise(qe.NetworkNotFoundClient(status_code=404))

        neutronclient.Client.show_network(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({"network": {
            "status": "ACTIVE",
            "subnets": [],
            "name": "name",
            "admin_state_up": True,
            "shared": True,
            "tenant_id": "c1210485b2424d48804aad5d39c61b8f",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766",
            "mtu": 0
        }})

        neutronclient.Client.show_network(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({"network": {
            "status": "ACTIVE",
            "subnets": [],
            "name": "name",
            "admin_state_up": True,
            "shared": True,
            "tenant_id": "c1210485b2424d48804aad5d39c61b8f",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766",
            "mtu": 0
        }})

        # Update script
        neutronclient.Client.list_dhcp_agent_hosting_networks(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({
            "agents": [{
                "admin_state_up": True,
                "agent_type": "DHCP agent",
                "alive": True,
                "binary": "neutron-dhcp-agent",
                "configurations": {
                    "dhcp_driver": "DummyDriver",
                    "dhcp_lease_duration": 86400,
                    "networks": 0,
                    "ports": 0,
                    "subnets": 0,
                    "use_namespaces": True},
                "created_at": "2014-03-20 05:12:34",
                "description": None,
                "heartbeat_timestamp": "2014-03-20 05:12:34",
                "host": "hostname",
                "id": "28c25a04-3f73-45a7-a2b4-59e183943ddc",
                "started_at": "2014-03-20 05:12:34",
                "topic": "dhcp_agent"
            }]
        })

        neutronclient.Client.add_network_to_dhcp_agent(
            'bb09cfcd-5277-473d-8336-d4ed8628ae68',
            {'network_id': u'fc68ea2c-b60b-4b4f-bd82-94ec81110766'}
        ).AndReturn(None)

        neutronclient.Client.remove_network_from_dhcp_agent(
            '28c25a04-3f73-45a7-a2b4-59e183943ddc',
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn(None)

        # Update script
        neutronclient.Client.update_network(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766',
            {'network': {
                'name': 'mynet',
                'qos_policy_id': '0389f747-7785-4757-b7bb-2ab07e4b09c3'
            }}).AndReturn(None)
        # update again to detach qos_policy
        neutronclient.Client.update_network(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766',
            {'network': {
                'name': 'mynet',
                'qos_policy_id': None
            }}).AndReturn(None)

        neutronclient.Client.update_network(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766',
            {'network': {
                'name': 'mynet',
                'port_security_enabled': True,
                'qos_policy_id': None
            }}).AndReturn(None)

        # update with name = None
        neutronclient.Client.update_network(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766',
            {'network': {
                'name': utils.PhysName(stack.name, 'test_net'),
            }}).AndReturn(None)

        # Delete script
        neutronclient.Client.delete_network(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn(None)

        neutronclient.Client.show_network(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndRaise(qe.NetworkNotFoundClient(status_code=404))

        neutronclient.Client.delete_network(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndRaise(qe.NetworkNotFoundClient(status_code=404))

        self.patchobject(neutron.NeutronClientPlugin, 'get_qos_policy_id',
                         return_value='0389f747-7785-4757-b7bb-2ab07e4b09c3')

        self.m.ReplayAll()
        self.patchobject(stack['router'], 'FnGetRefId',
                         return_value='792ff887-6c85-4a56-b518-23f24fa65581')

        rsrc = self.create_net(t, stack, 'network')

        # assert the implicit dependency between the gateway and the interface
        deps = stack.dependencies[stack['router_interface']]
        self.assertIn(stack['gateway'], deps)

        # assert the implicit dependency between the gateway and the subnet
        deps = stack.dependencies[stack['subnet']]
        self.assertIn(stack['gateway'], deps)

        rsrc.validate()

        ref_id = rsrc.FnGetRefId()
        self.assertEqual('fc68ea2c-b60b-4b4f-bd82-94ec81110766', ref_id)

        self.assertIsNone(rsrc.FnGetAtt('status'))
        self.assertEqual('ACTIVE', rsrc.FnGetAtt('status'))
        self.assertEqual(0, rsrc.FnGetAtt('mtu'))
        self.assertRaises(
            exception.InvalidTemplateAttribute, rsrc.FnGetAtt, 'Foo')
        prop_diff = {
            "name": "mynet",
            "dhcp_agent_ids": [
                "bb09cfcd-5277-473d-8336-d4ed8628ae68"
            ],
            'qos_policy': '0389f747-7785-4757-b7bb-2ab07e4b09c3'
        }
        update_snippet = rsrc_defn.ResourceDefinition(rsrc.name, rsrc.type(),
                                                      prop_diff)
        rsrc.handle_update(update_snippet, {}, prop_diff)

        # Update with None qos_policy
        prop_diff['qos_policy'] = None
        rsrc.handle_update(update_snippet, {}, prop_diff)

        # Update with value_specs
        prop_diff['value_specs'] = {"port_security_enabled": True}
        rsrc.handle_update(update_snippet, {}, prop_diff)

        # Update with name = None
        rsrc.handle_update(update_snippet, {}, {'name': None})

        # Update with empty prop_diff
        rsrc.handle_update(update_snippet, {}, {})

        scheduler.TaskRunner(rsrc.delete)()
        rsrc.state_set(rsrc.CREATE, rsrc.COMPLETE, 'to delete again')
        scheduler.TaskRunner(rsrc.delete)()
        self.m.VerifyAll()
