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

import mock

from heat.engine.clients.os import senlin as senlin_plugin
from heat.tests import common
from heat.tests import utils
from senlinclient.common import exc


class SenlinClientPluginTest(common.HeatTestCase):
    def setUp(self):
        super(SenlinClientPluginTest, self).setUp()
        context = utils.dummy_context()
        self.plugin = context.clients.client_plugin('senlin')
        self.client = self.plugin.client()

    def test_cluster_get(self):
        self.assertIsNotNone(self.client.clusters)

    def test_is_bad_request(self):
        self.assertTrue(self.plugin.is_bad_request(
            exc.sdkexc.HttpException(http_status=400)))
        self.assertFalse(self.plugin.is_bad_request(Exception))
        self.assertFalse(self.plugin.is_bad_request(
            exc.sdkexc.HttpException(http_status=404)))

    def test_check_action_success(self):
        mock_action = mock.MagicMock()
        mock_action.status = 'SUCCEEDED'
        mock_get = self.patchobject(self.client, 'get_action')
        mock_get.return_value = mock_action
        self.assertTrue(self.plugin.check_action_status('fake_id'))
        mock_get.assert_called_once_with('fake_id')


class ProfileConstraintTest(common.HeatTestCase):

    def setUp(self):
        super(ProfileConstraintTest, self).setUp()
        self.senlin_client = mock.MagicMock()
        self.ctx = utils.dummy_context()
        self.mock_get_profile = mock.Mock()
        self.ctx.clients.client(
            'senlin').get_profile = self.mock_get_profile
        self.constraint = senlin_plugin.ProfileConstraint()

    def test_validate_true(self):
        self.mock_get_profile.return_value = None
        self.assertTrue(self.constraint.validate("PROFILE_ID", self.ctx))

    def test_validate_false(self):
        self.mock_get_profile.side_effect = exc.sdkexc.ResourceNotFound(
            'PROFILE_ID')
        self.assertFalse(self.constraint.validate("PROFILE_ID", self.ctx))
        self.mock_get_profile.side_effect = exc.sdkexc.HttpException(
            'PROFILE_ID')
        self.assertFalse(self.constraint.validate("PROFILE_ID", self.ctx))


class ClusterConstraintTest(common.HeatTestCase):

    def setUp(self):
        super(ClusterConstraintTest, self).setUp()
        self.senlin_client = mock.MagicMock()
        self.ctx = utils.dummy_context()
        self.mock_get_cluster = mock.Mock()
        self.ctx.clients.client(
            'senlin').get_cluster = self.mock_get_cluster
        self.constraint = senlin_plugin.ClusterConstraint()

    def test_validate_true(self):
        self.mock_get_cluster.return_value = None
        self.assertTrue(self.constraint.validate("CLUSTER_ID", self.ctx))

    def test_validate_false(self):
        self.mock_get_cluster.side_effect = exc.sdkexc.ResourceNotFound(
            'CLUSTER_ID')
        self.assertFalse(self.constraint.validate("CLUSTER_ID", self.ctx))
        self.mock_get_cluster.side_effect = exc.sdkexc.HttpException(
            'CLUSTER_ID')
        self.assertFalse(self.constraint.validate("CLUSTER_ID", self.ctx))


class ProfileTypeConstraintTest(common.HeatTestCase):

    def setUp(self):
        super(ProfileTypeConstraintTest, self).setUp()
        self.senlin_client = mock.MagicMock()
        self.ctx = utils.dummy_context()
        heat_profile_type = mock.MagicMock()
        heat_profile_type.name = 'os.heat.stack-1.0'
        nova_profile_type = mock.MagicMock()
        nova_profile_type.name = 'os.nova.server-1.0'
        self.mock_profile_types = mock.Mock(
            return_value=[heat_profile_type, nova_profile_type])
        self.ctx.clients.client(
            'senlin').profile_types = self.mock_profile_types
        self.constraint = senlin_plugin.ProfileTypeConstraint()

    def test_validate_true(self):
        self.assertTrue(self.constraint.validate("os.heat.stack-1.0",
                                                 self.ctx))

    def test_validate_false(self):
        self.assertFalse(self.constraint.validate("Invalid_type",
                                                  self.ctx))


class PolicyTypeConstraintTest(common.HeatTestCase):

    def setUp(self):
        super(PolicyTypeConstraintTest, self).setUp()
        self.senlin_client = mock.MagicMock()
        self.ctx = utils.dummy_context()
        deletion_policy_type = mock.MagicMock()
        deletion_policy_type.name = 'senlin.policy.deletion-1.0'
        lb_policy_type = mock.MagicMock()
        lb_policy_type.name = 'senlin.policy.loadbalance-1.0'
        self.mock_policy_types = mock.Mock(
            return_value=[deletion_policy_type, lb_policy_type])
        self.ctx.clients.client(
            'senlin').policy_types = self.mock_policy_types
        self.constraint = senlin_plugin.PolicyTypeConstraint()

    def test_validate_true(self):
        self.assertTrue(self.constraint.validate(
            "senlin.policy.deletion-1.0", self.ctx))

    def test_validate_false(self):
        self.assertFalse(self.constraint.validate("Invalid_type",
                                                  self.ctx))
