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
error message reads, "FOO" was required to be a string, but we gave it an
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
