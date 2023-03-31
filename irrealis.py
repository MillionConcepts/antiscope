import ast
from abc import ABC, abstractmethod
from types import MappingProxyType, FunctionType

# noinspection PyUnresolvedReferences, PyProtectedMember
from typing import (
    Optional,
    Mapping,
    Literal,
    Union,
    Callable,
    Any,
    _GenericAlias,
)

from dynamic import Dynamic, UnreadyError, AlreadyLoadedError
from utilz import (
    digsource,
    exc_report,
    pluck_from_execution,
    filter_assignment,
)


# TODO: async versions. maybe only needs to happen at implementation level,
#  but there might be helper structures here. implementations still need to
#  be responsible for not blocking when running async (but not parallel).
#  if we do want true parallelism we will probably want to implement pickling
#  functionality for these classes.


class ImplicationFailure(Exception):
    pass


class EvocationFailure(Exception):
    pass


Performative = Literal[
    "command",
    "warning",
    "request",
    "advice",
    "curse",
    "permission",
    "concession",
    "wish",
    "assertion",
    "promise",
    "threat",
    "invitation",
]


class Irrealis(Dynamic, ABC):
    """
    simple class to help manage function evocation and implication
    """

    def __init__(
        self,
        description: Union[str, Mapping, FunctionType, None] = None,
        side: Literal["invocative", "evocative"] = "invocative",
        stance: Literal["explicit", "implicit"] = "explicit",
        optional: bool = False,
        performativity: Optional[Performative] = 'wish',
        lazy: bool = True,
        auto_reimply: bool = False,
        globals_: Optional[dict] = None,
        **api_kwargs
    ):
        self.description = description
        self.side = side
        self.stance = stance
        # no default effect. may be used by implementations of this class
        self.performativity = performativity
        self.api_settings = self.default_api_settings | api_kwargs
        self.auto_reimply = auto_reimply
        self.imply_fail = False
        self.evoke_fail = False
        self.history = []
        if self.stance == "implicit":
            source = None
        elif isinstance(description, Callable):
            source = digsource(description)
        elif isinstance(description, str):
            source = description
        elif isinstance(description, Mapping):
            raise TypeError(
                "Cannot initialize an Irrealis in explicit stance with a "
                "Mapping description."
            )
        elif description is None:
            source = None
        else:
            raise TypeError("unknown description format.")
        super().__init__(source, globals_, optional, lazy)

    def load(self, reload=False):
        if self.stance == "explicit":
            return super().load()
        if (self.source is not None) and (reload is False):
            raise AlreadyLoadedError
        self.imply_fail = True
        try:
            self.source = self.imply()
            self.imply_fail = False
        except KeyboardInterrupt:
            raise
        except ImplicationFailure:
            # this case means exception was logged by the
            # implementation of self.imply
            if self.optional is False:
                raise
        except Exception as ex:
            self.errors.append(exc_report(ex) | {"category": "imply"})
            if self.optional is False:
                raise
        return super().load()

    @abstractmethod
    def evoke(self, *args, _optional=None, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def imply(self, _sideload_settings: Optional[Mapping] = None) -> str:
        raise NotImplementedError

    def invoke(self, *args, _optional=None, **kwargs):
        _optional = self.optional if _optional is None else _optional
        return super().__call__(*args, _optional=_optional, **kwargs)

    def unload(self):
        super().unload()
        self.imply_fail, self.evoke_fail, self.history = False, False, []

    def set(self, api_attr, val):
        self.api_settings[api_attr] = val

    def __call__(self, *args, _optional=None, **kwargs):
        reload = (self.stance == "implicit") and self.auto_reimply
        super()._maybe_load_on_call(reload=reload)
        if self.side == "invocative":
            return self.invoke(*args, _optional=_optional, **kwargs)
        return self.evoke(*args, _optional=_optional, **kwargs)

    default_api_settings: MappingProxyType
    __name__ = "<unloaded Irrealis>"


# TODO: should this actually have a Dynamic-analogous base class that, like,
#  just evaluates source?
class EvaluationError(Exception):
    pass


class Implication(ABC):
    def __init__(
        self,
        description: Union[str, Mapping, None],
        implied_type: Union[None, type, _GenericAlias] = None,
        optional: bool = False,
        lazy: bool = True,
        auto_reimply: bool = False,
        load_on_access: bool = True,
        eval_mode: Literal["literal", "eval", "exec"] = "literal",
        auto_retry_failed: bool = False,
        **api_kwargs
    ):
        self.eval_fail = False
        self.description = description
        self.implied_type = implied_type
        self.api_settings = self.default_api_settings | api_kwargs
        self.auto_reimply = auto_reimply
        self.imply_fail = False
        self.optional = optional
        self.lazy = lazy
        self.eval_mode = eval_mode
        self.obj = None
        self.source = None
        self.load_on_access = load_on_access
        self.auto_retry_failed = auto_retry_failed
        self.errors = []
        self.history = []
        if self.lazy is False:
            self.load()

    def _maybe_load(self, on_access, reload=False) -> bool:
        if (self.load_on_access is False) and (on_access is True):
            return False
        if (self.imply_fail or self.eval_fail) and not self.auto_retry_failed:
            return False
        return self.load(reload=reload)

    def load(self, reload=False) -> bool:
        # TODO: can probably reuse this + Irrealis.load
        if (self.source is not None) and (reload is False):
            raise AlreadyLoadedError
        self.imply_fail, exception = True, None
        try:
            self.source = self.imply()
            self.imply_fail = False
        except KeyboardInterrupt:
            raise
        except ImplicationFailure as exc:
            exception = exc
            # this case means exception was logged by the implementation
            # of self.imply
        except Exception as exc:
            exception = exc
            self.errors.append(exc_report(exc) | {"category": "imply"})
        if self.imply_fail is True:
            self._raise_if_nonoptional(ImplicationFailure(str(exception)))
            return False
        return self.evaluate()

    def evaluate(self, *args, globals_=None, **kwargs) -> bool:
        kwargs["globals"] = globals_ if globals_ is not None else globals()
        self.eval_fail = True
        try:
            # TODO, pass locals/globals in some nicer way
            if self.eval_mode == "literal":
                self.obj = self.literalize(self.source)
            elif self.eval_mode == "eval":
                self.obj = eval(self.source, *args, **kwargs)
            elif self.eval_mode == "exec":
                self.obj = pluck_from_execution(self.source, *args, **kwargs)
            self.eval_fail = False
            return True
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            self.errors.append(exc_report(exc) | {"category": "evaluate"})
            self._raise_if_nonoptional(EvaluationError(str(exc)))
        return False

    @abstractmethod
    def imply(self) -> str:
        raise NotImplementedError

    def _raise_if_nonoptional(self, exctype: Exception = UnreadyError):
        if self.optional is True:
            return
        raise exctype

    def setobjattr(self, attr, value):
        if self.obj is None:
            return self._raise_if_nonoptional()
        self.obj.__setattr__(attr, value)

    def getobjattr(self, attr):
        if self.obj is None:
            return self._raise_if_nonoptional()
        self.obj.__getattr__(attr)

    literalize: lambda a: ast.literal_eval(filter_assignment(a))
    default_api_settings: MappingProxyType


# TODO, maybe: implement auto-reimply for this. might need to limit it to
#  particular attributes. Could basically just freeze all execution.
# TODO: all the magic methods. not very useful right now.
# noinspection PyProtectedMember
class ImplicationWrapper:
    def __init__(self, *args, **kw):
        if "_constructor" in kw.keys():
            self._constructor = kw.pop("_constructor")
        elif "_constructor" not in dir(self):
            raise TypeError(
                "Must pass a _constructor kwarg to __init__ "
                "if no _constructor attribute already exists."
            )
        self._interior = self._constructor(*args, **kw)
        self._optional = self._interior.optional
        if self._interior.lazy is False:
            self.load()
            return
        if self._interior.load_on_access is False:
            return
        self._initialized = True

    def load(self, *args, **kwargs):
        load_success = self._interior.load(*args, **kwargs)
        self._initialized = load_success
        self._loaded = load_success

    # TODO: the difference in functionality re: fallback to _interior's
    #  attributes during initialization and loading, and __getattribute__ and
    #  __setattribute__, is concerning. need to work with some implementations
    #  to see what behaviors make most sense.

    def __getattribute__(self, attr):
        if attr == "_getattr":
            return object.__getattribute__(self, "_getattr")
        if attr == "_private_attributes":
            return self._getattr(attr)
        if attr in self._private_attributes:
            return self._getattr(attr)
        if attr == "__setattribute__":
            return self._getattr(attr)
        if self._initialized is False:
            try:
                return self._getattr(attr)
            except AttributeError:
                return self._interior.__getattribute__(attr)
        if self._loaded is False:
            self._loaded = self._interior._maybe_load(on_access=True)
        if self._loaded is False:
            return self._getattr(attr)
        return self._interior.getobjattr(attr)

    def __setattr__(self, attr, value):
        if self._initialized is False:
            return self._setattr(attr, value)
        if attr in self._private_attributes:
            return self._setattr(attr, value)
        if self._loaded is False:
            self._loaded = self._interior._maybe_load(on_access=True)
        if self._loaded is False:
            return self._setattr(attr, value)
        return self._interior.setobjattr(attr, value)

    def _getattr(self, attr):
        return object.__getattribute__(self, attr)

    def _setattr(self, attr, value):
        return object.__setattr__(self, attr, value)

    _initialized = False
    _loaded = False
    _constructor: Union[Implication, Callable[[Any], Implication]]
    _private_attributes = (
        "_interior",
        "_initialized",
        "_loaded",
        "_optional",
        "_interior_constructor",
        "_getattr",
        "_setattr",
        "_private_attributes",
    )


def base_evoked(func: FunctionType, *args, irrealis: type[Irrealis], **kwargs):
    return irrealis.from_function(func, *args, side="evocative", **kwargs)


def base_implied(
    base: Union[FunctionType, str, dict],
    *args,
    irrealis: type[Irrealis],
    **kwargs
):
    return irrealis(base, *args, stance="implicit", **kwargs)


def base_impliedobj(
    base: Union[str, Mapping, None],
    implied_type: Union[None, type, _GenericAlias] = None,
    *args,
    implication: type[Implication],
    lazy: bool = False,
    **kwargs
) -> Union[Implication, Any]:
    if lazy is True:
        return implication(base, implied_type, *args, lazy=True, **kwargs)
    return implication(base, implied_type, *args, lazy=False, **kwargs).obj


"""quasigraphs"""

"""
The Problem of Functional Heterogeneity:
Crosslinguistically, imperatives get associated with a rather heterogeneous 
range of speech act types (Commands, Warnings, Requests, Advice, Curses, 
Permissions, Concessions...)
(Condoravdi and Lauer 2009, ref. Schmerling 1982)
"""

"""
Thus, translations between stances occur, and they are significant as 
manuals for communication and interaction. So, are implicit intuitionistic 
and explicit epistemic logic then just the same system in different guises 
because of their faithful mutual embeddings? This question raises delicate 
issues of system identity.
(van Benthem 2018)
"""

"""
Rather, its significance was invocative and evocative: through it, the virgin's
presence was invoked and her story evoked [...] It was the opposite of 
traditional images of Mary looking up at Christ on the cross. Here, the man 
looked up from below at Mary [...] "All the dances, somewhere along the line, 
have a meaning to that apparition," Rico said.
(Sklar 1999)
"""

"""
The evocative method practices a perceptive address to living meaning in 
the act of writing. [...]  When concrete things are named in text in which 
words are evocative, then a peculiar effect may occur: its textual meaning 
begins to address us. [...by contrast,] The [invocative] writer invokes 
powers of language to have certain effects on the reader. Invocative words 
become infected or contaminated by the meanings of other words to which they 
stand in alliterative or repetitive relation. [...] It seems that the 
repeating sense of sounds tends to create a spell-binding quality. 
(van Manen 2014)
"""
