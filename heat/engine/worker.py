# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import eventlet.queue

from oslo_log import log as logging
import oslo_messaging
from oslo_service import service
from oslo_utils import uuidutils
from osprofiler import profiler

from heat.common import context
from heat.common.i18n import _LE
from heat.common.i18n import _LI
from heat.common.i18n import _LW
from heat.common import messaging as rpc_messaging
from heat.db import api as db_api
from heat.engine import check_resource
from heat.engine import stack as parser
from heat.engine import sync_point
from heat.objects import stack as stack_objects
from heat.rpc import api as rpc_api
from heat.rpc import worker_client as rpc_client

LOG = logging.getLogger(__name__)

CANCEL_RETRIES = 3


@profiler.trace_cls("rpc")
class WorkerService(service.Service):
    """Service that has 'worker' actor in convergence.

    This service is dedicated to handle internal messages to the 'worker'
    (a.k.a. 'converger') actor in convergence. Messages on this bus will
    use the 'cast' rather than 'call' method to anycast the message to
    an engine that will handle it asynchronously. It won't wait for
    or expect replies from these messages.
    """

    RPC_API_VERSION = '1.3'

    def __init__(self,
                 host,
                 topic,
                 engine_id,
                 thread_group_mgr):
        super(WorkerService, self).__init__()
        self.host = host
        self.topic = topic
        self.engine_id = engine_id
        self.thread_group_mgr = thread_group_mgr

        self._rpc_client = rpc_client.WorkerClient()
        self._rpc_server = None
        self.target = None

    def start(self):
        target = oslo_messaging.Target(
            version=self.RPC_API_VERSION,
            server=self.engine_id,
            topic=self.topic)
        self.target = target
        LOG.info(_LI("Starting %(topic)s (%(version)s) in engine %(engine)s."),
                 {'topic': self.topic,
                  'version': self.RPC_API_VERSION,
                  'engine': self.engine_id})

        self._rpc_server = rpc_messaging.get_rpc_server(target, self)
        self._rpc_server.start()

        super(WorkerService, self).start()

    def stop(self):
        if self._rpc_server is None:
            return
        # Stop rpc connection at first for preventing new requests
        LOG.info(_LI("Stopping %(topic)s in engine %(engine)s."),
                 {'topic': self.topic, 'engine': self.engine_id})
        try:
            self._rpc_server.stop()
            self._rpc_server.wait()
        except Exception as e:
            LOG.error(_LE("%(topic)s is failed to stop, %(exc)s"),
                      {'topic': self.topic, 'exc': e})

        super(WorkerService, self).stop()

    def stop_traversal(self, stack):
        """Update current traversal to stop workers from propagating.

        Marks the stack as FAILED due to cancellation, but, allows all
        in_progress resources to complete normally; no worker is stopped
        abruptly.
        """
        _stop_traversal(stack)

        db_child_stacks = stack_objects.Stack.get_all_by_root_owner_id(
            stack.context, stack.id)

        for db_child in db_child_stacks:
            if db_child.status == parser.Stack.IN_PROGRESS:
                child = parser.Stack.load(stack.context,
                                          stack_id=db_child.id,
                                          stack=db_child)
                _stop_traversal(child)

    def stop_all_workers(self, stack):
        # stop the traversal
        if stack.status == stack.IN_PROGRESS:
            self.stop_traversal(stack)

        # cancel existing workers
        cancelled = _cancel_workers(stack, self.thread_group_mgr,
                                    self.engine_id, self._rpc_client)
        if not cancelled:
            LOG.error(_LE("Failed to stop all workers of stack %(name)s "
                          ", stack cancel not complete"),
                      {'name': stack.name})
            return False

        LOG.info(_LI('[%(name)s(%(id)s)] Stopped all active workers for stack '
                     '%(action)s'),
                 {'name': stack.name, 'id': stack.id, 'action': stack.action})

        return True

    def _retrigger_replaced(self, is_update, rsrc, stack, msg_queue):
        graph = stack.convergence_dependencies.graph()
        key = (rsrc.id, is_update)
        if key not in graph and rsrc.replaces is not None:
            # This resource replaces old one and is not needed in
            # current traversal. You need to mark the resource as
            # DELETED so that it gets cleaned up in purge_db.
            values = {'action': rsrc.DELETE}
            db_api.resource_update_and_save(stack.context, rsrc.id, values)
            # The old resource might be in the graph (a rollback case);
            # just re-trigger it.
            key = (rsrc.replaces, is_update)
            cr = check_resource.CheckResource(self.engine_id, self._rpc_client,
                                              self.thread_group_mgr, msg_queue)
            cr.retrigger_check_resource(stack.context, is_update, key[0],
                                        stack)

    @context.request_context
    def check_resource(self, cnxt, resource_id, current_traversal, data,
                       is_update, adopt_stack_data):
        """Process a node in the dependency graph.

        The node may be associated with either an update or a cleanup of its
        associated resource.
        """
        resource_data = dict(sync_point.deserialize_input_data(data))
        rsrc, rsrc_owning_stack, stack = check_resource.load_resource(
            cnxt, resource_id, resource_data, is_update)

        if rsrc is None:
            return

        msg_queue = eventlet.queue.LightQueue()
        try:
            self.thread_group_mgr.add_msg_queue(stack.id, msg_queue)
            if current_traversal != stack.current_traversal:
                LOG.debug('[%s] Traversal cancelled; re-trigerring.',
                          current_traversal)
                self._retrigger_replaced(is_update, rsrc, stack, msg_queue)
            else:
                cr = check_resource.CheckResource(self.engine_id,
                                                  self._rpc_client,
                                                  self.thread_group_mgr,
                                                  msg_queue)
                cr.check(cnxt, resource_id, current_traversal, resource_data,
                         is_update, adopt_stack_data, rsrc, stack)
        finally:
            self.thread_group_mgr.remove_msg_queue(None,
                                                   stack.id, msg_queue)

    @context.request_context
    def cancel_check_resource(self, cnxt, stack_id):
        """Cancel check_resource for given stack.

        All the workers running for the given stack will be
        cancelled.
        """
        _cancel_check_resource(stack_id, self.engine_id, self.thread_group_mgr)


def _stop_traversal(stack):
    old_trvsl = stack.current_traversal
    updated = _update_current_traversal(stack)
    if not updated:
        LOG.warning(_LW("Failed to update stack %(name)s with new "
                        "traversal, aborting stack cancel"),
                    {'name': stack.name})
        return

    reason = 'Stack %(action)s cancelled' % {'action': stack.action}
    updated = stack.state_set(stack.action, stack.FAILED, reason)
    if not updated:
        LOG.warning(_LW("Failed to update stack %(name)s status"
                        " to %(action)_%(state)"),
                    {'name': stack.name, 'action': stack.action,
                    'state': stack.FAILED})
        return

    sync_point.delete_all(stack.context, stack.id, old_trvsl)


def _update_current_traversal(stack):
    previous_traversal = stack.current_traversal
    stack.current_traversal = uuidutils.generate_uuid()
    values = {'current_traversal': stack.current_traversal}
    return stack_objects.Stack.select_and_update(
        stack.context, stack.id, values,
        exp_trvsl=previous_traversal)


def _cancel_check_resource(stack_id, engine_id, tgm):
    LOG.debug('Cancelling workers for stack [%s] in engine [%s]',
              stack_id, engine_id)
    tgm.send(stack_id, rpc_api.THREAD_CANCEL)


def _wait_for_cancellation(stack, wait=5):
    # give enough time to wait till cancel is completed
    retries = CANCEL_RETRIES
    while retries > 0:
        retries -= 1
        eventlet.sleep(wait)
        engines = db_api.engine_get_all_locked_by_stack(
            stack.context, stack.id)
        if not engines:
            return True

    return False


def _cancel_workers(stack, tgm, local_engine_id, rpc_client):
    engines = db_api.engine_get_all_locked_by_stack(stack.context, stack.id)

    if not engines:
        return True

    # cancel workers running locally
    if local_engine_id in engines:
        _cancel_check_resource(stack.id, local_engine_id, tgm)
        engines.remove(local_engine_id)

    # cancel workers on remote engines
    for engine_id in engines:
        rpc_client.cancel_check_resource(stack.context, stack.id, engine_id)

    return _wait_for_cancellation(stack)
