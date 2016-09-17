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

from oslo_log import log as logging
from oslo_utils import timeutils

from heat.common import exception
from heat.common.i18n import _
from heat.common.i18n import _LI
from heat.common.i18n import _LW
from heat.engine import stack
from heat.engine import timestamp
from heat.objects import stack as stack_object
from heat.objects import watch_data as watch_data_objects
from heat.objects import watch_rule as watch_rule_objects
from heat.rpc import api as rpc_api

LOG = logging.getLogger(__name__)


class WatchRule(object):
    WATCH_STATES = (
        ALARM,
        NORMAL,
        NODATA,
        SUSPENDED,
        CEILOMETER_CONTROLLED,
    ) = (
        rpc_api.WATCH_STATE_ALARM,
        rpc_api.WATCH_STATE_OK,
        rpc_api.WATCH_STATE_NODATA,
        rpc_api.WATCH_STATE_SUSPENDED,
        rpc_api.WATCH_STATE_CEILOMETER_CONTROLLED,
    )
    ACTION_MAP = {ALARM: 'AlarmActions',
                  NORMAL: 'OKActions',
                  NODATA: 'InsufficientDataActions'}

    created_at = timestamp.Timestamp(watch_rule_objects.WatchRule.get_by_id,
                                     'created_at')
    updated_at = timestamp.Timestamp(watch_rule_objects.WatchRule.get_by_id,
                                     'updated_at')

    def __init__(self, context, watch_name, rule, stack_id=None,
                 state=NODATA, wid=None, watch_data=None,
                 last_evaluated=timeutils.utcnow()):
        self.context = context
        self.now = timeutils.utcnow()
        self.name = watch_name
        self.state = state
        self.rule = rule
        self.stack_id = stack_id
        period = 0
        if 'Period' in rule:
            period = int(rule['Period'])
        elif 'period' in rule:
            period = int(rule['period'])
        self.timeperiod = datetime.timedelta(seconds=period)
        self.id = wid
        self.watch_data = watch_data or []
        self.last_evaluated = last_evaluated

    @classmethod
    def load(cls, context, watch_name=None, watch=None):
        """Load the watchrule object.

        The object can be loaded either from the DB by name or from an existing
        DB object.
        """
        if watch is None:
            try:
                watch = watch_rule_objects.WatchRule.get_by_name(context,
                                                                 watch_name)
            except Exception as ex:
                LOG.warning(_LW('WatchRule.load (%(watch_name)s) db error '
                                '%(ex)s'), {'watch_name': watch_name,
                                            'ex': ex})
        if watch is None:
            raise exception.EntityNotFound(entity='Watch Rule',
                                           name=watch_name)
        else:
            return cls(context=context,
                       watch_name=watch.name,
                       rule=watch.rule,
                       stack_id=watch.stack_id,
                       state=watch.state,
                       wid=watch.id,
                       watch_data=watch.watch_data,
                       last_evaluated=watch.last_evaluated)

    def store(self):
        """Store the watchrule in the database and return its ID.

        If self.id is set, we update the existing rule.
        """

        wr_values = {
            'name': self.name,
            'rule': self.rule,
            'state': self.state,
            'stack_id': self.stack_id
        }

        if not self.id:
            wr = watch_rule_objects.WatchRule.create(self.context, wr_values)
            self.id = wr.id
        else:
            watch_rule_objects.WatchRule.update_by_id(self.context, self.id,
                                                      wr_values)

    def destroy(self):
        """Delete the watchrule from the database."""
        if self.id:
            watch_rule_objects.WatchRule.delete(self.context, self.id)

    def do_data_cmp(self, data, threshold):
        op = self.rule['ComparisonOperator']
        if op == 'GreaterThanThreshold':
            return data > threshold
        elif op == 'GreaterThanOrEqualToThreshold':
            return data >= threshold
        elif op == 'LessThanThreshold':
            return data < threshold
        elif op == 'LessThanOrEqualToThreshold':
            return data <= threshold
        else:
            return False

    def do_Maximum(self):
        data = 0
        have_data = False
        for d in self.watch_data:
            if d.created_at < self.now - self.timeperiod:
                continue
            if not have_data:
                data = float(d.data[self.rule['MetricName']]['Value'])
                have_data = True
            if float(d.data[self.rule['MetricName']]['Value']) > data:
                data = float(d.data[self.rule['MetricName']]['Value'])

        if not have_data:
            return self.NODATA

        if self.do_data_cmp(data,
                            float(self.rule['Threshold'])):
            return self.ALARM
        else:
            return self.NORMAL

    def do_Minimum(self):
        data = 0
        have_data = False
        for d in self.watch_data:
            if d.created_at < self.now - self.timeperiod:
                continue
            if not have_data:
                data = float(d.data[self.rule['MetricName']]['Value'])
                have_data = True
            elif float(d.data[self.rule['MetricName']]['Value']) < data:
                data = float(d.data[self.rule['MetricName']]['Value'])

        if not have_data:
            return self.NODATA

        if self.do_data_cmp(data,
                            float(self.rule['Threshold'])):
            return self.ALARM
        else:
            return self.NORMAL

    def do_SampleCount(self):
        """Count all samples within the specified period."""
        data = 0
        for d in self.watch_data:
            if d.created_at < self.now - self.timeperiod:
                continue
            data = data + 1

        if self.do_data_cmp(data,
                            float(self.rule['Threshold'])):
            return self.ALARM
        else:
            return self.NORMAL

    def do_Average(self):
        data = 0
        samples = 0
        for d in self.watch_data:
            if d.created_at < self.now - self.timeperiod:
                continue
            samples = samples + 1
            data = data + float(d.data[self.rule['MetricName']]['Value'])

        if samples == 0:
            return self.NODATA

        data = data / samples
        if self.do_data_cmp(data,
                            float(self.rule['Threshold'])):
            return self.ALARM
        else:
            return self.NORMAL

    def do_Sum(self):
        data = 0
        for d in self.watch_data:
            if d.created_at < self.now - self.timeperiod:
                LOG.debug('ignoring %s' % str(d.data))
                continue
            data = data + float(d.data[self.rule['MetricName']]['Value'])

        if self.do_data_cmp(data,
                            float(self.rule['Threshold'])):
            return self.ALARM
        else:
            return self.NORMAL

    def get_alarm_state(self):
        fn = getattr(self, 'do_%s' % self.rule['Statistic'])
        return fn()

    def evaluate(self):
        if self.state in [self.CEILOMETER_CONTROLLED, self.SUSPENDED]:
            return []
        # has enough time progressed to run the rule
        self.now = timeutils.utcnow()
        if self.now < (self.last_evaluated + self.timeperiod):
            return []
        return self.run_rule()

    def get_details(self):
        return {'alarm': self.name,
                'state': self.state}

    def run_rule(self):
        new_state = self.get_alarm_state()
        actions = self.rule_actions(new_state)
        self.state = new_state

        self.last_evaluated = self.now
        self.store()
        return actions

    def rule_actions(self, new_state):
        LOG.info(_LI('WATCH: stack:%(stack)s, watch_name:%(watch_name)s, '
                     'new_state:%(new_state)s'), {'stack': self.stack_id,
                                                  'watch_name': self.name,
                                                  'new_state': new_state})
        actions = []
        if self.ACTION_MAP[new_state] not in self.rule:
            LOG.info(_LI('no action for new state %s'), new_state)
        else:
            s = stack_object.Stack.get_by_id(
                self.context,
                self.stack_id)
            stk = stack.Stack.load(self.context, stack=s)
            if (stk.action != stk.DELETE
                    and stk.status == stk.COMPLETE):
                for refid in self.rule[self.ACTION_MAP[new_state]]:
                    actions.append(stk.resource_by_refid(refid).signal)
            else:
                LOG.warning(_LW("Could not process watch state %s for stack"),
                            new_state)
        return actions

    def _to_ceilometer(self, data):
        clients = self.context.clients
        sample = {}
        sample['counter_type'] = 'gauge'

        for k, d in iter(data.items()):
            if k == 'Namespace':
                continue
            sample['counter_name'] = k
            sample['counter_volume'] = d['Value']
            sample['counter_unit'] = d['Unit']
            dims = d.get('Dimensions', {})
            if isinstance(dims, list):
                dims = dims[0]
            sample['resource_metadata'] = dims
            sample['resource_id'] = dims.get('InstanceId')
            LOG.debug('new sample:%(k)s data:%(sample)s' % {
                      'k': k, 'sample': sample})
            clients.client('ceilometer').samples.create(**sample)

    def create_watch_data(self, data):
        if self.state == self.CEILOMETER_CONTROLLED:
            # this is a short term measure for those that have cfn-push-stats
            # within their templates, but want to use Ceilometer alarms.

            self._to_ceilometer(data)
            return

        if self.state == self.SUSPENDED:
            LOG.debug('Ignoring metric data for %s, SUSPENDED state'
                      % self.name)
            return []

        if self.rule['MetricName'] not in data:
            # Our simplified cloudwatch implementation only expects a single
            # Metric associated with each alarm, but some cfn-push-stats
            # options, e.g --haproxy try to push multiple metrics when we
            # actually only care about one (the one we're alarming on)
            # so just ignore any data which doesn't contain MetricName
            LOG.debug('Ignoring metric data (only accept %(metric)s) '
                      ': %(data)s' % {'metric': self.rule['MetricName'],
                                      'data': data})
            return

        watch_data = {
            'data': data,
            'watch_rule_id': self.id
        }
        wd = watch_data_objects.WatchData.create(self.context, watch_data)
        LOG.debug('new watch:%(name)s data:%(data)s'
                  % {'name': self.name, 'data': str(wd.data)})

    def state_set(self, state):
        """Persistently store the watch state."""
        if state not in self.WATCH_STATES:
            raise ValueError(_("Invalid watch state %s") % state)

        self.state = state
        self.store()

    def set_watch_state(self, state):
        """Temporarily set the watch state.

        :returns: list of functions to be scheduled in the stack ThreadGroup
                  for the specified state.
        """

        if state not in self.WATCH_STATES:
            raise ValueError(_('Unknown watch state %s') % state)

        actions = []
        if state != self.state:
            actions = self.rule_actions(state)
            if actions:
                LOG.debug("Overriding state %(self_state)s for watch "
                          "%(name)s with %(state)s"
                          % {'self_state': self.state, 'name': self.name,
                             'state': state})
            else:
                LOG.warning(_LW("Unable to override state %(state)s for "
                                "watch %(name)s"), {'state': self.state,
                                                    'name': self.name})
        return actions


def rule_can_use_sample(wr, stats_data):
    def match_dimesions(rule, data):
        for k, v in iter(rule.items()):
            if k not in data:
                return False
            elif v != data[k]:
                return False
        return True

    if wr.state == WatchRule.SUSPENDED:
        return False
    if wr.state == WatchRule.CEILOMETER_CONTROLLED:
        metric = wr.rule['meter_name']
        rule_dims = {}
        for k, v in iter(wr.rule.get('matching_metadata', {}).items()):
            name = k.split('.')[-1]
            rule_dims[name] = v
    else:
        metric = wr.rule['MetricName']
        rule_dims = dict((d['Name'], d['Value'])
                         for d in wr.rule.get('Dimensions', []))

    if metric not in stats_data:
        return False

    for k, v in iter(stats_data.items()):
        if k == 'Namespace':
            continue
        if k == metric:
            data_dims = v.get('Dimensions', {})
            if isinstance(data_dims, list):
                data_dims = data_dims[0]
            if match_dimesions(rule_dims, data_dims):
                return True
    return False
