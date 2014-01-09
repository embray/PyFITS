from __future__ import division, with_statement

import pyfits as fits
from pyfits.schema import SchemaDefinitionError, SchemaValidationError
from pyfits.tests import PyfitsTestCase
from pyfits.tests.util import catch_warnings

from nose.tools import assert_raises


class TestSchema(PyfitsTestCase):
    def test_empty_schema(self):
        """
        An empty schema is perfectly valid and will pass any header.
        """

        class EmptySchema(fits.Schema):
            pass

        assert EmptySchema.validate(fits.Header())

        h = fits.Header([('TEST', 'TEST')])
        assert EmptySchema.validate(h)

    def test_trivial_schema(self):
        """
        A schema that lists keywords but does not place *any* requirements
        on those keywords is as good as an empty schema.
        """

        h1 = fits.Header([('TEST2', 'TEST')])
        h2 = fits.Header([('TEST2', 'TEST')])

        class TrivialSchema_1(fits.Schema):
            keywords = {
                'TEST1': {}
            }

        class TrivialSchema_2(fits.Schema):
            keywords = {
                'TEST1': {},
                'TEST2': {},
                'TEST3': {}
            }

        assert TrivialSchema_1.validate(fits.Header())
        assert TrivialSchema_1.validate(h1)
        assert TrivialSchema_1.validate(h2)
        assert TrivialSchema_2.validate(fits.Header())
        assert TrivialSchema_2.validate(h1)
        assert TrivialSchema_2.validate(h2)

    def test_schema_contains_keyword(self):
        """
        Test whether a schema defines a particular keyword (even if trivially).
        """

        with catch_warnings(record=True) as w:
            class TrivialSchema(fits.Schema):
                keywords = {
                    'TEST1': {},
                    'TesT2': {},
                    'TEST3': {}
                }

        assert len(w) == 1

        assert 'TEST1' in TrivialSchema
        assert 'TEST2' in TrivialSchema
        assert 'TEST3' in TrivialSchema
        assert 'TEST4' not in TrivialSchema

        # Keywords not listed in upper-case should have been normalized
        assert 'TesT2' not in TrivialSchema.keywords
        assert 'TEST2' in TrivialSchema.keywords

        # Keywords in schemas are also case-insensitive (at least for standard
        # keywords; this might not hold for HIERARCH or RVKC keywords if they
        # are supported)
        assert 'tEsT1' in TrivialSchema

    def test_invalid_keyword_property(self):
        """
        Test that defining a schema containing a keyword with invalid
        properties raises a SchemaError.
        """

        def make_invalid_schema():
            class InvalidSchema(fits.Schema):
                keywords = {
                    'TEST': {'kqwijibo': True}
                }

        assert_raises(SchemaDefinitionError, make_invalid_schema)

    def test_mandatory_keywords(self):
        """Basic test of mandatory keyword validation."""

        class TestSchema(fits.Schema):
            keywords = {
                'TEST1': {'mandatory': True},
                'TEST2': {'mandatory': False}
            }

        h1 = fits.Header([('TEST1', '')])  # no TEST2
        h2 = fits.Header([('TEST1', ''), ('TEST2', '')])
        h3 = fits.Header([('TEST2', '')])

        assert TestSchema.validate(h1)
        assert TestSchema.validate(h2)
        assert_raises(SchemaValidationError, TestSchema.validate, h3)

    def test_keyword_positions(self):
        """Basic test of keyword position validation."""

        class TestSchema(fits.Schema):
            keywords = {
                'TEST1': {'position': 0},
                'TEST2': {'position': 1, 'mandatory': True},
                'TEST3': {}  # position: anywhere
            }

        # Note: The position property does not mean a keyword is *mandatory*,
        # just that if it is present it must have the specified position
        h1 = fits.Header([('TEST1', ''), ('TEST2', ''), ('TEST4', ''),
                          ('TEST3', '')])
        h2 = fits.Header([('TEST3', ''), ('TEST2', ''), ('TEST1', '')])
        h3 = fits.Header([('TEST3', ''), ('TEST2', '')])
        h4 = fits.Header([('TEST2', ''), ('TEST1', '')])

        assert TestSchema.validate(h1)
        assert_raises(SchemaValidationError, TestSchema.validate, h2)
        assert TestSchema.validate(h3)
        assert_raises(SchemaValidationError, TestSchema.validate, h4)
