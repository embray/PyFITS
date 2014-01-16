import itertools
import re
import warnings

from datetime import datetime

import numpy as np

from pyfits.card import KEYWORD_LENGTH
from pyfits.util import split_multiple, join_multiple


__all__ = ['Schema', 'validate_fits_datetime']


INT_TYPES = (int, long, np.integer)
FLOAT_TYPES = (float, np.floating)
COMPLEX_TYPES = (complex, np.complex)
NUMERIC_TYPES = (int, long, float, complex, np.number)
BOOL_TYPES = (bool, np.bool_)
SCALAR_TYPES = (basestring,) + NUMERIC_TYPES + BOOL_TYPES


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
    keyword_properties = set(['mandatory', 'position', 'value', 'indices',
                              'valid'])
    keyword_required_properties = set(['mandatory'])

    def __new__(mcls, name, bases, members):
        # Determine initial keyword properties from the base classes
        base_keywords = {}
        for base_cls in reversed(bases):
            if not isinstance(base_cls, mcls):
                continue

            for keyword in base_cls._explicit_keywords:
                properties = base_cls.keywords[keyword]
                if keyword in base_keywords:
                    base_keywords[keyword].update(properties)
                else:
                    base_keywords[keyword] = properties.copy()

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

        mcls._normalize_keywords(name, members, keywords, base_keywords)

        # This is a set of keywords that were *explicitly* defined properties
        # in this schema (as opposed to inherited from a base schema) either
        # via a class attribute or the 'keywords' dict
        members['_explicit_keywords'] = set(keywords)

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
                validator(name, keyword, value)

            # Now compose the properties defined on this schema with any
            # properties from its base schema
            if keyword in base_keywords:
                base_keywords[keyword].update(properties)
            else:
                base_keywords[keyword] = properties.copy()

            if keyword in members:
                members[keyword] = base_keywords[keyword]

        members['keywords'] = base_keywords

        return super(mcls, mcls).__new__(mcls, name, bases, members)

    def __contains__(cls, keyword):
        # Seems trivial for now, but will become more complicated to support
        # indexed keywords like NAXISn
        return keyword.upper() in cls.keywords

    @staticmethod
    def _normalize_keywords(name, members, keywords, base_keywords):
        """
        For standard FITS keywords, ensure that all keyword definitions are
        normalized to uppercase, updating the members dict if necessary.

        This includes exceptions, however, for indexed keywords.  Here the
        common use case is that while the keyword is all uppercase, a keyword
        index is represented by a lowercase character which may appear only
        *once* in the keyword name.
        """

        def normalize(keyword):
            keyword_upper = keyword.upper()
            if len(keyword) <= KEYWORD_LENGTH and keyword != keyword_upper:
                return keyword_upper
            else:
                # Keywords with length beyond the standard length currently are
                # not automatically normalized since they can only be
                # represented by a specialized convention
                # TODO: Update the schema definition to support *explicit*
                # mention of conventions used for a keyword
                return keyword

        def normalize_indexed(keyword, indices):
            # First validate that each index placeholder appears only once
            # in the keyword.  Might as well do this now--don't bother
            # duplicating this check in _meta_validate_indices
            for index in indices:
                if len(index) != 1:
                    raise SchemaDefinitionError(name,
                        'invalid index placeholder %r for keyword %r; index '
                        'placeholders may only be a single character' %
                        (index, keyword))

                if keyword.count(index) != 1:
                    raise SchemaDefinitionError(name,
                        'index placeholder %r for keyword %r may only appear '
                        'exactly once in the keyword; use an index '
                        'placeholder that is guaranteed to be a unique '
                        'character in the keyword name' % (index, keyword))

            # Split keyword into any index placeholder, and non-index portions;
            # normalize just the non-index portions to uppercase
            kw_fixed, kw_indices = split_multiple(keyword, *indices)
            kw_fixed_upper = [part.upper() for part in kw_fixed]

            # TODO: This assumes that the index portion of the keyword will be
            # no longer than would be allowed for a standard FITS keyword.
            # Might update this another time to be more explicit as to how many
            # characters an index can use
            if len(keyword) <= KEYWORD_LENGTH and kw_fixed != kw_fixed_upper:
                kw_fixed = kw_fixed_upper

            return join_multiple(kw_fixed, kw_indices)

        for keyword in list(keywords):
            indices = keywords[keyword].get('indices')

            if indices is None and keyword in base_keywords:
                # Inherit indices from base class if necessary
                indices = base_keywords[keyword].get('indices', {})

            if indices:
                normalized = normalize_indexed(keyword, list(indices))
            else:
                normalized = normalize(keyword)

            if keyword != normalized:
                warnings.warn(
                    'Keyword %s should be listed in all caps (excluding '
                    'index placeholders) in schema %s' % (keyword, name))
                keywords[normalized] = keywords[keyword]
                del keywords[keyword]

                if keyword in members:
                    members[normalized] = members[keyword]
                    del members[keyword]

    @classmethod
    def _meta_validate_mandatory(mcls, clsname, keyword, value):
        """The 'mandatory' property must be a boolean or a callable."""

        if not (isinstance(value, BOOL_TYPES) or callable(value)):
            # TODO: For callables, also check that they support the correct
            # number of arguments
            raise SchemaDefinitionError(clsname,
                "invalid 'mandatory' property for %r; must be either a "
                "bool or a callable returning a bool; got %r" %
                (keyword, value))

    @classmethod
    def _meta_validate_valid(mcls, clsname, keyword, value):
        """The 'valid' property must be a boolean or a callable."""

        if not (isinstance(value, BOOL_TYPES) or callable(value)):
            # TODO: For callables, also check that they support the correct
            # number of arguments
            raise SchemaDefinitionError(clsname,
                "invalid 'valid' property for %r; must be either a "
                "bool or a callable returning a bool; got %r" %
                (keyword, value))


    @classmethod
    def _meta_validate_position(mcls, clsname, keyword, value):
        """
        The 'position' property must be a non-negative integer or a callable.

        TODO: Maybe allow negative integers for testing position relative to
        the end of the header...
        """

        if not ((isinstance(value, INT_TYPES) and value >= 0) or
                callable(value)):
            raise SchemaDefinitionError(clsname,
                "invalid 'position' property for %r; must be either a "
                "non-negative integer or a callable returning a non-negative "
                "integer or boolean; got %r" % (keyword, value))

    @classmethod
    def _meta_validate_value(mcls, clsname, keyword, value):
        """
        The 'value' property has a number of possible values:

        * a tuple representing a conjunction of any of the other options
        * a string, numeric, or boolean scalar
        * a Python class/type that can be used for a string, numeric, or
          boolean value (used for type checking only)
        * an arbitrary callable that returns a bool, indicating that the
          value is valid
        """

        if not (isinstance(value, (tuple,) + SCALAR_TYPES) or
                (isinstance(value, type) and
                    issubclass(value, SCALAR_TYPES)) or
                callable(value)):
            raise SchemaDefinitionError(clsname, 'TODO')

    @classmethod
    def _meta_validate_indices(mcls, clsname, keyword, value):
        """
        The 'indices' property must be a dictionary mapping a string
        (preferably a single lower-case character (TODO: maybe make this
        a mandatory requirement?) to either:

        * an iterable
        * a callable (the callable must return an iterable)

        Note: A lot of the validation for this property is performed in the
        `_normalize_keywords` method as it needs to be performed early on to
        determine which keywords have indices.
        """

        for placeholder, values in value.items():
            if callable(values):
                # TODO: Maybe check that it takes the correct arguments?
                continue

            try:
                iter(values)
            except TypeError:
                raise SchemaDefinitionError(clsname, 'TODO')


# TODO: Also validate non-existence of duplicate keywords (excepting commentary
# keywords and RVKC base keywords)

class Schema(object):
    __metaclass__ = MetaSchema

    @classmethod
    def validate(cls, header):
        for keyword, properties in cls.keywords.items():
            indices = properties.get('indices', {})
            if indices:
                keywords = cls._interpolate_indices(header, keyword, indices)
            else:
                keywords = [(keyword, {})]

            for keyword, index_values in keywords:
                cls._validate_single_keyword(header, keyword, properties,
                                             index_values)
        return True

    @classmethod
    def _interpolate_indices(cls, header, keyword, indices):
        """
        Given a keyword "template" and the dict of indices attached to that
        keyword, return the list of concrete keywords generated from the
        indices on that keyword.

        For example:

            >>> Schema._interpolate_indices('NAXISn', {'n': [1, 2, 3]})
            ['NAXIS1', 'NAXIS2', 'NAXIS3']

        or for more complicated cases involving multiple indices:

            >>> Schema._interpolate_indices('CDi_ja',
                                            {'i': [1, 2],
                                             'j': [1, 2],
                                             'a': ['A', 'B']})
            ['CD1_1A', 'CD1_1B', 'CD1_2A', 'CD1_2B', 'CD2_1A', 'CD2_1B',
             'CD2_2A', 'CD2_2B']
        """

        keywords = []
        placeholders = []
        values = []

        # Sort indices by their appearance in the keyword template
        sort_key = lambda i: keyword.index(i[0])

        for ph, vals in sorted(indices.items(), key=sort_key):
            placeholders.append(ph)

            if callable(vals):
                vals = vals(keyword, header)
                # Validate that the value returned by the callable is
                # iterable
                try:
                    iter(vals)
                except TypeError:
                    raise SchemaDefinitionError(cls.__name__,
                        'the callable used to determine the %r indices for '
                        '%r did not return an iterable; the function must '
                        'return an iterable of values to use as indices to '
                        'this keyword' % (ph, keyword))

            values.append(vals)

        for prod in itertools.product(*values):
            full_keyword = keyword
            index_values = {}
            for ph, val in itertools.izip(placeholders, prod):
                full_keyword = full_keyword.replace(ph, str(val))
                index_values[ph] = val
            keywords.append((full_keyword, index_values))

        return keywords

    @classmethod
    def _validate_single_keyword(cls, header, keyword, properties, indices):
        keyword_present = keyword in header
        for propname, propval in properties.items():
            if (not keyword_present and
                    propname not in cls.keyword_required_properties):
                # Most properties are inapplicable if the keyword is not
                # present in the header; so far the only exception is checking
                # presence of a mandatory keyword
                continue
            validator = getattr(cls, '_validate_%s' % propname)
            validator(header, keyword, indices, propval)


    @classmethod
    def _validate_mandatory(cls, header, keyword, indices, mandatory):
        if not isinstance(mandatory, BOOL_TYPES):
            mandatory = _call_with_indices(mandatory, indices, keyword,
                                           header)

        if mandatory and keyword not in header:
            raise SchemaValidationError(cls.__name__,
                'mandatory keyword %r missing from header' % keyword)

    @classmethod
    def _validate_valid(cls, header, keyword, indices, valid):
        if not isinstance(valid, BOOL_TYPES):
            valid = _call_with_indices(valid, indices, keyword, header)

        if not valid and keyword in header:
            raise SchemaValidationError(cls.__name__,
                'keyword %r is invalid in this header' % keyword)

    @classmethod
    def _validate_indices(cls, header, keyword, indices, indices_):
        # This method is a no-op since the 'indices' property is given special
        # handling
        return

    @classmethod
    def _validate_position(cls, header, keyword, indices, position):
        if not isinstance(position, INT_TYPES):
            # Need to check this explicitly, since types are almost always also
            # callable; if not an int position *must* be callable or else the
            # schema would not have valided against the MetaSchema
            position = _call_with_indices(position, indices, keyword, header)

            if not ((isinstance(position, INT_TYPES) and position >= 0) or
                    isinstance(position, BOOL_TYPES)):
                raise SchemaDefinitionError(cls.__name__,
                    'position validation function for keyword %r is required '
                    'to return either a non-negative integer or a boolean; '
                    'returned %r instead' % (keyword, position))

            if isinstance(position, BOOL_TYPES):
                # In this case, the validation function just performs a custom
                # check that the keyword's position is valid--it does not
                # return a specific position that the keyword must have
                if position:
                    return

                raise SchemaValidationError(cls.__name__,
                    'keyword %r is not in a valid position in the header, '
                    'but a required position for this keyword has not been '
                    'specified; please check the schema definition to '
                    'determine where this keyword should be positioned')

        found = header.index(keyword)
        if found != position:
            raise SchemaValidationError(cls.__name__,
                'keyword %r is required to have position %d in the '
                'header; instead it was found in position %d (note: '
                'position is zero-indexed)' % (keyword, position, found))

    @classmethod
    def _validate_value(cls, header, keyword, indices, value_test):
        # any string, Python numeric type, numpy numeric type, or boolean type
        # is a valid scalar value

        if isinstance(value_test, tuple):
            for test in value_test:
                cls._validate_value(header, keyword, indices, test)

            return

        value = header[keyword]

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
        elif isinstance(value_test, (basestring,) + NUMERIC_TYPES):
            if isinstance(value, BOOL_TYPES) or value != value_test:
                raise SchemaValidationError(cls.__name__,
                    'keyword %r is required to have the value %r; got '
                    '%r instead' % (keyword, value_test, value))
        elif isinstance(value_test, type):
            if issubclass(value_test, BOOL_TYPES):
                valid = isinstance(value, BOOL_TYPES)
            elif issubclass(value_test, INT_TYPES):
                # FITS (and Python 3) have no int/long distinction, so as long
                # as the value is one of those it will pass validation as
                # either an int or a long
                valid = (not isinstance(value, BOOL_TYPES) and
                         isinstance(value, INT_TYPES))
            elif issubclass(value_test, FLOAT_TYPES):
                # An int is also acceptable for floating point tests
                valid = isinstance(value, INT_TYPES + FLOAT_TYPES)
            elif issubclass(value_test, COMPLEX_TYPES):
                valid = isinstance(value, NUMERIC_TYPES)
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
                result = _call_with_indices(value_test, indices,
                                            value, keyword, header)
            except Exception, e:
                raise SchemaDefinitionError(cls.__name__,
                    'an exception occurred in the value validation function '
                    'for the keyword %r; the value validation function must '
                    'not raise an exception: %r' % (keyword, e))

            if not isinstance(result, BOOL_TYPES):
                raise SchemaDefinitionError(cls.__name__,
                    'the value valudation function for keyword %r must return '
                    'a boolean value; instead it returned %r' %
                    (keyword, result))

            if not result:
                raise SchemaValidationError(cls.__name__,
                    'the value of keyword %r failed validation; see the '
                    'schema in which this keyword was defined for details '
                    'on its correct value format' % keyword)


_FITS_DATE_FMT = '%Y-%m-%d'
# TODO: The standard also supports optional fractions of seconds.
# Unfortunately the format code %f for that is not supported in Python 2.5 so
# we will handle it manually in validate_fits_datetime, but once 2.5 support is
# dropped we can use %f
_FITS_DATETIME_FMT = _FITS_DATE_FMT + 'T%H:%M:%S'
# Only for dates before year 2000
_FITS_LEGACY_DATE_FMT = '%d/%m/%y'
_FITS_DATETIME_RE = re.compile('|'.join([
    r'(?P<date>\d{4}-[01]\d-[0123]\d$)',
    r'(?:(?P<datetime>\d{4}-[01]\d-[0123]\dT[012]\d:[0-5]\d:[0-5]\d)'
       r'(?P<microseconds>\.\d+)?$)',
    r'(?P<legacy>[0123]\d/[01]\d/\d\d$)']))


# TODO: Perhaps use a more generalized version of this function to actually
# return datetime objects from the Header for known date keywords...
def validate_fits_datetime(value, keyword, header):
    """
    Validate date/time values in FITS headers according to the format given
    for the ``DATE`` keyword in Section 4.4.2.1 of the FITS Standard version
    3.0 (July 10, 2008).

    Note: the ``keyword`` and ``header`` arguments are not currently used
    directly, but are included to match the required interface for keyword
    value validation functions.
    """

    # There are a few different time and/or date formats supported by the FITS
    # standard, including an older format only valid pre-2000.  So we have to
    # do a bit of fancy footwork to determine which format to use, and cannot
    # simply rely on strptime alone
    if not isinstance(value, basestring):
        return False

    # TODO: Value validation functions need a way to return custom error
    # messages to the schema validator as there are many ways a datetime value
    # can go wrong that should be communicated to the user
    m = _FITS_DATETIME_RE.match(value)

    if not m:
        # TODO: Does not even begin to match one of the valid FITS datetime
        # formats; the user should be informed as much of this
        return False

    for group, fmt in [('datetime', _FITS_DATETIME_FMT),
                       ('date', _FITS_DATE_FMT),
                       ('legacy', _FITS_LEGACY_DATE_FMT)]:
        # Currently don't do anything with microseconds, but the regexp ensures
        # that if they are present they're valid
        # Parse the datetime to ensure that it's a logical datetime
        if not m.group(group):
            continue

        try:
            datetime.strptime(m.group(group), fmt)
        except ValueError:
            # Invalidate datetime
            return False
        return True
    else:
        return False


def _call_with_indices(func, indices, *args):
    """
    Calls the given func, with given args, optionally passing in keyword
    arguments from the ``indices`` dict if it is not empty.

    Support for indices in the given func may be optional, however, so if
    calling it with keyword arguments fails, fall back on calling it without
    keyword arguments.
    """

    if indices:
        try:
            return func(*args, **indices)
        except TypeError:
            pass

    return func(*args)