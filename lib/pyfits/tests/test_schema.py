from __future__ import division, with_statement

import pyfits as fits
from pyfits.tests import PyfitsTestCase


class TestSchema(PyfitsTestCase):
    def test_empty_schema(self):
        """
        An empty schema is perfectly valid and will pass any header.
        """

        class EmptySchema(fits.Schema):
            pass

        assert EmptySchema.validate(fits.Header())

        h = Header([('TEST', 'TEST')])
        assert EmptySchema.validate(h)
