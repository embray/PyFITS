import warnings

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
    keyword_properties = set(['mandatory', 'position'])

    def __new__(mcls, name, bases, members):
        keywords = members.setdefault('keywords', {})
        # For standard FITS keywords, ensure that all keyword definitions are
        # normalized to uppercase
        for keyword in list(keywords):
            if len(keyword) <= KEYWORD_LENGTH and keyword != keyword.upper():
                warnings.warn(
                    'Keyword %s should be listed in all caps in schema %s' %
                    (keyword, name))
                keywords[keyword.upper()] = keywords[keyword]
                del keywords[keyword]

        for keyword, properties in keywords.items():
            # validate each of the keyword properties
            for propname, value in properties.items():
                if propname not in mcls.keyword_properties:
                    raise SchemaDefinitionError(name,
                        'invalid keyword property for %r: %r; valid keyword '
                        'properties are: %r' %
                        (keyword, propname, sorted(mcls.keyword_properties)))

        return super(mcls, mcls).__new__(mcls, name, bases, members)

    def __contains__(cls, keyword):
        # Seems trivial for now, but will become more complicated to support
        # indexed keywords like NAXISn
        return keyword.upper() in cls.keywords


# TODO: Also validate non-existence of duplicate keywords (excepting commentary
# keywords and RVKC base keywords)

class Schema(object):
    __metaclass__ = MetaSchema

    @classmethod
    def validate(cls, header):
        for keyword, properties in cls.keywords.items():
            for propname, propval in properties.items():
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
        if keyword in header:
            found = header.index(keyword)
            if found != position:
                raise SchemaValidationError(cls.__name__,
                    'keyword %r is required to have position %d in the '
                    'header; instead it was found in position %d (note: '
                    'position is zero-indexed)' % (keyword, position, found))
