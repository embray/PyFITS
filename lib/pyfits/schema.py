import warnings

import numpy as np

from pyfits.card import KEYWORD_LENGTH


__all__ = ['Schema']


class SchemaError(Exception):
    """Base class for schema-related exceptions."""

    def __init__(self, name, message):
        self.name = name
        self.message = message
        super(SchemaError, self).__init__(name, message)

    def __str__(self):
        return '%s in %s: %s' % (self.__class__.__name__, self.name,
                                 self.message)

class SchemaDefinitionError(SchemaError):
    """Exception raised when a FITS schema definition is not valid."""


class SchemaValidationError(SchemaError):
    """Exception raised when a Schema does not validate a FITS header."""

# TODO: Currently we raise an exception as soon as a violation of a schema
# is detected; in the future we will collect all schema violations and
# encapsulate them in a single SchemaValidationError


class MetaSchema(type):
    schema_attributes = set(['keywords'])
    keyword_properties = set(['mandatory', 'position', 'value'])
    keyword_required_properties = set(['mandatory'])

    def __new__(mcls, name, bases, members):
        # Determine initial keyword properties from the base classes
        base_keywords = {}
        for base_cls in reversed(bases):
            if not isinstance(base_cls, mcls):
                continue

            for keyword, properties in base_cls.keywords.items():
                if keyword in base_keywords:
                    base_keywords[keyword].update(properties)
                else:
                    base_keywords[keyword] = properties

        keywords = members.setdefault('keywords', {})

        # All class attributes of a schema that are not attributes used
        # specifically by the schema class (listed in `schema_attributes`)
        # and that have a dict value are treated as schemas for specific FITS
        # keywords.  If a FITS keyword happens to match one of the
        # `schema_attributes` it must be provided in the `keywords` attribute
        # of the schema, which is a dict mapping FITS keywords to their
        # schemas.  If a keyword is defined in both ways, the attribute
        # overrides the entry in the `keywords` dict.
        for key, value in members.items():
            if key not in mcls.schema_attributes and isinstance(value, dict):
                keywords[key] = value

        # For standard FITS keywords, ensure that all keyword definitions are
        # normalized to uppercase
        for keyword in list(keywords):
            keyword_upper = keyword.upper()
            if len(keyword) <= KEYWORD_LENGTH and keyword != keyword_upper:
                warnings.warn(
                    'Keyword %s should be listed in all caps in schema %s' %
                    (keyword, name))
                keywords[keyword_upper] = keywords[keyword]
                del keywords[keyword]

                if keyword in members:
                    members[keyword_upper] = members[keyword]
                    del members[keyword]

        for keyword, properties in keywords.items():
            # validate each of the keyword properties
            for propname, value in properties.items():
                if propname not in mcls.keyword_properties:
                    raise SchemaDefinitionError(name,
                        'invalid keyword property for %r: %r; valid keyword '
                        'properties are: %r' %
                        (keyword, propname, sorted(mcls.keyword_properties)))
                # validate keyword property definitions against the meta-schema
                validator = getattr(mcls, '_meta_validate_%s' % propname)
                validator(keyword, value)

            # Now compose the properties defined on this schema with any
            # properties from its base schema
            if keyword in base_keywords:
                # We need to *copy* any properties dict from the base classes
                # to ensure we don't modify the keyword properties in the base
                # class with the .update() call
                base_properties = base_keywords[keyword].copy()
                base_properties.update(properties)
                base_keywords[keyword] = base_properties
            else:
                base_keywords[keyword] = properties

            if keyword in members:
                members[keyword] = base_keywords[keyword]

        members['keywords'] = base_keywords

        return super(mcls, mcls).__new__(mcls, name, bases, members)

    def __contains__(cls, keyword):
        # Seems trivial for now, but will become more complicated to support
        # indexed keywords like NAXISn
        return keyword.upper() in cls.keywords

    @classmethod
    def _meta_validate_mandatory(mcls, keyword, value):
        """The 'mandatory' property must be a boolean or a callable."""

        if not (isinstance(value, (bool, np.bool_)) or callable(value)):
            # TODO: For callables, also check that they support the correct
            # number of arguments
            raise SchemaDefinitionError(cls.__name__,
                "invalid 'mandatory' property for %r; must be either a "
                "bool or a callable returning a bool; got %r" %
                (keyword, value))

    @classmethod
    def _meta_validate_position(mcls, keyword, value):
        """
        The 'position' property must be a non-negative integer or a callable.

        TODO: Maybe allow negative integers for testing position relative to
        the end of the header...
        """

        if not ((isinstance(value, (int, long, np.integer)) and value >= 0) or
                callable(value)):
            raise SchemaDefinitionError(cls.__name__,
                "invalid 'position' property for %r; must be either a "
                "non-negative integer or a callable returning a non-negative "
                "integer; got %r" % (keyword, value))

    @classmethod
    def _meta_validate_value(mcls, keyword, value):
        """
        The 'value' property has a number of possible values:

        * a tuple representing a conjunction of any of the other options
        * a string, numeric, or boolean scalar
        * a Python class/type that can be used for a string, numeric, or
          boolean value (used for type checking only)
        * an arbitrary callable that returns a bool, indicating that the
          value is valid
        """

        if not (isinstance(value, (tuple, int, long, np.integer, float,
                                   np.floating, complex, np.complex, bool,
                                   np.bool_, basestring)) or
                (isinstance(value, type) and
                 issubclass(value, (int, long, np.integer, float, np.floating,
                                    complex, np.complex, bool, np.bool_,
                                    basestring))) or callable(value)):
            raise SchemaDefinitionError(cls.__name__, 'TODO')

# TODO: Also validate non-existence of duplicate keywords (excepting commentary
# keywords and RVKC base keywords)

class Schema(object):
    __metaclass__ = MetaSchema

    @classmethod
    def validate(cls, header):
        for keyword, properties in cls.keywords.items():
            keyword_present = keyword in header
            for propname, propval in properties.items():
                if (not keyword_present and
                        propname not in cls.keyword_required_properties):
                    # Most properties are inapplicable if the keyword is not
                    # present in the header; so far the only exception is
                    # checking presence of a mandatory keyword
                    continue
                validator = getattr(cls, '_validate_%s' % propname)
                validator(header, keyword, propval)

        return True

    @classmethod
    def _validate_mandatory(cls, header, keyword, mandatory):
        if mandatory and keyword not in header:
            raise SchemaValidationError(cls.__name__,
                'mandatory keyword %r missing from header' % keyword)

    @classmethod
    def _validate_position(cls, header, keyword, position):
        found = header.index(keyword)
        if found != position:
            raise SchemaValidationError(cls.__name__,
                'keyword %r is required to have position %d in the '
                'header; instead it was found in position %d (note: '
                'position is zero-indexed)' % (keyword, position, found))

    @classmethod
    def _validate_value(cls, header, keyword, value_test):
        # any string, Python numeric type, numpy numeric type, or boolean type
        # is a valid scalar value
        value = header[keyword]

        if isinstance(value_test, tuple):
            for test in value_test:
                cls._validate_value(header, keyword, test)

            return

        if isinstance(value_test, np.bool_):
            value_test = bool(value_test)

        if isinstance(value_test, bool):
            # True/False compare equal to 1/0, but for boolean values we want
            # to confirm strict equality
            if isinstance(value, np.bool_):
                value = bool(value)

            if value is not value_test:
                raise SchemaValidationError(cls.__name__,
                    'keyword %r is required to have the value %r; got '
                    '%r instead' % (keyword, value_test, value))
        elif isinstance(value_test, (int, long, float, complex, np.number,
                                     basestring)):
            if isinstance(value, (bool, np.bool_)) or value != value_test:
                raise SchemaValidationError(cls.__name__,
                    'keyword %r is required to have the value %r; got '
                    '%r instead' % (keyword, value_test, value))
        elif isinstance(value_test, type):
            if issubclass(value_test, (int, long, np.integer)):
                # FITS (and Python 3) have no int/long distinction, so as long
                # as the value is one of those it will pass validation as
                # either an int or a long
                valid = isinstance(value, (int, long, np.integer))
            elif issubclass(value_test, (float, np.floating)):
                # An int is also acceptable for floating point tests
                valid = isinstance(value, (int, long, np.integer, float,
                                           np.floating))
            elif issubclass(value_test, (complex, np.complex)):
                valid = isinstance(value, (int, long, np.integer, float,
                                           np.floating, complex, np.complex))
            else:
                valid = isinstance(value, value_test)

            if not valid:
                raise SchemaValidationError(cls.__name__,
                    'keyword %r is required to have a value of type %r; got '
                    'a value of type %r instead' %
                    (keyword, value_test.__name__, type(value).__name__))
        elif callable(value_test):
            # TODO: Since an arbitrary function cannot help explain *why* a
            # validation error occurred, we need to rework this so that the
            # schema can provide a custom validation error message

            try:
                result = value_test(value, keyword, header)
            except Exception, e:
                raise SchemaDefinitionError(cls.__name__,
                    'an exception occurred in the value validation function '
                    'for the keyword %r; the value validation function must '
                    'not raise an exception: %r' % (keyword, e))

            if not isinstance(result, (bool, np.bool_)):
                raise SchemaDefinitionError(cls.__name__,
                    'the value valudation function for keyword %r must return '
                    'a boolean value; instead it returned %r' %
                    (keyword, result))

            if not result:
                raise SchemaValidationError(cls.__name__,
                    'the value of keyword %r failed validation; see the '
                    'schema in which this keyword was defined for details '
                    'on its correct value format' % keyword)
