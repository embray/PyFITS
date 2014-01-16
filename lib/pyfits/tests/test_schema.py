from __future__ import division, with_statement

import glob
import os

import numpy as np

import pyfits as fits
from pyfits.hdu.base import BaseSchema, PrimarySchema
from pyfits.hdu.image import BaseArraySchema, PrimaryArraySchema
from pyfits.schema import (SchemaDefinitionError, SchemaValidationError,
                           validate_fits_datetime)
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
            TEST1 = {}

        class TrivialSchema_2(fits.Schema):
            TEST1 = {}
            TEST2 = {}
            TEST3 = {}

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
                TEST1 = {}
                TesT2 = {}
                TEST3 = {}

        assert len(w) == 1

        assert 'TEST1' in TrivialSchema
        assert 'TEST2' in TrivialSchema
        assert 'TEST3' in TrivialSchema
        assert 'TEST4' not in TrivialSchema

        # Keywords not listed in upper-case should have been normalized
        assert 'TesT2' not in TrivialSchema.keywords
        assert 'TEST2' in TrivialSchema.keywords

        assert hasattr(TrivialSchema, 'TEST2')
        assert not hasattr(TrivialSchema, 'TesT2')

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
                TEST = {'kqwijibo': True}

        assert_raises(SchemaDefinitionError, make_invalid_schema)

    def test_mandatory_keywords(self):
        """Basic test of mandatory keyword validation."""

        class TestSchema(fits.Schema):
            TEST1 = {'mandatory': True}
            TEST2 = {'mandatory': False}

        h1 = fits.Header([('TEST1', '')])  # no TEST2
        h2 = fits.Header([('TEST1', ''), ('TEST2', '')])
        h3 = fits.Header([('TEST2', '')])

        assert TestSchema.validate(h1)
        assert TestSchema.validate(h2)
        assert_raises(SchemaValidationError, TestSchema.validate, h3)

    def test_keyword_positions(self):
        """Basic test of keyword position validation."""

        class TestSchema(fits.Schema):
            TEST1 = {'position': 0}
            TEST2 = {'position': 1, 'mandatory': True}
            TEST3 = {}  # position: anywhere

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

    def test_keyword_value(self):
        """Basic test of value validation.

        There are several cases for the value property:

        TODO: Move most of the following text in the documentation for schemas.

        * if given as a string, numeric, or boolean scalar value then
          the value in the keyword is compared directly to that value
          (TODO: support Astropy units as well)

        * if given as a Python class or type, perform an isinstance check
          against that type (this may be a tuple of types as well)

        * otherwise, if provided a callable object, (eg. a function or a
          lambda) call the function with the value as the first argument, the
          name of the keyword being validated as the second argument, and the
          full header as the third argument (other supported arguments may be
          added in the future). The callable much return a boolean value;
          obviously there is no way to test this when the schema is defined,
          but it *is* tested at runtime and can result in a runtime
          SchemaDefinitionError, so make sure that custom validation functions
          are well tested.
        """

        # Map a keyword name to a 3-tuple consisting of its "value" property
        # in a schema, a good value to test it against, and a bad value to test
        # it against
        test_values = {
            'NUM01': (1.1, 1.1, 1),
            # a value of False should *not* validate for the integer 0
            'NUM02': (0, 0, False),
            'NUM03': (1+2j, 1+2j, 0),
            'NUM04': (1.1+2.2j, 1.1+2.2j, 1.1+2j),
            'NUM05': (np.int64(0), 0, np.int64(1)),
            'NUM06': (np.byte(1), 1, np.byte(0)),
            'NUM07': (np.float32(0), 0.0, 1.0),
            'STR01': ('', '', 'a'),
            'STR02': ('ABC', 'ABC', 'abc'),
            'BOOL01': (True, True, 1),
            'BOOL02': (False, False, 0),
            'BOOL03': (np.bool_(True), True, 1),
            'BOOL04': (np.bool_(False), False, 0),
            'TYPE01': (str, '', 0),
            'TYPE02': (basestring, '', 0),
            'TYPE03': (int, np.uint32(1), 0.1),
            'TYPE04': (long, np.uint32(1), 0.1),
            'TYPE05': (complex, 1, 'abc'),
            'TYPE06': (complex, 1+1j, 'def'),
            'TYPE07': (bool, True, 1),
            'TYPE08': (bool, False, 0),
            'TYPE09': (int, 1, True),
            'TYPE10': (int, 0, False),
            'FUNC01': (lambda v, k, h: v > 1, 2, 0),
            'FUNC02': (lambda v, k, h: (k == 'FUNC02') == v, True, False),
            'FUNC03': (lambda v, k, h: isinstance(h, fits.Header) == v,
                       True, False)
        }

        TestSchema = type('TestSchema', (fits.Schema,),
                          dict((k, {'value': v[0]})
                               for k, v in test_values.items()))

        for keyword, values in test_values.items():
            good, bad = values[1:]
            h_good = fits.Header([(keyword, good)])
            assert TestSchema.validate(h_good)
            h_bad = fits.Header([(keyword, bad)])
            assert_raises(SchemaValidationError, TestSchema.validate, h_bad)

        # Test a header containing all the good values
        h_good = fits.Header([(k, v[1]) for k, v in test_values.items()])
        assert TestSchema.validate(h_good)

        h_bad = fits.Header([(k, v[2]) for k, v in test_values.items()])
        assert_raises(SchemaValidationError, TestSchema.validate, h_bad)

    def test_schema_composition(self):
        """Basic tests of schema single-inheritance."""

        class TestSchema_A(fits.Schema):
            TEST1 = {'mandatory': True}

        class TestSchema_B(TestSchema_A):
            # Add further restrictions
            TEST1 = {'value': 1}
            TEST2 = {'mandatory': True}
            TEST3 = {}

        class TestSchema_C(TestSchema_B):
            # Override existing properties
            TEST1 = {'value': 2}
            TEST2 = {'mandatory': False}

        h1 = fits.Header([('TEST1', 2)])
        assert TestSchema_A.validate(h1)
        assert_raises(SchemaValidationError, TestSchema_B.validate, h1)

        h1['TEST2'] = True
        assert_raises(SchemaValidationError, TestSchema_B.validate, h1)

        h1['TEST1'] = 1
        assert TestSchema_A.validate(h1)
        assert TestSchema_B.validate(h1)

        del h1['TEST1']
        # TEST1 should be mandatory in both schemas
        assert_raises(SchemaValidationError, TestSchema_A.validate, h1)
        assert_raises(SchemaValidationError, TestSchema_B.validate, h1)

        assert hasattr(TestSchema_C, 'TEST3')
        assert TestSchema_C.TEST3 == {}

        h1['TEST1'] = 1
        assert_raises(SchemaValidationError, TestSchema_C.validate, h1)

        h1['TEST1'] = 2
        assert TestSchema_C.validate(h1)

        del h1['TEST2']
        assert TestSchema_C.validate(h1)

    def test_multiple_schema_composition(self):
        """
        Test schema composition using multiple inheritance; particularly
        diamond-pattern multiple inheritance.
        """

        class TestSchema_A(fits.Schema):
            TEST1 = {'mandatory': True}  # this one will remain unchanged

        class TestSchema_B(TestSchema_A):
            TEST1 = {'value': 1}
            TEST2 = {'mandatory': True}

        class TestSchema_C(TestSchema_A):
            TEST1 = {'mandatory': False, 'value': 2}
            TEST2 = {'value': 1}
            TEST3 = {'mandatory': True}

        class TestSchema_D(TestSchema_B, TestSchema_C):
            TEST3 = {'value': 1}

        header = fits.Header([('TEST1', True)])
        assert_raises(SchemaValidationError, TestSchema_B.validate, header)

        header['TEST1'] = 1
        header['TEST2'] = True
        assert TestSchema_B.validate(header)
        assert_raises(SchemaValidationError, TestSchema_C.validate, header)

        header['TEST1'] = 2
        header['TEST2'] = 1
        header['TEST3'] = True
        assert TestSchema_C.validate(header)

        header['TEST2'] = 2
        assert_raises(SchemaValidationError, TestSchema_C.validate, header)

        header['TEST2'] = 1
        del header['TEST1']
        assert TestSchema_C.validate(header)

        header['TEST1'] = 1
        assert_raises(SchemaValidationError, TestSchema_C.validate, header)

        header['TEST1'] = 2
        del header['TEST2']
        assert TestSchema_C.validate(header)

        # Schema D should, according to the MRO, have a mandatory TEST1
        # with value 1, a mandatory TEST2 with value 1, and a mandatory
        # TEST3 with value 1
        header['TEST1'] = 1
        header['TEST2'] = 1
        header['TEST3'] = 1
        assert TestSchema_D.validate(header)

        header['TEST1'] = 2
        assert_raises(SchemaValidationError, TestSchema_D.validate, header)

        del header['TEST1']
        assert_raises(SchemaValidationError, TestSchema_D.validate, header)

        header['TEST1'] = 1
        header['TEST2'] = 2
        assert_raises(SchemaValidationError, TestSchema_D.validate, header)

        del header['TEST2']
        assert_raises(SchemaValidationError, TestSchema_D.validate, header)

        header['TEST2'] = 1
        header['TEST3'] = 2
        assert_raises(SchemaValidationError, TestSchema_D.validate, header)

        del header['TEST3']
        assert_raises(SchemaValidationError, TestSchema_D.validate, header)

    def test_schema_composition_2(self):
        """
        Test for an actual bug that appeared in the `PrimaryArraySchema` where
        the 'valid' property of the ``BLOCKED`` keyword was not handled
        correctly.
        """

        # BaseArraySchema inherits directly from BaseSchema, so their
        # BLOCKED properties should be identical
        assert 'BLOCKED' in BaseSchema._explicit_keywords
        assert 'BLOCKED' not in BaseArraySchema._explicit_keywords

        assert BaseSchema.BLOCKED == BaseArraySchema.BLOCKED
        assert (BaseSchema.keywords['BLOCKED'] ==
                BaseArraySchema.keywords['BLOCKED'])

        # But in fact, as BaseArraySchema does not explicitly say *anything*
        # about BLOCKED, its BLOCKED keyword should actually be looked up
        # through its base class
        assert 'BLOCKED' not in BaseArraySchema.__dict__
        assert BaseArraySchema.BLOCKED is BaseSchema.BLOCKED

        # On the other hand PrimarySchema does partially override
        # BaseSchema.BLOCKED
        assert 'BLOCKED' in PrimarySchema._explicit_keywords
        assert PrimarySchema.BLOCKED is not BaseSchema.BLOCKED
        assert PrimarySchema.BLOCKED['valid'] == True
        assert PrimarySchema.keywords['BLOCKED']['valid'] == True

        # Since BaseArraySchema does not explicitly say anything about BLOCKED,
        # but PrimarySchema does, then even though the bases of
        # PrimaryArraySchema are (BaseArraySchema, PrimarySchema), its values
        # for BLOCKED should come primarily from PrimarySchema first.
        assert 'BLOCKED' not in PrimaryArraySchema._explicit_keywords
        assert PrimaryArraySchema.BLOCKED == PrimarySchema.BLOCKED
        assert (PrimaryArraySchema.keywords['BLOCKED'] ==
                PrimarySchema.keywords['BLOCKED'])

    def test_invalid_keyword(self):
        """
        By default all keywords listed in a schema are 'valid'.  This tests
        that if a header contains a keyword marked with 'valid': False in the
        schema then the header is invalid.
        """

        class TestSchema1(fits.Schema):
            # If TEST is present in the header it is invalid, but it *may*
            # be marked valid in an extension, in which case its value must be
            # an int
            TEST = {
                'value': int,
                'valid': False
            }

        h1 = fits.Header([('TEST', False)])
        assert_raises(SchemaValidationError, TestSchema1.validate, h1)

        # Still invalid even if the value is set to the correct type
        h1['TEST'] = 1
        assert_raises(SchemaValidationError, TestSchema1.validate, h1)

        class TestSchema2(TestSchema1):
            TEST = {'valid': True}

        # Should pass
        assert TestSchema2.validate(h1)

        # Should fail since the type is wrong
        h1['TEST'] = True
        assert_raises(SchemaValidationError, TestSchema2.validate, h1)


    def test_indexed_keywords(self):
        """
        Basic test for keyword definitions that can match a set of keywords
        (eg. NAXISn).
        """

        class TestSchema(fits.Schema):
            NAXIS = {
                'value': (int, lambda v, k, h: v >= 0),
                'mandatory': True}
            NAXISn = {
                'indices': {'n': lambda k, h: range(1, h['NAXIS'] + 1)},
                'value': (int, lambda v, k, h: v >= 0)
            }

        h1 = fits.Header([('NAXIS', 2), ('NAXIS1', 1), ('NAXIS2', 2),
                          ('NAXIS3', False)])

        assert TestSchema.validate(h1)

        h1['NAXIS1'] = 'abc'
        assert_raises(SchemaValidationError, TestSchema.validate, h1)

        # This should cause NAXIS3 to start being validated as well, which for
        # now should fail
        h1['NAXIS1'] = 1
        h1['NAXIS'] = 3
        assert_raises(SchemaValidationError, TestSchema.validate, h1)

        # Should still fail...
        h1['NAXIS3'] = -1
        assert_raises(SchemaValidationError, TestSchema.validate, h1)

        h1['NAXIS3'] = 3
        assert TestSchema.validate(h1)

        # This should make each NAXISn keyword mandatory...
        class TestSchema2(TestSchema):
            NAXISn = {'mandatory': True}

        # Ensure that subclassing handled indexed keywords properly more or
        # less
        assert 'mandatory' in TestSchema2.NAXISn
        assert TestSchema2.NAXISn['mandatory'] is True
        assert 'NAXISn' in TestSchema2.keywords
        assert 'mandatory' in TestSchema2.keywords['NAXISn']
        assert TestSchema2.keywords['NAXISn']['mandatory'] is True

        h1['NAXIS'] = 2
        del h1['NAXIS?']
        assert_raises(SchemaValidationError, TestSchema2.validate, h1)

        h1['NAXIS1'] = 1
        assert_raises(SchemaValidationError, TestSchema2.validate, h1)

        h1['NAXIS2'] = 2
        assert TestSchema2.validate(h1)

    def test_position_dependent_on_index(self):
        """
        Test indexed keyword with callable position test that depends on the
        keyword's index value (the NAXISn case).
        """

        class TestSchema(fits.Schema):
            NAXIS = {
                'value': (int, lambda v, k, h: 999 >= v >= 0),
                'mandatory': True}
            NAXISn = {
                'indices': {'n': lambda k, h: range(1, h['NAXIS'] + 1)},
                'position': lambda k, h, n: n,
                'value': (int, lambda v, k, h: v >= 0)
            }

        h1 = fits.Header([('NAXIS', 2), ('NAXIS1', 1), ('NAXIS2', 2)])
        assert TestSchema.validate(h1)

        h1.insert(1, ('FOO', 'bar'))
        assert_raises(SchemaValidationError, TestSchema.validate, h1)

    def test_validate_datetime(self):
        """
        Test validation of datetime keywords against the formats allowed by
        the FITS Standard.
        """

        class TestSchema(fits.Schema):
            DATE = {'value': (str, validate_fits_datetime)}

        header = fits.Header([('DATE', 1234)])
        assert_raises(SchemaValidationError, TestSchema.validate, header)

        header['DATE'] = '1234'
        assert_raises(SchemaValidationError, TestSchema.validate, header)

        header['DATE'] = '2001-01-02T33:44:55'
        assert_raises(SchemaValidationError, TestSchema.validate, header)

        # A valid-looking date, but not an actual date
        header['DATE'] = '2001-02-29'
        assert_raises(SchemaValidationError, TestSchema.validate, header)

        header['DATE'] = '2001-02-28'
        assert TestSchema.validate(header)

        header['DATE'] = '2001-02-28T11:22:33'
        assert TestSchema.validate(header)

        # Incomplete fraction of seconds
        header['DATE'] = '2001-02-28T11:22:33.'
        assert_raises(SchemaValidationError, TestSchema.validate, header)

        header['DATE'] = '2001-02-28T11:33:33.0'
        assert TestSchema.validate(header)

        header['DATE'] = '2001-02-28T11:33:33.123'
        assert TestSchema.validate(header)

        header['DATE'] = '29/02/99'
        assert_raises(SchemaValidationError, TestSchema.validate, header)

        header['DATE'] = '28/02/99'
        assert TestSchema.validate(header)

    def test_datexxxx(self):
        """
        Test implementation of the DATExxxx requirement from the FITS Standard
        that all keywords beginning with 'DATE' are validated as date(times).
        """

        class TestSchema(fits.Schema):
            # Ensure that just 'DATE' is excluded from DATEx
            DATE = {'value': True}
            DATEx = {
                'indices': {'x': lambda k, h: [kw[4:] for kw in h['DATE?*']]},
                'value': (str, validate_fits_datetime)
            }

        header = fits.Header([('DATE', True), ('DATE-OBS', '1'),
                              ('DATE-FOO', '2')])
        assert_raises(SchemaValidationError, TestSchema.validate, header)

        header['DATE-OBS'] = '2000-01-01T00:00:00.0'
        assert_raises(SchemaValidationError, TestSchema.validate, header)

        header['DATE-FOO'] = '2000-01-01T00:00:00.0'
        assert TestSchema.validate(header)

    def test_test_files_against_schema(self):
        """
        Ensure that all HDUs in all the test files included in this package
        validate against their associated schemas.
        """

        for filename in glob.glob(os.path.join(self.data_dir, '*.fits')):
            with fits.open(os.path.join(self.data_dir, filename)) as hdul:
                for hdu in hdul:
                    # Use ._header instead of .header to ensure that the raw
                    # header is used for compressed image HDUs
                    # TODO: Maybe determine a better way of handling this
                    # distinction?
                    assert hdu.schema.validate(hdu._header)
