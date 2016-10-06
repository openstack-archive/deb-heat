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

import copy
import mock
import mox
from neutronclient.common import exceptions as qe
from neutronclient.neutron import v2_0 as neutronV20
from neutronclient.v2_0 import client as neutronclient
from oslo_serialization import jsonutils
import six

from heat.common import exception
from heat.common import template_format
from heat.engine import resource
from heat.engine import rsrc_defn
from heat.engine import scheduler
from heat.tests import common
from heat.tests import utils


neutron_port_template = '''
heat_template_version: 2015-04-30
description: Template to test port Neutron resource
resources:
  port:
    type: OS::Neutron::Port
    properties:
      network: net1234
      fixed_ips:
        - subnet: sub1234
          ip_address: 10.0.3.21
      device_owner: network:dhcp
'''


neutron_port_with_address_pair_template = '''
heat_template_version: 2015-04-30
description: Template to test port Neutron resource
resources:
  port:
    type: OS::Neutron::Port
    properties:
      network: abcd1234
      allowed_address_pairs:
        - ip_address: 10.0.3.21
          mac_address: 00-B0-D0-86-BB-F7
'''


neutron_port_security_template = '''
heat_template_version: 2015-04-30
description: Template to test port Neutron resource
resources:
  port:
    type: OS::Neutron::Port
    properties:
      network: abcd1234
      port_security_enabled: False
'''


class NeutronPortTest(common.HeatTestCase):

    def setUp(self):
        super(NeutronPortTest, self).setUp()
        self.m.StubOutWithMock(neutronclient.Client, 'create_port')
        self.m.StubOutWithMock(neutronclient.Client, 'show_port')
        self.m.StubOutWithMock(neutronclient.Client, 'update_port')
        self.m.StubOutWithMock(neutronclient.Client, 'show_subnet')
        self.m.StubOutWithMock(neutronV20, 'find_resourceid_by_name_or_id')

    def test_missing_subnet_id(self):
        t = template_format.parse(neutron_port_template)
        t['resources']['port']['properties']['fixed_ips'][0].pop('subnet')
        stack = utils.parse_stack(t)

        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'net1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('net1234')
        neutronclient.Client.create_port({'port': {
            'network_id': u'net1234',
            'fixed_ips': [
                {'ip_address': u'10.0.3.21'}
            ],
            'name': utils.PhysName(stack.name, 'port'),
            'admin_state_up': True,
            'device_owner': u'network:dhcp'}}
        ).AndReturn({'port': {
            "status": "BUILD",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})
        neutronclient.Client.show_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({'port': {
            "status": "ACTIVE",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})

        self.m.ReplayAll()

        port = stack['port']
        scheduler.TaskRunner(port.create)()

        self.m.VerifyAll()

    def test_missing_ip_address(self):
        t = template_format.parse(neutron_port_template)
        t['resources']['port']['properties']['fixed_ips'][0].pop('ip_address')
        stack = utils.parse_stack(t)

        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'net1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('net1234')
        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'subnet',
            'sub1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('sub1234')

        neutronclient.Client.create_port({'port': {
            'network_id': u'net1234',
            'fixed_ips': [
                {'subnet_id': u'sub1234'}
            ],
            'name': utils.PhysName(stack.name, 'port'),
            'admin_state_up': True,
            'device_owner': u'network:dhcp'}}
        ).AndReturn({'port': {
            "status": "BUILD",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})
        neutronclient.Client.show_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({'port': {
            "status": "ACTIVE",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})

        self.m.ReplayAll()

        port = stack['port']
        scheduler.TaskRunner(port.create)()
        self.m.VerifyAll()

    def test_missing_fixed_ips(self):
        t = template_format.parse(neutron_port_template)
        t['resources']['port']['properties'].pop('fixed_ips')
        stack = utils.parse_stack(t)

        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'net1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('net1234')
        neutronclient.Client.create_port({'port': {
            'network_id': u'net1234',
            'name': utils.PhysName(stack.name, 'port'),
            'admin_state_up': True,
            'device_owner': u'network:dhcp'}}
        ).AndReturn({'port': {
            "status": "BUILD",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})
        neutronclient.Client.show_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({'port': {
            "status": "ACTIVE",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766",
            "fixed_ips": {
                "subnet_id": "d0e971a6-a6b4-4f4c-8c88-b75e9c120b7e",
                "ip_address": "10.0.0.2"
            }
        }})

        self.m.ReplayAll()

        port = stack['port']
        scheduler.TaskRunner(port.create)()
        self.m.VerifyAll()

    def test_allowed_address_pair(self):
        t = template_format.parse(neutron_port_with_address_pair_template)
        stack = utils.parse_stack(t)

        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'abcd1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('abcd1234')
        neutronclient.Client.create_port({'port': {
            'network_id': u'abcd1234',
            'allowed_address_pairs': [{
                'ip_address': u'10.0.3.21',
                'mac_address': u'00-B0-D0-86-BB-F7'
            }],
            'name': utils.PhysName(stack.name, 'port'),
            'admin_state_up': True}}
        ).AndReturn({'port': {
            "status": "BUILD",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})
        neutronclient.Client.show_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({'port': {
            "status": "ACTIVE",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})

        self.m.ReplayAll()

        port = stack['port']
        scheduler.TaskRunner(port.create)()
        self.m.VerifyAll()

    def test_port_security_enabled(self):
        t = template_format.parse(neutron_port_security_template)
        stack = utils.parse_stack(t)

        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'abcd1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('abcd1234')

        neutronclient.Client.create_port({'port': {
            'network_id': u'abcd1234',
            'port_security_enabled': False,
            'name': utils.PhysName(stack.name, 'port'),
            'admin_state_up': True}}
        ).AndReturn({'port': {
            "status": "BUILD",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})

        neutronclient.Client.show_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({'port': {
            "status": "ACTIVE",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766",
        }})

        self.m.ReplayAll()

        port = stack['port']
        scheduler.TaskRunner(port.create)()
        self.m.VerifyAll()

    def test_missing_mac_address(self):
        t = template_format.parse(neutron_port_with_address_pair_template)
        t['resources']['port']['properties']['allowed_address_pairs'][0].pop(
            'mac_address'
        )
        stack = utils.parse_stack(t)

        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'abcd1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('abcd1234')
        neutronclient.Client.create_port({'port': {
            'network_id': u'abcd1234',
            'allowed_address_pairs': [{
                'ip_address': u'10.0.3.21',
            }],
            'name': utils.PhysName(stack.name, 'port'),
            'admin_state_up': True}}
        ).AndReturn({'port': {
            "status": "BUILD",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})
        neutronclient.Client.show_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({'port': {
            "status": "ACTIVE",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})

        self.m.ReplayAll()

        port = stack['port']
        scheduler.TaskRunner(port.create)()
        self.m.VerifyAll()

    def test_ip_address_is_cidr(self):
        t = template_format.parse(neutron_port_with_address_pair_template)
        t['resources']['port']['properties'][
            'allowed_address_pairs'][0]['ip_address'] = '10.0.3.0/24'
        stack = utils.parse_stack(t)

        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'abcd1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('abcd1234')
        neutronclient.Client.create_port({'port': {
            'network_id': u'abcd1234',
            'allowed_address_pairs': [{
                'ip_address': u'10.0.3.0/24',
                'mac_address': u'00-B0-D0-86-BB-F7'
            }],
            'name': utils.PhysName(stack.name, 'port'),
            'admin_state_up': True}}
        ).AndReturn({'port': {
            "status": "BUILD",
            "id": "2e00180a-ff9d-42c4-b701-a0606b243447"
        }})
        neutronclient.Client.show_port(
            '2e00180a-ff9d-42c4-b701-a0606b243447'
        ).AndReturn({'port': {
            "status": "ACTIVE",
            "id": "2e00180a-ff9d-42c4-b701-a0606b243447"
        }})

        self.m.ReplayAll()

        port = stack['port']
        scheduler.TaskRunner(port.create)()
        self.m.VerifyAll()

    def _mock_create_with_props(self, port_prop):
        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'net1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('net1234')
        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'subnet',
            'sub1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('sub1234')
        neutronclient.Client.create_port({'port': port_prop}).AndReturn(
            {'port': {
                "status": "BUILD",
                "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"}})
        neutronclient.Client.show_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).MultipleTimes().AndReturn({'port': {
            "status": "ACTIVE",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766",
            "dns_assignment": {
                "hostname": "my-vm",
                "ip_address": "10.0.0.15",
                "fqdn": "my-vm.openstack.org."}

        }})

        self.m.ReplayAll()

    def test_security_groups(self):
        t = template_format.parse(neutron_port_template)
        t['resources']['port']['properties']['security_groups'] = [
            '8a2f582a-e1cd-480f-b85d-b02631c10656',
            '024613dc-b489-4478-b46f-ada462738740']
        stack = utils.parse_stack(t)

        port_prop = {
            'network_id': u'net1234',
            'security_groups': ['8a2f582a-e1cd-480f-b85d-b02631c10656',
                                '024613dc-b489-4478-b46f-ada462738740'],
            'fixed_ips': [
                {'subnet_id': u'sub1234', 'ip_address': u'10.0.3.21'}
            ],
            'name': utils.PhysName(stack.name, 'port'),
            'admin_state_up': True,
            'device_owner': u'network:dhcp'}

        self._mock_create_with_props(port_prop)

        port = stack['port']
        scheduler.TaskRunner(port.create)()

        self.m.VerifyAll()

    def test_port_with_dns_name(self):
        t = template_format.parse(neutron_port_template)
        t['resources']['port']['properties']['dns_name'] = 'myvm'
        stack = utils.parse_stack(t)

        port_prop = {
            'network_id': u'net1234',
            'dns_name': 'myvm',
            'fixed_ips': [
                {'subnet_id': u'sub1234', 'ip_address': u'10.0.3.21'}
            ],
            'name': utils.PhysName(stack.name, 'port'),
            'admin_state_up': True,
            'device_owner': u'network:dhcp'}

        self._mock_create_with_props(port_prop)
        port = stack['port']
        scheduler.TaskRunner(port.create)()
        self.assertEqual('my-vm.openstack.org.',
                         port.FnGetAtt('dns_assignment')['fqdn'])
        self.m.VerifyAll()

    def test_security_groups_empty_list(self):
        t = template_format.parse(neutron_port_template)
        t['resources']['port']['properties']['security_groups'] = []
        stack = utils.parse_stack(t)

        port_prop = {
            'network_id': u'net1234',
            'security_groups': [],
            'fixed_ips': [
                {'subnet_id': u'sub1234', 'ip_address': u'10.0.3.21'}
            ],
            'name': utils.PhysName(stack.name, 'port'),
            'admin_state_up': True,
            'device_owner': u'network:dhcp'
        }

        self._mock_create_with_props(port_prop)

        port = stack['port']
        scheduler.TaskRunner(port.create)()

        self.m.VerifyAll()

    def test_port_needs_update(self):
        t = template_format.parse(neutron_port_template)
        t['resources']['port']['properties'].pop('fixed_ips')
        stack = utils.parse_stack(t)

        props = {'network_id': u'net1234',
                 'name': utils.PhysName(stack.name, 'port'),
                 'admin_state_up': True,
                 'device_owner': u'network:dhcp'}

        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'net1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('net1234')
        neutronclient.Client.create_port(
            {'port': props}
        ).AndReturn({'port': {
            "status": "BUILD",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})
        neutronclient.Client.show_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({'port': {
            "status": "ACTIVE",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766",
            "fixed_ips": {
                "subnet_id": "d0e971a6-a6b4-4f4c-8c88-b75e9c120b7e",
                "ip_address": "10.0.0.2"
            }
        }})

        self.m.ReplayAll()

        # create port
        port = stack['port']
        scheduler.TaskRunner(port.create)()

        new_props = props.copy()

        # test always replace
        new_props['replacement_policy'] = 'REPLACE_ALWAYS'
        new_props['network'] = new_props.pop('network_id')
        update_snippet = rsrc_defn.ResourceDefinition(port.name, port.type(),
                                                      new_props)
        self.assertRaises(resource.UpdateReplace, port._needs_update,
                          update_snippet, port.frozen_definition(),
                          new_props, port.properties, None)

        # test deferring to Resource._needs_update
        new_props['replacement_policy'] = 'AUTO'
        update_snippet = rsrc_defn.ResourceDefinition(port.name, port.type(),
                                                      new_props)
        self.assertTrue(port._needs_update(update_snippet,
                                           port.frozen_definition(),
                                           new_props, port.properties, None))

        self.m.VerifyAll()

    def test_port_needs_update_network(self):
        props = {'network_id': u'net1234',
                 'name': 'test_port',
                 'admin_state_up': True,
                 'device_owner': u'network:dhcp'}
        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'net1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('net1234')

        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'old_network',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('net1234')
        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'new_network',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('net5678')

        create_props = props.copy()
        neutronclient.Client.create_port(
            {'port': create_props}
        ).AndReturn({'port': {
            "status": "BUILD",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})
        neutronclient.Client.show_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({'port': {
            "status": "ACTIVE",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766",
            "fixed_ips": {
                "subnet_id": "d0e971a6-a6b4-4f4c-8c88-b75e9c120b7e",
                "ip_address": "10.0.0.2"
            }
        }})
        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'net5678',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('net5678')

        call_dict = copy.deepcopy(props)
        call_dict['security_groups'] = [
            '0389f747-7785-4757-b7bb-2ab07e4b09c3']
        del call_dict['network_id']

        neutronclient.Client.show_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({'port': {
            "status": "ACTIVE",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})

        neutronclient.Client.show_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).AndReturn({'port': {
            "status": "ACTIVE",
            "id": "fc68ea2c-b60b-4b4f-bd82-94ec81110766"
        }})

        neutronclient.Client.update_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766',
            {'port': {'fixed_ips': []}}
        ).AndReturn(None)

        self.m.ReplayAll()

        # create port
        t = template_format.parse(neutron_port_template)
        t['resources']['port']['properties'].pop('fixed_ips')
        t['resources']['port']['properties']['name'] = 'test_port'
        stack = utils.parse_stack(t)

        port = stack['port']
        scheduler.TaskRunner(port.create)()

        # Switch from network_id=ID to network=ID (no replace)
        new_props = props.copy()
        new_props['network'] = new_props.pop('network_id')
        update_snippet = rsrc_defn.ResourceDefinition(port.name, port.type(),
                                                      new_props)
        scheduler.TaskRunner(port.update, update_snippet)()
        self.assertEqual((port.UPDATE, port.COMPLETE), port.state)

        # Switch from network=ID to network=NAME (no replace)
        new_props['network'] = 'old_network'
        update_snippet = rsrc_defn.ResourceDefinition(port.name, port.type(),
                                                      new_props)

        scheduler.TaskRunner(port.update, update_snippet)()
        self.assertEqual((port.UPDATE, port.COMPLETE), port.state)

        # Switch to a different network (replace)
        new_props['network'] = 'new_network'
        update_snippet = rsrc_defn.ResourceDefinition(port.name, port.type(),
                                                      new_props)
        updater = scheduler.TaskRunner(port.update, update_snippet)
        self.assertRaises(resource.UpdateReplace, updater)

        self.m.VerifyAll()

    def test_get_port_attributes(self):
        t = template_format.parse(neutron_port_template)
        t['resources']['port']['properties'].pop('fixed_ips')
        stack = utils.parse_stack(t)

        subnet_dict = {'name': 'test-subnet', 'enable_dhcp': True,
                       'network_id': 'net1234', 'dns_nameservers': [],
                       'tenant_id': '58a61fc3992944ce971404a2ece6ff98',
                       'ipv6_ra_mode': None, 'cidr': '10.0.0.0/24',
                       'allocation_pools': [{'start': '10.0.0.2',
                                             'end': u'10.0.0.254'}],
                       'gateway_ip': '10.0.0.1', 'ipv6_address_mode': None,
                       'ip_version': 4, 'host_routes': [],
                       'id': '6dd609ad-d52a-4587-b1a0-b335f76062a5'}
        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'net1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('net1234')
        neutronclient.Client.create_port({'port': {
            'network_id': u'net1234',
            'name': utils.PhysName(stack.name, 'port'),
            'admin_state_up': True,
            'device_owner': u'network:dhcp'}}
        ).AndReturn({'port': {
            'status': 'BUILD',
            'id': 'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        }})
        neutronclient.Client.show_subnet(
            'd0e971a6-a6b4-4f4c-8c88-b75e9c120b7e'
        ).AndReturn({'subnet': subnet_dict})
        neutronclient.Client.show_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).MultipleTimes().AndReturn({'port': {
            'status': 'DOWN',
            'name': utils.PhysName(stack.name, 'port'),
            'allowed_address_pairs': [],
            'admin_state_up': True,
            'network_id': 'net1234',
            'device_id': 'dc68eg2c-b60g-4b3f-bd82-67ec87650532',
            'mac_address': 'fa:16:3e:75:67:60',
            'tenant_id': '58a61fc3992944ce971404a2ece6ff98',
            'security_groups': ['5b15d80c-6b70-4a1c-89c9-253538c5ade6'],
            'fixed_ips': [{'subnet_id': 'd0e971a6-a6b4-4f4c-8c88-b75e9c120b7e',
                           'ip_address': '10.0.0.2'}]
        }})
        self.m.ReplayAll()

        port = stack['port']
        scheduler.TaskRunner(port.create)()
        self.assertEqual('DOWN', port.FnGetAtt('status'))
        self.assertEqual([], port.FnGetAtt('allowed_address_pairs'))
        self.assertTrue(port.FnGetAtt('admin_state_up'))
        self.assertEqual('net1234', port.FnGetAtt('network_id'))
        self.assertEqual('fa:16:3e:75:67:60', port.FnGetAtt('mac_address'))
        self.assertEqual(utils.PhysName(stack.name, 'port'),
                         port.FnGetAtt('name'))
        self.assertEqual('dc68eg2c-b60g-4b3f-bd82-67ec87650532',
                         port.FnGetAtt('device_id'))
        self.assertEqual('58a61fc3992944ce971404a2ece6ff98',
                         port.FnGetAtt('tenant_id'))
        self.assertEqual(['5b15d80c-6b70-4a1c-89c9-253538c5ade6'],
                         port.FnGetAtt('security_groups'))
        self.assertEqual([{'subnet_id': 'd0e971a6-a6b4-4f4c-8c88-b75e9c120b7e',
                           'ip_address': '10.0.0.2'}],
                         port.FnGetAtt('fixed_ips'))
        self.assertEqual([subnet_dict], port.FnGetAtt('subnets'))
        self.assertRaises(exception.InvalidTemplateAttribute,
                          port.FnGetAtt, 'Foo')
        self.m.VerifyAll()

    def test_subnet_attribute_exception(self):
        t = template_format.parse(neutron_port_template)
        t['resources']['port']['properties'].pop('fixed_ips')
        stack = utils.parse_stack(t)

        neutronV20.find_resourceid_by_name_or_id(
            mox.IsA(neutronclient.Client),
            'network',
            'net1234',
            cmd_resource=None,
        ).MultipleTimes().AndReturn('net1234')
        neutronclient.Client.create_port({'port': {
            'network_id': u'net1234',
            'name': utils.PhysName(stack.name, 'port'),
            'admin_state_up': True,
            'device_owner': u'network:dhcp'}}
        ).AndReturn({'port': {
            'status': 'BUILD',
            'id': 'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        }})
        neutronclient.Client.show_port(
            'fc68ea2c-b60b-4b4f-bd82-94ec81110766'
        ).MultipleTimes().AndReturn({'port': {
            'status': 'DOWN',
            'name': utils.PhysName(stack.name, 'port'),
            'allowed_address_pairs': [],
            'admin_state_up': True,
            'network_id': 'net1234',
            'device_id': 'dc68eg2c-b60g-4b3f-bd82-67ec87650532',
            'mac_address': 'fa:16:3e:75:67:60',
            'tenant_id': '58a61fc3992944ce971404a2ece6ff98',
            'security_groups': ['5b15d80c-6b70-4a1c-89c9-253538c5ade6'],
            'fixed_ips': [{'subnet_id': 'd0e971a6-a6b4-4f4c-8c88-b75e9c120b7e',
                           'ip_address': '10.0.0.2'}]
        }})
        neutronclient.Client.show_subnet(
            'd0e971a6-a6b4-4f4c-8c88-b75e9c120b7e'
        ).AndRaise(qe.NeutronClientException('ConnectionFailed: Connection '
                                             'to neutron failed: Maximum '
                                             'attempts reached'))
        self.m.ReplayAll()

        port = stack['port']
        scheduler.TaskRunner(port.create)()
        self.assertIsNone(port.FnGetAtt('subnets'))
        log_msg = ('Failed to fetch resource attributes: ConnectionFailed: '
                   'Connection to neutron failed: Maximum attempts reached')
        self.assertIn(log_msg, self.LOG.output)
        self.m.VerifyAll()

    def test_prepare_for_replace_port_not_created(self):
        t = template_format.parse(neutron_port_template)
        stack = utils.parse_stack(t)
        port = stack['port']
        port._show_resource = mock.Mock()
        port.data_set = mock.Mock()
        n_client = mock.Mock()
        port.client = mock.Mock(return_value=n_client)

        self.assertIsNone(port.resource_id)

        # execute prepare_for_replace
        port.prepare_for_replace()

        # check, if the port is not created, do nothing in
        # prepare_for_replace()
        self.assertFalse(port._show_resource.called)
        self.assertFalse(port.data_set.called)
        self.assertFalse(n_client.update_port.called)

    def test_prepare_for_replace_port(self):
        t = template_format.parse(neutron_port_template)
        stack = utils.parse_stack(t)
        port = stack['port']
        port.resource_id = 'test_res_id'
        _value = {
            'fixed_ips': {
                'subnet_id': 'test_subnet',
                'ip_address': '42.42.42.42'
            }
        }
        port._show_resource = mock.Mock(return_value=_value)
        port.data_set = mock.Mock()
        n_client = mock.Mock()
        port.client = mock.Mock(return_value=n_client)

        # execute prepare_for_replace
        port.prepare_for_replace()

        # check, that data was stored
        port.data_set.assert_called_once_with(
            'port_fip', jsonutils.dumps(_value.get('fixed_ips')))

        # check, that port was updated and ip was removed
        expected_props = {'port': {'fixed_ips': []}}
        n_client.update_port.assert_called_once_with('test_res_id',
                                                     expected_props)

    def test_restore_prev_rsrc(self):
        t = template_format.parse(neutron_port_template)
        stack = utils.parse_stack(t)
        new_port = stack['port']
        new_port.resource_id = 'new_res_id'
        # mock backup stack to return only one mocked old_port
        old_port = mock.Mock()
        new_port.stack._backup_stack = mock.Mock()
        new_port.stack._backup_stack().resources.get.return_value = old_port
        old_port.resource_id = 'old_res_id'
        _value = {
            'subnet_id': 'test_subnet',
            'ip_address': '42.42.42.42'
        }
        old_port.data = mock.Mock(
            return_value={'port_fip': jsonutils.dumps(_value)})

        n_client = mock.Mock()
        new_port.client = mock.Mock(return_value=n_client)

        # execute restore_prev_rsrc
        new_port.restore_prev_rsrc()

        # check, that ports were updated: old port get ip and
        # same ip was removed from old port
        expected_new_props = {'port': {'fixed_ips': []}}
        expected_old_props = {'port': {'fixed_ips': _value}}
        n_client.update_port.assert_has_calls([
            mock.call('new_res_id', expected_new_props),
            mock.call('old_res_id', expected_old_props)])

    def test_restore_prev_rsrc_convergence(self):
        t = template_format.parse(neutron_port_template)
        stack = utils.parse_stack(t)
        stack.store()

        # mock resource from previous template
        prev_rsrc = stack['port']
        prev_rsrc.resource_id = 'prev-rsrc'
        # store in db
        prev_rsrc.state_set(prev_rsrc.UPDATE, prev_rsrc.COMPLETE)

        # mock resource from existing template and store in db
        existing_rsrc = stack['port']
        existing_rsrc.current_template_id = stack.t.id
        existing_rsrc.resource_id = 'existing-rsrc'
        existing_rsrc.state_set(existing_rsrc.UPDATE, existing_rsrc.COMPLETE)

        # mock previous resource was replaced by existing resource
        prev_rsrc.replaced_by = existing_rsrc.id
        _value = {
            'subnet_id': 'test_subnet',
            'ip_address': '42.42.42.42'
        }
        prev_rsrc._data = {'port_fip': jsonutils.dumps(_value)}

        n_client = mock.Mock()
        prev_rsrc.client = mock.Mock(return_value=n_client)

        # execute restore_prev_rsrc
        prev_rsrc.restore_prev_rsrc(convergence=True)

        expected_existing_props = {'port': {'fixed_ips': []}}
        expected_prev_props = {'port': {'fixed_ips': _value}}
        n_client.update_port.assert_has_calls([
            mock.call(existing_rsrc.resource_id, expected_existing_props),
            mock.call(prev_rsrc.resource_id, expected_prev_props)])


class UpdatePortTest(common.HeatTestCase):
    scenarios = [
        ('with_secgrp', dict(secgrp=['8a2f582a-e1cd-480f-b85d-b02631c10656'],
                             name='test',
                             value_specs={},
                             fixed_ips=None,
                             addr_pair=None,
                             vnic_type=None)),
        ('with_no_name', dict(secgrp=['8a2f582a-e1cd-480f-b85d-b02631c10656'],
                              name=None,
                              value_specs={},
                              fixed_ips=None,
                              addr_pair=None,
                              vnic_type=None)),
        ('with_empty_values', dict(secgrp=[],
                                   name='test',
                                   value_specs={},
                                   fixed_ips=[],
                                   addr_pair=[],
                                   vnic_type=None)),
        ('with_fixed_ips', dict(secgrp=None,
                                value_specs={},
                                fixed_ips=[
                                    {"subnet_id": "d0e971a6-a6b4-4f4c",
                                     "ip_address": "10.0.0.2"}],
                                addr_pair=None,
                                vnic_type=None)),
        ('with_addr_pair', dict(secgrp=None,
                                value_specs={},
                                fixed_ips=None,
                                addr_pair=[{'ip_address': '10.0.3.21',
                                            'mac_address': '00-B0-D0-86'}],
                                vnic_type=None)),

        ('with_value_specs', dict(secgrp=None,
                                  value_specs={'binding:vnic_type': 'direct'},
                                  fixed_ips=None,
                                  addr_pair=None,
                                  vnic_type=None)),
        ('normal_vnic', dict(secgrp=None,
                             value_specs={},
                             fixed_ips=None,
                             addr_pair=None,
                             vnic_type='normal')),
        ('direct_vnic', dict(secgrp=None,
                             value_specs={},
                             fixed_ips=None,
                             addr_pair=None,
                             vnic_type='direct')),
        ('with_all', dict(secgrp=['8a2f582a-e1cd-480f-b85d-b02631c10656'],
                          value_specs={},
                          fixed_ips=[
                              {"subnet_id": "d0e971a6-a6b4-4f4c",
                               "ip_address": "10.0.0.2"}],
                          addr_pair=[{'ip_address': '10.0.3.21',
                                      'mac_address': '00-B0-D0-86-BB-F7'}],
                          vnic_type='normal')),

        ]

    def test_update_port(self):
        t = template_format.parse(neutron_port_template)
        t['resources']['port']['properties'].pop('fixed_ips')
        stack = utils.parse_stack(t)

        self.patchobject(neutronV20, 'find_resourceid_by_name_or_id',
                         return_value='net1234')
        create_port = self.patchobject(neutronclient.Client, 'create_port')
        update_port = self.patchobject(neutronclient.Client, 'update_port')
        fake_groups_list = {
            'security_groups': [
                {
                    'tenant_id': 'dc4b074874244f7693dd65583733a758',
                    'id': '0389f747-7785-4757-b7bb-2ab07e4b09c3',
                    'name': 'default',
                    'security_group_rules': [],
                    'description': 'no protocol'
                }
            ]
        }
        self.patchobject(neutronclient.Client, 'list_security_groups',
                         return_value=fake_groups_list)

        props = {'network_id': u'net1234',
                 'name': str(utils.PhysName(stack.name, 'port')),
                 'admin_state_up': True,
                 'device_owner': u'network:dhcp'}

        update_props = props.copy()
        update_props['security_groups'] = self.secgrp
        update_props['value_specs'] = self.value_specs
        if self.fixed_ips:
            update_props['fixed_ips'] = self.fixed_ips
        update_props['allowed_address_pairs'] = self.addr_pair
        update_props['binding:vnic_type'] = self.vnic_type

        update_dict = update_props.copy()

        if update_props['security_groups'] is None:
            update_dict['security_groups'] = ['default']

        if update_props['name'] is None:
            update_dict['name'] = utils.PhysName(stack.name, 'test_subnet')

        value_specs = update_dict.pop('value_specs')
        if value_specs:
            for value_spec in six.iteritems(value_specs):
                update_dict[value_spec[0]] = value_spec[1]

        # create port
        port = stack['port']
        self.assertIsNone(scheduler.TaskRunner(port.handle_create)())
        create_port.assset_called_once_with(props)
        # update port
        update_snippet = rsrc_defn.ResourceDefinition(port.name, port.type(),
                                                      update_props)
        self.assertIsNone(scheduler.TaskRunner(port.handle_update,
                                               update_snippet, {},
                                               update_props)())

        update_port.assset_called_once_with(update_dict)

        # check, that update does not cause of Update Replace
        create_snippet = rsrc_defn.ResourceDefinition(port.name, port.type(),
                                                      props)
        after_props, before_props = port._prepare_update_props(update_snippet,
                                                               create_snippet)
        self.assertIsNotNone(
            port.update_template_diff_properties(after_props, before_props))

        # update with empty prop_diff
        scheduler.TaskRunner(port.handle_update, update_snippet, {}, {})()
        self.assertEqual(1, update_port.call_count)
