from abc import ABC, abstractmethod
from types import MappingProxyType, FunctionType
# noinspection PyUnresolvedReferences, PyProtectedMember
from typing import (
    Optional, Mapping, Literal, Union, Callable, Any, _GenericAlias
)

from cytoolz import identity

from dynamic import Dynamic, UnreadyError
from utilz import digsource, exc_report


# TODO: async versions. maybe only needs to happen at implementation level,
#  but there might be helper structures here. implementations still need to
#  be responsible for not blocking when running async (but not parallel).
#  if we do want true parallelism we will probably want to implement pickling
#  functionality for these classes.


class ImplicationFailure(Exception):
    pass


class EvocationFailure(Exception):
    pass


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
        # performativity: Literal["imperative", "desiderative"] = "imperative"
        lazy: bool = True,
        auto_reimply: bool = False,
        globals_: Optional[dict] = None,
        **api_kwargs
    ):
        self.description = description
        self.side = side
        self.stance = stance
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
        if self.stance == "implicit":
            if (self.source is None) or (reload is True):
                try:
                    self.source = self.imply()
                except KeyboardInterrupt:
                    raise
                except ImplicationFailure:
                    if self.optional is False:
                        raise
                except Exception as ex:
                    self.errors.append(exc_report(ex) | {'category': 'imply'})
                    if self.optional is False:
                        raise
                finally:
                    self.imply_fail = True
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
    __name__ = '<unloaded Irrealis>'


def base_evoked(func: FunctionType, *args, irrealis: type[Irrealis], **kwargs):
    return irrealis.from_function(func, *args, side='evocative', **kwargs)


def base_implied(
    base: Union[FunctionType, str, dict],
    *args,
    irrealis: type[Irrealis],
    **kwargs
):
    return irrealis(base, *args, stance='implicit', **kwargs)


class ImplicationInterior(ABC):
    def __init__(
        self,
        description: Union[str, Mapping, None],
        implied_type: Union[None, type, _GenericAlias] = None,
        optional: bool = False,
        lazy: bool = True,
        auto_reimply: bool = False,
        formatter: Callable = identity,
        load_on_access: bool = True,
        **api_kwargs
    ):
        self.description = description
        self.implied_type = implied_type
        self.api_settings = self.default_api_settings | api_kwargs
        self.auto_reimply = auto_reimply
        self.imply_fail = False
        self.optional = optional
        self.formatter = formatter
        self.lazy = lazy
        self.obj = None
        self.load_on_access = load_on_access

    @abstractmethod
    def load(self, reload=False) -> bool:
        raise NotImplementedError

    @abstractmethod
    def imply(self) -> str:
        raise NotImplementedError

    def _raise_if_nonoptional(self):
        if self.optional is True:
            return
        raise UnreadyError

    def setobjattr(self, attr, value):
        if self.obj is None:
            return self._raise_if_nonoptional()
        self.obj.__setattr__(attr, value)

    def getobjattr(self, attr):
        if self.obj is None:
            return self._raise_if_nonoptional()
        self.obj.__getattr__(attr)

    default_api_settings: MappingProxyType


# TODO, maybe: implement auto-reimply for this. might need to limit it to
#  particular attributes. Could basically just freeze all execution.
class Implication:

    def __init__(self, *args, **kw):
        if "__constructor" in kw.keys():
            self.__constructor = kw.pop('__constructor')
        elif "__constructor" not in dir(self):
            raise TypeError(
                "Must pass a __constructor kwarg to __init__ "
                "if no __constructor attribute already exists."
            )
        self.__interior = self.__constructor(*args, **kw)
        self.__optional = self.__interior.optional
        if self.__interior.lazy is False:
            self.load()
            return
        if self.__interior.load_on_access is False:
            return
        self.__initialized = True

    def load(self, *args, **kwargs):
        load_success = self.__interior.load(*args, **kwargs)
        self.__initialized = load_success
        self.__loaded = load_success

    def __getattribute__(self, attr):
        if attr == "__private_attributes":
            return object.__getattribute__(self, "__private_attributes")
        if attr in self.__private_attributes:
            return object.__getattribute__(self, attr)
        if attr == "__setattribute__":
            return self.__getattr("__setattribute__")
        if self.__initialized is False:
            try:
                return self.__getattr(attr)
            except AttributeError:
                return self.__interior.__getattribute__(attr)
        if self.__loaded is False:
            if self.__interior.load_on_access is True:
                self.load()
            else:
                return self.__getattr(attr)
        return self.__interior.getobjattr(attr)

    # TODO: the difference in functionality re: fallback to __interior's
    #  attributes during initialization and loading, and __getattribute__ and
    #  __setattribute__, is concerning. need to work with some implementations
    #  to see what behaviors make most sense.
    def __setattr__(self, attr, value):
        if self.__initialized is False:
            return self.__setattr(attr, value)
        if attr in self.__private_attributes:
            return self.__setattr(attr, value)
        if self.__loaded is False:
            if self.__interior.load_on_access is True:
                self.load()
            else:
                return self.__setattr(attr, value)
        return self.__interior.setobjattr(attr, value)

    def __getattr(self, attr):
        return object.__getattribute__(self, attr)

    def __setattr(self, attr, value):
        return object.__setattr__(self, attr, value)

    __initialized = False
    __loaded = False
    __constructor: Union[
        ImplicationInterior, Callable[[Any], ImplicationInterior]
    ]
    __private_attributes = (
        "__interior",
        "__initialized",
        "__loaded",
        "__optional",
        "__interior_constructor",
        "__getattr",
        "__setattr",
        "__private_attributes",
    )


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

