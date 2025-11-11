from __future__ import annotations

import io
from typing import Any, ClassVar

from . import dumper as _dumper_module
from . import loader as _loader_module
from .dumper import *
from .error import *
from .events import *
from .loader import *
from .nodes import *
from .tokens import *

__version__ = "6.0"
try:
    from .cyaml import *

    __with_libyaml__ = True
except ImportError:
    __with_libyaml__ = False


def _normalize_class_argument(
    *,
    argument: type[Any] | None,
    kwargs: dict[str, Any],
    default: type[Any] | None,
    func_name: str,
    legacy_name: str,
    require: bool,
) -> type[Any] | None:
    if legacy_name in kwargs:
        legacy_value = kwargs.pop(legacy_name)
        if argument is not None:
            raise TypeError(
                f"{func_name}() received both '{legacy_name}' and its replacement "
                f"parameter; pass only one of them",
            )
        argument = legacy_value
    if argument is None:
        if require:
            raise TypeError(
                f"{func_name}() missing required argument '{legacy_name.lower()}'",
            )
        if default is not None:
            argument = default
    return argument


def _normalize_loader_argument(
    loader: type[_loader_module.BaseLoader] | None,
    kwargs: dict[str, Any],
    *,
    default: type[_loader_module.BaseLoader] | None,
    func_name: str,
    require: bool,
) -> type[_loader_module.BaseLoader] | None:
    return _normalize_class_argument(
        argument=loader,
        kwargs=kwargs,
        default=default,
        func_name=func_name,
        legacy_name="Loader",
        require=require,
    )


def _normalize_dumper_argument(
    dumper: type[_dumper_module.BaseDumper] | None,
    kwargs: dict[str, Any],
    *,
    default: type[_dumper_module.BaseDumper] | None,
    func_name: str,
    require: bool,
) -> type[_dumper_module.BaseDumper] | None:
    return _normalize_class_argument(
        argument=dumper,
        kwargs=kwargs,
        default=default,
        func_name=func_name,
        legacy_name="Dumper",
        require=require,
    )


def _reject_unexpected_kwargs(func_name: str, kwargs: dict[str, Any]) -> None:
    if kwargs:
        unexpected = ", ".join(sorted(kwargs))
        raise TypeError(f"{func_name}() got unexpected keyword arguments: {unexpected}")


# ------------------------------------------------------------------------------
# XXX "Warnings control" is now deprecated. Leaving in the API function to not
# break code that uses it.
# ------------------------------------------------------------------------------
def warnings(settings=None):
    if settings is None:
        return {}


# ------------------------------------------------------------------------------
def scan(stream, loader: type[_loader_module.BaseLoader] | None = None, /, **kwargs):
    """
    Scan a YAML stream and produce scanning tokens.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=_loader_module.Loader,
        func_name="scan",
        require=False,
    )
    _reject_unexpected_kwargs("scan", kwargs)
    loader_instance = loader_cls(stream)
    try:
        while loader_instance.check_token():
            yield loader_instance.get_token()
    finally:
        loader_instance.dispose()


def parse(stream, loader: type[_loader_module.BaseLoader] | None = None, /, **kwargs):
    """
    Parse a YAML stream and produce parsing events.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=_loader_module.Loader,
        func_name="parse",
        require=False,
    )
    _reject_unexpected_kwargs("parse", kwargs)
    loader_instance = loader_cls(stream)
    try:
        while loader_instance.check_event():
            yield loader_instance.get_event()
    finally:
        loader_instance.dispose()


def compose(stream, loader: type[_loader_module.BaseLoader] | None = None, /, **kwargs):
    """
    Parse the first YAML document in a stream
    and produce the corresponding representation tree.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=_loader_module.Loader,
        func_name="compose",
        require=False,
    )
    _reject_unexpected_kwargs("compose", kwargs)
    loader_instance = loader_cls(stream)
    try:
        return loader_instance.get_single_node()
    finally:
        loader_instance.dispose()


def compose_all(
    stream, loader: type[_loader_module.BaseLoader] | None = None, /, **kwargs
):
    """
    Parse all YAML documents in a stream
    and produce corresponding representation trees.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=_loader_module.Loader,
        func_name="compose_all",
        require=False,
    )
    _reject_unexpected_kwargs("compose_all", kwargs)
    loader_instance = loader_cls(stream)
    try:
        while loader_instance.check_node():
            yield loader_instance.get_node()
    finally:
        loader_instance.dispose()


def load(stream, loader: type[_loader_module.BaseLoader] | None = None, /, **kwargs):
    """
    Parse the first YAML document in a stream
    and produce the corresponding Python object.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=_loader_module.Loader,
        func_name="load",
        require=False,
    )
    _reject_unexpected_kwargs("load", kwargs)
    assert loader_cls is not None
    loader_instance = loader_cls(stream)
    try:
        return loader_instance.get_single_data()
    finally:
        loader_instance.dispose()


def load_all(
    stream, loader: type[_loader_module.BaseLoader] | None = None, /, **kwargs
):
    """
    Parse all YAML documents in a stream
    and produce corresponding Python objects.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=_loader_module.Loader,
        func_name="load_all",
        require=False,
    )
    _reject_unexpected_kwargs("load_all", kwargs)
    assert loader_cls is not None
    loader_instance = loader_cls(stream)
    try:
        while loader_instance.check_data():
            yield loader_instance.get_data()
    finally:
        loader_instance.dispose()


def full_load(
    stream, loader: type[_loader_module.BaseLoader] | None = None, /, **kwargs
):
    """
    Parse the first YAML document in a stream
    and produce the corresponding Python object.

    Resolve all tags except those known to be
    unsafe on untrusted input.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=_loader_module.FullLoader,
        func_name="full_load",
        require=False,
    )
    _reject_unexpected_kwargs("full_load", kwargs)
    assert loader_cls is not None
    return load(stream, loader_cls)


def full_load_all(
    stream, loader: type[_loader_module.BaseLoader] | None = None, /, **kwargs
):
    """
    Parse all YAML documents in a stream
    and produce corresponding Python objects.

    Resolve all tags except those known to be
    unsafe on untrusted input.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=_loader_module.FullLoader,
        func_name="full_load_all",
        require=False,
    )
    _reject_unexpected_kwargs("full_load_all", kwargs)
    assert loader_cls is not None
    return load_all(stream, loader_cls)


def safe_load(
    stream, loader: type[_loader_module.BaseLoader] | None = None, /, **kwargs
):
    """
    Parse the first YAML document in a stream
    and produce the corresponding Python object.

    Resolve only basic YAML tags. This is known
    to be safe for untrusted input.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=_loader_module.SafeLoader,
        func_name="safe_load",
        require=False,
    )
    _reject_unexpected_kwargs("safe_load", kwargs)
    assert loader_cls is not None
    return load(stream, loader_cls)


def safe_load_all(
    stream, loader: type[_loader_module.BaseLoader] | None = None, /, **kwargs
):
    """
    Parse all YAML documents in a stream
    and produce corresponding Python objects.

    Resolve only basic YAML tags. This is known
    to be safe for untrusted input.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=_loader_module.SafeLoader,
        func_name="safe_load_all",
        require=False,
    )
    _reject_unexpected_kwargs("safe_load_all", kwargs)
    assert loader_cls is not None
    return load_all(stream, loader_cls)


def unsafe_load(
    stream, loader: type[_loader_module.BaseLoader] | None = None, /, **kwargs
):
    """
    Parse the first YAML document in a stream
    and produce the corresponding Python object.

    Resolve all tags, even those known to be
    unsafe on untrusted input.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=_loader_module.UnsafeLoader,
        func_name="unsafe_load",
        require=False,
    )
    _reject_unexpected_kwargs("unsafe_load", kwargs)
    assert loader_cls is not None
    return load(stream, loader_cls)


def unsafe_load_all(
    stream, loader: type[_loader_module.BaseLoader] | None = None, /, **kwargs
):
    """
    Parse all YAML documents in a stream
    and produce corresponding Python objects.

    Resolve all tags, even those known to be
    unsafe on untrusted input.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=_loader_module.UnsafeLoader,
        func_name="unsafe_load_all",
        require=False,
    )
    _reject_unexpected_kwargs("unsafe_load_all", kwargs)
    assert loader_cls is not None
    return load_all(stream, loader_cls)


def emit(
    events,
    stream=None,
    dumper: type[_dumper_module.BaseDumper] | None = None,
    canonical=None,
    indent=None,
    width=None,
    allow_unicode=None,
    line_break=None,
    **kwargs,
):
    """
    Emit YAML parsing events into a stream.
    If stream is None, return the produced string instead.
    """
    getvalue = None
    if stream is None:
        stream = io.StringIO()
        getvalue = stream.getvalue
    dumper_cls = _normalize_dumper_argument(
        dumper,
        kwargs,
        default=_dumper_module.Dumper,
        func_name="emit",
        require=False,
    )
    _reject_unexpected_kwargs("emit", kwargs)
    dumper_instance = dumper_cls(
        stream,
        canonical=canonical,
        indent=indent,
        width=width,
        allow_unicode=allow_unicode,
        line_break=line_break,
    )
    try:
        for event in events:
            dumper_instance.emit(event)
    finally:
        dumper_instance.dispose()
    if getvalue:
        return getvalue()


def serialize_all(
    nodes,
    stream=None,
    dumper: type[_dumper_module.BaseDumper] | None = None,
    canonical=None,
    indent=None,
    width=None,
    allow_unicode=None,
    line_break=None,
    encoding=None,
    explicit_start=None,
    explicit_end=None,
    version=None,
    tags=None,
    **kwargs,
):
    """
    Serialize a sequence of representation trees into a YAML stream.
    If stream is None, return the produced string instead.
    """
    getvalue = None
    if stream is None:
        stream = io.StringIO() if encoding is None else io.BytesIO()
        getvalue = stream.getvalue
    dumper_cls = _normalize_dumper_argument(
        dumper,
        kwargs,
        default=_dumper_module.Dumper,
        func_name="serialize_all",
        require=False,
    )
    _reject_unexpected_kwargs("serialize_all", kwargs)
    dumper_instance = dumper_cls(
        stream,
        canonical=canonical,
        indent=indent,
        width=width,
        allow_unicode=allow_unicode,
        line_break=line_break,
        encoding=encoding,
        version=version,
        tags=tags,
        explicit_start=explicit_start,
        explicit_end=explicit_end,
    )
    try:
        dumper_instance.open()
        for node in nodes:
            dumper_instance.serialize(node)
        dumper_instance.close()
    finally:
        dumper_instance.dispose()
    if getvalue:
        return getvalue()


def serialize(
    node,
    stream=None,
    dumper: type[_dumper_module.BaseDumper] | None = None,
    **kwds,
):
    """
    Serialize a representation tree into a YAML stream.
    If stream is None, return the produced string instead.
    """
    return serialize_all([node], stream, dumper=dumper, **kwds)


def dump_all(
    documents,
    stream=None,
    dumper: type[_dumper_module.BaseDumper] | None = None,
    default_style=None,
    default_flow_style=False,
    canonical=None,
    indent=None,
    width=None,
    allow_unicode=None,
    line_break=None,
    encoding=None,
    explicit_start=None,
    explicit_end=None,
    version=None,
    tags=None,
    sort_keys=True,
    **kwargs,
):
    """
    Serialize a sequence of Python objects into a YAML stream.
    If stream is None, return the produced string instead.
    """
    getvalue = None
    if stream is None:
        stream = io.StringIO() if encoding is None else io.BytesIO()
        getvalue = stream.getvalue
    dumper_cls = _normalize_dumper_argument(
        dumper,
        kwargs,
        default=_dumper_module.Dumper,
        func_name="dump_all",
        require=False,
    )
    _reject_unexpected_kwargs("dump_all", kwargs)
    dumper_instance = dumper_cls(
        stream,
        default_style=default_style,
        default_flow_style=default_flow_style,
        canonical=canonical,
        indent=indent,
        width=width,
        allow_unicode=allow_unicode,
        line_break=line_break,
        encoding=encoding,
        version=version,
        tags=tags,
        explicit_start=explicit_start,
        explicit_end=explicit_end,
        sort_keys=sort_keys,
    )
    try:
        dumper_instance.open()
        for data in documents:
            dumper_instance.represent(data)
        dumper_instance.close()
    finally:
        dumper_instance.dispose()
    if getvalue:
        return getvalue()


def dump(
    data,
    stream=None,
    dumper: type[_dumper_module.BaseDumper] | None = None,
    **kwds,
):
    """
    Serialize a Python object into a YAML stream.
    If stream is None, return the produced string instead.
    """
    return dump_all([data], stream, dumper=dumper, **kwds)


def safe_dump_all(documents, stream=None, **kwds):
    """
    Serialize a sequence of Python objects into a YAML stream.
    Produce only basic YAML tags.
    If stream is None, return the produced string instead.
    """
    return dump_all(documents, stream, dumper=_dumper_module.SafeDumper, **kwds)


def safe_dump(data, stream=None, **kwds):
    """
    Serialize a Python object into a YAML stream.
    Produce only basic YAML tags.
    If stream is None, return the produced string instead.
    """
    return dump_all([data], stream, dumper=_dumper_module.SafeDumper, **kwds)


def add_implicit_resolver(
    tag,
    regexp,
    first=None,
    loader: type[_loader_module.BaseLoader] | None = None,
    dumper: type[_dumper_module.BaseDumper] | None = None,
    **kwargs,
):
    """
    Add an implicit scalar detector.
    If an implicit scalar value matches the given regexp,
    the corresponding tag is assigned to the scalar.
    first is a sequence of possible initial characters or None.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=None,
        func_name="add_implicit_resolver",
        require=False,
    )
    dumper_cls = _normalize_dumper_argument(
        dumper,
        kwargs,
        default=_dumper_module.Dumper,
        func_name="add_implicit_resolver",
        require=False,
    )
    _reject_unexpected_kwargs("add_implicit_resolver", kwargs)
    if loader_cls is None:
        _loader_module.Loader.add_implicit_resolver(tag, regexp, first)
        _loader_module.FullLoader.add_implicit_resolver(tag, regexp, first)
        _loader_module.UnsafeLoader.add_implicit_resolver(tag, regexp, first)
    else:
        loader_cls.add_implicit_resolver(tag, regexp, first)
    dumper_cls.add_implicit_resolver(tag, regexp, first)


def add_path_resolver(
    tag,
    path,
    kind=None,
    loader: type[_loader_module.BaseLoader] | None = None,
    dumper: type[_dumper_module.BaseDumper] | None = None,
    **kwargs,
):
    """
    Add a path based resolver for the given tag.
    A path is a list of keys that forms a path
    to a node in the representation tree.
    Keys can be string values, integers, or None.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=None,
        func_name="add_path_resolver",
        require=False,
    )
    dumper_cls = _normalize_dumper_argument(
        dumper,
        kwargs,
        default=_dumper_module.Dumper,
        func_name="add_path_resolver",
        require=False,
    )
    _reject_unexpected_kwargs("add_path_resolver", kwargs)
    if loader_cls is None:
        _loader_module.Loader.add_path_resolver(tag, path, kind)
        _loader_module.FullLoader.add_path_resolver(tag, path, kind)
        _loader_module.UnsafeLoader.add_path_resolver(tag, path, kind)
    else:
        loader_cls.add_path_resolver(tag, path, kind)
    dumper_cls.add_path_resolver(tag, path, kind)


def add_constructor(
    tag, constructor, loader: type[_loader_module.BaseLoader] | None = None, **kwargs
):
    """
    Add a constructor for the given tag.
    Constructor is a function that accepts a Loader instance
    and a node object and produces the corresponding Python object.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=None,
        func_name="add_constructor",
        require=False,
    )
    _reject_unexpected_kwargs("add_constructor", kwargs)
    if loader_cls is None:
        _loader_module.Loader.add_constructor(tag, constructor)
        _loader_module.FullLoader.add_constructor(tag, constructor)
        _loader_module.UnsafeLoader.add_constructor(tag, constructor)
    else:
        loader_cls.add_constructor(tag, constructor)


def add_multi_constructor(
    tag_prefix,
    multi_constructor,
    loader: type[_loader_module.BaseLoader] | None = None,
    **kwargs,
):
    """
    Add a multi-constructor for the given tag prefix.
    Multi-constructor is called for a node if its tag starts with tag_prefix.
    Multi-constructor accepts a Loader instance, a tag suffix,
    and a node object and produces the corresponding Python object.
    """
    loader_cls = _normalize_loader_argument(
        loader,
        kwargs,
        default=None,
        func_name="add_multi_constructor",
        require=False,
    )
    _reject_unexpected_kwargs("add_multi_constructor", kwargs)
    if loader_cls is None:
        _loader_module.Loader.add_multi_constructor(tag_prefix, multi_constructor)
        _loader_module.FullLoader.add_multi_constructor(tag_prefix, multi_constructor)
        _loader_module.UnsafeLoader.add_multi_constructor(tag_prefix, multi_constructor)
    else:
        loader_cls.add_multi_constructor(tag_prefix, multi_constructor)


def add_representer(
    data_type,
    representer,
    dumper: type[_dumper_module.BaseDumper] | None = None,
    **kwargs,
):
    """
    Add a representer for the given type.
    Representer is a function accepting a Dumper instance
    and an instance of the given data type
    and producing the corresponding representation node.
    """
    dumper_cls = _normalize_dumper_argument(
        dumper,
        kwargs,
        default=_dumper_module.Dumper,
        func_name="add_representer",
        require=False,
    )
    _reject_unexpected_kwargs("add_representer", kwargs)
    dumper_cls.add_representer(data_type, representer)


def add_multi_representer(
    data_type,
    multi_representer,
    dumper: type[_dumper_module.BaseDumper] | None = None,
    **kwargs,
):
    """
    Add a representer for the given type.
    Multi-representer is a function accepting a Dumper instance
    and an instance of the given data type or subtype
    and producing the corresponding representation node.
    """
    dumper_cls = _normalize_dumper_argument(
        dumper,
        kwargs,
        default=_dumper_module.Dumper,
        func_name="add_multi_representer",
        require=False,
    )
    _reject_unexpected_kwargs("add_multi_representer", kwargs)
    dumper_cls.add_multi_representer(data_type, multi_representer)


class YAMLObjectMetaclass(type):
    """
    The metaclass for YAMLObject.
    """

    def __init__(cls, name, bases, kwds):
        super().__init__(name, bases, kwds)
        if "yaml_tag" in kwds and kwds["yaml_tag"] is not None:
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

    yaml_loader: ClassVar[list[type[_loader_module.BaseLoader]]] = [
        _loader_module.Loader,
        _loader_module.FullLoader,
        _loader_module.UnsafeLoader,
    ]
    yaml_dumper: ClassVar[type[_dumper_module.BaseDumper]] = _dumper_module.Dumper

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
        return dumper.represent_yaml_object(
            cls.yaml_tag, data, cls, flow_style=cls.yaml_flow_style
        )
