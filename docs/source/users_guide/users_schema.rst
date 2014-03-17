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
the case of `XML Schema <http://en.wikipedia.org/wiki/XML_schema>`_ or
`JSON Schema <http://en.wikipedia.org/wiki/JSON_Schema#JSON_Schema>`_.

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
<http://docs.python.org/2/tutorial/classes.html>`_.

A schema class *may* have methods defined on, but the primary contents of any
schema class are one or more class *attributes* that take their name from FITS
keywords that we expect to find in headers conforming to our schema.  In
Python, a class attribute is just any variable (other than a method or
function) that is defined at the class level.  The values of each of these
so-called "keyword attributes" *must* be a Python `dict` object.  The keys of
that `dict` represent "keyword properties", that is, properties or rules
defining the semantics of that keyword as it is used in that particular data
model.

To give a very basic example, one of the most common keyword properties is
`value`_.  This defines the rules for the value that may be associated with
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
``.validate`` directly on the schema class itself.  This is an example of a
Python `classmethod`, and is the intended usage.  In general there is no reason
to create specific instances of schema classes.  The class itself contains all
the functionality we need.

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
simply use the `mandatory`_ property with a value of `True`::

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

There also exists a `valid`_ property.  This is in some ways the inverse of
``'mandatory'``:  By default all keywords are "valid" (``'valid': True``), but
if a keyword is marked as ``'valid': False`` it is *invalid* for that keyword
to appear in headers using this schema.  For example::

    >>> class MySchema5(Schema):
    ...     FOO = {'valid': False}
    ...
    >>> hdr = Header([('FOO', 1), ('BAR', 2)])
    >>> MySchema5.validate(hdr)
    Traceback (most recent call last):
    ...
    pyfits.schema.SchemaValidationError: SchemaValidationError in MySchema5:
    keyword 'FOO' is invalid in this header
    >>> del hdr['FOO']
    >>> MySchema5.validate(hdr)
    True

For many FITS keywords it's enough to set them as mandatory or optional (the
default).  But in some cases we also want some keywords to be present in a
header in a *specific* order.  To give a familiar example, the first keyword of
any conforming FITS primary header must be "SIMPLE" (and it must have a value
of `True`).  The second keyword must always be "BITPIX" (with an integer value
of one of -64, -32, 8, 16, 32, or 64).  We use the `position`_ property to
define rules for keyword order.  The simplest use of the ``'position'``
property is to hard-code the exact index into the header a keyword must have.

Remember, Python is zero-indexed, which means the *first* keyword has an index
of zero.  A schema encoding the rules given in the previous paragraph for
"SIMPLE" and "BITPIX" might look like this::

    >>> class PrimaryHeaderSchema(Schema):
    ...     SIMPLE = {'value': True, 'mandatory': True, 'position': 0}
    ...     BITPIX = {
    ...         'value': [-64, -32, 8, 16, 32, 64],
    ...         'mandatory': True,
    ...         'position': 1
    ...     }
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

Gotchas
-------

Since the PyFITS schema format actually uses Python syntax to define a schema,
keywords listed in that schema must be valid Python identifiers.  For most
keywords this is not a problem:  The valid characters included uppercase 'A'
through 'Z', the digits 0-9, and the underscore.  However, it also includes
the hyphen, '-', which is *not* a valid character in Python identifiers.  A
common example of this is ``DATE-OBS``.  There is an alternate means of
specifying keywords in a schema that works around this problem:  All `Schema`
classes recognized a class attribute called simply ``keywords`` (all lowercase)
that contains a dictionary mapping keyword names to the rules for that keyword.

For example,

::

    >>> class ExampleSchema(Schema):
    ...     keywords = {
    ...         'FOO': {'mandatory': True}
    ...     }
    ...

is equivalent to

::

    >>> class ExampleSchema(Schema):
    ...     FOO = {'mandatory': True}
    ...

In most cases the latter, attribute-based, listing of keywords is simply a bit
more convenient.  The two formats can also be used simultaneously.  This is how
one might support ``DATE-OBS``::

    >>> class ExampleSchema(Schema):
    ...     FOO = {'mandatory': True}
    ...     keywords = {
    ...         'DATE-OBS': {'value': str}
    ...     }
    ...

In this case ``keywords`` should really be read as "additional keywords".

In fact, even if the ``keywords`` attribute isn't specified explicitly, *all*
`Schema` classes automatically have a ``keywords`` attribute listing the
keywords defined by that schema.  From the above example::

    >>> ExampleSchema.keywords
    {'DATE-OBS': {'value': True}, 'FOO': {'mandatory': True}}

One can see that ``'FOO'`` was added to the ``.keywords`` `dict` along with
``'DATE-OBS'`` (which was included explicitly).  This can be used to introspect
the keywords defined on a given schema without having to manually look through
all of its class attributes.


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
``'position'`` we can supply a *function* (or often a ``lambda`` as a shortcut)
that computes what index ``INSTRUME`` *should* have if it is to come after
``TELESCOP``.  To do this, the function would need access to the actual header
being validated, and it would need to be able to look up the index of the
``TELESCOP`` keyword.  This could be implemented something like this::

    >>> class MySchema6(Schema):
    ...     TELESCOP = {'value': str, 'mandatory': True}
    ...     INSTRUME = {
    ...         'value': str,
    ...         'position': lambda **ctx: ctx['header'].index('TELESCOP') + 1
    ...     }
    ...
    >>> hdr = Header([('TELESCOP', 'HST'), ('FOO', 'abc'),
    ...               ('INSTRUME', 'ACS')])
    >>> hdr
    TELESCOP= 'HST     '
    FOO     = 'abc     '
    INSTRUME= 'ACS     '
    >>> MySchema6.validate(hdr)
    Traceback (most recent call last):
    ...
    pyfits.schema.SchemaValidationError: SchemaValidationError in MySchema6:
    keyword 'INSTRUME' is required to have position 1 in the header; instead it
    was found in position 2 (note: position is zero-indexed)
    >>> hdr.set('INSTRUME', after='TELESCOP')
    >>> hdr
    TELESCOP= 'HST     '
    INSTRUME= 'ACS     '
    FOO     = 'abc     '
    >>> MySchema6.validate(hdr)
    True

.. note::

    Admittedly a more useful error message here might explicitly state that
    ``INSTRUME`` belongs after ``TELESCOP``.  There is no good way for the
    software to parse that meaning out of the validation function, but it
    remains a todo item to add custom error messages to the schema.  This would
    have the added advantage of documenting the intent of the schema.

The ``'position'`` property in the previous example deserves further
explanation.  Although a ``lambda`` was used, any callable (that is, anything
that acts *like* a function) will work.  The only requirement at the moment is
that it take arbitrary keyword arguments using the ``**kwargs`` syntax, and no
positional arguments.  By convention, instead of ``kwargs`` the name ``ctx`` is
used.  This is short for "context", as in, the context in which this keyword is
being validated.

The reason this is kept very flexible is so that additional context variables
may be added later on without requiring all existing validation functions to
be rewritten.  They can simply ignore any new context that may be added.

The most common example of context given to a callable property is the actual
header in the process of being validated.  This is passed in as the ``header``
keyword argument, so it can be accessed via ``ctx['header']``.  This usage is
seen in the previous example where we use ``ctx['header']`` to look up the
index of the ``TELESCOP`` keyword.  We then return that index incremented by
one, giving the index at which the ``INSTRUME`` keyword *should* appear.  In
that example ``ctx['header'].index('TELESCOP')`` returns ``0`` (it is the first
keyword).  So this ends up being equivalent to if we had written ``'position':
1`` for ``INSTRUME``.  The difference being that ``1`` is not
hard-coded--instead it is dependent on the individual header being validated.

Another very common usage of callable properties is validation of keyword
values.  By writing the validation rules for values in Python they may be
arbitrarily complex.  For example, in order to write a rule that a value
is greater than zero we can write::

    >>> class MySchema6(Schema):
    ...     FOO = {'value': lambda **ctx: ctx['value'] > 0}
    ...

Here the actual value of the ``FOO`` keyword being validated is passed in as
the ``value`` context variable.  If the callable returns `True` the value is
considered valid.  But what if we also want to ensure that the value is an
*integer* (as opposed to, say, a floating point value).  We already saw that we
can do type checking like ``FOO = {'value': int}``.  But we can also combine
the two checks in a `tuple`::

    >>> class MySchema7(Schema):
    ...     FOO = {
    ...         'value': (int, lambda **ctx: ctx['value'] > 0)
    ...     }
    ...

This will first ensure that the value is *strictly* an integer.  *Then* runs
the callable to ensure that the value is greater than zero.  Any number of
value tests can be conjoined as a tuple.

Most keyword properties like ``'value'`` and ``'position'`` accept callables
that can implement context-dependent rules for that keyword.  The exact
semantics of those callables, such as what context is provided and what return
values are expected are described in the full documentation for `individual
properties <#supported-keyword-properties>`_.


Indexed keywords
================

One of the unique issues of designing a schema format for FITS is the common
use of sequences of indexed keywords that share a common prefix and the same
semantics.  Because a single FITS keyword can only store scalar values, it is
necessary to use a scheme involving a prefix followed by a numerical (or
in some cases even alphabetical) index in order to store the elements of
compound values.

The most common and familiar example of this by far is the ``NAXISn``
keywords-- ``NAXIS1``, ``NAXIS2``, ..., ``NAXISn`` where ``n`` is the value of
the ``NAXIS`` keyword and may be from 1 through 99.  In principle this could be
handled by manually listing out all possible ``NAXISn`` keywords in the schema,
but this is cumbersome to write, cumbersome to read, and error-prone.

In order to provide an interface for keywords like these that translates
easily from the FITS Standard and other FITS conventions, the PyFITS schema
interface allows defining a sort of "keyword template" where specific
characters in the keyword are designated as placeholders that will later be
interpolated with an index value.  How this works is easier to explain with an
example.  One might implement a schema for the ``NAXISn`` keywords like so::

    >>> class NaxisSchema(Schema):
    ...     NAXISn = {
    ...         'value': (int, lambda **ctx: ctx['value'] >= 0),
    ...         'indices': {'n': range(1, 100)}
    ...     }
    ...

Here the ``'value'`` property expresess that ``NAXISn`` keywords should have
non-negative integer values.  More interesting here is the new `indices`_
property:  This expresses which characters in the keyword should be replaced
with index values.  In this example the character ``'n'`` should be
replaced with the values in the range 1 through 99.  Two things should be
pointed out about this:

 1. Keywords listed in the schema are case-sensitive:  "NAXISn" contains an
    uppercase "N" and a lowercase "n", but only the lowercase "n" is treated
    as the index placeholder.

 2. The range of allowed index values is given as the integers 1 through 99,
    but keyword names are always strings.  When interpolating the possible
    index values those values are automatically converted to strings via their
    ``__str__`` method.  The most common case here is integers, so this just
    automatically converts integer values to their string representations.

In practice, the above example works exactly the same as a schema in which all
99 possible ``NAXISn`` keywords were written out one by one::

    >>> class NaxisSchema(Schema):
    ...     NAXIS1 = {'value': (int, lambda **ctx: ctx['value'] >= 0)}
    ...     NAXIS2 = {'value': (int, lambda **ctx: ctx['value'] >= 0)}
    ...     # .. and so on up to
    ...     NAXIS99 = {'value': (int, lambda **ctx: ctx['value'] >= 0)}
    ...

At this point, the reader might noticed that the last example is still not a
complete schema for the ``NAXISn`` keywords in a standard FITS header.  If a
header has, for example, ``NAXIS = 2``, then it *must* have an ``NAXIS1``
keyword and an ``NAXIS2`` keyword and any other ``NAXISn`` keywords are in
fact invalid.  One could use a context-based callable to define the allowed
range of ``NAXISn`` keywords like so::

    >>> class NaxisSchema(Schema):
    ...     NAXISn = {
    ...         'value': (int, lambda **ctx: ctx['value'] >= 0),
    ...         'indices': {
    ...             'n': lambda **ctx: range(1, ctx['header']['NAXIS'] + 1)
    ...         },
    ...         'mandatory': True
    ...     }
    ...

In this example a *function* is used to determine the range of indices allowed
for ``NAXISn`` based on the value of the header's ``NAXIS`` keyword.  If
validating a header in which ``NAXIS = 2`` this will make ``NAXIS1`` and
``NAXIS2`` mandatory and validate that they are non-negative integers.  This is
still not as strong as it could be, in that it *allows* keywords with ``n > 2``
such as ``NAXIS3`` and above.  But they are simply ignored--treated as
non-meaningful to the schema.  Once could make a strong schema that outright
disallows them::

    >>> class NaxisSchema(Schema):
    ...     NAXISn = {
    ...         'value': (int, lambda **ctx: ctx['value'] >= 0),
    ...         'indices': {'n': range(1, 100)}
    ...         'mandatory': \
    ...             lambda **ctx: ctx['header']['NAXIS'] >= ctx['n'] >= 1,
    ...         'invalid': lambda **ctx: ctx['n'] > ctx['header']['NAXIS']
    ...     }
    ...

This last example deserves some unpacking:  Now were are again checking all
possible indices from 1 to 99.  If the index is between 1 and the value of
``NAXIS`` it is mandatory.  If the index is greated than ``NAXIS`` then that
keyword is invalid.  The index of a given keyword is passed to the
``'mandatory'`` and ``'invalid'`` functions in the context dict as ``'n'``.

For example, consider the header::

    NAXIS   =                    2
    NAXIS1  =                  100
    NAXIS2  =                  100

When evaluating this header against the above schema, all keywords ``NAXIS1``
through ``NAXIS99`` are looped over and the functions for ``'mandatory'`` and
``'invalid'`` are evaluated for that keyword.  For ``NAXIS1``, where ``n = 1``,
``'mandatory'`` returns `True` and ``'invalid'`` returns `False`.  Likewise
for ``NAXIS2``.  But for ``NAXIS3`` and above ``'mandatory'`` returns `False`
and the ``'invalid'`` function returns `True`.  If any of those keywords appear
in the header it will fail validation.

.. note::

    In the future it might be worth adding a means of marking some rules so
    that they return warnings rather than outright invalidate the header.

Multiple indices
----------------

Part of the complexity (or if you prefer "flexibility") of the ``'indices'``
property comes from its support for keywords containing multiple indices.  One
of the most common examples of this is the ``CDi_j`` keywords used to represent
elements of the transformation matrix used in the FITS WCS convention.  Here
there are two indices, ``i`` and ``j``.  This can be implemented in a PyFITS
schema like::

    >>> class WcsSchema(Schema):
    ...     CDi_j = {
    ...         'value': float,
    ...         'indices': {
    ...             'i': lambda **ctx: WcsSchema.wcs_range(**ctx),
    ...             'j', lambda **ctx: range(1, ctx['header']['NAXIS'] + 1)
    ...         }
    ...    }
    ...    
    ...    @staticmethod
    ...    def wcs_range(header=None, **ctx):
    ...        return range(1, header.get('WCSAXES', header['NAXIS']))
    ...

In this example the allowed range ``'j'`` index (the number of pixel
coordinates) is determined from the headers ``NAXIS`` keyword.  The allowed
range for ``'i'`` (the number of WCS coordinates) is determined from
``WCSAXES`` if it exists, and otherwise falls back on ``NAXIS``.  This time
the range function for ``'i'`` was defined in a separate staticmethod rather
than in-line for clarity's sake.  This also allows it to be reused in the
rules for other keywords, such as ``CTYPEi``.

This schema will check keywords in the ``CDi_j`` format over the Cartesian
product of the ranges for those indices.  For example if ``NAXIS = 2`` this
schema will check for all of ``CD1_1``, ``CD1_2``, ``CD2_1``, and ``CD2_2``.
This is a rough implementation of the rules for this keyword; a fully-compliant
implementation is a bit more complex.  One modification we would need to make,
for example, is support for multiple WCS transformations.  This is an example
where the range of values are not integers::

    >>> class BaseWCSSchema(Schema):
    ...     # 'A'-'Z' including blank
    ...     coordinate_versions = \
    ...         [''] + [chr(x) for x in range(ord('A'), ord('Z') + 1)]
    ...    
    ...     CDi_ja = {
    ...         'value': float,
    ...         'indices': {
    ...             'i': lambda **ctx: WcsSchema.wcs_range(**ctx),
    ...             'j', lambda **ctx: range(1, ctx['header']['NAXIS'] + 1),
    ...             'a': coordinate_versions
    ...         }
    ...    }
    ...    
    ...    @staticmethod
    ...    def wcs_range(header=None, **ctx):
    ...        return range(1, header.get('WCSAXES', header['NAXIS']))
    ...

This is still a rough example, but might be the basic approach in writing a
schema for FITS WCS.  But even in the case of complex rules such as these, the
author posits that such a schema still provides a more concise and cogent
description of the rules for these keywords than ad-hoc code might.  Future
enhancements to the schema format may further simplify definition of complex
patterns of rules that appear commonly in FITS-based conventions.


Schema inheritance
==================

Some of the greatest power of PyFITS schemas is their extensibility.  PyFITS
includes built-in schemas for all of the basic data types supported by the FITS
standard--particularly image arrays.  This schema includes all the rules for
keywords like ``NAXIS`` and ``BITPIX`` as well as standard metadata such as
``DATE-OBS``.  When developing a schema with which to check correctness of
describing observations made with a specific instrument one might start with
`BaseArraySchema` which describes headers for all FITS standard array-like
data (whether in the primary HDU or an extension).  Basic extension to PyFITS
schemas works through Python class inheritance.  So to add rules for
additional keywords to `BaseArraySchema` one simply subclasses it.  For
example, a general schema for ACS headers might start out something like::

    >>> class BaseACSImageSchema(pyfits.BaseArraySchema):
    ...     TELESCOP = {'value': 'HST', 'mandatory': True}
    ...     INSTRUME = {'value': 'ACS', 'mandatory': True}
    ...     OBSTYPE = {
    ...         'value': ['IMAGING', 'SPECTROSCOPIC', 'CORONAGRAPHIC'],
    ...         'mandatory': True
    ...     }
    ...     DETECTOR = {'value': ['WCF', 'HRC', 'SBC'], 'mandatory': True}
    ...

These are just a small set of the keywords one would define rules for in this
case, but they would fairly uniquely identify a given header as belonging to
an ACS observation.  The first thing to note about this example is that the
``TELESCOP`` and ``INSTRUME`` keywords are not unique to ACS--these are
keywords defined by the FITS standard, and are indeed part of the basic
`BaseArraySchema`::

    >>> pyfits.BaseArraySchema.TELESCOP
    {'value': str}
    >>> pyfits.BaseArraySchema.INSTRUME
    {'value': str}

However, their definitions are very loose--they are entirely optional, and the
only rule for them is that their value contains a string.  The
``BaseACSImageSchema`` we defined above overrides these rules by adding that
the keyword is mandatory, and restricting the exact values that the keywords
may have.

``OBSTYPE`` and ``DETECTOR`` on the other hand are not mentioned by the FITS
standard and are entirely unique to this extension schema.

An extension schema may also extend/inherit from multiple base schemas
following Python's standard multiple-inheritance rules.  For example, the
`PrimaryArraySchema` is composed from `BaseArraySchema` and `PrimarySchema`
(where the latter is a schema that matches all FITS primary HDUs (i.e. where
the first keyword is ``SIMPLE = T``).  `PrimaryArraySchema` gets most of its
rules first from `BaseArraySchema`, but then adds some additional rules (for
the ``SIMPLE``, ``EXTEND``, and ``BLOCKED`` keywords) from `PrimarySchema`.

Another possible use case is "mixin" schemas that add support for additional
keywords defined by a particular convention.  For example the included
`ChecksumSchema` provides validation for the ``DATASUM`` and ``CHECKSUM``
keywords defined by the `FITS Checksum <http://fits.gsfc.nasa.gov/registry/checksum.html>`_
convention.  As PyFITS supports this convention it mixes this schema into
the basic schemas for valid FITS headers, but still keeps it logically as an
independent schema, clarifying that it is a separate convention and not
part of the FITS standard.


Supported keyword properties
============================

This section lists all presently supported keyword properties and their allowed
values.  This is likely to change as the feature is used more and the set of
required use cases becomes clearer.  In particular, it is likely to grow as
shortcuts are added for common use cases.

mandatory
---------

This property indicates that the presence of a keyword is *required* in a
header in order for that header to be valid under the current schema.  By
default no keywords are mandatory--this property must be explicitly set to
`True`.

Allowed values: `bool`, callable

 * If given a `bool`, a value of `True` means the keyword is mandatory, and a
   value of `False` means the keyword is not mandatory (it is optional)
 * If given a callable, that callable *must* return a `bool` to be interpreted
   as in the previous bullet point.  The context arguments provided to this
   callable when validating a specific header include:

   * the current header being validated
   * the name of the keyword being validated
   * any indices defined on the keyword being validated

valid
-----

This property is in some sense the opposite of `mandatory`_--by defaut any
keywords that appear in a header, whether they are explicitly checked by the
schema or not, are valid.  But if a keyword is marked invalid by setting valid
to `False` then the mere presence of that keyword in a header makes the header
invalid under that schema.

Allowed values: `bool`, callable

 * If given a `bool`, a value of `False` means the keyword is *invalid*, and a
   value of `True` (the default) means that the keyword's presence is valid.
 * If given a callable, that callable *must* return a `bool` to be interpreted
   as in the previous bullet point.  The context arguments provided to this
   callable when validating a specific header include:

   * the current header being validated
   * the name of the keyword being validated
   * any indices defined on the keyword being validated

position
--------

This property defines the exact position, indicated by a zero-based numerical
index into the list of header cards, that a keyword must be found in for the
header to be valid.  More advanced rules can be defined by providing a callable
that simply indicates whether or not the keyword's position is valid regardless
of its exact position.

Allowed values: `int`, callable

 * If given an `int` it must be greater than or equal to zero.  This indicates
   the exact index that the keyword must have in the list of all cards in the
   header being validated.
 * If given a callable, that callable *must* return either an `int` or a
   `bool`.  If it returns and `int`, that value is to be interpreted as in the
   previous bullet point.  If it returns a value of `True` that simply
   indicates that the keyword's position is valid (regardless of its exact)
   index, and a value of `False` indicates that the keyword's position is
   invalid (and hence the header is invalid under that schema).  The context
   arguments provided to this callable when validating a specific header
   include:

   * the current header being validated
   * the name of the keyword being validated
   * any indices defined on the keyword being validated

value
-----

This property defines rules for the value associated with a keyword in a
header.  It is one of the most complicated keyword properties, as it allows
checking the type of the value (numeric, string, etc.), the exact allowed
value(s) for that keyword, or various combinations thereof.

Allowed values: `type`, `int`, `float`, `complex`, `str`, `bool`, `list`,
`tuple`, callable

 * If given a Python `type` object it must be Python built-in type
   corresponding to the types of scalar values that can be stored in a FITS
   header value.  These include `int`, `float`, `complex`, `str`, and `bool`.
   That is, to require the value to be an integer, the `int` type itself is
   given for the ``'value'`` property.
 * If given an `int`, `float`, `complex`, `str`, or `bool`--that is, an
   individual instance of one of those types rather than the types itself (eg.
   the integer ``1`` or the string ``'HST'``) then the value of the keyword is
   compared for equality with this property.  If that comparison succeeds then
   the header is valid under that schema.  For comparison of numerical values
   this incorporates normal casting rules, so a rule like ``{'value': 1}``
   (where the value is must be equal to the integer ``1``) succeeds for a
   floating-point value of ``1.0``.  It is also possible to require a value of
   ``1`` that *must* be an strictly integer (without a decimal point anywhere
   in the value).  See two bullet points down.
 * If given a `list` this suggests a range of values that are valid.  For
   example a list containing the strings ``['WCF', 'HRC', 'SBC']`` means that
   any one of those values (and only those values) is considered valid for
   the current keyword.  The lists need not be homogeneous so long as its
   members are only of the types listed in the previous bullet point.
 * If given a `tuple` this represents a conjunction of any of the above three
   bullet points and the following one (a callable).  That is, a tuple of
   more than one ``'value'`` properties means that all those properties must
   be satisfied simultaneously.  A common case for this would be something like
   ``(int, 1)`` which ensures that the value is equivalent to ``1`` and that
   it must be an integer (and not a floating point or complex value).
 * If given a callable that callable *must* return a `bool` indicating whether
   or not the value is valid.  If `False` the value, and hence the header being
   validated under that schema are invalid.  This allows for completely
   arbitrary validation rules.  The context
   arguments provided to this callable when validating a specific header
   include:

   * the current header being validated
   * the name of the keyword being validated
   * any indices defined on the keyword being validated
   * the actual value of the keyword in the current header being validated;
     this would be equivalent to ``ctx['header'][ctx['keyword']]`` and is
     provided for convenience

indices
-------

This property defines the indices associated with a keyword *template* such as
``NAXISn``, where ``n`` is replaced with an index value.  See the section on
`Indexed keywords`_ for full details.  The ``'indices'`` property is different
from others in that it does not determine validity of a *specific* keyword
against the schema.  Rather, it generates a set of rules for a whole class of
keywords determined by the keyword template and the range(s) of index values.

Allowed values: `dict`

 * The value of this property is a `dict` mapping a single character string
   representing each index in the keyword template with either a `list` or
   a callable defining the range of values that specific index may take.
   * If given a `list` the contents of that list are the exact values that
     index may take.  For example the list generated by `range(1, 100)` allows
     the index character to be replaced with the values 1 through 99.  The
     elements of the list need not be strings, but when interpolating them
     into the keyword template they will be converted to strings by calling the
     `str` function on them.  For integers (the most common case) this just
     returns the normal string representation of that integer.
   * If given a callable, that callable must return a `list` as described in
     the previous bullet point.  The context arguments provided to this
     callable when validating a specific header include:

     * the current header being validated
     * the name of the keyword template that indices for which indices are
       being generated
