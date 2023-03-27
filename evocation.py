import ast
import re
from inspect import getcallargs, getsource
from types import FunctionType
from typing import Any, Mapping, Optional, Sequence, Union

import openai

from api_secrets import OPENAI_API_KEY, OPENAI_ORGANIZATION
from dynamic import Dynamic
from openai_utils import (
    strip_codeblock,
    getchoice,
    CHAT_MODELS,
    chatinit,
    complete,
)
from settings import DEFAULT_SETTINGS, CHATGPT_NO, IEXEC_CHAT, REDEF_CHAT

openai.api_key = OPENAI_API_KEY
openai.organization = OPENAI_ORGANIZATION


def reconstruct_def(response, defstem, choice_ix=0, raise_truncated=True):
    received = strip_codeblock(getchoice(response, choice_ix, raise_truncated))
    if received.startswith("def"):
        # TODO: add docstring and stuff back.
        #  probably just extract the body first.
        return received
    if isinstance(defstem, FunctionType):
        defstem = getdef(defstem)
    return f"{defstem}\n{received}"


def getdef(func: FunctionType, get_docstring: bool = True) -> str:
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
        r"def.*\) ?(-> ?[^\n:]*)?:", getsource(func), re.M + re.DOTALL
    ).group()
    if (func.__doc__ is None) or (get_docstring is False):
        return defstring
    return defstring + '\n    """' + func.__doc__ + '"""\n'


def request_function_definition(
    base: Union[str, FunctionType, None],
    name: Optional[str] = None,
    args_like: Optional[Sequence[Any]] = None,
    return_like: Optional[Sequence[Any]] = None,
    *,
    language: str = "Python",
    _settings: Mapping = DEFAULT_SETTINGS,
):
    if isinstance(base, FunctionType):
        return _request_redefinition(base, _settings)
    parts = [f"Write a {language} function"]
    if name is not None:
        parts[0] += f" named {name}"
    if base is not None:
        parts[0] += f" that {base}"
    parts[0] += ".\n"
    if args_like is not None:
        if not isinstance(args_like, str):
            args_like = "\n".join(a.__repr__() for a in args_like)
        parts.append(f"Example inputs: {args_like}\n")
    if return_like is not None:
        if not isinstance(return_like, str):
            return_like = "\n".join(a.__repr__() for a in return_like)
        parts.append(f"Example outputs: {return_like}\n")
    prompt = "".join(parts)
    if _settings["model"] in CHAT_MODELS:
        prompt = chatinit(prompt + CHATGPT_NO, _settings.get("system"))
    return complete(prompt, _settings)


def _request_redefinition(
    func: FunctionType, _settings: Mapping = DEFAULT_SETTINGS
):
    prompt = getdef(func)
    if _settings["model"] in CHAT_MODELS:
        prompt = chatinit(
            f"{REDEF_CHAT + CHATGPT_NO}:\n{prompt}", _settings.get("system")
        )
    else:
        prompt = "# use this function:\n" + prompt
    return complete(prompt, _settings)


def format_calltext(func, *args, **kwargs):
    pretty_args = {}
    callargs = getcallargs(func, *args, **kwargs)
    for k, v in callargs.items():
        if isinstance(v, str):
            pretty_args[k] = f"'{v}'"
        elif v.__repr__().startswith("<"):
            if "__name__" in dir(v):
                pretty_args[k] = v.__name__
                continue
            raise TypeError(
                (
                    f"the __repr__ method of the object passed as the "
                    f"argument {k} returns the value {v}, which is too ugly "
                    f"to pass to this function. Give {k} a __name__ or a "
                    f"prettier __repr__ method."
                )
            )
        else:
            pretty_args[k] = v.__repr__()
    arglist, kwargdict = [], {}
    argcount = len(locals()["args"])
    for i, k in enumerate(pretty_args.keys()):
        if i < argcount:
            arglist.append(pretty_args[k])
        else:
            kwargdict[k] = pretty_args[k]
    # TODO: text wrapping or formatting or something
    callstring = f"{func.__name__}("
    callstring += ", ".join(arglist)
    if (len(arglist) > 0) and (len(kwargdict) > 0):
        callstring += ", "
    callstring += ", ".join(f"{k}={v}" for k, v in kwargdict.items())
    callstring += ")"
    return callstring


def request_function_call(
    _func: FunctionType,
    *args,
    _settings=DEFAULT_SETTINGS,
    **kwargs,
):
    callstring = format_calltext(_func, *args, **kwargs)
    if _settings["model"] in CHAT_MODELS:
        prefix = IEXEC_CHAT + CHATGPT_NO
        prompt = f"{prefix}\n{getsource(_func)}\n{callstring}\n"
        prompt = chatinit(prompt, _settings.get("system"))
    else:
        prefix = "# result of the function call\n>>> "
        prompt = f"{getsource(_func)}\n{prefix}{callstring}\n"
    return complete(prompt, _settings)


def evoke(
    _func: FunctionType, *args, _settings: Mapping = DEFAULT_SETTINGS, **kwargs
):
    """evoke a function, producing a possible result of its execution"""
    result, prompt = request_function_call(
        _func, *args, _settings=_settings, **kwargs
    )
    for step in (getchoice, strip_codeblock, ast.literal_eval):
        # TODO: dissociate this or hook it into something
        #  -- maybe basically a maybe monad --
        #  -- or it can be given some kind of cache/target argument
        #  that corresponds to an attribute of a Dynamic-like class
        #  (sort of like we do for killscreen Viewers)
        try:
            result = step(result)
        except KeyboardInterrupt:
            raise
        except Exception as ex:
            return result
    return result


def imply(
    base: Union[str, FunctionType],
    *,
    args_like: Any = None,
    return_like: Any = None,
    _settings: Mapping = DEFAULT_SETTINGS,
):
    """produce a function definition through implication"""
    result, prompt = request_function_definition(
        base, args_like=args_like, return_like=return_like, _settings=_settings
    )
    return Dynamic(reconstruct_def(result, base))
