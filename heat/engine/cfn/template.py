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
from heat.engine.cfn import functions as cfn_funcs
from heat.engine import function
from heat.engine.hot import functions as hot_funcs
from heat.engine import parameters
from heat.engine import rsrc_defn
from heat.engine import template_common


class CfnTemplateBase(template_common.CommonTemplate):
    """The base implementation of cfn template."""

    SECTIONS = (
        VERSION, ALTERNATE_VERSION,
        DESCRIPTION, MAPPINGS, PARAMETERS, RESOURCES, OUTPUTS,
    ) = (
        'AWSTemplateFormatVersion', 'HeatTemplateFormatVersion',
        'Description', 'Mappings', 'Parameters', 'Resources', 'Outputs',
    )

    OUTPUT_KEYS = (
        OUTPUT_DESCRIPTION, OUTPUT_VALUE,
    ) = (
        'Description', 'Value',
    )

    SECTIONS_NO_DIRECT_ACCESS = set([PARAMETERS, VERSION, ALTERNATE_VERSION])

    _RESOURCE_KEYS = (
        RES_TYPE, RES_PROPERTIES, RES_METADATA, RES_DEPENDS_ON,
        RES_DELETION_POLICY, RES_UPDATE_POLICY, RES_DESCRIPTION,
    ) = (
        'Type', 'Properties', 'Metadata', 'DependsOn',
        'DeletionPolicy', 'UpdatePolicy', 'Description',
    )

    extra_rsrc_defn = ()
    functions = {
        'Fn::FindInMap': cfn_funcs.FindInMap,
        'Fn::GetAZs': cfn_funcs.GetAZs,
        'Ref': cfn_funcs.Ref,
        'Fn::GetAtt': cfn_funcs.GetAtt,
        'Fn::Select': cfn_funcs.Select,
        'Fn::Join': cfn_funcs.Join,
        'Fn::Base64': cfn_funcs.Base64,
    }

    deletion_policies = {
        'Delete': rsrc_defn.ResourceDefinition.DELETE,
        'Retain': rsrc_defn.ResourceDefinition.RETAIN,
        'Snapshot': rsrc_defn.ResourceDefinition.SNAPSHOT
    }

    HOT_TO_CFN_RES_ATTRS = {'type': RES_TYPE,
                            'properties': RES_PROPERTIES,
                            'metadata': RES_METADATA,
                            'depends_on': RES_DEPENDS_ON,
                            'deletion_policy': RES_DELETION_POLICY,
                            'update_policy': RES_UPDATE_POLICY}

    def __getitem__(self, section):
        """Get the relevant section in the template."""
        if section not in self.SECTIONS:
            raise KeyError(_('"%s" is not a valid template section') % section)
        if section in self.SECTIONS_NO_DIRECT_ACCESS:
            raise KeyError(
                _('Section %s can not be accessed directly.') % section)

        if section == self.DESCRIPTION:
            default = 'No description'
        else:
            default = {}

        # if a section is None (empty yaml section) return {}
        # to be consistent with an empty json section.
        return self.t.get(section) or default

    def param_schemata(self, param_defaults=None):
        params = self.t.get(self.PARAMETERS) or {}
        pdefaults = param_defaults or {}
        for name, schema in six.iteritems(params):
            if name in pdefaults:
                params[name][parameters.DEFAULT] = pdefaults[name]

        return dict((name, parameters.Schema.from_dict(name, schema))
                    for name, schema in six.iteritems(params))

    def get_section_name(self, section):
        return section

    def parameters(self, stack_identifier, user_params, param_defaults=None):
        return parameters.Parameters(stack_identifier, self,
                                     user_params=user_params,
                                     param_defaults=param_defaults)

    def resource_definitions(self, stack):
        resources = self.t.get(self.RESOURCES) or {}

        def rsrc_defn_item(name, snippet):
            data = self.parse(stack, snippet)

            depends = data.get(self.RES_DEPENDS_ON)
            if isinstance(depends, six.string_types):
                depends = [depends]

            deletion_policy = function.resolve(
                data.get(self.RES_DELETION_POLICY))
            if deletion_policy is not None:
                if deletion_policy not in self.deletion_policies:
                    msg = _('Invalid deletion policy "%s"') % deletion_policy
                    raise exception.StackValidationFailed(message=msg)
                else:
                    deletion_policy = self.deletion_policies[deletion_policy]

            kwargs = {
                'resource_type': data.get(self.RES_TYPE),
                'properties': data.get(self.RES_PROPERTIES),
                'metadata': data.get(self.RES_METADATA),
                'depends': depends,
                'deletion_policy': deletion_policy,
                'update_policy': data.get(self.RES_UPDATE_POLICY),
                'description': data.get(self.RES_DESCRIPTION) or ''
            }

            for key in self.extra_rsrc_defn:
                kwargs[key.lower()] = data.get(key)

            defn = rsrc_defn.ResourceDefinition(name, **kwargs)
            return name, defn

        return dict(
            rsrc_defn_item(name, data)
            for name, data in resources.items() if self.get_res_condition(
                stack, data, name))

    def add_resource(self, definition, name=None):
        if name is None:
            name = definition.name
        hot_tmpl = definition.render_hot()

        cfn_tmpl = dict((self.HOT_TO_CFN_RES_ATTRS[k], v)
                        for k, v in hot_tmpl.items())

        if len(cfn_tmpl.get(self.RES_DEPENDS_ON, [])) == 1:
            cfn_tmpl[self.RES_DEPENDS_ON] = cfn_tmpl[self.RES_DEPENDS_ON][0]

        if self.t.get(self.RESOURCES) is None:
            self.t[self.RESOURCES] = {}
        self.t[self.RESOURCES][name] = cfn_tmpl


class CfnTemplate(CfnTemplateBase):

    CONDITION = 'Condition'
    CONDITIONS = 'Conditions'
    SECTIONS = CfnTemplateBase.SECTIONS + (CONDITIONS,)

    RES_CONDITION = CONDITION
    _RESOURCE_KEYS = CfnTemplateBase._RESOURCE_KEYS + (RES_CONDITION,)
    HOT_TO_CFN_RES_ATTRS = CfnTemplateBase.HOT_TO_CFN_RES_ATTRS
    HOT_TO_CFN_RES_ATTRS.update({'condition': RES_CONDITION})

    extra_rsrc_defn = CfnTemplateBase.extra_rsrc_defn + (RES_CONDITION,)

    OUTPUT_CONDITION = CONDITION
    OUTPUT_KEYS = CfnTemplateBase.OUTPUT_KEYS + (OUTPUT_CONDITION,)

    functions = {
        'Fn::FindInMap': cfn_funcs.FindInMap,
        'Fn::GetAZs': cfn_funcs.GetAZs,
        'Ref': cfn_funcs.Ref,
        'Fn::GetAtt': cfn_funcs.GetAtt,
        'Fn::Select': cfn_funcs.Select,
        'Fn::Join': cfn_funcs.Join,
        'Fn::Split': cfn_funcs.Split,
        'Fn::Replace': cfn_funcs.Replace,
        'Fn::Base64': cfn_funcs.Base64,
        'Fn::MemberListToMap': cfn_funcs.MemberListToMap,
        'Fn::ResourceFacade': cfn_funcs.ResourceFacade,
        'Fn::If': hot_funcs.If,
    }

    condition_functions = {
        'Fn::Equals': hot_funcs.Equals,
        'Ref': cfn_funcs.ParamRef,
        'Fn::FindInMap': cfn_funcs.FindInMap,
        'Fn::Not': cfn_funcs.Not,
        'Fn::And': hot_funcs.And,
        'Fn::Or': hot_funcs.Or
    }

    def __init__(self, tmpl, template_id=None, files=None, env=None):
        super(CfnTemplate, self).__init__(tmpl, template_id, files, env)

        self._parser_condition_functions = dict(
            (n, function.Invalid) for n in self.functions)
        self._parser_condition_functions.update(self.condition_functions)
        self.merge_sections = [self.PARAMETERS, self.CONDITIONS]

    def get_condition_definitions(self):
        return self[self.CONDITIONS]

    def has_condition_section(self, snippet):
        if snippet and self.CONDITION in snippet:
            return True

        return False

    def validate_resource_definition(self, name, data):
        super(CfnTemplate, self).validate_resource_definition(name, data)

        self.validate_resource_key_type(
            self.RES_CONDITION,
            (six.string_types, bool),
            'string or boolean', self._RESOURCE_KEYS, name, data)


class HeatTemplate(CfnTemplateBase):
    functions = {
        'Fn::FindInMap': cfn_funcs.FindInMap,
        'Fn::GetAZs': cfn_funcs.GetAZs,
        'Ref': cfn_funcs.Ref,
        'Fn::GetAtt': cfn_funcs.GetAtt,
        'Fn::Select': cfn_funcs.Select,
        'Fn::Join': cfn_funcs.Join,
        'Fn::Split': cfn_funcs.Split,
        'Fn::Replace': cfn_funcs.Replace,
        'Fn::Base64': cfn_funcs.Base64,
        'Fn::MemberListToMap': cfn_funcs.MemberListToMap,
        'Fn::ResourceFacade': cfn_funcs.ResourceFacade,
    }
