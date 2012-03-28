from __future__ import with_statement

import numpy as np
from numpy import char as chararray

from nose.tools import assert_equal, assert_true

import pyfits
from pyfits.tests import PyfitsTestCase
from pyfits.tests.test_table import comparerecords


class TestGroupsFunctions(PyfitsTestCase):
    def test_open(self):
        with pyfits.open(self.data('random_groups.fits')) as hdul:
            assert_true(isinstance(hdul[0], pyfits.GroupsHDU))
            naxes = (3, 1, 128, 1, 1)
            parameters = ['UU', 'VV', 'WW', 'BASELINE', 'DATE']
            assert_equal(hdul.info(output=False),
                         [(0, 'PRIMARY', 'GroupsHDU', 147, naxes, 'float32',
                           '3 Groups  5 Parameters')])

            ghdu = hdul[0]
            assert_equal(ghdu.parnames, parameters)
            assert_equal(list(ghdu.data.dtype.names), parameters + ['DATA'])

            assert_true(isinstance(ghdu.data, pyfits.GroupData))
            # The data should be equal to the number of groups
            assert_equal(ghdu.header['GCOUNT'], len(ghdu.data))
            assert_equal(ghdu.data.data.shape, (len(ghdu.data),) + naxes[::-1])
            assert_equal(ghdu.data.parnames, parameters)

            assert_true(isinstance(ghdu.data[0], pyfits.Group))
            assert_equal(len(ghdu.data[0]), len(parameters) + 1)
            assert_equal(ghdu.data[0].data.shape, naxes[::-1])
            assert_equal(ghdu.data[0].parnames, parameters)

    def test_parnames_round_trip(self):
        """
        Regression test for #130.  Ensures that opening a random groups file in
        update mode or writing it to a new file does not cause any change to
        the parameter names.
        """

        parameters = ['UU', 'VV', 'WW', 'BASELINE', 'DATE']
        with pyfits.open(self.data('random_groups.fits'), mode='update') as h:
            assert_equal(h[0].parnames, parameters)
            h.flush()
        # Open again just in read-only mode to ensure the parnames didn't
        # change
        with pyfits.open(self.data('random_groups.fits')) as h:
            assert_equal(h[0].parnames, parameters)
            h.writeto(self.temp('test.fits'))

        with pyfits.open(self.temp('test.fits')) as h:
            assert_equal(h[0].parnames, parameters)

    def test_groupdata_slice(self):
        """
        A simple test to ensure that slicing GroupData returns a new, smaller
        GroupData object, as is the case with a normal FITS_rec.  This is a
        regression test for an as-of-yet unreported issue where slicing
        GroupData returned a single Group record.
        """


        with pyfits.open(self.data('random_groups.fits')) as hdul:
            s = hdul[0].data[1:]
            assert_true(isinstance(s, pyfits.GroupData))
            assert_equal(len(s), 2)
            assert_equal(hdul[0].data.parnames, s.parnames)

    def test_group_slice(self):
        """
        Tests basic slicing a single group record.
        """

        # A very basic slice test
        with pyfits.open(self.data('random_groups.fits')) as hdul:
            g = hdul[0].data[0]
            s = g[2:4]
            assert_equal(len(s), 2)
            assert_equal(s[0], g[2])
            assert_equal(s[-1], g[-3])
            s = g[::-1]
            assert_equal(len(s), 6)
            assert_true((s[0] == g[-1]).all())
            assert_equal(s[-1], g[0])
            s = g[::2]
            assert_equal(len(s), 3)
            assert_equal(s[0], g[0])
            assert_equal(s[1], g[2])
            assert_equal(s[2], g[4])

    def test_create_groupdata(self):
        """
        Basic test for creating GroupData from scratch.
        """

        imdata = np.arange(100.0)
        imdata.shape = (10, 1, 1, 2, 5)
        pdata1 = np.arange(10, dtype=np.float32) + 0.1
        pdata2 = 42.0
        x = pyfits.hdu.groups.GroupData(imdata, parnames=['abc', 'xyz'],
                                        pardata=[pdata1, pdata2], bitpix=-32)

        assert_equal(x.parnames, ['abc', 'xyz'])
        assert_true((x.par('abc') == pdata1).all())
        assert_true((x.par('xyz') == ([pdata2] * len(x))).all())
        assert_true((x.data == imdata).all())

        # Test putting the data into a GroupsHDU and round-tripping it
        ghdu = pyfits.GroupsHDU(data=x)
        ghdu.writeto(self.temp('test.fits'))

        with pyfits.open(self.temp('test.fits')) as h:
            hdr = h[0].header
            assert_equal(hdr['GCOUNT'], 10)
            assert_equal(hdr['PCOUNT'], 2)
            assert_equal(hdr['NAXIS'], 5)
            assert_equal(hdr['NAXIS1'], 0)
            assert_equal(hdr['NAXIS2'], 5)
            assert_equal(hdr['NAXIS3'], 2)
            assert_equal(hdr['NAXIS4'], 1)
            assert_equal(hdr['NAXIS5'], 1)
            assert_equal(h[0].data.parnames, ['abc', 'xyz'])
            assert_true(comparerecords(h[0].data, x))
