from inspect import signature, Signature
from types import FunctionType
from typing import Optional

from antiscope.utilz import (
    digsource, dontcare, compile_source, define, exc_report
)


# TODO: some kind of "FunctionLike" type

class AlreadyLoadedError(ValueError):
    pass


class UnreadyError(ValueError):
    pass


# TODO, maybe: optimization stuff re: kwarg mapping, etc. -- but if you wanted
#  to engage in really high call volume, you could also just explicitly call
#  the wrapped function...
class Dynamic:
    """
    simple class to help manage function definition / execution from
    dynamically-generated source.
    """
    def __init__(
        self,
        source: Optional[str] = None,
        globals_: Optional[dict] = None,
        optional: bool = False,
        lazy: bool = False,
        load_on_call: bool = True
    ):
        self.globals_ = globals_
        self.optional = optional
        self.errors = []
        self.load_on_call = load_on_call
        self.lazy = lazy
        self.call_fail = False
        self.compile_fail = False
        self.source = source
        if lazy is False:
            try:
                self.load()
            # should only encounter this when called from a class constructor
            except AlreadyLoadedError:
                pass

    # TODO: deal with modules not imported at compile-time
    #  -- maybe just permit second compilation --
    #  -- or do we need to pass globals? ugh.

    def load(self, reload=False):
        if (reload is False) and (self.func is not None):
            raise AlreadyLoadedError("self.func already loaded")
        self.compile_source(reload)
        self.define(reload)

    def compile_source(self, recompile=True):
        if (recompile is False) and (self.code is not None):
            raise AlreadyLoadedError("self.code already compiled")
        try:
            self.code = compile_source(self.source)
        except KeyboardInterrupt:
            raise
        except Exception as ex:
            self.errors.append(exc_report(ex) | {'category': 'compile'})
            self.compile_fail = True

    def define(self, redefine=False):
        if (self.func is not None) and (redefine is not True):
            raise AlreadyLoadedError("self.func already defined")
        self.func = define(self.code, self.globals_)
        self.__signature__ = signature(self.func)
        self.__name__ = self.func.__name__

    def unload(self):
        del self.code, self.func, self.errors
        self.call_fail, self.compile_fail = False, False
        self.code, self.func, self.errors = None, None, []
        self.__name__ = self.__class__.__name__
        self.__signature__ = None

    def _maybe_load_on_call(self, reload=False):
        if self.func is not None:
            return
        if self.load_on_call is True:
            return self.load(reload)
        raise UnreadyError("No loaded function.")

    def __call__(self, *args, _optional=None, **kwargs):
        self._maybe_load_on_call()
        if _optional is None:
            _optional = self.optional
        if _optional is False:
            # noinspection PyUnresolvedReferences
            return self.func(*args, **kwargs)
        try:
            return dontcare(self.func, self.errors)(*args, **kwargs)
        finally:
            if len(self.errors) > 0:
                if self.errors[-1].get('category') == 'call':
                    self.call_fail = True

    def __str__(self):
        if self.func is None:
            return self.__class__.__name__
        return f"{self.__class__.__name__} {signature(self.func)}"

    def __repr__(self):
        return self.__str__()

    @classmethod
    def from_function(cls, func: FunctionType, *init_args, **init_kwargs):
        # TODO: some of this boilerplate could be reduced with a bunch of
        #  fancy getattr overrides
        dynamic = super().__new__(cls)
        dynamic.source = digsource(func)
        dynamic.code = func.__code__
        dynamic.func = func
        dynamic.__signature__ = signature(dynamic.func)
        dynamic.__name__ = dynamic.func.__name__
        dynamic.globals_ = func.__globals__
        dynamic.__init__(*init_args, **init_kwargs)
        return dynamic

    __signature__ = Signature()
    source, code, func, __name__ = None, None, None, '<unloaded Dynamic>'


def test_dynamic():
    testdef = """def f(x: float) -> float:\n    return x + 1"""
    dyn = Dynamic(testdef, optional=True)
    assert dyn(1) == 2
    dyn("j")
    assert (
        str(dyn.errors[0]["exception"])
        == 'can only concatenate str (not "int") to str'
    )
