import sys
import os

import nose
import unittest
import mox
import json
import sqlalchemy

from nose.plugins.attrib import attr
from nose import with_setup

from heat.tests.v1_1 import fakes
from heat.engine import instance as instances
from heat.engine import volume as volumes
import heat.db as db_api
from heat.engine import parser

test_template_volumeattach = '''
{
  "AWSTemplateFormatVersion" : "2010-09-09",
  "Description" : "test.",
  "Resources" : {
    "WikiDatabase": {
      "Type": "AWS::EC2::Instance",
      "Properties": {
        "ImageId": "image_name",
        "InstanceType": "m1.large",
        "KeyName": "test_KeyName"
      }
    },
    "DataVolume" : {
      "Type" : "AWS::EC2::Volume",
      "Properties" : {
        "Size" : "6",
        "AvailabilityZone" : "nova"
      }
    },
    "MountPoint" : {
      "Type" : "AWS::EC2::VolumeAttachment",
      "Properties" : {
        "InstanceId" : { "Ref" : "WikiDatabase" },
        "VolumeId"  : { "Ref" : "DataVolume" },
        "Device" : "/dev/%s"
      }
    }
  }
}
'''

test_template_ref = '''
{
  "AWSTemplateFormatVersion" : "2010-09-09",
  "Description" : "test.",
  "Parameters" : {

    "KeyName" : {
      "Description" : "Name of an existing EC2 KeyPair to enable SSH access to the instances",
      "Type" : "String"
    }
  },

  "Resources" : {
    "WikiDatabase": {
      "Type": "AWS::EC2::Instance",
      "Properties": {
        "ImageId": "image_name",
        "InstanceType": "m1.large",
        "KeyName": "test_KeyName"
      }
    },
    "DataVolume" : {
      "Type" : "AWS::EC2::Volume",
      "Properties" : {
        "Size" : "6",
        "AvailabilityZone" : "nova"
      }
    },
    "MountPoint" : {
      "Type" : "AWS::EC2::VolumeAttachment",
      "Properties" : {
        "InstanceId" : { "Ref" : "%s" },
        "VolumeId"  : { "Ref" : "DataVolume" },
        "Device" : "/dev/vdb"
      }
    }
  }
}
'''
@attr(tag=['unit', 'validate'])
@attr(speed='fast')
class validateTest(unittest.TestCase):
    def setUp(self):
        self.m = mox.Mox()
        self.fc = fakes.FakeClient()

    def tearDown(self):
        self.m.UnsetStubs()
        print "volumeTest teardown complete"

    def test_validate_volumeattach_valid(self):
        t = json.loads(test_template_volumeattach % 'vdq')
        params = {}
        params['KeyStoneCreds'] = None
        stack = parser.Stack('test_stack', t, 0, params)

        self.m.StubOutWithMock(db_api, 'resource_get_by_name_and_stack')
        db_api.resource_get_by_name_and_stack(None, 'test_resource_name',\
                                              stack).AndReturn(None)

        self.m.ReplayAll()
        volumeattach = stack.resources['MountPoint']
        stack.resolve_attributes(volumeattach.t)
        stack.resolve_joins(volumeattach.t)
        stack.resolve_base64(volumeattach.t)
        assert(volumeattach.validate() == None)

    def test_validate_volumeattach_invalid(self):
        t = json.loads(test_template_volumeattach % 'sda')
        params = {}
        params['KeyStoneCreds'] = None
        stack = parser.Stack('test_stack', t, 0, params)

        self.m.StubOutWithMock(db_api, 'resource_get_by_name_and_stack')
        db_api.resource_get_by_name_and_stack(None, 'test_resource_name',\
                                              stack).AndReturn(None)

        self.m.ReplayAll()
        volumeattach = stack.resources['MountPoint']
        stack.resolve_attributes(volumeattach.t)
        stack.resolve_joins(volumeattach.t)
        stack.resolve_base64(volumeattach.t)
        assert(volumeattach.validate())

    def test_validate_ref_valid(self):
        t = json.loads(test_template_ref % 'WikiDatabase')
        params = {}
        params['KeyStoneCreds'] = None
        t['Parameters']['KeyName']['Value'] = 'test'
        stack = parser.Stack('test_stack', t, 0, params)
        self.m.StubOutWithMock(instances.Instance, 'nova')
        instances.Instance.nova().AndReturn(self.fc)
        instance = stack.resources['WikiDatabase']
        instance.itype_oflavor['m1.large'] = 'm1.large'
        instance.stack.resolve_attributes(instance.t)
        instance.stack.resolve_joins(instance.t)
        instance.stack.resolve_base64(instance.t)

        self.m.StubOutWithMock(db_api, 'resource_get_by_name_and_stack')
        db_api.resource_get_by_name_and_stack(None, 'test_resource_name',\
                                              stack).AndReturn(None)

        self.m.ReplayAll()
        stack.resolve_attributes(stack.t)
        stack.resolve_joins(stack.t)
        stack.resolve_base64(stack.t)
        res = dict(stack.validate()['ValidateTemplateResult'])
        assert (res['Description'] == 'Successfully validated')

    def test_validate_ref_invalid(self):
        t = json.loads(test_template_ref % 'WikiDatabasez')
        params = {}
        params['KeyStoneCreds'] = None
        t['Parameters']['KeyName']['Value'] = 'test'
        stack = parser.Stack('test_stack', t, 0, params)
        self.m.StubOutWithMock(instances.Instance, 'nova')
        instances.Instance.nova().AndReturn(self.fc)
        instance = stack.resources['WikiDatabase']
        instance.itype_oflavor['m1.large'] = 'm1.large'
        instance.stack.resolve_attributes(instance.t)
        instance.stack.resolve_joins(instance.t)
        instance.stack.resolve_base64(instance.t)

        self.m.StubOutWithMock(db_api, 'resource_get_by_name_and_stack')
        db_api.resource_get_by_name_and_stack(None, 'test_resource_name',\
                                              stack).AndReturn(None)

        self.m.ReplayAll()
        stack.resolve_attributes(stack.t)
        stack.resolve_joins(stack.t)
        stack.resolve_base64(stack.t)
        res = dict(stack.validate()['ValidateTemplateResult'])
        assert (res['Description'] != 'Successfully validated')

    # allows testing of the test directly, shown below
    if __name__ == '__main__':
        sys.argv.append(__file__)
        nose.main()
