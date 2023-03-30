"""generic functional/formatting utilities"""
import ast
import datetime as dt
import re
import traceback
from functools import wraps
from inspect import getsource
from types import FunctionType, CodeType
from typing import Callable, Optional, Sequence

from cytoolz import nth

EXPECTED_DECORATORS = ("@evoked", "@implied", "@cache")


def _strip_our_decorators(defstring: str) -> str:
    for decorator in EXPECTED_DECORATORS:
        defstring = re.sub(f"{decorator}.*\n", "", defstring)
    return defstring


def getdef(func: Callable, get_docstring: bool = True) -> str:
    """
    return a string containing the 'definition portion' of func's
    source code (including annotations and inline comments).
    optionally also append its docstring (if it has one).

    caveats:
    1. may not work on functions with complicated inline comments
     in their definitions.
    2. does not work on lambdas; may not work on some other classes
     of dynamically-defined functions.
    """
    defstring = re.search(
        r"def.*\) ?(-> ?[^\n:]*)?:", digsource(func), re.M + re.DOTALL
    ).group()
    if (func.__doc__ is None) or (get_docstring is False):
        return defstring
    return defstring + '\n    """' + func.__doc__ + '"""\n'


def digsource(obj: Callable):
    """
    wrapper for inspect.getsource that attempts to work on objects like
    Dynamic, functools.partial, etc.
    """
    if isinstance(obj, FunctionType):
        return getsource(obj)
    if "func" in dir(obj):
        # noinspection PyUnresolvedReferences
        return getsource(obj.func)
    raise TypeError(f"cannot get source for type {type(obj)}")


def get_codechild(code: CodeType, ix: int = 0) -> CodeType:
    return nth(ix, filter(lambda c: isinstance(c, CodeType), code.co_consts))


def dontcare(func, target=None):
    @wraps(func)
    def carelessly(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            target.append(exc_report(e) | {"func": func, 'category': 'call'})

    return carelessly


def compile_source(source: str):
    return get_codechild(compile(source, "", "exec"))


def define(code: CodeType, globals_: Optional[dict] = None) -> FunctionType:
    globals_ = globals_ if globals_ is not None else globals()
    return FunctionType(code, globals_)


# TODO: will currently fail for multi-target assignments
# noinspection PyUnresolvedReferences
def terminal_assignment_line(parsed: Sequence[ast.stmt]):
    for statement in reversed(parsed):
        if isinstance(statement, ast.Assign):
            return True, statement.lineno - 1, statement.targets[0].id
    return False, None, None


def filter_assignment(text):
    has_assign, ix, varname = terminal_assignment_line(ast.parse(text).body)
    if has_assign is False:
        return text
    text = "\n".join(text.split("\n")[ix:])
    text = re.sub(fr"\s*{varname}\s*=\s*", "", text)
    return text


def pluck_from_execution(text, *ex_args, **ex_kw):
    _, _, varname = terminal_assignment_line(ast.parse(text).body)
    exec(text, *ex_args, **ex_kw)
    return locals()[varname]


def exc_report(exc):
    if exc is None:
        return {}
    return {
        "time": dt.datetime.now().isoformat()[:-3],
        "exception": exc,
        "stack": tuple([a.name for a in traceback.extract_stack()[:-3]]),
    }
