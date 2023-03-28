from abc import ABC, abstractmethod
from types import MappingProxyType
from typing import Optional, Mapping, Literal, MutableMapping, Union

from dynamic import Dynamic, exc_report


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
        description: Union[str, Mapping, None] = None,
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
        super().__init__(description, globals_, optional, lazy)

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
    def evoke(self, *args, **kwargs):
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
            return self.invoke(*args, _optional, **kwargs)
        return self.evoke(*args, _optional, **kwargs)

    default_api_settings: MappingProxyType
    __name__ = '<unloaded Irrealis>'


"""quasigraphs"""

"""
The Problem of Functional Heterogeneity:
Crosslinguistically, imperatives get associated with a rather heterogeneous 
range of speech act types (Commands, Warnings, Requests, Advice, Curses, 
Permissions, Permissions, Concessions...)
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

