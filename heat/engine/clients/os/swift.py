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

import datetime
import email.utils
import hashlib
import logging
import random
import time

import six
from six.moves.urllib import parse
from swiftclient import client as sc
from swiftclient import exceptions
from swiftclient import utils as swiftclient_utils

from heat.engine.clients import client_plugin

IN_PROGRESS = 'in progress'

MAX_EPOCH = 2147483647

CLIENT_NAME = 'swift'


# silence the swiftclient logging
sc_logger = logging.getLogger("swiftclient")
sc_logger.setLevel(logging.CRITICAL)


class SwiftClientPlugin(client_plugin.ClientPlugin):

    exceptions_module = exceptions

    service_types = [OBJECT_STORE] = ['object-store']

    def _create(self):

        con = self.context
        endpoint_type = self._get_client_option(CLIENT_NAME, 'endpoint_type')
        args = {
            'auth_version': '2.0',
            'tenant_name': con.project_name,
            'user': con.username,
            'key': None,
            'authurl': None,
            'preauthtoken': con.keystone_session.get_token(),
            'preauthurl': self.url_for(service_type=self.OBJECT_STORE,
                                       endpoint_type=endpoint_type),
            'os_options': {'endpoint_type': endpoint_type},
            'cacert': self._get_client_option(CLIENT_NAME, 'ca_file'),
            'insecure': self._get_client_option(CLIENT_NAME, 'insecure')
        }
        return sc.Connection(**args)

    def is_client_exception(self, ex):
        return isinstance(ex, exceptions.ClientException)

    def is_not_found(self, ex):
        return (isinstance(ex, exceptions.ClientException) and
                ex.http_status == 404)

    def is_over_limit(self, ex):
        return (isinstance(ex, exceptions.ClientException) and
                ex.http_status == 413)

    def is_conflict(self, ex):
        return (isinstance(ex, exceptions.ClientException) and
                ex.http_status == 409)

    def is_valid_temp_url_path(self, path):
        """Return True if path is a valid Swift TempURL path, False otherwise.

        A Swift TempURL path must:
        - Be five parts, ['', 'v1', 'account', 'container', 'object']
        - Be a v1 request
        - Have account, container, and object values
        - Have an object value with more than just '/'s

        :param path: The TempURL path
        :type path: string
        """
        parts = path.split('/', 4)
        return bool(len(parts) == 5 and
                    not parts[0] and
                    parts[1] == 'v1' and
                    parts[2].endswith(self.context.tenant_id) and
                    parts[3] and
                    parts[4].strip('/'))

    def get_temp_url(self, container_name, obj_name, timeout=None,
                     method='PUT'):
        """Return a Swift TempURL."""
        key_header = 'x-account-meta-temp-url-key'
        if key_header not in self.client().head_account():
            self.client().post_account({
                key_header: hashlib.sha224(
                    six.b(six.text_type(
                        random.getrandbits(256)))).hexdigest()[:32]})

        key = self.client().head_account()[key_header]

        path = '/v1/AUTH_%s/%s/%s' % (self.context.tenant_id, container_name,
                                      obj_name)
        if timeout is None:
            timeout = MAX_EPOCH - 60 - time.time()
        tempurl = swiftclient_utils.generate_temp_url(path, timeout, key,
                                                      method)
        sw_url = parse.urlparse(self.client().url)
        return '%s://%s%s' % (sw_url.scheme, sw_url.netloc, tempurl)

    def get_signal_url(self, container_name, obj_name, timeout=None):
        """Turn on object versioning.

        We can use a single TempURL for multiple signals and return a Swift
        TempURL.
        """
        self.client().put_container(
            container_name, headers={'x-versions-location': container_name})
        self.client().put_object(container_name, obj_name, IN_PROGRESS)

        return self.get_temp_url(container_name, obj_name, timeout)

    def parse_last_modified(self, lm):
        """Parses the last-modified value.

        For example, last-modified values from a swift object header.
        Returns the datetime.datetime of that value.

        :param lm: The last-modified value (or None)
        :type lm: string
        :returns: An offset-naive UTC datetime of the value (or None)
        """
        if not lm:
            return None
        pd = email.utils.parsedate(lm)[:6]
        # according to RFC 2616, all HTTP time headers must be
        # in GMT time, so create an offset-naive UTC datetime
        return datetime.datetime(*pd)
