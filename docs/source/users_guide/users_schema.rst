.. currentmodule:: pyfits

*******************
FITS Header Schemas
*******************

It is not uncommon in computing to define data structures to which one's data
must conform in order to meaningfully represent some data model of interest.
A simple example of this is a "struct" in the C programming language:  It
groups together a set of a data values in a specific order, and defines what
types (as understood by the programming language) they may have.  In some ways
a C struct imposes a very "loose" set of constraints on one's data:  For
example, it may require that one datum be a 32-bit integer, but it places no
constraints beyond that on what values it may hold, or its relationship to
other data in the structure (other than the relative order in which they are
stored in memory).

There are other data modeling languages, often designed around specific data
storage formats, that enable stronger and more expressive constraints on one's
data.  This allows one to at least partially, if not fully define the semantics
of one's data and enables arbitrary data to be checked for conformance with
those semantics.  By using a standardized data modeling language we can then
write software *once* that can check arbitrary data against arbitrary sets of
constraints.  Sometimes these languages are referred to as a "schema", as in
the case of `XML Schema <http://en.wikipedia.org/wiki/XML_schema>` or
`JSON Schema <http://en.wikipedia.org/wiki/JSON_Schema#JSON_Schema>`.

One of the major shortcoming of FITS, and as a result of the data structures
for observations built around FITS, is the lack of any kind of data modeling
and validation *language* for FITS.  Indeed, the FITS Standard itself lists the
requirements of standard FITS headers in a combination of prose and tables that
must be read and interpreted by a human any time one wants to write software
that reads and writes valid FITS files.  That's not to say that there
*shouldn't* be natural language explanations of the keywords expected to be
found in a FITS header and of their semantics, but the lack of a *computer*
readable set of rules for FITS headers leaves open the possibility for a great
many mistakes when writing software that attempts to adhere to the FITS
Standard.

This incomplete approach has, as such, extended beyond the FITS Standard to
usage conventions for specific observational products from different
observatories and others who have modeled their data products around FITS.
For example, while the various HST data handbooks contain tables listing the
keywords that should be attached to different types of observations by
different instruments, one has to read carefully through the documentation
to determine the allowed ranges of values for many of those keywords.
Furthermore, any time *anyone* wants to write software that works on those
specific header conventions one has to hand-write code that validates the
output products against those conventions.  It is all too easy for developers
to make mistakes or miss specific requirements.  The situation becomes even
worse when the semantics of the convention evolve, but the software does not.

To be fair, there are limitations to the extent to which a simple schema format
can assure the semantic validity of complex science data products.  Take for
example the FITS WCS keywords: Say one takes an existing image that has been
fully calibrated and rescales it.  There is only so much at that point that a
schema for FITS could validate whether the coordinate transformations are still
correct.  It *can*, however, ensure that all of the required keywords are
present and have meaningful values (for example a transformation matrix element
must be a real number, not a boolean).  Currently these kinds of checks must
be implemented time and time again, and it is not usually clear from even
visual inspection of one's code whether all constraints of the data model are
correctly adhered to and validated against.


Enter `pyfits.schema`
=====================

The `pyfits.schema` model introduced in PyFITS version 3.3.0 (tentative)
attempts to partially solve this problem for data models designed around FITS.
Although it is generally preferable to define a data modeling language in some
programming language-independent "plain text" format (think for example an SQL
database schema), this can place heavy limitations on the complexity of
constraints one may define in a schema.  In order to fully capture the full set
of rules some data must conform to, the data modeling language itself may need
enough complexity and expressiveness to approach that of a programming
language.

As PyFITS itself is already written in Python, there is little gained from
defining a complex new language for validating FITS headers.  Instead, PyFITS
uses Python itself to implement most of the validation rules.  What the classes
and functions in `pyfits.schema` provide are simply a way to organize those
rules into something resembling a "schema" for FITS headers.  It also provides
a number of shortcuts for common types of validation (eg. "keyword ``OBSERVER``
must have a string value), and a way to extend existing schemas to define new
ones.

For example, PyFITS already provides schemas that can validate a FITS header
against all the keywords defined by the FITS Standard.  For example,
`BaseArraySchema` captures all the rules in the FITS Standard for headers
describing an image (or n-dimensional array of any kind).  This includes all
the rules for the ``NAXIS``, ``NAXISn``, ``BITPIX``, ``DATAMIN``, ``DATAMAX``,
and other keywords that are used to describe the array data (otherwise divorced
from any description of what the data represents).  In order to define a schema
for images taken from a specific telescope on instrument one might *extend*
`BaseArraySchema` and include additional rules.  For example, all observations
taken from the Hubble Space Telescope might require that the ``TELESCOP``
keyword have a value of ``'HST'``.  Because these rules are defined using a
general purpose programming language (Python) they may be arbitrarily complex.
It is also possible (or will be possible in future versions) to pass
additional context to the validation rules, such as the data arrays themselves,
or the name of the file containing the header(s) being validated.


PyFITS schema basics
====================

To define a schema using `pyfits.schema` one must create a Python *class* that
inherits from the class called simply `~pyfits.Schema`.  For a good referesher
on how to define a class in Python see the official `Python Tutorial
<http://docs.python.org/2/tutorial/classes.html>`.

A schema class *may* have methods defined on, but the primary contents of any
schema class are one or more class *attributes* that take their name from FITS
keywords that we expect to find in headers conforming to our schema.  In
Python, a class attribute is just any variable (other than a method or
function) that is defined at the class level.  The values of each of these
so-called "keyword attributes" *must* be a Python `dict` object.  The keys of
that `dict` represent "keyword properties"--that is--properties or rules
defining the semantics of that keyword as it is used in that particular data
model.

To give a very basic example, one of the most common keyword properties is
``'value'``.  This defines the rules for the value that may be associated with
that keyword.  Say we want to define a model where the keyword ``FOO``, if it
appears in a header, *must* have a character string value.  The schema for
such a model (which we're calling ``MySchema``) looks like this::

    >>> from pyfits import Schema
    >>> class MySchema(Schema):
    ...     FOO = {'value': str}

And that's it.  Again, this schema states that if a header contains a keyword
named "FOO", the value of that keyword must be a string.  We can now validate
any FITS header (stored in a PyFITS `Header` object) against this schema like
so::

    >>> from pyfits import Header
    >>> hdr = Header([('FOO', 1)])
    >>> hdr  # Note that 'FOO' is an *int*, not a string
    FOO     =                    1
    >>> MySchema.validate(hdr)
    Traceback (most recent call last):
    ...
    pyfits.schema.SchemaValidationError: SchemaValidationError in MySchema:
    keyword 'FOO' is required to have a value of type 'str'; got a value of
    type 'int' instead

This first example used a header that does *not* conform to the schema.  As the
error message reads, ``FOO`` was required to be a string, but we gave it an
integer value instead.  Testing against invalid headers is a good way to ensure
that our schema is looking out for us.  We are free to correct the header and
attempt validation a second time::

    >>> hdr['FOO'] = 'abc'
    >>> hdr
    FOO     = 'abc     '
    >>> MySchema.validate(hdr)
    True

Currently `Schema.validate` simply returns `True` if validation succeeds.

Note also that we never created an *instance* of ``MySchema``.  We just called
``.validate`` directly on the schema class itself.  This is the intended usage,
and in general there is no reason to create specific instances of schema
classes.  The class itself contains all the functionality we need.

What if we want ``FOO`` to always have a *specific* value; not just be an
arbitrary string.  This this case, rather than specifying `str` for the
``'value'`` property we specify the exact value you want it to have::

    >>> class MySchema2(Schema):
    ...     FOO = {'value': 'on'}
    ...
    >>> MySchema2.validate(hdr)
    Traceback (most recent call last):
    ...
    pyfits.schema.SchemaValidationError: SchemaValidationError in MySchema2:
    keyword 'FOO' is required to have the value 'on'; got 'abc' instead
    >>> hdr['FOO'] = 'on'
    >>> MySchema2.validate(hdr)
    True

We can also provide a list of allowed values like so::

    >>> class MySchema3(Schema):
    ...     FOO = {'value': ['on', 'off']}
    ...
    >>> MySchema3.validate(hdr)
    True
    >>> hdr['FOO'] = 'off'
    >>> MySchema3.validate(hdr)
    True
    >>> hdr['FOO'] = 'abc'
    >>> MySchema3.validate(hdr)
    Traceback (most recent call last):
    ...
    pyfits.schema.SchemaValidationError: SchemaValidationError in MySchema2:
    keyword 'FOO' is required to have the value of one of ['on', 'off']; got
    'abc' instead

.. note::

    For multiple value sets a Python `list` must be used.  A `tuple` has
    different semantics that will be discussed later.

Note also that the previous example schemas do not require a keyword called
"FOO" to be present in the header.  They only require that *if* present it
meets the prescribed rules.  In order to *require* a keyword to be present,
simply use the ``'mandatory'`` property with a value of `True`::

    >>> class MySchema4(Schema):
    ...     FOO = {'value': str, 'mandatory': True}
    ...
        >>> hdr = Header([('ZAPHOD', 1), ('FORD', 2)])
    >>> MySchema.validate(hdr)
    Traceback (most recent call last):
    ...
    pyfits.schema.SchemaValidationError: SchemaValidationError in MySchema4:
    mandatory keyword 'FOO' missing from header
    >>> hdr['FOO'] = 'abc'
    >>> MySchema.validate(hdr)
    True

For many FITS keywords it's enough to set them as mandatory or optional (the
default).  But in some cases we also want some keywords to be present in a
header in a *specific* order.  To give a familiar example, the first keyword of
any conforming FITS primary header must be "SIMPLE" (and it must have a value
of `True`).  The second keyword must always be "BITPIX" (with an integer value
of one of -64, -32, 8, 16, 32, or 64).  We use the ``'position'`` property to
define rules for keyword order.  The simplest use of the ``'position'``
property is to hard-code the exact index into the header a keyword must have.

Remember, Python is zero-indexed, which means the *first* keyword has an index
of zero.  A schema encoding the rules given in the previous paragraph for
"SIMPLE" and "BITPIX" might look like this::

    >>> class PrimaryHeaderSchema(Schema):
    ...     SIMPLE = {'value': True, 'mandatory': True, 'position': 0}
    ...     BITPIX = {'value': [-64, -32, 8, 16, 32, 64],
    ...               'mandatory': True,
    ...               'position': 1
    ...              }
    ...
    >>> hdr = Header([('BITPIX', 16), ('SIMPLE', True)])
    >>> hdr
    BITPIX  =                   16
    SIMPLE  =                    T
    >>> PrimaryHeaderSchema.validate(hdr)
    Traceback (most recent call last):
    ...
    pyfits.schema.SchemaValidationError: SchemaValidationError in
    PrimaryHeaderSchema: keyword 'SIMPLE' is required to have position 0 in the
    header; instead it was found in position 1 (note: position is zero-indexed)

(Note: This only reported ``SIMPLE`` as out of place.  In a future version it
will be possible to report all schema violations with a single
`Schema.validate` call.)

Now we can fix the header and try validating again::

    >>> hdr.set('SIMPLE', before='BITPIX')
    >>> hdr
    SIMPLE  =                    T
    BITPIX  =                   16
    >>> PrimaryHeaderSchema.validate(hdr)
    True

Of course this is only the tip of the iceberg of the full set rules for a FITS
primary header.  Fortunately a schema defining all the rules already comes with
PyFITS (see `PrimarySchema`).


Using callable properties
=========================

We have seen how to require a specific absolute position at which a keyword
must be placed in a header by using the ``'position'`` property.  But what if
we don't care about the absolute position but rather the position relative to
another keyword.  For example: The keywords ``TELESCOP`` and ``INSTRUME``
(FITSisms for "telescope" and "instrument") as defined by the FITS standard do
*not* have required positions.  But say, as a matter of convention, for the
sake of consistency we want all files output by our pipeline to place the
``INSTRUME`` keyword immediately *after* ``TELESCOP``.  Conventions like this
are useful for users visually inspecting headers--having keywords in a
consistent order means less visual overhead in searching a long header for
them.

*Currently* PyFITS schema does not define any keyword properties that
explicitly define such a rule (though we could add them if it turns out to be
a very common case).  Instead, rather than supplying an exact integer value to
``'property'`` we can supply a *function* (or often a ``lambda`` as a shortcut)
that computes what index ``INSTRUME`` *should* have if it is to come after
``TELESCOP``.  To do this, the function would need access to the actual header
being validated, and it would need to be able to look up the index of the
``TELESCOP`` keyword.  This could be implemented something like this::

    >>> class MySchema5(Schema):
    ...     TELESCOP = {'value': str, 'mandatory': True}
    ...     INSTRUME = {'value': str,
    ...                 lambda **ctx: ctx['header'].index('TELESCOP') + 1
    ...                }
    ...
    >>>
