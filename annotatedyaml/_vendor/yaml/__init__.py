
from .error import *

from .tokens import *
from .events import *
from .nodes import *

from .loader import *
from .dumper import *

__version__ = '6.0.3'
try:
    from .cyaml import *
    __with_libyaml__ = True
except ImportError:
    __with_libyaml__ = False

import io
from typing import Any, BinaryIO, Iterator, TextIO, Type

_MISSING_LOADER = object()
LoaderClsArg = Type[Any] | object
_DEFAULT_SAFE_LOADER: Type[Any] = SafeLoader

#------------------------------------------------------------------------------
# XXX "Warnings control" is now deprecated. Leaving in the API function to not
# break code that uses it.
#------------------------------------------------------------------------------
def _extract_legacy_loader(func_name: str, kwargs: dict[str, Any]) -> Any | None:
    legacy_loader = kwargs.pop("Loader", None)
    if kwargs:
        unexpected = ", ".join(sorted(kwargs))
        raise TypeError(
            f"{func_name}() got unexpected keyword argument(s): {unexpected}"
        )
    return legacy_loader


def _ensure_safe_loader(func_name: str, loader_cls: Type[Any]) -> Type[Any]:
    try:
        is_safe = issubclass(loader_cls, SafeLoader)
    except TypeError as exc:  # pragma: no cover - defensive guard
        raise TypeError(
            f"{func_name}() expected a Loader class, got {loader_cls!r}"
        ) from exc
    if not is_safe:
        raise ValueError(
            f"{func_name}() custom Loader must be a subclass of yaml.SafeLoader"
        )
    return loader_cls


def _select_loader(
    func_name: str,
    loader_cls: Any | None,
    legacy_loader: Any | None,
    *,
    default_loader: Any | None = None,
    required: bool = False,
) -> Any:
    if legacy_loader is not None:
        if loader_cls is not None:
            raise TypeError(
                f"{func_name}() received both 'Loader' and its replacement"
            )
        loader_cls = legacy_loader
    if loader_cls is None:
        loader_cls = default_loader
    if loader_cls is None and required:
        raise TypeError(
            f"{func_name}() missing 1 required positional argument: 'Loader'"
        )
    return loader_cls


def _resolve_loader_arguments(
    func_name: str,
    loader_args: tuple[Any, ...],
    loader_cls: Any | None,
    kwargs: dict[str, Any],
    *,
    default_loader: Any | None = None,
    required: bool,
) -> Any:
    positional_loader: Any | None = None
    if loader_args:
        if len(loader_args) > 1:
            raise TypeError(
                f"{func_name}() takes at most 1 positional loader argument"
            )
        positional_loader = loader_args[0]
        if loader_cls is not None:
            raise TypeError(
                f"{func_name}() received multiple loader arguments"
            )

    legacy_loader = _extract_legacy_loader(func_name, kwargs)
    if positional_loader is not None and legacy_loader is not None:
        raise TypeError(
            f"{func_name}() received multiple loader arguments"
        )

    effective_loader = positional_loader or loader_cls

    return _select_loader(
        func_name,
        effective_loader,
        legacy_loader,
        default_loader=default_loader,
        required=required,
    )


def _load_single(stream: str | bytes | TextIO | BinaryIO, loader_cls: Type[Any]) -> Any:
    loader = loader_cls(stream)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def _load_all(
    stream: str | bytes | TextIO | BinaryIO,
    loader_cls: Type[Any],
) -> Iterator[Any]:
    loader = loader_cls(stream)
    try:
        while loader.check_data():
            yield loader.get_data()
    finally:
        loader.dispose()


def warnings(settings=None):
    if settings is None:
        return {}

#------------------------------------------------------------------------------
def scan(stream, Loader=Loader):
    """
    Scan a YAML stream and produce scanning tokens.
    """
    loader = Loader(stream)
    try:
        while loader.check_token():
            yield loader.get_token()
    finally:
        loader.dispose()

def parse(stream, Loader=Loader):
    """
    Parse a YAML stream and produce parsing events.
    """
    loader = Loader(stream)
    try:
        while loader.check_event():
            yield loader.get_event()
    finally:
        loader.dispose()

def compose(stream, Loader=Loader):
    """
    Parse the first YAML document in a stream
    and produce the corresponding representation tree.
    """
    loader = Loader(stream)
    try:
        return loader.get_single_node()
    finally:
        loader.dispose()

def compose_all(stream, Loader=Loader):
    """
    Parse all YAML documents in a stream
    and produce corresponding representation trees.
    """
    loader = Loader(stream)
    try:
        while loader.check_node():
            yield loader.get_node()
    finally:
        loader.dispose()

def load(
    stream: str | bytes | TextIO | BinaryIO,
    loader_cls: Type[Any] | Literal[_MISSING_LOADER] = _MISSING_LOADER,
    **kwargs: Any,
) -> Any:
    """
    Parse the first YAML document in a stream
    and produce the corresponding Python object.
    """
    legacy_loader = _extract_legacy_loader("load", kwargs)
    effective_loader = None if loader_cls is _MISSING_LOADER else loader_cls
    resolved_loader = _select_loader(
        "load", effective_loader, legacy_loader, required=True
    )
    return _load_single(stream, resolved_loader)


def load_all(
    stream: str | bytes | TextIO | BinaryIO,
    loader_cls: Type[Any] | Literal[_MISSING_LOADER] = _MISSING_LOADER,
    **kwargs: Any,
) -> Iterator[Any]:
    """
    Parse all YAML documents in a stream
    and produce corresponding Python objects.
    """
    legacy_loader = _extract_legacy_loader("load_all", kwargs)
    effective_loader = None if loader_cls is _MISSING_LOADER else loader_cls
    resolved_loader = _select_loader(
        "load_all", effective_loader, legacy_loader, required=True
    )
    yield from _load_all(stream, resolved_loader)

def full_load(stream):
    """
    Parse the first YAML document in a stream
    and produce the corresponding Python object.

    Resolve all tags except those known to be
    unsafe on untrusted input.
    """
    return load(stream, FullLoader)

def full_load_all(stream):
    """
    Parse all YAML documents in a stream
    and produce corresponding Python objects.

    Resolve all tags except those known to be
    unsafe on untrusted input.
    """
    return load_all(stream, FullLoader)

def safe_load(
    stream: str | bytes | TextIO | BinaryIO,
    /,
    *loader_args: Any,
    loader_cls: Type[Any] | None = None,
    **kwargs: Any,
) -> Any:
    """
    Parse the first YAML document in a stream
    and produce the corresponding Python object.

    Resolve only basic YAML tags. This is known
    to be safe for untrusted input.
    """
    resolved_loader = _resolve_loader_arguments(
        "safe_load",
        loader_args,
        loader_cls,
        kwargs,
        default_loader=_DEFAULT_SAFE_LOADER,
        required=False,
    )
    safe_loader = _ensure_safe_loader("safe_load", resolved_loader)
    return _load_single(stream, safe_loader)


def safe_load_all(
    stream: str | bytes | TextIO | BinaryIO,
    /,
    *loader_args: Any,
    loader_cls: Type[Any] | None = None,
    **kwargs: Any,
) -> Iterator[Any]:
    """
    Parse all YAML documents in a stream
    and produce corresponding Python objects.

    Resolve only basic YAML tags. This is known
    to be safe for untrusted input.
    """
    resolved_loader = _resolve_loader_arguments(
        "safe_load_all",
        loader_args,
        loader_cls,
        kwargs,
        default_loader=_DEFAULT_SAFE_LOADER,
        required=False,
    )
    safe_loader = _ensure_safe_loader("safe_load_all", resolved_loader)
    yield from _load_all(stream, safe_loader)

def unsafe_load(stream):
    """
    Parse the first YAML document in a stream
    and produce the corresponding Python object.

    Resolve all tags, even those known to be
    unsafe on untrusted input.
    """
    return load(stream, UnsafeLoader)

def unsafe_load_all(stream):
    """
    Parse all YAML documents in a stream
    and produce corresponding Python objects.

    Resolve all tags, even those known to be
    unsafe on untrusted input.
    """
    return load_all(stream, UnsafeLoader)

def emit(events, stream=None, Dumper=Dumper,
        canonical=None, indent=None, width=None,
        allow_unicode=None, line_break=None):
    """
    Emit YAML parsing events into a stream.
    If stream is None, return the produced string instead.
    """
    getvalue = None
    if stream is None:
        stream = io.StringIO()
        getvalue = stream.getvalue
    dumper = Dumper(stream, canonical=canonical, indent=indent, width=width,
            allow_unicode=allow_unicode, line_break=line_break)
    try:
        for event in events:
            dumper.emit(event)
    finally:
        dumper.dispose()
    if getvalue:
        return getvalue()

def serialize_all(nodes, stream=None, Dumper=Dumper,
        canonical=None, indent=None, width=None,
        allow_unicode=None, line_break=None,
        encoding=None, explicit_start=None, explicit_end=None,
        version=None, tags=None):
    """
    Serialize a sequence of representation trees into a YAML stream.
    If stream is None, return the produced string instead.
    """
    getvalue = None
    if stream is None:
        if encoding is None:
            stream = io.StringIO()
        else:
            stream = io.BytesIO()
        getvalue = stream.getvalue
    dumper = Dumper(stream, canonical=canonical, indent=indent, width=width,
            allow_unicode=allow_unicode, line_break=line_break,
            encoding=encoding, version=version, tags=tags,
            explicit_start=explicit_start, explicit_end=explicit_end)
    try:
        dumper.open()
        for node in nodes:
            dumper.serialize(node)
        dumper.close()
    finally:
        dumper.dispose()
    if getvalue:
        return getvalue()

def serialize(node, stream=None, Dumper=Dumper, **kwds):
    """
    Serialize a representation tree into a YAML stream.
    If stream is None, return the produced string instead.
    """
    return serialize_all([node], stream, Dumper=Dumper, **kwds)

def dump_all(documents, stream=None, Dumper=Dumper,
        default_style=None, default_flow_style=False,
        canonical=None, indent=None, width=None,
        allow_unicode=None, line_break=None,
        encoding=None, explicit_start=None, explicit_end=None,
        version=None, tags=None, sort_keys=True):
    """
    Serialize a sequence of Python objects into a YAML stream.
    If stream is None, return the produced string instead.
    """
    getvalue = None
    if stream is None:
        if encoding is None:
            stream = io.StringIO()
        else:
            stream = io.BytesIO()
        getvalue = stream.getvalue
    dumper = Dumper(stream, default_style=default_style,
            default_flow_style=default_flow_style,
            canonical=canonical, indent=indent, width=width,
            allow_unicode=allow_unicode, line_break=line_break,
            encoding=encoding, version=version, tags=tags,
            explicit_start=explicit_start, explicit_end=explicit_end, sort_keys=sort_keys)
    try:
        dumper.open()
        for data in documents:
            dumper.represent(data)
        dumper.close()
    finally:
        dumper.dispose()
    if getvalue:
        return getvalue()

def dump(data, stream=None, Dumper=Dumper, **kwds):
    """
    Serialize a Python object into a YAML stream.
    If stream is None, return the produced string instead.
    """
    return dump_all([data], stream, Dumper=Dumper, **kwds)

def safe_dump_all(documents, stream=None, **kwds):
    """
    Serialize a sequence of Python objects into a YAML stream.
    Produce only basic YAML tags.
    If stream is None, return the produced string instead.
    """
    return dump_all(documents, stream, Dumper=SafeDumper, **kwds)

def safe_dump(data, stream=None, **kwds):
    """
    Serialize a Python object into a YAML stream.
    Produce only basic YAML tags.
    If stream is None, return the produced string instead.
    """
    return dump_all([data], stream, Dumper=SafeDumper, **kwds)

def add_implicit_resolver(tag, regexp, first=None,
        Loader=None, Dumper=Dumper):
    """
    Add an implicit scalar detector.
    If an implicit scalar value matches the given regexp,
    the corresponding tag is assigned to the scalar.
    first is a sequence of possible initial characters or None.
    """
    if Loader is None:
        loader.Loader.add_implicit_resolver(tag, regexp, first)
        loader.FullLoader.add_implicit_resolver(tag, regexp, first)
        loader.UnsafeLoader.add_implicit_resolver(tag, regexp, first)
    else:
        Loader.add_implicit_resolver(tag, regexp, first)
    Dumper.add_implicit_resolver(tag, regexp, first)

def add_path_resolver(tag, path, kind=None, Loader=None, Dumper=Dumper):
    """
    Add a path based resolver for the given tag.
    A path is a list of keys that forms a path
    to a node in the representation tree.
    Keys can be string values, integers, or None.
    """
    if Loader is None:
        loader.Loader.add_path_resolver(tag, path, kind)
        loader.FullLoader.add_path_resolver(tag, path, kind)
        loader.UnsafeLoader.add_path_resolver(tag, path, kind)
    else:
        Loader.add_path_resolver(tag, path, kind)
    Dumper.add_path_resolver(tag, path, kind)

def add_constructor(tag, constructor, Loader=None):
    """
    Add a constructor for the given tag.
    Constructor is a function that accepts a Loader instance
    and a node object and produces the corresponding Python object.
    """
    if Loader is None:
        loader.Loader.add_constructor(tag, constructor)
        loader.FullLoader.add_constructor(tag, constructor)
        loader.UnsafeLoader.add_constructor(tag, constructor)
    else:
        Loader.add_constructor(tag, constructor)

def add_multi_constructor(tag_prefix, multi_constructor, Loader=None):
    """
    Add a multi-constructor for the given tag prefix.
    Multi-constructor is called for a node if its tag starts with tag_prefix.
    Multi-constructor accepts a Loader instance, a tag suffix,
    and a node object and produces the corresponding Python object.
    """
    if Loader is None:
        loader.Loader.add_multi_constructor(tag_prefix, multi_constructor)
        loader.FullLoader.add_multi_constructor(tag_prefix, multi_constructor)
        loader.UnsafeLoader.add_multi_constructor(tag_prefix, multi_constructor)
    else:
        Loader.add_multi_constructor(tag_prefix, multi_constructor)

def add_representer(data_type, representer, Dumper=Dumper):
    """
    Add a representer for the given type.
    Representer is a function accepting a Dumper instance
    and an instance of the given data type
    and producing the corresponding representation node.
    """
    Dumper.add_representer(data_type, representer)

def add_multi_representer(data_type, multi_representer, Dumper=Dumper):
    """
    Add a representer for the given type.
    Multi-representer is a function accepting a Dumper instance
    and an instance of the given data type or subtype
    and producing the corresponding representation node.
    """
    Dumper.add_multi_representer(data_type, multi_representer)

class YAMLObjectMetaclass(type):
    """
    The metaclass for YAMLObject.
    """
    def __init__(cls, name, bases, kwds):
        super(YAMLObjectMetaclass, cls).__init__(name, bases, kwds)
        if 'yaml_tag' in kwds and kwds['yaml_tag'] is not None:
            if isinstance(cls.yaml_loader, list):
                for loader in cls.yaml_loader:
                    loader.add_constructor(cls.yaml_tag, cls.from_yaml)
            else:
                cls.yaml_loader.add_constructor(cls.yaml_tag, cls.from_yaml)

            cls.yaml_dumper.add_representer(cls, cls.to_yaml)

class YAMLObject(metaclass=YAMLObjectMetaclass):
    """
    An object that can dump itself to a YAML stream
    and load itself from a YAML stream.
    """

    __slots__ = ()  # no direct instantiation, so allow immutable subclasses

    yaml_loader = [Loader, FullLoader, UnsafeLoader]
    yaml_dumper = Dumper

    yaml_tag = None
    yaml_flow_style = None

    @classmethod
    def from_yaml(cls, loader, node):
        """
        Convert a representation node to a Python object.
        """
        return loader.construct_yaml_object(node, cls)

    @classmethod
    def to_yaml(cls, dumper, data):
        """
        Convert a Python object to a representation node.
        """
        return dumper.represent_yaml_object(cls.yaml_tag, data, cls,
                flow_style=cls.yaml_flow_style)
