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

import pickle
import six

import oslo_db.exception
from oslo_log import log as logging

from heat.common import identifier
from heat.objects import event as event_object

LOG = logging.getLogger(__name__)

MAX_EVENT_RESOURCE_PROPERTIES_SIZE = (1 << 16) - 1


class Event(object):
    """Class representing a Resource state change."""

    def __init__(self, context, stack, action, status, reason,
                 physical_resource_id, resource_properties, resource_name,
                 resource_type, uuid=None, timestamp=None, id=None):
        """Initialise from a context, stack, and event information.

        The timestamp and database ID may also be initialised if the event is
        already in the database.
        """
        self.context = context
        self._stack_identifier = stack.identifier()
        self.action = action
        self.status = status
        self.reason = reason
        self.physical_resource_id = physical_resource_id
        self.resource_name = resource_name
        self.resource_type = resource_type
        try:
            self.resource_properties = dict(resource_properties)
        except ValueError as ex:
            self.resource_properties = {'Error': six.text_type(ex)}
        self.uuid = uuid
        self.timestamp = timestamp
        self.id = id

    def store(self):
        """Store the Event in the database."""
        ev = {
            'resource_name': self.resource_name,
            'physical_resource_id': self.physical_resource_id,
            'stack_id': self._stack_identifier.stack_id,
            'resource_action': self.action,
            'resource_status': self.status,
            'resource_status_reason': self.reason,
            'resource_type': self.resource_type,
            'resource_properties': self.resource_properties,
        }

        if self.uuid is not None:
            ev['uuid'] = self.uuid

        if self.timestamp is not None:
            ev['created_at'] = self.timestamp

        # Workaround: we don't want to attempt to store the
        # event.resource_properties column if the data is too large
        # (greater than permitted by BLOB). Otherwise, we end up with
        # an unsightly log message.
        rp_size = len(pickle.dumps(ev['resource_properties']))
        if rp_size > MAX_EVENT_RESOURCE_PROPERTIES_SIZE:
            LOG.debug('event\'s resource_properties too large to store at '
                      '%d bytes', rp_size)
            # Try truncating the largest value and see if that gets us under
            # the db column's size constraint.
            max_key, max_val = max(ev['resource_properties'].items(),
                                   key=lambda i: len(repr(i[1])))
            err = 'Resource properties are too large to store fully'
            ev['resource_properties'].update({'Error': err})
            ev['resource_properties'][max_key] = '<Deleted, too large>'
            rp_size = len(pickle.dumps(ev['resource_properties']))
            if rp_size > MAX_EVENT_RESOURCE_PROPERTIES_SIZE:
                LOG.debug('event\'s resource_properties STILL too large '
                          'after truncating largest key at %d bytes', rp_size)
                err = 'Resource properties are too large to attempt to store'
                ev['resource_properties'] = {'Error': err}

        # We should have worked around the issue, but let's be extra
        # careful.
        try:
            new_ev = event_object.Event.create(self.context, ev)
        except oslo_db.exception.DBError:
            # Give up and drop all properties..
            err = 'Resource properties are too large to store'
            ev['resource_properties'] = {'Error': err}
            new_ev = event_object.Event.create(self.context, ev)

        self.id = new_ev.id
        self.timestamp = new_ev.created_at
        self.uuid = new_ev.uuid
        return self.id

    def identifier(self):
        """Return a unique identifier for the event."""
        if self.uuid is None:
            return None

        res_id = identifier.ResourceIdentifier(
            resource_name=self.resource_name, **self._stack_identifier)

        return identifier.EventIdentifier(event_id=str(self.uuid), **res_id)

    def as_dict(self):
        return {
            'timestamp': self.timestamp.isoformat(),
            'version': '0.1',
            'type': 'os.heat.event',
            'id': self.uuid,
            'payload': {
                'resource_name': self.resource_name,
                'physical_resource_id': self.physical_resource_id,
                'stack_id': self._stack_identifier.stack_id,
                'resource_action': self.action,
                'resource_status': self.status,
                'resource_status_reason': self.reason,
                'resource_type': self.resource_type,
                'resource_properties': self.resource_properties,
                'version': '0.1'
            }
        }
