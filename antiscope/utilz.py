"""generic functional/formatting utilities"""
import ast
import datetime as dt
import re
import traceback
from functools import wraps
from inspect import getsource, getdoc, getcallargs, currentframe, getframeinfo
from types import FunctionType, CodeType, FrameType
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
        r"def.*?\) ?(-> ?(\w|[\[\]])*?[^\n:]*)?:",
        digsource(func),
        re.M + re.DOTALL
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


def pluck_from_execution(text, globals_):
    _, _, varname = terminal_assignment_line(ast.parse(text).body)
    exec(text, globals_, locals())
    return locals()[varname]


def exc_report(exc):
    if exc is None:
        return {}
    return {
        "time": dt.datetime.now().isoformat()[:-3],
        "exception": exc,
        "stack": tuple([a.name for a in traceback.extract_stack()[:-3]]),
    }


def tabtext(text, tabsize=4):
    tab = " " * tabsize
    return tab + re.sub("\n", f"\n{tab}", text)


def argformat_docstring(func: FunctionType, *args, **kwargs) -> str:
    return getdoc(func).format(**getcallargs(func, *args, **kwargs))


def capture_call() -> str:
    return parse_call_from_source(*get_call_source(currentframe().f_back))


def get_call_source(frame: FrameType, maxlines: int = 25) -> tuple[str, str]:
    caller = frame.f_back
    call_line = getframeinfo(caller).code_context[0]
    context = getframeinfo(caller, maxlines).code_context
    return call_line, "".join(context)


def subquote(text):
    return re.sub("'", '"', text)


def parse_call_from_source(call_line: str, context: str) -> str:
    callmatch = re.search(r"(\w|_|\d)+?(?=\()", call_line)
    if callmatch is None:
        raise ValueError("Couldn't find callable variable name in source.")
    callable_varname = callmatch.group()
    parsed = ast.parse("".join(context))
    callsource = None
    for obj in ast.walk(parsed):
        if not isinstance(obj, ast.Call):
            continue
        # noinspection PyTypeChecker
        unparsed = ast.unparse(obj)
        if not unparsed.startswith(callable_varname):
            continue
        if (
            subquote(call_line[callmatch.span()[0]:].strip())
            not in subquote(unparsed)
        ):
            continue
        callsource = unparsed
        break
    if callsource is None:
        raise ValueError("Couldn't find function call in source.")
    return callsource
