import datetime as dt
from functools import wraps
from inspect import signature, Signature
import traceback
from types import CodeType, FunctionType, MappingProxyType
from typing import Mapping


def get_first_codechild(codeobj: CodeType) -> CodeType:
    return next(filter(lambda c: isinstance(c, CodeType), codeobj.co_consts))


def exc_report(exc):
    return {
        "time": dt.datetime.now().isoformat()[:-3],
        "exception": exc,
        "stack": tuple([a.name for a in traceback.extract_stack()[:-3]]),
    }


def dontcare(func, target=None):
    @wraps(func)
    def carelessly(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            target.append(exc_report(e) | {"func": func})

    return carelessly


class Dynamic:
    def __init__(
        self,
        source,
        globaldict: Mapping = MappingProxyType({}),
        optional: bool = True,
    ):
        self.globaldict = dict(globaldict)
        self.optional = optional
        self.errors = []
        if source is None:
            return
        self.source = source
        self.load()

    def compile_source(self):
        if self.code is not None:
            raise ValueError("self.code already compiled")
        self.code = get_first_codechild(compile(self.source, "", "exec"))

    def define(self):
        if self.func is not None:
            raise ValueError("self.func already defined")
        func = FunctionType(self.code, self.globaldict)
        self.__signature__ = signature(func)
        if self.optional is True:
            func = dontcare(func, self.errors)
        self.func = func

    def load(self):
        self.compile_source()
        self.define()

    @classmethod
    def from_source(
        cls,
        source: str,
        globaldict: Mapping = MappingProxyType({}),
        optional: bool = True,
    ):
        dyn = object.__new__(cls)
        dyn.__init__(source, globaldict, optional)
        dyn.compile_source()
        dyn.define()

    def __call__(self, *args, _strict=False, **kwargs):
        if _strict is True:
            # noinspection PyUnresolvedReferences
            return self.func.__wrapped__(*args, **kwargs)
        return self.func(*args, **kwargs)

    def __str__(self):
        if self.func is None:
            return "unloaded Dynamic"
        return f"Dynamic: {signature(self.func)}"

    def __repr__(self):
        return self.__str__()

    __signature__ = Signature()
    source, code, func = None, None, None


def test_dynamic():
    testdef = """def f(x: float) -> float:\n    return x + 1"""
    dyn = Dynamic(testdef)
    assert dyn(1) == 2
    dyn("j")
    assert (
        str(dyn.errors[0]["exception"])
        == 'can only concatenate str (not "int") to str'
    )
