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

from oslo_config import cfg
import six
import swiftclient.client as sc

from heat.common import exception
from heat.common import template_format
from heat.engine.resources.aws.s3 import s3
from heat.engine import scheduler
from heat.tests import common
from heat.tests import utils


swift_template = '''
{
  "AWSTemplateFormatVersion" : "2010-09-09",
  "Description" : "Template to test S3 Bucket resources",
  "Resources" : {
    "S3BucketWebsite" : {
      "Type" : "AWS::S3::Bucket",
      "DeletionPolicy" : "Delete",
      "Properties" : {
        "AccessControl" : "PublicRead",
        "WebsiteConfiguration" : {
          "IndexDocument" : "index.html",
          "ErrorDocument" : "error.html"
         }
      }
    },
    "SwiftContainer": {
         "Type": "OS::Swift::Container",
         "Properties": {
            "S3Bucket": {"Ref" : "S3Bucket"},
         }
      },
    "S3Bucket" : {
      "Type" : "AWS::S3::Bucket",
      "Properties" : {
        "AccessControl" : "Private"
      }
    },
    "S3Bucket_with_tags" : {
      "Type" : "AWS::S3::Bucket",
      "Properties" : {
        "Tags" : [{"Key": "greeting", "Value": "hello"},
                  {"Key": "location", "Value": "here"}]
      }
    }
  }
}
'''


class s3Test(common.HeatTestCase):
    def setUp(self):
        super(s3Test, self).setUp()
        self.m.CreateMock(sc.Connection)
        self.m.StubOutWithMock(sc.Connection, 'put_container')
        self.m.StubOutWithMock(sc.Connection, 'get_container')
        self.m.StubOutWithMock(sc.Connection, 'delete_container')
        self.m.StubOutWithMock(sc.Connection, 'get_auth')

    def create_resource(self, t, stack, resource_name):
        resource_defns = stack.t.resource_definitions(stack)
        rsrc = s3.S3Bucket('test_resource',
                           resource_defns[resource_name],
                           stack)
        scheduler.TaskRunner(rsrc.create)()
        self.assertEqual((rsrc.CREATE, rsrc.COMPLETE), rsrc.state)
        return rsrc

    def test_attributes(self):
        t = template_format.parse(swift_template)
        stack = utils.parse_stack(t)

        container_name = utils.PhysName(stack.name, 'test_resource')
        sc.Connection.put_container(
            container_name,
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': 'test_tenant:test_username'}
        ).AndReturn(None)
        sc.Connection.get_auth().MultipleTimes().AndReturn(
            ('http://server.test:8080/v_2', None))
        sc.Connection.delete_container(container_name).AndReturn(None)

        self.m.ReplayAll()
        rsrc = self.create_resource(t, stack, 'S3Bucket')

        ref_id = rsrc.FnGetRefId()
        self.assertEqual(container_name, ref_id)

        self.assertEqual('server.test', rsrc.FnGetAtt('DomainName'))
        url = 'http://server.test:8080/v_2/%s' % ref_id

        self.assertEqual(url, rsrc.FnGetAtt('WebsiteURL'))

        self.assertRaises(exception.InvalidTemplateAttribute,
                          rsrc.FnGetAtt, 'Foo')

        scheduler.TaskRunner(rsrc.delete)()
        self.m.VerifyAll()

    def test_public_read(self):
        t = template_format.parse(swift_template)
        properties = t['Resources']['S3Bucket']['Properties']
        properties['AccessControl'] = 'PublicRead'
        stack = utils.parse_stack(t)

        container_name = utils.PhysName(stack.name, 'test_resource')
        sc.Connection.put_container(
            utils.PhysName(stack.name, 'test_resource'),
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': '.r:*'}).AndReturn(None)
        sc.Connection.delete_container(
            container_name).AndReturn(None)

        self.m.ReplayAll()

        rsrc = self.create_resource(t, stack, 'S3Bucket')
        scheduler.TaskRunner(rsrc.delete)()
        self.m.VerifyAll()

    def test_tags(self):
        t = template_format.parse(swift_template)
        stack = utils.parse_stack(t)

        container_name = utils.PhysName(stack.name, 'test_resource')
        sc.Connection.put_container(
            utils.PhysName(stack.name, 'test_resource'),
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': 'test_tenant:test_username',
             'X-Container-Meta-S3-Tag-greeting': 'hello',
             'X-Container-Meta-S3-Tag-location': 'here'}).AndReturn(None)
        sc.Connection.delete_container(
            container_name).AndReturn(None)

        self.m.ReplayAll()

        rsrc = self.create_resource(t, stack, 'S3Bucket_with_tags')
        scheduler.TaskRunner(rsrc.delete)()
        self.m.VerifyAll()

    def test_public_read_write(self):
        t = template_format.parse(swift_template)
        properties = t['Resources']['S3Bucket']['Properties']
        properties['AccessControl'] = 'PublicReadWrite'
        stack = utils.parse_stack(t)

        container_name = utils.PhysName(stack.name, 'test_resource')
        sc.Connection.put_container(
            container_name,
            {'X-Container-Write': '.r:*',
             'X-Container-Read': '.r:*'}).AndReturn(None)
        sc.Connection.delete_container(
            container_name).AndReturn(None)

        self.m.ReplayAll()

        rsrc = self.create_resource(t, stack, 'S3Bucket')
        scheduler.TaskRunner(rsrc.delete)()
        self.m.VerifyAll()

    def test_authenticated_read(self):
        t = template_format.parse(swift_template)
        properties = t['Resources']['S3Bucket']['Properties']
        properties['AccessControl'] = 'AuthenticatedRead'
        stack = utils.parse_stack(t)

        container_name = utils.PhysName(stack.name, 'test_resource')
        sc.Connection.put_container(
            container_name,
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': 'test_tenant'}).AndReturn(None)
        sc.Connection.delete_container(container_name).AndReturn(None)

        self.m.ReplayAll()

        rsrc = self.create_resource(t, stack, 'S3Bucket')
        scheduler.TaskRunner(rsrc.delete)()
        self.m.VerifyAll()

    def test_website(self):
        t = template_format.parse(swift_template)
        stack = utils.parse_stack(t)

        container_name = utils.PhysName(stack.name, 'test_resource')
        sc.Connection.put_container(
            container_name,
            {'X-Container-Meta-Web-Error': 'error.html',
             'X-Container-Meta-Web-Index': 'index.html',
             'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': '.r:*'}).AndReturn(None)
        sc.Connection.delete_container(container_name).AndReturn(None)

        self.m.ReplayAll()

        rsrc = self.create_resource(t, stack, 'S3BucketWebsite')
        scheduler.TaskRunner(rsrc.delete)()
        self.m.VerifyAll()

    def test_delete_exception(self):
        t = template_format.parse(swift_template)
        stack = utils.parse_stack(t)

        container_name = utils.PhysName(stack.name, 'test_resource')
        sc.Connection.put_container(
            container_name,
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': 'test_tenant:test_username'}).AndReturn(None)
        sc.Connection.delete_container(container_name).AndRaise(
            sc.ClientException('Test delete failure'))

        self.m.ReplayAll()

        rsrc = self.create_resource(t, stack, 'S3Bucket')
        self.assertRaises(exception.ResourceFailure,
                          scheduler.TaskRunner(rsrc.delete))

        self.m.VerifyAll()

    def test_delete_not_found(self):
        t = template_format.parse(swift_template)
        stack = utils.parse_stack(t)

        container_name = utils.PhysName(stack.name, 'test_resource')
        sc.Connection.put_container(
            container_name,
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': 'test_tenant:test_username'}).AndReturn(None)
        sc.Connection.delete_container(container_name).AndRaise(
            sc.ClientException('Its gone', http_status=404))

        self.m.ReplayAll()

        rsrc = self.create_resource(t, stack, 'S3Bucket')
        scheduler.TaskRunner(rsrc.delete)()

        self.m.VerifyAll()

    def test_delete_conflict_not_empty(self):
        t = template_format.parse(swift_template)
        stack = utils.parse_stack(t)

        container_name = utils.PhysName(stack.name, 'test_resource')
        sc.Connection.put_container(
            container_name,
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': 'test_tenant:test_username'}).AndReturn(None)
        sc.Connection.delete_container(container_name).AndRaise(
            sc.ClientException('Not empty', http_status=409))
        sc.Connection.get_container(container_name).AndReturn(
            ({'name': container_name}, [{'name': 'test_object'}]))
        self.m.ReplayAll()

        rsrc = self.create_resource(t, stack, 'S3Bucket')
        deleter = scheduler.TaskRunner(rsrc.delete)
        ex = self.assertRaises(exception.ResourceFailure, deleter)
        self.assertIn("ResourceActionNotSupported: resources.test_resource: "
                      "The bucket you tried to delete is not empty",
                      six.text_type(ex))

        self.m.VerifyAll()

    def test_delete_conflict_empty(self):
        cfg.CONF.set_override('action_retry_limit', 0, enforce_type=True)
        t = template_format.parse(swift_template)
        stack = utils.parse_stack(t)

        container_name = utils.PhysName(stack.name, 'test_resource')
        sc.Connection.put_container(
            container_name,
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': 'test_tenant:test_username'}).AndReturn(None)
        sc.Connection.delete_container(container_name).AndRaise(
            sc.ClientException('Conflict', http_status=409))
        sc.Connection.get_container(container_name).AndReturn(
            ({'name': container_name}, []))

        self.m.ReplayAll()

        rsrc = self.create_resource(t, stack, 'S3Bucket')
        deleter = scheduler.TaskRunner(rsrc.delete)
        ex = self.assertRaises(exception.ResourceFailure, deleter)
        self.assertIn("Conflict", six.text_type(ex))

        self.m.VerifyAll()

    def test_delete_retain(self):
        t = template_format.parse(swift_template)
        bucket = t['Resources']['S3Bucket']
        bucket['DeletionPolicy'] = 'Retain'
        stack = utils.parse_stack(t)

        # first run, with retain policy
        sc.Connection.put_container(
            utils.PhysName(stack.name, 'test_resource'),
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': 'test_tenant:test_username'}).AndReturn(None)

        self.m.ReplayAll()

        rsrc = self.create_resource(t, stack, 'S3Bucket')
        scheduler.TaskRunner(rsrc.delete)()
        self.assertEqual((rsrc.DELETE, rsrc.COMPLETE), rsrc.state)

        self.m.VerifyAll()
