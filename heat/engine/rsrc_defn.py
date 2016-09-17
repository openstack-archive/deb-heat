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

import collections
import copy
import itertools
import operator
import warnings

import six

from heat.common import exception
from heat.common.i18n import repr_wrapper
from heat.engine import function
from heat.engine import properties


__all__ = ['ResourceDefinition']


@repr_wrapper
class ResourceDefinitionCore(object):
    """A definition of a resource, independent of any template format."""

    class Diff(object):
        """A diff between two versions of the same resource definition."""

        def __init__(self, old_defn, new_defn):
            if not (isinstance(old_defn, ResourceDefinitionCore) and
                    isinstance(new_defn, ResourceDefinitionCore)):
                raise TypeError

            self.old_defn = old_defn
            self.new_defn = new_defn

        def properties_changed(self):
            """Return True if the resource properties have changed."""
            return self.old_defn._properties != self.new_defn._properties

        def metadata_changed(self):
            """Return True if the resource metadata has changed."""
            return self.old_defn._metadata != self.new_defn._metadata

        def update_policy_changed(self):
            """Return True if the resource update policy has changed."""
            return self.old_defn._update_policy != self.new_defn._update_policy

        def __bool__(self):
            """Return True if anything has changed."""
            return (self.properties_changed() or
                    self.metadata_changed() or
                    self.update_policy_changed())

        __nonzero__ = __bool__

    DELETION_POLICIES = (
        DELETE, RETAIN, SNAPSHOT,
    ) = (
        'Delete', 'Retain', 'Snapshot',
    )

    def __init__(self, name, resource_type, properties=None, metadata=None,
                 depends=None, deletion_policy=None, update_policy=None,
                 description=None, external_id=None, condition=None):
        """Initialise with the parsed definition of a resource.

        Any intrinsic functions present in any of the sections should have been
        parsed into Function objects before constructing the definition.

        :param name: The name of the resource (for use in error messages)
        :param resource_type: The resource type
        :param properties: A dictionary of supplied property values
        :param metadata: The supplied metadata
        :param depends: A list of resource names on which this resource depends
        :param deletion_policy: The deletion policy for the resource
        :param update_policy: A dictionary of supplied update policies
        :param description: A string describing the resource
        :param external_id: A uuid of an external resource
        :param condition: A condition name associated with the resource
        """
        self.name = name
        self.resource_type = resource_type
        self.description = description or ''
        self._properties = properties
        self._metadata = metadata
        self._depends = depends
        self._deletion_policy = deletion_policy
        self._update_policy = update_policy
        self._external_id = external_id
        self._condition = condition

        self._hash = hash(self.resource_type)
        self._rendering = None

        assert isinstance(self.description, six.string_types)

        if properties is not None:
            assert isinstance(properties, (collections.Mapping,
                                           function.Function))
            self._hash ^= _hash_data(properties)

        if metadata is not None:
            assert isinstance(metadata, (collections.Mapping,
                                         function.Function))
            self._hash ^= _hash_data(metadata)

        if depends is not None:
            assert isinstance(depends, (collections.Sequence,
                                        function.Function))
            assert not isinstance(depends, six.string_types)
            self._hash ^= _hash_data(depends)

        if deletion_policy is not None:
            assert deletion_policy in self.DELETION_POLICIES
            self._hash ^= _hash_data(deletion_policy)

        if update_policy is not None:
            assert isinstance(update_policy, (collections.Mapping,
                                              function.Function))
            self._hash ^= _hash_data(update_policy)

        if external_id is not None:
            assert isinstance(external_id, (six.string_types,
                                            function.Function))
            self._hash ^= _hash_data(external_id)
            self._deletion_policy = self.RETAIN

        if condition is not None:
            assert isinstance(condition, six.string_types)
            self._hash ^= hash(condition)

    def freeze(self, **overrides):
        """Return a frozen resource definition, with all functions resolved.

        This return a new resource definition with fixed data (containing no
        intrinsic functions). Named arguments passed to this method override
        the values passed as arguments to the constructor.
        """
        if getattr(self, '_frozen', False) and not overrides:
            return self

        def arg_item(attr_name):
            name = attr_name.lstrip('_')
            if name in overrides:
                value = overrides[name]
                if not value and getattr(self, attr_name) is None:
                    value = None
            else:
                value = function.resolve(getattr(self, attr_name))

            return name, value

        args = ('name', 'resource_type', '_properties', '_metadata',
                '_depends', '_deletion_policy', '_update_policy',
                'description', '_external_id', '_condition')

        defn = type(self)(**dict(arg_item(a) for a in args))
        defn._frozen = True
        return defn

    def reparse(self, stack, template):
        """Reinterpret the resource definition in the context of a new stack.

        This returns a new resource definition, with all of the functions
        parsed in the context of the specified stack and template.
        """
        assert not getattr(self, '_frozen', False
                           ), "Cannot re-parse a frozen definition"

        def reparse_snippet(snippet):
            return template.parse(stack, copy.deepcopy(snippet))

        return type(self)(
            self.name, self.resource_type,
            properties=reparse_snippet(self._properties),
            metadata=reparse_snippet(self._metadata),
            depends=reparse_snippet(self._depends),
            deletion_policy=reparse_snippet(self._deletion_policy),
            update_policy=reparse_snippet(self._update_policy),
            external_id=reparse_snippet(self._external_id),
            condition=self._condition)

    def dep_attrs(self, resource_name):
        """Iterate over attributes of a given resource that this references.

        Return an iterator over dependent attributes for specified
        resource_name in resources' properties and metadata fields.
        """
        return itertools.chain(function.dep_attrs(self._properties,
                                                  resource_name),
                               function.dep_attrs(self._metadata,
                                                  resource_name))

    def dependencies(self, stack):
        """Return the Resource objects in given stack on which this depends."""
        def path(section):
            return '.'.join([self.name, section])

        def get_resource(res_name):
            if res_name not in stack:
                raise exception.InvalidTemplateReference(resource=res_name,
                                                         key=self.name)
            return stack[res_name]

        def strict_func_deps(data, datapath):
            return six.moves.filter(
                lambda r: getattr(r, 'strict_dependency', True),
                function.dependencies(data, datapath))

        explicit_depends = [] if self._depends is None else self._depends
        prop_deps = strict_func_deps(self._properties, path(PROPERTIES))
        metadata_deps = strict_func_deps(self._metadata, path(METADATA))

        # (ricolin) External resource should not depend on any other resources.
        # This operation is not allowed for now.
        if self.external_id():
            if explicit_depends:
                raise exception.InvalidExternalResourceDependency(
                    external_id=self.external_id(),
                    resource_type=self.resource_type
                )
            return itertools.chain()

        return itertools.chain((get_resource(dep) for dep in explicit_depends),
                               prop_deps, metadata_deps)

    def properties(self, schema, context=None):
        """Return a Properties object representing the resource properties.

        The Properties object is constructed from the given schema, and may
        require a context to validate constraints.
        """
        return properties.Properties(schema, self._properties or {},
                                     function.resolve, self.name, context,
                                     section=PROPERTIES)

    def deletion_policy(self):
        """Return the deletion policy for the resource.

        The policy will be one of those listed in DELETION_POLICIES.
        """
        return function.resolve(self._deletion_policy) or self.DELETE

    def update_policy(self, schema, context=None):
        """Return a Properties object representing the resource update policy.

        The Properties object is constructed from the given schema, and may
        require a context to validate constraints.
        """
        return properties.Properties(schema, self._update_policy or {},
                                     function.resolve, self.name, context,
                                     section=UPDATE_POLICY)

    def metadata(self):
        """Return the resource metadata."""
        return function.resolve(self._metadata) or {}

    def external_id(self):
        """Return the external resource id."""
        return function.resolve(self._external_id)

    def render_hot(self):
        """Return a HOT snippet for the resource definition."""
        if self._rendering is None:
            attrs = {
                'type': 'resource_type',
                'properties': '_properties',
                'metadata': '_metadata',
                'deletion_policy': '_deletion_policy',
                'update_policy': '_update_policy',
                'depends_on': '_depends',
                'external_id': '_external_id',
                'condition': '_condition'
            }

            def rawattrs():
                """Get an attribute with function objects stripped out."""
                for key, attr in attrs.items():
                    value = getattr(self, attr)
                    if value is not None:
                        yield key, copy.deepcopy(value)

            self._rendering = dict(rawattrs())

        return self._rendering

    def __sub__(self, previous):
        """Calculate the difference between this definition and a previous one.

        Return a Diff object that can be used to establish differences between
        this definition and a previous definition of the same resource.
        """
        if not isinstance(previous, ResourceDefinitionCore):
            return NotImplemented

        return self.Diff(previous, self)

    def __eq__(self, other):
        """Compare this resource definition for equality with another.

        Two resource definitions are considered to be equal if they can be
        generated from the same template snippet. The name of the resource is
        ignored, as are the actual values that any included functions resolve
        to.
        """
        if not isinstance(other, ResourceDefinitionCore):
            return NotImplemented

        return self.render_hot() == other.render_hot()

    def __ne__(self, other):
        """Compare this resource definition for inequality with another.

        See __eq__() for the definition of equality.
        """
        equal = self.__eq__(other)
        if equal is NotImplemented:
            return NotImplemented

        return not equal

    def __hash__(self):
        """Return a hash value for this resource definition.

        Resource definitions that compare equal will have the same hash. (In
        particular, the resource name is *not* taken into account.) See
        the __eq__() method for the definition of equality.
        """
        return self._hash

    def __repr__(self):
        """Return a string representation of the resource definition."""

        def arg_repr(arg_name):
            return '='.join([arg_name, repr(getattr(self, '_%s' % arg_name))])

        args = ('properties', 'metadata', 'depends',
                'deletion_policy', 'update_policy', 'condition')
        data = {
            'classname': type(self).__name__,
            'name': repr(self.name),
            'type': repr(self.resource_type),
            'args': ', '.join(arg_repr(n) for n in args)
        }
        return '%(classname)s(%(name)s, %(type)s, %(args)s)' % data


_KEYS = (
    TYPE, PROPERTIES, METADATA, DELETION_POLICY, UPDATE_POLICY,
    DEPENDS_ON, DESCRIPTION,
) = (
    'Type', 'Properties', 'Metadata', 'DeletionPolicy', 'UpdatePolicy',
    'DependsOn', 'Description',
)


class ResourceDefinition(ResourceDefinitionCore, collections.Mapping):
    """A resource definition that also acts like a cfn template snippet.

    This class exists only for backwards compatibility with existing resource
    plugins and unit tests; it is deprecated and will be replaced with
    ResourceDefinitionCore, possibly as soon as the Ocata release.
    """

    _deprecation_msg = (
        'Reading the ResourceDefinition as if it were a snippet of a '
        'CloudFormation template is deprecated, and the ability to treat it '
        'as such will be removed in the future. Resource plugins should use '
        'the ResourceDefinition API to work with the definition of the '
        'resource instance.')

    class Diff(ResourceDefinitionCore.Diff, collections.Mapping):
        """A resource definition diff that acts like a cfn template snippet.

        This class exists only for backwards compatibility with existing
        resource plugins and unit tests; it is deprecated and could be removed
        as soon as the Ocata release. Prefer using the API directly rather than
        treating the diff as a dict containing the differences between two cfn
        template snippets.
        """

        _deprecation_msg = (
            'Reading the ResourceDefinition Diff as if it were a diff of two '
            'snippets from CloudFormation templates is deprecated, and the '
            'ability to treat it as such will be removed in the future. '
            'Resource plugins should use the ResourceDefinition.Diff API and '
            'the ResourceDefinition API to detect changes in the definition '
            'and work with the new definition of the resource.')

        def __contains__(self, key):
            warnings.warn(self._deprecation_msg, DeprecationWarning)

            if key == PROPERTIES:
                return self.properties_changed()
            elif key == METADATA:
                return self.metadata_changed()
            elif key == UPDATE_POLICY:
                return self.update_policy_changed()
            else:
                return False

        def __iter__(self):
            return (k for k in _KEYS if k in self)

        def __getitem__(self, key):
            if key not in self:
                raise KeyError
            return self.new_defn.get(key)

        def __len__(self):
            return len(list(iter(self)))

        def __repr__(self):
            """Return a string representation of the diff."""
            return 'ResourceDefinition.Diff %s' % repr(dict(self))

    def __eq__(self, other):
        """Compare this resource definition for equality with another.

        Two resource definitions are considered to be equal if they can be
        generated from the same template snippet. The name of the resource is
        ignored, as are the actual values that any included functions resolve
        to.

        This method can also compare the resource definition to a template
        snippet. In this case, two snippets are considered equal if they
        compare equal in a dictionary comparison. (Specifically, this means
        that intrinsic functions are compared by their results.) This exists
        solely to not break existing unit tests.
        """
        if not isinstance(other, ResourceDefinitionCore):
            if isinstance(other, collections.Mapping):
                return dict(self) == other

        return super(ResourceDefinition, self).__eq__(other)

    __hash__ = ResourceDefinitionCore.__hash__

    def __iter__(self):
        """Iterate over the available CFN template keys.

        This is for backwards compatibility with existing code that expects a
        parsed-JSON template snippet.
        """
        warnings.warn(self._deprecation_msg, DeprecationWarning)

        yield TYPE
        if self._properties is not None:
            yield PROPERTIES
        if self._metadata is not None:
            yield METADATA
        if self._deletion_policy is not None:
            yield DELETION_POLICY
        if self._update_policy is not None:
            yield UPDATE_POLICY
        if self._depends:
            yield DEPENDS_ON
        if self.description:
            yield DESCRIPTION

    def __getitem__(self, key):
        """Get the specified item from a CFN template snippet.

        This is for backwards compatibility with existing code that expects a
        parsed-JSON template snippet.
        """
        warnings.warn(self._deprecation_msg, DeprecationWarning)

        if key == TYPE:
            return self.resource_type
        elif key == PROPERTIES:
            if self._properties is not None:
                return self._properties
        elif key == METADATA:
            if self._metadata is not None:
                return self._metadata
        elif key == DELETION_POLICY:
            if self._deletion_policy is not None:
                return self._deletion_policy
        elif key == UPDATE_POLICY:
            if self._update_policy is not None:
                return self._update_policy
        elif key == DEPENDS_ON:
            if self._depends:
                if len(self._depends) == 1:
                    return self._depends[0]
                return self._depends
        elif key == DESCRIPTION:
            if self.description:
                return self.description

        raise KeyError(key)

    def __len__(self):
        """Return the number of available CFN template keys.

        This is for backwards compatibility with existing code that expects a
        parsed-JSON template snippet.
        """
        return len(list(iter(self)))

    def __repr__(self):
        """Return a string representation of the resource definition."""
        return 'ResourceDefinition %s' % repr(dict(self))


def _hash_data(data):
    """Return a stable hash value for an arbitrary parsed-JSON data snippet."""
    if isinstance(data, function.Function):
        data = copy.deepcopy(data)

    if not isinstance(data, six.string_types):
        if isinstance(data, collections.Sequence):
            return hash(tuple(_hash_data(d) for d in data))

        if isinstance(data, collections.Mapping):
            item_hashes = (hash(k) ^ _hash_data(v) for k, v in data.items())
            return six.moves.reduce(operator.xor, item_hashes, 0)

    return hash(data)
