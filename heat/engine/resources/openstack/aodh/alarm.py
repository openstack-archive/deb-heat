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

import six

from heat.common import exception
from heat.common.i18n import _
from heat.engine import constraints
from heat.engine import properties
from heat.engine.resources import alarm_base
from heat.engine import support
from heat.engine import watchrule


class AodhAlarm(alarm_base.BaseAlarm):
    """A resource that implements alarming service of Aodh.

    A resource that allows for the setting alarms based on threshold evaluation
    for a collection of samples. Also, you can define actions to take if state
    of watched resource will be satisfied specified conditions. For example, it
    can watch for the memory consumption and when it reaches 70% on a given
    instance if the instance has been up for more than 10 min, some action will
    be called.
    """

    PROPERTIES = (
        COMPARISON_OPERATOR, EVALUATION_PERIODS, METER_NAME, PERIOD,
        STATISTIC, THRESHOLD, MATCHING_METADATA, QUERY,
    ) = (
        'comparison_operator', 'evaluation_periods', 'meter_name', 'period',
        'statistic', 'threshold', 'matching_metadata', 'query',
    )

    QUERY_FACTOR_FIELDS = (
        QF_FIELD, QF_OP, QF_VALUE,
    ) = (
        'field', 'op', 'value',
    )

    QF_OP_VALS = constraints.AllowedValues(['le', 'ge', 'eq',
                                            'lt', 'gt', 'ne'])

    properties_schema = {
        COMPARISON_OPERATOR: properties.Schema(
            properties.Schema.STRING,
            _('Operator used to compare specified statistic with threshold.'),
            constraints=[
                constraints.AllowedValues(['ge', 'gt', 'eq', 'ne', 'lt',
                                           'le']),
            ],
            update_allowed=True
        ),
        EVALUATION_PERIODS: properties.Schema(
            properties.Schema.INTEGER,
            _('Number of periods to evaluate over.'),
            update_allowed=True
        ),
        METER_NAME: properties.Schema(
            properties.Schema.STRING,
            _('Meter name watched by the alarm.'),
            required=True
        ),
        PERIOD: properties.Schema(
            properties.Schema.INTEGER,
            _('Period (seconds) to evaluate over.'),
            update_allowed=True
        ),
        STATISTIC: properties.Schema(
            properties.Schema.STRING,
            _('Meter statistic to evaluate.'),
            constraints=[
                constraints.AllowedValues(['count', 'avg', 'sum', 'min',
                                           'max']),
            ],
            update_allowed=True
        ),
        THRESHOLD: properties.Schema(
            properties.Schema.NUMBER,
            _('Threshold to evaluate against.'),
            required=True,
            update_allowed=True
        ),
        MATCHING_METADATA: properties.Schema(
            properties.Schema.MAP,
            _('Meter should match this resource metadata (key=value) '
              'additionally to the meter_name.'),
            default={},
            update_allowed=True
        ),
        QUERY: properties.Schema(
            properties.Schema.LIST,
            _('A list of query factors, each comparing '
              'a Sample attribute with a value. '
              'Implicitly combined with matching_metadata, if any.'),
            update_allowed=True,
            support_status=support.SupportStatus(version='2015.1'),
            schema=properties.Schema(
                properties.Schema.MAP,
                schema={
                    QF_FIELD: properties.Schema(
                        properties.Schema.STRING,
                        _('Name of attribute to compare. '
                          'Names of the form metadata.user_metadata.X '
                          'or metadata.metering.X are equivalent to what '
                          'you can address through matching_metadata; '
                          'the former for Nova meters, '
                          'the latter for all others. '
                          'To see the attributes of your Samples, '
                          'use `ceilometer --debug sample-list`.')
                    ),
                    QF_OP: properties.Schema(
                        properties.Schema.STRING,
                        _('Comparison operator.'),
                        constraints=[QF_OP_VALS]
                    ),
                    QF_VALUE: properties.Schema(
                        properties.Schema.STRING,
                        _('String value with which to compare.')
                    )
                }
            )
        )
    }

    properties_schema.update(alarm_base.common_properties_schema)

    def get_alarm_props(self, props):
        """Apply all relevant compatibility xforms."""

        kwargs = self.actions_to_urls(props)
        kwargs['type'] = self.alarm_type
        if kwargs.get(self.METER_NAME) in alarm_base.NOVA_METERS:
            prefix = 'user_metadata.'
        else:
            prefix = 'metering.'

        rule = {}
        for field in ['period', 'evaluation_periods', 'threshold',
                      'statistic', 'comparison_operator', 'meter_name']:
            if field in kwargs:
                rule[field] = kwargs[field]
                del kwargs[field]
        mmd = props.get(self.MATCHING_METADATA) or {}
        query = props.get(self.QUERY) or []

        # make sure the matching_metadata appears in the query like this:
        # {field: metadata.$prefix.x, ...}
        for m_k, m_v in six.iteritems(mmd):
            key = 'metadata.%s' % prefix
            if m_k.startswith('metadata.'):
                m_k = m_k[len('metadata.'):]
            if m_k.startswith('metering.') or m_k.startswith('user_metadata.'):
                # check prefix
                m_k = m_k.split('.', 1)[-1]
            key = '%s%s' % (key, m_k)
            # NOTE(prazumovsky): type of query value must be a string, but
            # matching_metadata value type can not be a string, so we
            # must convert value to a string type.
            query.append(dict(field=key, op='eq', value=six.text_type(m_v)))
        if self.MATCHING_METADATA in kwargs:
            del kwargs[self.MATCHING_METADATA]
        if self.QUERY in kwargs:
            del kwargs[self.QUERY]
        if query:
            rule['query'] = query
        kwargs['threshold_rule'] = rule
        return kwargs

    def handle_create(self):
        props = self.get_alarm_props(self.properties)
        props['name'] = self.physical_resource_name()
        alarm = self.client().alarm.create(props)
        self.resource_id_set(alarm['alarm_id'])

        # the watchrule below is for backwards compatibility.
        # 1) so we don't create watch tasks unnecessarily
        # 2) to support CW stats post, we will redirect the request
        #    to ceilometer.
        wr = watchrule.WatchRule(context=self.context,
                                 watch_name=self.physical_resource_name(),
                                 rule=dict(self.properties),
                                 stack_id=self.stack.id)
        wr.state = wr.CEILOMETER_CONTROLLED
        wr.store()

    def handle_update(self, json_snippet, tmpl_diff, prop_diff):
        if prop_diff:
            kwargs = {}
            kwargs.update(self.properties)
            kwargs.update(prop_diff)
            self.client().alarm.update(self.resource_id,
                                       self.get_alarm_props(kwargs))

    def parse_live_resource_data(self, resource_properties, resource_data):
        record_reality = {}
        threshold_data = resource_data.get('threshold_rule').copy()
        threshold_data.update(resource_data)
        props_upd_allowed = set(
            self.PROPERTIES + alarm_base.COMMON_PROPERTIES) - {
            self.METER_NAME, alarm_base.TIME_CONSTRAINTS}
        for key in props_upd_allowed:
            record_reality.update({key: threshold_data.get(key)})

        return record_reality

    def handle_delete(self):
        try:
            wr = watchrule.WatchRule.load(
                self.context, watch_name=self.physical_resource_name())
            wr.destroy()
        except exception.EntityNotFound:
            pass

        return super(AodhAlarm, self).handle_delete()

    def handle_check(self):
        watch_name = self.physical_resource_name()
        watchrule.WatchRule.load(self.context, watch_name=watch_name)
        self.client().alarm.get(self.resource_id)

    def _show_resource(self):
        return self.client().alarm.get(self.resource_id)


class CombinationAlarm(alarm_base.BaseAlarm):
    """A resource that implements combination of Aodh alarms.

    Allows to use alarm as a combination of other alarms with some operator:
    activate this alarm if any alarm in combination has been activated or
    if all alarms in combination have been activated.
    """

    alarm_type = 'combination'

    # aodhclient doesn't support to manage combination-alarm,
    # so we use ceilometerclient to manage this resource as before,
    # after two release cycles, to hidden this resource.
    default_client_name = 'ceilometer'

    entity = 'alarms'

    support_status = support.SupportStatus(
        status=support.DEPRECATED,
        version='7.0.0',
        message=_('The combination alarm is deprecated and '
                  'disabled by default in Aodh.'),
        previous_status=support.SupportStatus(version='2014.1'))

    PROPERTIES = (
        ALARM_IDS, OPERATOR,
    ) = (
        'alarm_ids', 'operator',
    )

    properties_schema = {
        ALARM_IDS: properties.Schema(
            properties.Schema.LIST,
            _('List of alarm identifiers to combine.'),
            required=True,
            constraints=[constraints.Length(min=1)],
            update_allowed=True),
        OPERATOR: properties.Schema(
            properties.Schema.STRING,
            _('Operator used to combine the alarms.'),
            constraints=[constraints.AllowedValues(['and', 'or'])],
            update_allowed=True)
    }
    properties_schema.update(alarm_base.common_properties_schema)

    def handle_create(self):
        props = self.actions_to_urls(self.properties)
        props['name'] = self.physical_resource_name()
        props['type'] = self.alarm_type
        alarm = self.client().alarms.create(
            **self._reformat_properties(props))
        self.resource_id_set(alarm.alarm_id)

    def handle_update(self, json_snippet, tmpl_diff, prop_diff):
        if prop_diff:
            kwargs = {'alarm_id': self.resource_id}
            kwargs.update(prop_diff)
            alarms_client = self.client().alarms
            alarms_client.update(**self._reformat_properties(
                self.actions_to_urls(kwargs)))

    def handle_suspend(self):
        self.client().alarms.update(
            alarm_id=self.resource_id, enabled=False)

    def handle_resume(self):
        self.client().alarms.update(
            alarm_id=self.resource_id, enabled=True)

    def handle_check(self):
        self.client().alarms.get(self.resource_id)


def resource_mapping():
    return {
        'OS::Aodh::Alarm': AodhAlarm,
        'OS::Aodh::CombinationAlarm': CombinationAlarm,
    }
