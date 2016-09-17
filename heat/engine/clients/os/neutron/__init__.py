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

from neutronclient.common import exceptions
from neutronclient.neutron import v2_0 as neutronV20
from neutronclient.v2_0 import client as nc
from oslo_utils import uuidutils

from heat.common import exception
from heat.engine.clients import client_plugin
from heat.engine.clients import os as os_client


class NeutronClientPlugin(client_plugin.ClientPlugin):

    exceptions_module = exceptions

    service_types = [NETWORK] = ['network']

    def _create(self):

        con = self.context
        interface = self._get_client_option('neutron', 'endpoint_type')
        args = {
            'session': con.keystone_session,
            'service_type': self.NETWORK,
            'interface': interface
        }

        return nc.Client(**args)

    def is_not_found(self, ex):
        if isinstance(ex, (exceptions.NotFound,
                           exceptions.NetworkNotFoundClient,
                           exceptions.PortNotFoundClient)):
            return True
        return (isinstance(ex, exceptions.NeutronClientException) and
                ex.status_code == 404)

    def is_conflict(self, ex):
        bad_conflicts = (exceptions.OverQuotaClient,)
        return (isinstance(ex, exceptions.Conflict) and
                not isinstance(ex, bad_conflicts))

    def is_over_limit(self, ex):
        if not isinstance(ex, exceptions.NeutronClientException):
            return False
        return ex.status_code == 413

    def is_no_unique(self, ex):
        return isinstance(ex, exceptions.NeutronClientNoUniqueMatch)

    def is_invalid(self, ex):
        return isinstance(ex, exceptions.StateInvalidClient)

    def find_resourceid_by_name_or_id(self, resource, name_or_id,
                                      cmd_resource=None):
        return self._find_resource_id(self.context.tenant_id,
                                      resource, name_or_id,
                                      cmd_resource)

    @os_client.MEMOIZE_FINDER
    def _find_resource_id(self, tenant_id,
                          resource, name_or_id, cmd_resource):
        # tenant id in the signature is used for the memoization key,
        # that would differentiate similar resource names across tenants.
        return neutronV20.find_resourceid_by_name_or_id(
            self.client(), resource, name_or_id, cmd_resource=cmd_resource)

    @os_client.MEMOIZE_EXTENSIONS
    def _list_extensions(self):
        extensions = self.client().list_extensions().get('extensions')
        return set(extension.get('alias') for extension in extensions)

    def has_extension(self, alias):
        """Check if specific extension is present."""
        return alias in self._list_extensions()

    def _resolve(self, props, key, id_key, key_type):
        if props.get(key):
            props[id_key] = self.find_resourceid_by_name_or_id(key_type,
                                                               props.pop(key))
        return props[id_key]

    def resolve_pool(self, props, pool_key, pool_id_key):
        if props.get(pool_key):
            props[pool_id_key] = self.find_resourceid_by_name_or_id(
                'pool', props.get(pool_key), cmd_resource='lbaas_pool')
            props.pop(pool_key)
        return props[pool_id_key]

    def resolve_router(self, props, router_key, router_id_key):
        return self._resolve(props, router_key, router_id_key, 'router')

    def network_id_from_subnet_id(self, subnet_id):
        subnet_info = self.client().show_subnet(subnet_id)
        return subnet_info['subnet']['network_id']

    def check_lb_status(self, lb_id):
        lb = self.client().show_loadbalancer(lb_id)['loadbalancer']
        status = lb['provisioning_status']
        if status == 'ERROR':
            raise exception.ResourceInError(resource_status=status)
        return status == 'ACTIVE'

    def get_qos_policy_id(self, policy):
        """Returns the id of QoS policy.

        Args:
        policy: ID or name of the policy.
        """
        return self.find_resourceid_by_name_or_id(
            'policy', policy, cmd_resource='qos_policy')

    def get_secgroup_uuids(self, security_groups):
        '''Returns a list of security group UUIDs.

        Args:
        security_groups: List of security group names or UUIDs
        '''
        seclist = []
        all_groups = None
        for sg in security_groups:
            if uuidutils.is_uuid_like(sg):
                seclist.append(sg)
            else:
                if not all_groups:
                    response = self.client().list_security_groups()
                    all_groups = response['security_groups']
                same_name_groups = [g for g in all_groups if g['name'] == sg]
                groups = [g['id'] for g in same_name_groups]
                if len(groups) == 0:
                    raise exception.EntityNotFound(entity='Resource', name=sg)
                elif len(groups) == 1:
                    seclist.append(groups[0])
                else:
                    # for admin roles, can get the other users'
                    # securityGroups, so we should match the tenant_id with
                    # the groups, and return the own one
                    own_groups = [g['id'] for g in same_name_groups
                                  if g['tenant_id'] == self.context.tenant_id]
                    if len(own_groups) == 1:
                        seclist.append(own_groups[0])
                    else:
                        raise exception.PhysicalResourceNameAmbiguity(name=sg)
        return seclist

    def _resove_resource_path(self, resource):
        """Returns sfc resource path."""

        if resource == 'port_pair':
            RESOURCE_PATH = "/sfc/port_pairs"
            return RESOURCE_PATH

    def create_sfc_resource(self, resource, props):
        """Returns created sfc resource record."""

        path = self._resove_resource_path(resource)
        record = self.client().create_ext(path, {resource: props}
                                          ).get(resource)
        return record

    def update_sfc_resource(self, resource, prop_diff, resource_id):
        """Returns updated sfc resource record."""

        path = self._resove_resource_path(resource)
        return self.client().update_ext(path + '/%s', self.resource_id,
                                        {resource: prop_diff})

    def delete_sfc_resource(self, resource, resource_id):
        """deletes sfc resource record and returns status"""

        path = self._resove_resource_path(resource)
        return self.client().delete_ext(path + '/%s', self.resource_id)

    def show_sfc_resource(self, resource, resource_id):
        """returns specific sfc resource record"""

        path = self._resove_resource_path(resource)
        return self.client().show_ext(path + '/%s', self.resource_id
                                      ).get(resource)
