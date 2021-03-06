# -*- coding: utf-8 -*-
"""This module contains classes that are based on native types (lists,
dicts, string, datetime), but adds support for general attributes. The
attributes are set when the object is created (as keyword arguments to
the construct). Once an object has been instansiated, new attributes
cannot be added, but existing attributes can be changed.

The main purpose of using these classes is that they can be readily
converted to XHTML by the
:py:meth:`ferenda.DocumentRepository.render_xhtml` method.

The module also contains the convenience functions
:py:func:`serialize` and :py:func:`deserialize`, to convert object
hierarchies to and from strings.

"""
from __future__ import (absolute_import, division,
                        print_function, unicode_literals)
from builtins import *
from future import standard_library
standard_library.install_aliases()
import builtins
from future.utils import native

from operator import itemgetter
import ast
import datetime
import json
import logging
import re
import inspect
import unicodedata
import xml.etree.cElementTree as ET
import sys
from collections import OrderedDict


from layeredconfig import LayeredConfig
from lxml.builder import ElementMaker
from rdflib import Graph, Namespace, Literal, URIRef
import pyparsing

from ferenda import util

DCTERMS = Namespace(util.ns['dcterms'])
RDF = Namespace(util.ns['rdf'])
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
log = logging.getLogger(__name__)
E = ElementMaker(namespace="http://www.w3.org/1999/xhtml",
                 nsmap={None: "http://www.w3.org/1999/xhtml"})


def serialize(root, format="xml"):
    """Given any :py:class:`~ferenda.elements.AbstractElement` *root*
    object, returns a XML serialization of *root*, recursively.

    """
    if format == "xml":
        t = __serialize_xml(root)
        _indentTree(t)
        return ET.tostring(t, 'utf-8').decode('utf-8') + "\n"
    elif format == "json":
        t = __serialize_json(root)
        r = json.dumps(t, indent=4, ensure_ascii=False, sort_keys=True)
        return r
    else:
        raise ValueError("Invalid serialization format: %s" % format)


def deserialize(xmlstr, format="xml", caller_globals=None):
    """Given a XML string created by :py:func:`serialize`, returns a
    object tree of :py:class:`AbstractElement` derived objects that is
    identical to the initial object structure.

    .. note::

       This function is highly insecure -- use only with trusted data

    """
    # print "Caller globals()"
    # print repr(caller_globals.keys())
    # print "Callee globals()"
    # print repr(globals().keys())
    # print repr(locals().keys())
    if format == "xml":
        if (isinstance(xmlstr, str)):
            xmlstr = xmlstr.encode('utf-8')
        t = ET.fromstring(xmlstr)
        return __deserialize_xml(t, caller_globals)
    elif format == "json":
        root = json.loads(xmlstr)
        t = __deserialize_json(root)
        return t


class AbstractElement(object):

    """Base class for all elements. You should only inherit from this if
    you define new types directly based on python types.

    """
    def __new__(cls, *args, **kwargs):
        obj = super(AbstractElement, cls).__new__(cls)
        object.__setattr__(obj, '__initialized', False)
        return obj

    def __init__(self, *args, **kwargs):
        for (key, val) in list(kwargs.items()):
            object.__setattr__(self, key, val)

        # Declare this instance ready for usage. Note that derived
        # objects must do their own initialization first, before
        # calling the superclass constructor (i.e. this function),
        # since this effectively "seals" the instance.
        #
        # (we need to call object.__setattr__ directly to bypass our
        # own __setattr__ implementation)
        object.__setattr__(self, '__initialized', True)

    def __setattr__(self, name, value):
        if object.__getattribute__(self, '__initialized'):
            # initialization phase is over -- no new attributes should
            # be created. Check to see if the attribute exists -- if it
            # doesn't, we raise an AttributeError (with a sensible
            # error message)
            try:
                object.__getattribute__(self, name)
                object.__setattr__(self, name, value)
            except AttributeError:
                raise AttributeError(
                    "Can't set attribute '%s' on object '%s' after initialization" %
                    (name, self.__class__.__name__))
        else:
            # Still in initialization phase -- ok to create new
            # attributes
            object.__setattr__(self, name, value)

    def _get_tagname(self):
        return self.__class__.__name__.lower()

    tagname = property(_get_tagname)
    """The tag used for this element in the resulting XHTML (the default
    implementation simply uses the class name, lowercased)."""

    classname = None
    """If set, this property gets converted to a ``@class`` attribute in
    the resulting XHTML."""

    partrelation = DCTERMS.isPartOf
    """The default relationship between this element and any other element
that includes this element."""

    def as_xhtml(self, uri=None, parent_uri=None):
        """Converts this object to a ``lxml.etree`` object (with children)

        :param uri: If provided, gets converted to an ``@about`` attribute
                    in the resulting XHTML.
        :type uri: str
"""
        attrs = {}
        for stdattr in ('class', 'id', 'dir', 'lang', 'src',
                        'href', 'name', 'alt', 'role', 'action', 'method'):
            if hasattr(self, stdattr) and getattr(self, stdattr):
                attrs[stdattr] = getattr(self, stdattr)
        return E(self.tagname, attrs)


class UnicodeElement(AbstractElement, str):

    """Based on :py:class:`str`, but can also have other
properties (such as ordinal label, date of enactment, etc)."""

    # immutable objects (like strings, unicode, etc) must provide a
    # __new__ method
    def __new__(cls, arg='', *args, **kwargs):
        if not isinstance(arg, str):
            raise TypeError("%r is not a (unicode) str" % arg)
        # obj = str.__new__(cls, arg)
        obj = str.__new__(cls, arg)
        object.__setattr__(obj, '__initialized', False)
        return obj

    def as_xhtml(self, uri=None, parent_uri=None):
        res = super(UnicodeElement, self).as_xhtml(uri, parent_uri)
        if self.classname is not None:
            res.set('class', self.classname)
        if str(self).strip():
            s = self.clean_string()
            if len(res): # if there are already nodes, eg <span>
                          # nodes inserted by a mixin, insert text
                          # after those nodes
                res[-1].tail = s
            else:
                res.text = s
            return res
        else:
            return None

    def clean_string(self):
        # remove any control characters (except TAB, CR or LF as these
        # are allowed in XML) that might have been present in the
        # source
        newstring = ""
        for char in str(self):
            if char in ('\r', '\n', '\t') or unicodedata.category(char) != "Cc":
                newstring += char
        return newstring

    def __str__(self):
        if sys.version_info[0] < 3:
            return self
        else:
            return super(UnicodeElement, self).__str__()


class CompoundElement(AbstractElement, list):

    """Based on :py:class:`list` and contains other :py:class:`AbstractElement` objects, but can also have properties of it's own."""
    def __new__(cls, arg=[], *args, **kwargs):
        # ideally, we'd like to do just "obj = list.__new__(cls,arg)"
        # but that doesn't seem to work
        obj = list.__new__(cls)
        obj.extend(arg)
        object.__setattr__(obj, '__initialized', False)
        return obj

    def __str__(self):
        return self.as_plaintext()

    def __nonzero__(self):
        # on py2, we've had problems with empty elements (x =
        # CompoundElement()) being truthy. Avoid this by defining a
        # proper bool criteria using the magic __nonzero__
        # method. These problems don't show up on py3, so we don't
        # bother to define __bool__
        return len(self) != 0

    def _cleanstring(self, s):
        # valid chars according to the XML spec
        def _valid(i):
            return (
                0x20 <= i <= 0xD7FF
                or i in (0x9, 0xA, 0xD)
                or 0xE000 <= i <= 0xFFFD
                or 0x10000 <= i <= 0x10FFFF
            )
        return ''.join(c for c in s if _valid(ord(c)))

    def as_plaintext(self):
        """Returns the plain text of this element, including child elements."""
        res = []
        for subpart in self:
            if isinstance(subpart, str):
                res.append(util.normalize_space(subpart))
            elif (isinstance(subpart, AbstractElement) or
                  hasattr(subpart, 'as_plaintext')):
                res.append(subpart.as_plaintext())
        # the rule for concatenating children into a plaintext string is:
        # filter out all empty children, then place single space between
        # the others.
        return " ".join(filter(None, res))

    # body uri="http://ex.org/"
    # section ordinal="1" uri=body.uri+"#S"+ordinal, ispartof=parent.uri
    # subsection ordinal="1.1" uri=body.uri+"#S"+ordinal, ispartof=parent.uri
    # subsubsection ordinal="1.1.1" uri=body.uri+"#S"+ordinal, ispartof=parent.uri
    def as_xhtml(self, uri=None, parent_uri=None):
        children = []
        # start by handling all children recursively

        for subpart in self:
            if (isinstance(subpart, AbstractElement) or
                    hasattr(subpart, 'as_xhtml')):

                # this is the difficult part - p must be eg
                # "http://ex.org/#S1" but self doesn't have uri
                # property. the @about attribute is set later by
                # SectionalElement.as_xhtml (which overrides and calls
                # this method). can self.uri be a property method,
                # what will it need? (uri and self.ordinal)

                if hasattr(self, 'uri') and self.uri:
                    p = self.uri
                elif hasattr(self, 'compute_uri'):
                    p = self.compute_uri(baseuri=uri)
                elif parent_uri:
                    p = parent_uri
                else:
                    p = uri
                node = subpart.as_xhtml(uri, p)
                if node is not None:
                    children.append(node)
            elif isinstance(subpart, str):
                children.append(self._cleanstring(subpart))
            else:
                log.warning("as_xhtml: Can't render %s instance" %
                            subpart.__class__.__name__)
                # this is a reasonable attempt
                children.append(str(subpart))

        # Then massage a list of attributes for the main node
        attrs = OrderedDict()

        if self.classname is not None:
            attrs['class'] = self.classname

        # copy (a subset of) standard xhtml attributes (including some
        # RDFa ones). FIXME: There should be an overridable class
        # variable with this list. action and method is really only
        # applicable to html.Form, for is only for html.Label, and
        # type+name+placeholder for html.Input, and rows+cols for html.Textarea
        for stdattr in ('class', 'id', 'dir', 'lang', 'src',
                        'href', 'name', 'alt', 'role', 'typeof',
                        'datatype', 'property', 'rel', 'about', 'action', 'method', 'for', 'type', 'name', 'value', 'rows', 'cols', 'checked', 'placeholder'):
            if hasattr(self, stdattr) and getattr(self, stdattr):
                attrs[stdattr] = getattr(self, stdattr)

        # create extra attributes depending on circumstances
        if hasattr(self, 'uri') and self.uri:

            attrs['about'] = self.uri

            if hasattr(self, 'meta') and self.meta:
                assert isinstance(
                    self.meta, Graph), "self.meta is %r, not rdflib.Graph" % type(self.meta)
                # we use sorted() to get the triples in a predictable
                # order (by predicate, then subject, then object)
                for (s, p, o) in sorted(self.meta, key=itemgetter(1, 0, 2)):
                    if s != URIRef(self.uri):
                        continue
                    if p == RDF.type:
                        attrs['typeof'] = self.meta.qname(o)
                        # attrs['rev'] = self.meta.qname(DCTERMS.isPartOf)
                    elif p == DCTERMS.title:
                        attrs['property'] = self.meta.qname(p)
                        attrs['content'] = o.toPython()
                    else:
                        # FIXME: Is it sane to reverse the order of
                        # triples in this way? Maybe we should do a
                        # children.append instead
                        children.insert(0, self._span(s, p, o, self.meta))

            if self.partrelation and parent_uri:
                childattr = OrderedDict([('rel', self._qname(self.partrelation)),
                                         ('href', parent_uri)])
                children.insert(0,
                                E('span', childattr))
            # parent_uri = self.uri

        # for each childen that is a string, make sure it doesn't
        # contain any XML illegal characters
        res = E(self.tagname, attrs, *children)
        return res
    
    

    def _span(self, subj, pred, obj, graph=None):
        """Returns any triple as a span element with rdfa attributes. Object
           can be a uriref or literal, subject must be a
           uriref. Bnodes not supported. Recursively creates sub-span
           elements with for each uriref object that is the subject in
           another triple in graph.
        """
        children = []
        if isinstance(obj, Literal):
            o_python = obj.toPython()
            if isinstance(o_python, datetime.date):
                o_python = o_python.isoformat()
            attrs = {
                # 'about': self.uri,
                'property': self.meta.qname(pred),
                'content': o_python
            }

            if obj.datatype:
                attrs['datatype'] = self.meta.qname(obj.datatype)
            else:
                # only datatype-less literals can have language
                attrs[XML_LANG] = obj.language if obj.language else ''
        elif isinstance(obj, URIRef) and hasattr(self, 'meta'):
            attrs = {
                # 'about':self.uri,
                # 'about': str(obj),
                'rel': self.meta.qname(pred),
                'href': str(obj)
            }
            if graph:
                for sub_pred, sub_obj in sorted(graph.predicate_objects(subject=obj)):
                    children.append(self._span(obj, sub_pred, sub_obj, graph))
        else:
            attrs = {}
        # Theoretical, obj could be a BNode, but that should never happen. If
        # it does, just silently ignore it.
        # else:
        #     raise ValueError("Type %s not supported as object" % type(obj))

        return E('span', attrs, *children)

    def _qname(self, predicate):
        # we need to get hold of the root namespace mapping. But that
        # aint available. Or we could get hold of a graph from
        # docrepo.make_graph, but docrepo aint available. Gah!
        # FIXME:
        if predicate == Namespace("http://schema.org/").isPartOf:
            return "schema:isPartOf"
        else:
            return "dcterms:isPartOf"
        pass

# Abstract classes intendet to use with multiple inheritance, which
# adds common properties


class TemporalElement(AbstractElement):

    """A TemporalElement has a number of temporal properties
    (``entryintoforce``, ``expires``) which states the temporal frame
    of the object.

    This class is intended to be inherited using multiple inheritance
    together with some main element type.

    >>> class TemporalHeading(UnicodeElement, TemporalElement):
    ...     pass
    >>> c = TemporalHeading("This heading has a start and a end date",
    ...                      entryintoforce=datetime.date(2013,1,1),
    ...                      expires=datetime.date(2013,12,31))
    >>> c.in_effect(datetime.date(2013,7,1))
    True
    >>> c.in_effect(datetime.date(2014,7,1))
    False

    """
    # can't initialize these 2 fields, since they get serialized, and
    # this clashes with test case files.

#     def __init__(self, *args, **kwargs):
#         self.entryintoforce = None
#         self.expires = None
#         super(TemporalElement, self).__init__(*args, **kwargs)

    def in_effect(self, date=None):
        """Returns True if the object is in effect at *date*."""
        return (date >= self.entryintoforce) and (date <= self.expires)


class PredicateElement(AbstractElement):

    """Inheriting from this gives the subclass a ``predicate`` attribute,
    which describes the RDF predicate to which the class is the RDF
    subject (eg. if you want to model the title of a document, you
    would inherit from UnicodeElement and this, and then set
    ```predicate`` to ``rdflib.URIRef('http://purl.org/dc/elements/1.1/title')``.
    """

    def __init__(self, *args, **kwargs):
        if 'predicate' in kwargs:
            self.predicate = kwargs['predicate']
            # switch the full uriref
            # (http://rinfo.lagrummet...#paragraf) to one using a
            # namespace prefix, if we know of one:
            shorten = False
            for (prefix, ns) in list(util.ns.items()):
                if kwargs['predicate'].startswith(ns):
                    predicateuri = kwargs['predicate']
                    kwargs['predicate'] = kwargs[
                        'predicate'].replace(ns, prefix + ":")
                    # print "Shorten predicate %s to: %s" % (predicateuri,
                    # kwargs['predicate'])
                    shorten = True
            # if not shorten:
            #   print "Couldn't shorten predicate: %s" % self.predicate
        else:
            # From the RDF Schema spec: 'This is the class of
            # everything. All other classes are subclasses of this
            # class.'
            from rdflib import RDFS
            self.predicate = RDFS.Resource
        super(PredicateElement, self).__init__(*args, **kwargs)


class OrdinalElement(AbstractElement):

    """A OrdinalElement has a explicit ordinal number. The ordinal does
    not need to be strictly numerical, but can be eg. '6 a' (which is
    larger than 6, but smaller than 7). Classes inherited from this
    can be compared with each other.

    This class is intended to be inherited using multiple inheritance
    together with some main element type.

    >>> class OrdinalHeading(UnicodeElement, OrdinalElement):
    ...     pass
    >>> a = OrdinalHeading("First", ordinal="1")
    >>> b = OrdinalHeading("Second", ordinal="2")
    >>> c = OrdinalHeading("In-between", ordinal="1 a")
    >>> a < b
    True
    >>> a < c
    True
    >>> b < c
    False

    """



    def __init__(self, *args, **kwargs):
        self.ordinal = None
        super(OrdinalElement, self).__init__(*args, **kwargs)

    def __lt__(self, other):
        return util.numcmp(self.ordinal, other.ordinal) < 0

    def __le__(self, other):
        return util.numcmp(self.ordinal, other.ordinal) <= 0

    def __eq__(self, other):
        return (isinstance(other, OrdinalElement) and
                self.ordinal == other.ordinal)

    def __ne__(self, other):
        return not(isinstance(other, OrdinalElement) and
                   self.ordinal == other.ordinal)

    def __gt__(self, other):
        return util.numcmp(self.ordinal, other.ordinal) > 0

    def __ge__(self, other):
        return util.numcmp(self.ordinal, other.ordinal) >= 0


class Link(UnicodeElement):

    """A unicode string with also has a ``.uri`` attribute"""
    tagname = 'a'

    # FIXME: can __repr__ on PY2 return unicode data?
    def __repr__(self):
        # convoluted way around a UnicodeEncode error on py2 when self contains
        # non-ascii characters
        # if six.PY2:
        #     rep = repr(str(self))[2:-1]
        # else:
        rep = self
        return 'Link(\'%s\', uri=%s)' % (rep, self.uri)

    def as_xhtml(self, uri, parent_uri=None):
        element = super(Link, self).as_xhtml(uri, parent_uri)
        if element is None:  # might happen if UnicodeElement determines that this has no text content
            return None
        if hasattr(self, 'uri'):
            element.set('href', self.uri)
        return element


class LinkSubject(PredicateElement, Link):

    """A unicode string that has both ``predicate`` and ``uri``
    attributes, i.e. a typed link. Note that predicate should be a
    string that represents a Qname, eg 'dcterms:references', not a proper
    rdflib object.

    """

    def as_xhtml(self, uri, parent_uri=None):
        element = super(LinkSubject, self).as_xhtml(uri, parent_uri)
        if hasattr(self, 'predicate'):
            element.set('rel', self.predicate)
        return element


class LinkMarkup(CompoundElement):
    """A link that can contain mixed content, ie bold and italic tags, etc"""
    tagname = "a"

    def as_xhtml(self, uri, parent_uri=None):
        element = super(LinkMarkup, self).as_xhtml(uri, parent_uri)
        if hasattr(self, 'uri'):
            element.set('href', self.uri)
        return element
    

class Body(CompoundElement):

    def as_xhtml(self, uri, parent_uri=None):
        # A body should always be called with a uri. This becomes the
        # parent_uri for all subsections
        parent_uri = uri
        element = super(Body, self).as_xhtml(uri, parent_uri)
        element.set('about', uri)
        return element


class Title(CompoundElement):
    pass


class Page(CompoundElement, OrdinalElement):
    tagname = "div"
    classname = "page"


class Nav(CompoundElement):
    pass


class SectionalElement(CompoundElement):
    tagname = "div"

    def _get_classname(self):
        return self.__class__.__name__.lower()
    classname = property(_get_classname)

    # def __init__(self, *args, **kwargs):
    #     self.baseuri = None
    #     super(TemporalElement, self).__init__(*args, **kwargs)

    def compute_uri(self, baseuri):
        return baseuri + "#S%s" % self.ordinal

    def as_xhtml(self, baseuri, parent_uri=None):
        if hasattr(self, 'uri'):
            newuri = self.uri
        else:
            newuri = self.compute_uri(baseuri)
        # Addressable subelements (ie. elements which has an uri) are
        # expected to be able to construct that URI from the base uri
        # of the entire document (plus it's own internal state).
        element = super(SectionalElement, self).as_xhtml(baseuri, parent_uri)
        if not hasattr(self, 'uri') or not hasattr(self, 'meta'):
            element.set('property', 'dcterms:title')
            element.set('content', self.title)
            element.set('typeof', 'bibo:DocumentPart')
            if newuri:  # we might have defined the self.uri
                        # attribute, but set it to None
                element.set('about', newuri)
            # NOTE: we don't set xml:lang for either the main @content
            # or the @content in the below <span> -- the data does not
            # originate from RDF and so isn't typed like that.
            if hasattr(self, 'ordinal') and newuri:
                attrs = {'about': newuri,
                         'property': 'bibo:chapter',
                         'content': self.ordinal}
                element.insert(0, E('span', attrs))
            if hasattr(self, 'identifier') and newuri:
                attrs = {'about': newuri,
                         'property': 'dcterms:identifier',
                         'content': self.identifier}
                element.insert(0, E('span', attrs))
            if self.partrelation and newuri:
                attrs = {'rel': self._qname(self.partrelation),
                         'href': parent_uri}
                element.insert(0, E('span', attrs))

            # make sure that naked PCDATA comes after the elements we've
            # inserted
            if element.text:
                element[-1].tail = element.text
                element.text = None

        return element


class Section(SectionalElement):
    pass


class Subsection(SectionalElement):
    pass


class Subsubsection(SectionalElement):
    pass


class Paragraph(CompoundElement):
    tagname = 'p'


# A preformatted section might contain links, <b> tags etch, which is why it's not derived from UnicodeElement
class Preformatted(Paragraph):
    tagname = 'pre'
    def as_plaintext(self):
        # CompoundElement.as_plaintext does all kinds of string
        # normalization, which we don't want for a
        # whitespace-sensitive element
        return "".join(self)


class Heading(CompoundElement, OrdinalElement):
    tagname = 'h1'  # fixme: take level into account


class Footnote(CompoundElement):
    pass


class OrderedList(CompoundElement):
    tagname = 'ol'


class UnorderedList(CompoundElement):
    tagname = 'ul'
#
# class DefinitionList(CompoundElement):
#     tagname = 'dl'
#
# class Term(CompoundElement): pass
# class Definition(CompoundElement): pass


class ListItem(CompoundElement, OrdinalElement):
    tagname = 'li'


def __serialize_json(node):
    # some native datatypes should be returned as-is, ie not wrapped
    # in a dict. Note that types derived from these gets handled
    # differently. 
    if type(node) in (str, int, bool) or type(node).__name__ == "unicode":
        return node
    # lists and dicts gets returned as-is, but the values in those
    # containers are transformed if need be
    elif type(node) == list:
        return [__serialize_json(x) for x in node]
    elif type(node) == dict or type(node).__name__ == "dict":
        return native(dict([(k, __serialize_json(v)) for k, v in node.items()]))
    else:
        if node.__class__.__module__ in ('builtins', '__builtin__'):
            # py2 workaround -- we want a str to be known as 'str' always, but py2
            # thinks they're called 'unicode'...
            if type(node) == str:
                typename = "str"
            elif type(node) == bytes:
                typename = "bytes"
            else:
                typename = node.__class__.__name__
        else:
            typename = node.__class__.__module__ + "." + node.__class__.__name__

        e = {'@class': typename}
        if hasattr(node, '__dict__'):
            for key in [x for x in list(node.__dict__.keys()) if not x.startswith('_')]:
                val = node.__dict__[key]
                if val is None:
                    continue
                elif isinstance(val, LayeredConfig):  # FIXME: this is an
                                                      # ugly hack to avoid
                                                      # problems with
                                                      # pdfreader.TextBox.font
                    continue
                elif isinstance(val, logging.Logger):
                    continue
                e[key] = __serialize_json(val)
        if isinstance(node, list) or isinstance(node, tuple):
            # convert derived list to plain list
            e['@content'] = __serialize_json(list(node))
        elif isinstance(node, dict):
            e['@content'] = __serialize_json(dict(node))
        elif isinstance(node, bytes):
            # assume that all bytestrings are ascii only. When this
            # assumption does not hold, convert them into something
            # like base64.
            e['@content'] = node.decode()
        elif isinstance(node, str):
            e['@content'] = str(node)
        elif isinstance(node, pyparsing.ParseResults):
            e['name'] = node.getName()
            e['@content'] = repr(node)
        elif isinstance(node, Graph):
            i = node.identifier
            e['@content'] = node.serialize().decode('utf-8')  # default compact RDF/XML
            e['identifier'] = {'@class': i.__class__.__module__ + "." + i.__class__.__name__,
                               '@content': str(i)}
        else:
            # if hasattr(node, '__json__'): ...
            e['@content'] = repr(node)
        return e

_state = {'fontspec': None}


def __deserialize_json(node):
    from ferenda.pdfreader import PDFReader, Textbox
    from ferenda import Document
    nodetype = None
    if hasattr(node, 'get'):
        nodetype = node.get("@class")
    # 1. get the appropriate class object
    if nodetype:
        try:
            modulename, classname = nodetype.rsplit(".", 1)
            __import__(modulename)
            m = sys.modules[modulename]
            for name, cls in inspect.getmembers(m, inspect.isclass):
                if name == classname:
                    break  # setting cls to what we want
        # "need more than 1 value to unpack": we have a builtin type like str, int, bool
        except ValueError:
            cls = {'str': str,
                   'int': int,
                   'bool': bool,
                   'bytes': bytes}[nodetype]
        content = node['@content']
    else:
        # native objects (int, str, bool, list, dict (which is
        # distinguishable from complex/derived objects by the absence
        # of '@type'))
        cls = node.__class__
        content = node

    # 2. get any possible attributes
    attribs = {}
    if hasattr(node, 'items'):
        attribs = dict([(k, __deserialize_json(v))
                        for k, v in node.items() if not k.startswith("@")])

    # hack for deserializing pdfreader objects -- store the current
    # fontspecs dict as soon as we see it, we'll be needing it every
    # time we create a pdfreader.Textbox

    if issubclass(cls, PDFReader):
        _state['fontspec'] = attribs['fontspec']

    # 3. initialize the class

    if issubclass(cls, list):
        if issubclass(cls, Textbox):
            attribs['fontspec'] = _state['fontspec']
        o = cls([__deserialize_json(x) for x in content], **attribs)
    elif issubclass(cls, dict):
        o = cls([(k, __deserialize_json(v)) for k, v in content.items()], **attribs)
    elif issubclass(cls, bytes):
        # assume only ascii
        o = cls(content.encode(), **attribs)
    elif issubclass(cls, datetime.datetime):
        m = re.match(r'[\w\.]+\((\d+), (\d+), (\d+), (\d+), (\d+)(|, (\d+)\))', content)
        seconds = m.group(6) or '0'
        o = cls(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)), int(seconds), **attribs)
    elif issubclass(cls, datetime.date):
        m = re.match(r'[\w\.]+\((\d+), (\d+), (\d+)\)', content)
        o = cls(int(m.group(1)), int(m.group(2)), int(m.group(3)), **attribs)
    elif issubclass(cls, pyparsing.ParseResults):
        # attempt to reconstruct a pyparsing.ParseResult object from
        # its repr() serialization. It's not 100 %, but good enough to
        # be usable.
        tocdict = ast.literal_eval(content)
        o = cls([])
        parent = None
        accumNames = {}
        name = node['name']
        o.__setstate__((tocdict[0], (tocdict[1], parent, accumNames, name)))
    elif issubclass(cls, Graph):
        # first create the graph identifier (BNode or URIRef object)
        i = __deserialize_json(node['identifier'])
        o = cls(identifier=i).parse(data=content)
    elif issubclass(cls, Document):
        o = cls(**attribs)  # no actual content, only attributes/properties
    else:
        o = cls(content, **attribs)
    return o


def __serialize_xml(node, serialize_hidden_attrs=False):
    # print "serializing: %r" % node

    # Special handling of pyparsing.ParseResults -- deserializing of
    # these won't work (easily)
    if isinstance(node, pyparsing.ParseResults):
        xml = util.parseresults_as_xml(node)
        return ET.XML(xml)

    # We use type() instead of isinstance() because we want to
    # serialize str derived types using their correct class
    # names. This is now more involved since under py2, str is now
    # really future.types.newstr.newstr.
    if type(node) == str or (hasattr(builtins, 'unicode') and  # means py2 + future
                             type(node) == builtins.unicode):
        nodename = "str"
    elif type(node) == bytes:
        nodename = "bytes"
    else:
        nodename = node.__class__.__name__
    e = ET.Element(nodename)
    if hasattr(node, '__dict__'):
        for key in [
                x for x in list(node.__dict__.keys()) if serialize_hidden_attrs or not x.startswith('_')]:
            val = node.__dict__[key]
            if val is None:
                continue
            if (isinstance(val, (str, bytes))):
                e.set(key, native(val))
            elif isinstance(val, LayeredConfig):  # FIXME: this is an
                                                  # ugly hack to avoid
                                                  # problems with
                                                  # pdfreader.TextBox.font
                continue
            else:
                e.set(key, repr(val))

    if isinstance(node, str):
        if node:
            e.text = str(node)
    elif isinstance(node, bytes):
        if node:
            e.text = node.decode()
    elif isinstance(node, int):
        e.text = str(node)
    elif isinstance(node, list):
        for x in node:
            e.append(__serialize_xml(x))
    else:
        e.text = repr(node)
        # raise TypeError("Can't serialize %r (%r)" % (type(node), node))
    return e


def __deserialize_xml(elem, caller_globals):
    # print "element %r, attrs %r" % (elem.tag, elem.attrib)
    # kwargs = elem.attrib

    # specialcasing first -- class objects for these native objects
    # can't be created by the"caller_globals[elem.tag]" call below
    if elem.tag == 'int':
        cls = int
    elif elem.tag == 'str':
        cls = str
    elif elem.tag == 'bytes':
        cls = bytes
    elif elem.tag == 'dict':
        cls = dict
    else:
        # print "creating cls for %s" % elem.tag
        cls = caller_globals[elem.tag]

    if str == cls or str in cls.__bases__:
        c = cls(elem.text, **elem.attrib)

    elif bytes == cls or bytes in cls.__bases__:
        c = cls(elem.text.encode(), **elem.attrib)

    elif int == cls or int in cls.__bases__:
        c = cls(int(elem.text), **elem.attrib)

    elif dict == cls or dict in cls.__bases__:
        c = cls(ast.literal_eval(elem.text), **elem.attrib)

    elif datetime.datetime == cls or datetime.datetime in cls.__bases__:
        m = re.match(r'[\w\.]+\((\d+), (\d+), (\d+), (\d+), (\d+)(|, (\d+)\))', elem.text)
        seconds = m.group(6) or '0'
        c = cls(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)), int(seconds), **elem.attrib)

    elif datetime.date == cls or datetime.date in cls.__bases__:
        m = re.match(r'[\w\.]+\((\d+), (\d+), (\d+)\)', elem.text)
        c = cls(int(m.group(1)), int(m.group(2)), int(m.group(3)), **elem.attrib)

    else:
        c = cls(**elem.attrib)
        for subelem in elem:
            # print "Recursing"
            c.append(__deserialize_xml(subelem, caller_globals))

    return c

# in-place prettyprint formatter
# http://infix.se/2007/02/06/gentlemen-_indentElement-your-xml


def _indentTree(elem, level=0):
    i = "\n" + level * "  "
    if len(elem) > 0:
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for e in elem:
            _indentElement(e, level + 1)
            if not e.tail or not e.tail.strip():
                e.tail = i + "  "
        if not e.tail or not e.tail.strip():
            e.tail = i
# This should never happen
#    else:
#        if level and (not elem.tail or not elem.tail.strip()):
#            elem.tail = i


def _indentElement(elem, level=0):
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for elem in elem:
            _indentElement(elem, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i
