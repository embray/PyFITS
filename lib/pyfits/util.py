from __future__ import division

import functools
import gzip
import itertools
import mmap
import os
import signal
import sys
import tempfile
import textwrap
import threading
import warnings

try:
    import io
except ImportError:
    io = None

try:
    from StringIO import StringIO
except ImportError:
    class StringIO(object):
        pass

import numpy as np

from .extern.six import (PY3, iteritems, string_types, integer_types,
                         text_type, binary_type, next)
from .extern.six.moves import zip, reduce


BLOCK_SIZE = 2880  # the FITS block size


if PY3:
    cmp = lambda a, b: (a > b) - (a < b)
else:
    cmp = cmp


def first(iterable):
    """
    Returns the first item returned by iterating over an iterable object.

    Example:

    >>> a = [1, 2, 3]
    >>> first(a)
    1
    """

    return next(iter(iterable))


def itersubclasses(cls, _seen=None):
    """
    itersubclasses(cls)

    Generator over all subclasses of a given class, in depth first order.

    >>> list(itersubclasses(int)) == [bool]
    True
    >>> class A(object): pass
    >>> class B(A): pass
    >>> class C(A): pass
    >>> class D(B,C): pass
    >>> class E(D): pass
    >>>
    >>> for cls in itersubclasses(A):
    ...     print(cls.__name__)
    B
    D
    E
    C
    >>> # get ALL (new-style) classes currently defined
    >>> [cls.__name__ for cls in itersubclasses(object)] #doctest: +ELLIPSIS
    [...'tuple', ...'type', ...]

    From http://code.activestate.com/recipes/576949/
    """

    if not isinstance(cls, type):
        raise TypeError('itersubclasses must be called with '
                        'new-style classes, not %.100r' % cls)
    if _seen is None:
        _seen = set()
    try:
        subs = cls.__subclasses__()
    except TypeError:  # fails only when cls is type
        subs = cls.__subclasses__(cls)
    for sub in sorted(subs, key=lambda s: s.__name__):
        if sub not in _seen:
            _seen.add(sub)
            yield sub
            for sub in itersubclasses(sub, _seen):
                yield sub


class lazyproperty(object):
    """
    Works similarly to property(), but computes the value only once.

    Adapted from the recipe at
    http://code.activestate.com/recipes/363602-lazy-property-evaluation
    """

    def __init__(self, fget, fset=None, fdel=None, doc=None):
        self._fget = fget
        self._fset = fset
        self._fdel = fdel
        if doc is None:
            self.__doc__ = fget.__doc__
        else:
            self.__doc__ = doc
        self._key = self._fget.__name__

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        try:
            return obj.__dict__[self._key]
        except KeyError:
            val = self._fget(obj)
            obj.__dict__[self._key] = val
            return val

    def __set__(self, obj, val):
        obj_dict = obj.__dict__
        if self._fset:
            ret = self._fset(obj, val)
            if ret is not None and obj_dict.get(self._key) is ret:
                # By returning the value set the setter signals that it took
                # over setting the value in obj.__dict__; this mechanism allows
                # it to override the input value
                return
        obj_dict[self._key] = val

    def __delete__(self, obj):
        if self._fdel:
            self._fdel(obj)
        if self._key in obj.__dict__:
            del obj.__dict__[self._key]

    def getter(self, fget):
        return self.__ter(fget, 0)

    def setter(self, fset):
        return self.__ter(fset, 1)

    def deleter(self, fdel):
        return self.__ter(fdel, 2)

    def __ter(self, f, arg):
        args = [self._fget, self._fset, self._fdel, self.__doc__]
        args[arg] = f
        cls_ns = sys._getframe(1).f_locals
        for k, v in iteritems(cls_ns):
            if v is self:
                property_name = k
                break

        cls_ns[property_name] = lazyproperty(*args)

        return cls_ns[property_name]


class PyfitsDeprecationWarning(UserWarning):
    pass


class PyfitsPendingDeprecationWarning(UserWarning):
    pass


# TODO: Provide a class deprecation marker as well.
def deprecated(since, message='', name='', alternative='', pending=False):
    """
    Used to mark a function as deprecated.

    To mark an attribute as deprecated, replace that attribute with a
    depcrecated property.

    Parameters
    ------------
    since : str
        The release at which this API became deprecated.  This is required.

    message : str, optional
        Override the default deprecation message.  The format specifier
        %(func)s may be used for the name of the function, and %(alternative)s
        may be used in the deprecation message to insert the name of an
        alternative to the deprecated function.

    name : str, optional
        The name of the deprecated function; if not provided the name is
        automatically determined from the passed in function, though this is
        useful in the case of renamed functions, where the new function is just
        assigned to the name of the deprecated function.  For example:
            def new_function():
                ...
            oldFunction = new_function

    alternative : str, optional
        An alternative function that the user may use in place of the
        deprecated function.  The deprecation warning will tell the user about
        this alternative if provided.

    pending : bool, optional
        If True, uses a PyfitsPendingDeprecationWarning instead of a
        PyfitsDeprecationWarning.

    """

    def deprecate(func, message=message, name=name, alternative=alternative,
                  pending=pending):
        if isinstance(func, classmethod):
            try:
                func = func.__func__
            except AttributeError:
                # classmethods in Python2.6 and below lack the __func__
                # attribute so we need to hack around to get it
                method = func.__get__(None, object)
                if hasattr(method, '__func__'):
                    func = method.__func__
                elif hasattr(method, 'im_func'):
                    func = method.im_func
                else:
                    # Nothing we can do really...  just return the original
                    # classmethod
                    return func
            is_classmethod = True
        else:
            is_classmethod = False

        if not name:
            name = func.__name__

        altmessage = ''
        if not message or type(message) == type(deprecate):
            if pending:
                message = ('The %(func)s function will be deprecated in a '
                           'future version.')
            else:
                message = (
                    'The %(func)s function is deprecated as of version '
                    '%(since)s and may be removed in a future version.')
            if alternative:
                altmessage = '\n\n        Use %s instead.' % alternative

        message = ((message % {'func': name, 'alternative': alternative,
                               'since': since}) + altmessage)

        @functools.wraps(func)
        def deprecated_func(*args, **kwargs):
            if pending:
                category = PyfitsPendingDeprecationWarning
            else:
                category = PyfitsDeprecationWarning

            warnings.warn(message, category, stacklevel=2)

            return func(*args, **kwargs)

        old_doc = deprecated_func.__doc__
        if not old_doc:
            old_doc = ''
        old_doc = textwrap.dedent(old_doc).strip('\n')
        altmessage = altmessage.strip()
        if not altmessage:
            altmessage = message.strip()
        new_doc = (('\n.. deprecated:: %(since)s'
                    '\n    %(message)s\n\n' %
                    {'since': since, 'message': altmessage.strip()}) + old_doc)
        if not old_doc:
            # This is to prevent a spurious 'unexected unindent' warning from
            # docutils when the original docstring was blank.
            new_doc += r'\ '

        deprecated_func.__doc__ = new_doc

        if is_classmethod:
            deprecated_func = classmethod(deprecated_func)
        return deprecated_func

    if type(message) == type(deprecate):
        return deprecate(message)

    return deprecate


def ignore_sigint(func):
    """
    This decorator registers a custom SIGINT handler to catch and ignore SIGINT
    until the wrapped function is completed.
    """

    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        # Get the name of the current thread and determine if this is a single
        # treaded application
        curr_thread = threading.currentThread()
        single_thread = (threading.activeCount() == 1 and
                         curr_thread.getName() == 'MainThread')

        class SigintHandler(object):
            def __init__(self):
                self.sigint_received = False

            def __call__(self, signum, frame):
                warnings.warn('KeyboardInterrupt ignored until %s is '
                              'complete!' % func.__name__)
                self.sigint_received = True

        sigint_handler = SigintHandler()

        # Define new signal interput handler
        if single_thread:
            # Install new handler
            old_handler = signal.signal(signal.SIGINT, sigint_handler)

        try:
            func(*args, **kwargs)
        finally:
            if single_thread:
                if old_handler is not None:
                    signal.signal(signal.SIGINT, old_handler)
                else:
                    signal.signal(signal.SIGINT, signal.SIG_DFL)

                if sigint_handler.sigint_received:
                    raise KeyboardInterrupt

    return wrapped


def pairwise(iterable):
    """Return the items of an iterable paired with its next item.

    Ex: s -> (s0,s1), (s1,s2), (s2,s3), ....
    """

    a, b = itertools.tee(iterable)
    for _ in b:
        # Just a little trick to advance b without having to catch
        # StopIter if b happens to be empty
        break
    return zip(a, b)


def isiterable(obj):
    """Returns true of the given object is iterable."""

    # In Python2.6 and up this is simply a matter of checking isinstance
    # collections.Iterable, but this unavailable in Python 2.5 and below
    try:
        from collections import Iterable
        if isinstance(obj, Iterable):
            return True
    except ImportError:
        pass

    try:
        iter(obj)
        return True
    except TypeError:
        return False


def encode_ascii(s):
    """
    In Python 2 this is a no-op.  Strings are left alone.  In Python 3 this
    will be replaced with a function that actually encodes unicode strings to
    ASCII bytes.
    """

    return s


def decode_ascii(s):
    """
    In Python 2 this is a no-op.  Strings are left alone.  In Python 3 this
    will be replaced with a function that actually decodes ascii bytes to
    unicode.
    """

    return s


def isreadable(f):
    """
    Returns True if the file-like object can be read from.  This is a common-
    sense approximation of io.IOBase.readable.
    """

    if hasattr(f, 'closed') and f.closed:
        # This mimics the behavior of io.IOBase.readable
        raise ValueError('I/O operation on closed file')

    if not hasattr(f, 'read'):
        return False

    if hasattr(f, 'mode') and not any((c in f.mode for c in 'r+')):
        return False

    # Not closed, has a 'read()' method, and either has no known mode or a
    # readable mode--should be good enough to assume 'readable'
    return True


def iswritable(f):
    """
    Returns True if the file-like object can be written to.  This is a common-
    sense approximation of io.IOBase.writable.
    """

    if hasattr(f, 'closed') and f.closed:
        # This mimics the behavior of io.IOBase.writable
        raise ValueError('I/O operation on closed file')

    if not hasattr(f, 'write'):
        return False

    if hasattr(f, 'mode') and not any((c in f.mode for c in 'wa+')):
        return False

    # Note closed, has a 'write()' method, and either has no known mode or a
    # mode that supports writing--should be good enough to assume 'writable'
    return True


def isfile(f):
    """
    Returns True if the given object represents an OS-level file (that is,
    isinstance(f, file)).

    On Python 3 this also returns True if the given object is higher level
    wrapper on top of a FileIO object, such as a TextIOWrapper.
    """

    return isinstance(f, file)


def fileobj_open(filename, mode):
    """
    A wrapper around the `open()` builtin.

    This exists because in Python 3, `open()` returns an `io.BufferedReader` by
    default.  This is bad, because `io.BufferedReader` doesn't support random
    access, which we need in some cases.  In the Python 3 case (implemented in
    the py3compat module) we must call open with buffering=0 to get a raw
    random-access file reader.
    """

    return open(filename, mode)


def fileobj_name(f):
    """
    Returns the 'name' of file-like object f, if it has anything that could be
    called its name.  Otherwise f's class or type is returned.  If f is a
    string f itself is returned.
    """

    if isinstance(f, string_types):
        return f
    elif hasattr(f, 'name'):
        return f.name
    elif hasattr(f, 'filename'):
        return f.filename
    elif hasattr(f, '__class__'):
        return str(f.__class__)
    else:
        return str(type(f))


def fileobj_closed(f):
    """
    Returns True if the given file-like object is closed or if f is not a
    file-like object.
    """

    if hasattr(f, 'closed'):
        return f.closed
    elif hasattr(f, 'fileobj') and hasattr(f.fileobj, 'closed'):
        return f.fileobj.closed
    elif hasattr(f, 'fp') and hasattr(f.fp, 'closed'):
        return f.fp.closed
    else:
        return False


def fileobj_mode(f):
    """
    Returns the 'mode' string of a file-like object if such a thing exists.
    Otherwise returns None.
    """

    # Go from most to least specific--for example gzip objects have a 'mode'
    # attribute, but it's not analogous to the file.mode attribute
    if hasattr(f, 'fileobj') and hasattr(f.fileobj, 'mode'):
        fileobj = f.fileobj
    elif hasattr(f, 'fp') and hasattr(f.fp, 'mode'):
        fileobj = f.fp
    elif hasattr(f, 'mode'):
        fileobj = f
    else:
        return None

    return _fileobj_normalize_mode(fileobj)


def _fileobj_normalize_mode(f):
    """Takes care of some corner cases in Python where the mode string
    is either oddly formatted or does not truly represent the file mode.
    """

    # I've noticed that sometimes Python can produce modes like 'r+b' which I
    # would consider kind of a bug--mode strings should be normalized.  Let's
    # normalize it for them:
    mode = f.mode

    if isinstance(f, gzip.GzipFile):
        # GzipFiles can be either readonly or writeonly
        if mode == gzip.READ:
            return 'rb'
        elif mode == gzip.WRITE:
            return 'wb'
        else:
            # This shouldn't happen?
            return None

    if '+' in mode:
        mode = mode.replace('+', '')
        mode += '+'

    if _fileobj_is_append_mode(f) and 'a' not in mode:
        mode = mode.replace('r', 'a').replace('w', 'a')

    return mode


def _fileobj_is_append_mode(f):
    """Normally the way to tell if a file is in append mode is if it has
    'a' in the mode string.  However on Python 3 (or in particular with
    the io module) this can't be relied on.  See
    http://bugs.python.org/issue18876.
    """

    if 'a' in f.mode:
        # Take care of the obvious case first
        return True

    # We might have an io.FileIO in which case the only way to know for sure
    # if the file is in append mode is to ask the file descriptor
    if not hasattr(f, 'fileno'):
        # Who knows what this is?
        return False

    # Call platform-specific _is_append_mode
    # If this file is already closed this can result in an error
    try:
        return _is_append_mode_platform(f.fileno())
    except (ValueError, IOError):
        return False


if sys.platform.startswith('win32'):
    # This global variable is used in _is_append_mode to cache the computed
    # size of the ioinfo struct from msvcrt which may have a different size
    # depending on the version of the library and how it was compiled
    _sizeof_ioinfo = None

    def _make_is_append_mode():
        # We build the platform-specific _is_append_mode function for Windows
        # inside a function factory in order to avoid cluttering the local
        # namespace with ctypes stuff
        from ctypes import (cdll, c_size_t, c_void_p, c_int, c_char,
                            Structure, POINTER, cast)

        try:
            from ctypes.util import find_msvcrt
        except ImportError:
            # find_msvcrt is not available on Python 2.5 so we have to provide
            # it ourselves anyways
            from distutils.msvccompiler import get_build_version

            def find_msvcrt():
                version = get_build_version()
                if version is None:
                    # better be safe than sorry
                    return None
                if version <= 6:
                    clibname = 'msvcrt'
                else:
                    clibname = 'msvcr%d' % (version * 10)

                # If python was built with in debug mode
                import imp
                if imp.get_suffixes()[0][0] == '_d.pyd':
                    clibname += 'd'
                return clibname+'.dll'

        def _dummy_is_append_mode(fd):
            warnings.warn(
                'Could not find appropriate MS Visual C Runtime '
                'library or library is corrupt/misconfigured; cannot '
                'determine whether your file object was opened in append '
                'mode.  Please consider using a file object opened in write '
                'mode instead.')
            return False

        msvcrt_dll = find_msvcrt()
        if msvcrt_dll is None:
            # If for some reason the C runtime can't be located then we're dead
            # in the water.  Just return a dummy function
            return _dummy_is_append_mode

        msvcrt = cdll.LoadLibrary(msvcrt_dll)


        # Constants
        IOINFO_L2E = 5
        IOINFO_ARRAY_ELTS = 1 << IOINFO_L2E
        IOINFO_ARRAYS = 64
        FAPPEND = 0x20
        _NO_CONSOLE_FILENO = -2


        # Types
        intptr_t = POINTER(c_int)

        class my_ioinfo(Structure):
            _fields_ = [('osfhnd', intptr_t),
                        ('osfile', c_char)]

        # Functions
        _msize = msvcrt._msize
        _msize.argtypes = (c_void_p,)
        _msize.restype = c_size_t

        # Variables
        # Since we don't know how large the ioinfo struct is just treat the
        # __pioinfo array as an array of byte pointers
        __pioinfo = cast(msvcrt.__pioinfo, POINTER(POINTER(c_char)))

        # Determine size of the ioinfo struct; see the comment above where
        # _sizeof_ioinfo = None is set
        global _sizeof_ioinfo
        if __pioinfo[0] is not None:
            _sizeof_ioinfo = _msize(__pioinfo[0]) // IOINFO_ARRAY_ELTS

        if not _sizeof_ioinfo:
            # This shouldn't happen, but I suppose it could if one is using a
            # broken msvcrt, or just happened to have a dll of the same name
            # lying around.
            return _dummy_is_append_mode

        def _is_append_mode(fd):
            global _sizeof_ioinfo
            if fd != _NO_CONSOLE_FILENO:
                idx1 = fd >> IOINFO_L2E # The index into the __pioinfo array
                # The n-th ioinfo pointer in __pioinfo[idx1]
                idx2 = fd & ((1 << IOINFO_L2E) - 1)
                if 0 <= idx1 < IOINFO_ARRAYS and __pioinfo[idx1] is not None:
                    # Doing pointer arithmetic in ctypes is irritating
                    pio = c_void_p(cast(__pioinfo[idx1], c_void_p).value +
                                   idx2 * _sizeof_ioinfo)
                    ioinfo = cast(pio, POINTER(my_ioinfo)).contents
                    return bool(ord(ioinfo.osfile) & FAPPEND)
            return False

        return _is_append_mode

    _is_append_mode_platform = _make_is_append_mode()
    del _make_is_append_mode
else:
    import fcntl

    def _is_append_mode_platform(fd):
        return bool(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_APPEND)


def fileobj_is_binary(f):
    """
    Returns True if the give file or file-like object has a file open in binary
    mode.  When in doubt, returns True by default.
    """

    # This is kind of a hack for this to work correctly with _File objects,
    # which, for the time being, are *always* binary
    if hasattr(f, 'binary'):
        return f.binary

    if io is not None and isinstance(f, io.TextIOBase):
        return False

    mode = fileobj_mode(f)
    if mode:
        return 'b' in mode
    else:
        return True


def translate(s, table, deletechars):
    """
    This is a version of string/unicode.translate() that can handle string or
    unicode strings the same way using a translation table made with
    string.maketrans.
    """

    if isinstance(s, str):
        return s.translate(table, deletechars)
    elif isinstance(s, text_type):
        table = dict((x, ord(table[x])) for x in range(256)
                     if ord(table[x]) != x)
        for c in deletechars:
            table[ord(c)] = None
        return s.translate(table)


def indent(s, shift=1, width=4):
    indented = '\n'.join(' ' * (width * shift) + l if l else ''
                         for l in s.splitlines())
    if s[-1] == '\n':
        indented += '\n'

    return indented


def fill(text, width, *args, **kwargs):
    """
    Like :func:`textwrap.wrap` but preserves existing paragraphs which
    :func:`textwrap.wrap` does not otherwise handle well.  Also handles section
    headers.
    """

    paragraphs = text.split('\n\n')

    def maybe_fill(t):
        if all(len(l) < width for l in t.splitlines()):
            return t
        else:
            return textwrap.fill(t, width, *args, **kwargs)

    return '\n\n'.join(maybe_fill(p) for p in paragraphs)


def _array_from_file(infile, dtype, count, sep):
    """Create a numpy array from a file or a file-like object."""

    if isfile(infile):
        return np.fromfile(infile, dtype=dtype, count=count, sep=sep)
    else:
        # treat as file-like object with "read" method; this includes gzip file
        # objects, because numpy.fromfile just reads the compressed bytes from
        # their underlying file object, instead of the decompresed bytes
        read_size = np.dtype(dtype).itemsize * count
        s = infile.read(read_size)
        return np.fromstring(s, dtype=dtype, count=count, sep=sep)


def _array_to_file(arr, outfile):
    """Write a numpy array to a file or a file-like object."""

    if isfile(outfile):
        def write(a, f):
            a.tofile(f)
    else:
        # treat as file-like object with "write" method and write the array
        # via its buffer interface
        def write(a, f):
            # StringIO in Python 2.5 asks 'if not s' which fails for a Numpy
            # array; test ahead of time if the array is empty, and pass in the
            # array buffer directly
            if isinstance(f, StringIO):
                if len(a):
                    f.write(a.data)
            else:
                f.write(a)

    # Implements a workaround for a bug deep in OSX's stdlib file writing
    # functions; on 64-bit OSX it is not possible to correctly write a number
    # of bytes greater than 2 ** 32 and divisble by 4096 (or possibly 8192--
    # whatever the default blocksize for the filesystem is).
    # This issue should have a workaround in Numpy too, but hasn't been
    # implemented there yet: https://github.com/astropy/astropy/issues/839
    osx_write_limit = (2 ** 32) - 1

    if (sys.platform == 'darwin' and arr.nbytes >= osx_write_limit + 1 and
            arr.nbytes % 4096 == 0):
        idx = 0
        # chunksize is a count of elements in the array, not bytes
        chunksize = osx_write_limit // arr.itemsize
        while idx < arr.nbytes:
            write(arr[idx:idx + chunksize], outfile)
            idx += chunksize
    else:
        write(arr, outfile)


def _write_string(f, s):
    """
    Write a string to a file, encoding to ASCII if the file is open in binary
    mode, or decoding if the file is open in text mode.
    """

    # Assume if the file object doesn't have a specific mode, that the mode is
    # binary
    binmode = fileobj_is_binary(f)

    if binmode and isinstance(s, text_type):
        s = encode_ascii(s)
    elif not binmode and not isinstance(f, text_type):
        s = decode_ascii(s)
    elif isinstance(f, StringIO) and isinstance(s, np.ndarray):
        # Workaround for StringIO/ndarray incompatibility
        s = s.data
    f.write(s)


def _convert_array(array, dtype):
    """
    Converts an array to a new dtype--if the itemsize of the new dtype is
    the same as the old dtype and both types are not numeric, a view is
    returned.  Otherwise a new array must be created.
    """

    if array.dtype == dtype:
        return array
    elif (array.dtype.itemsize == dtype.itemsize and not
            (np.issubdtype(array.dtype, np.number) and
             np.issubdtype(dtype, np.number))):
        # Includes a special case when both dtypes are at least numeric to
        # account for ticket #218: https://aeon.stsci.edu/ssb/trac/pyfits/ticket/218
        return array.view(dtype)
    else:
        return array.astype(dtype)


def _unsigned_zero(dtype):
    """
    Given a numpy dtype, finds its "zero" point, which is exactly in the
    middle of its range.
    """

    assert dtype.kind == 'u'
    return 1 << (dtype.itemsize * 8 - 1)


def _is_pseudo_unsigned(dtype):
    return dtype.kind == 'u' and dtype.itemsize >= 2


def _is_int(val):
    return isinstance(val, integer_types + (np.integer,))


def _str_to_num(val):
    """Converts a given string to either an int or a float if necessary."""

    try:
        num = int(val)
    except ValueError:
        # If this fails then an exception should be raised anyways
        num = float(val)
    return num


def _pad_length(stringlen):
    """Bytes needed to pad the input stringlen to the next FITS block."""

    return (BLOCK_SIZE - (stringlen % BLOCK_SIZE)) % BLOCK_SIZE


def _normalize_slice(input, naxis):
    """
    Set the slice's start/stop in the regular range.
    """

    def _normalize(indx, npts):
        if indx < -npts:
            indx = 0
        elif indx < 0:
            indx += npts
        elif indx > npts:
            indx = npts
        return indx

    _start = input.start
    if _start is None:
        _start = 0
    elif _is_int(_start):
        _start = _normalize(_start, naxis)
    else:
        raise IndexError('Illegal slice %s; start must be integer.' % input)

    _stop = input.stop
    if _stop is None:
        _stop = naxis
    elif _is_int(_stop):
        _stop = _normalize(_stop, naxis)
    else:
        raise IndexError('Illegal slice %s; stop must be integer.' % input)

    if _stop < _start:
        raise IndexError('Illegal slice %s; stop < start.' % input)

    _step = input.step
    if _step is None:
        _step = 1
    elif _is_int(_step):
        if _step <= 0:
            raise IndexError('Illegal slice %s; step must be positive.'
                             % input)
    else:
        raise IndexError('Illegal slice %s; step must be integer.' % input)

    return slice(_start, _stop, _step)


def _words_group(input, strlen):
    """
    Split a long string into parts where each part is no longer
    than `strlen` and no word is cut into two pieces.  But if
    there is one single word which is longer than `strlen`, then
    it will be split in the middle of the word.
    """

    words = []
    nblanks = input.count(' ')
    nmax = max(nblanks, len(input) // strlen + 1)
    arr = np.fromstring((input + ' '), dtype=(binary_type, 1))

    # locations of the blanks
    blank_loc = np.nonzero(arr == ' '.encode('latin1'))[0]
    offset = 0
    xoffset = 0
    for idx in range(nmax):
        try:
            loc = np.nonzero(blank_loc >= strlen + offset)[0][0]
            offset = blank_loc[loc - 1] + 1
            if loc == 0:
                offset = -1
        except:
            offset = len(input)

        # check for one word longer than strlen, break in the middle
        if offset <= xoffset:
            offset = xoffset + strlen

        # collect the pieces in a list
        words.append(input[xoffset:offset])
        if len(input) == offset:
            break
        xoffset = offset

    return words


def _tmp_name(input):
    """
    Create a temporary file name which should not already exist.  Use the
    directory of the input file as the base name of the mkstemp() output.
    """

    if input is not None:
        input = os.path.dirname(input)
    f, fn = tempfile.mkstemp(dir=input)
    os.close(f)
    return fn


if sys.version_info[:2] < (2, 6):
    # In Python 2.5 mmap.mmap is a function that returns an object of type
    # 'mmap.mmap', but the mmap.mmap type is otherwise not accessible through
    # the module
    def _is_mmap(obj):
        return (type(obj).__module__ == 'mmap' and
                type(obj).__name__ == 'mmap')
else:
    def _is_mmap(obj):
        return isinstance(obj, mmap.mmap)


def _get_array_mmap(array):
    """
    If the array has an mmap.mmap at base of its base chain, return the mmap
    object; otherwise return None.
    """

    if _is_mmap(array):
        return array

    base = array
    while hasattr(base, 'base') and base.base is not None:
        if _is_mmap(base.base):
            return base.base
        base = base.base


if sys.version_info[:2] < (2, 6):
    import __builtin__
    # Replace the builtin property to add support for the getter/setter/deleter
    # mechanism as introduced in Python 2.6 (this can go away if we ever drop
    # 2.5 support)

    class property(property):
        def __init__(self, fget, *args, **kwargs):
            self.__doc__ = fget.__doc__
            super(property, self).__init__(fget, *args, **kwargs)

        def getter(self, fget):
            return self.__ter(fget, 0)

        def setter(self, fset):
            return self.__ter(fset, 1)

        def deleter(self, fdel):
            return self.__ter(fdel, 2)

        def __ter(self, f, arg):
            args = [self.fget, self.fset, self.fdel, self.__doc__]
            args[arg] = f
            cls_ns = sys._getframe(1).f_locals
            for k, v in iteritems(cls_ns):
                if v is self:
                    property_name = k
                    break

            cls_ns[property_name] = property(*args)

            return cls_ns[property_name]
    __builtin__.property = property


    # Provide an implementation of izip_longest
    class ZipExhausted(Exception):
        pass

    def izip_longest(*args, **kwds):
        # izip_longest('ABCD', 'xy', fillvalue='-') --> Ax By C- D-
        fillvalue = kwds.get('fillvalue')
        counter = [len(args) - 1]
        def sentinel():
            if not counter[0]:
                raise ZipExhausted
            counter[0] -= 1
            yield fillvalue
        fillers = itertools.repeat(fillvalue)
        iterators = [itertools.chain(it, sentinel(), fillers) for it in args]
        try:
            while iterators:
                yield tuple(map(next, iterators))
        except ZipExhausted:
            pass

    from .extern import six
    six.moves.zip_longest = izip_longest
