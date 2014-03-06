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

There also exists a ``'valid'`` property.  This is in some ways the inverse of
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
of one of -64, -32, 8, 16, 32, or 64).  We use the ``'position'`` property to
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
``'DATE-OBS'`` (which was alreadt there).  This can be used to introspect
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
``'property'`` we can supply a *function* (or often a ``lambda`` as a shortcut)
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
explanation.  Although a ``lambda`` was used, any callable will work.  The only
requirement at the moment is that it take arbitrary keyword arguments using
the ``**kwargs`` syntax, and no positional arguments.  By convention, instead
of ``kwargs`` the name ``ctx`` is used.  This is short for "context", as in,
the context in which this keyword is being validated.

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
values are expected are described in the full documentation for individual
properties.


Indexed keywords
================

One of the unique issues of designing a schema format for FITS is the common
use of sequences of indexed keywords that share a common prefix and the same
semantics.  Because a single FITS keyword can only store scalar values, it is
necessary to use a scheme involving a prefix followed by a numerical (or
in some cases even alphabetical) index in order to store the elements of
compound values.

The most common and familiar example of this by far is the ``NAXISn``
keywords-- ``NAXIS1``, ``NAXIS2``, ..., ```NAXISn`` where ``n`` is the value
of the ``NAXIS`` keyword and may be from 1 up to 99.  In principle this could
be handled by manually listing out all possible ``NAXISn`` keywords in the
schema, but this is cumbersome to write, cumbersome to read, and error-prone.

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
non-negative integer values.  More interesting here is the new ``'indices'``
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
property comes from its support for keywords ontaining multiple indices.  One
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

    >>> class WcsSchema(Schema):
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
