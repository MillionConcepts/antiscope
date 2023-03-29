"""
reference implementation of irrealis-mood functionality w/the OpenAI API
"""
import ast
import datetime as dt
import re
from inspect import getcallargs
from types import FunctionType
from typing import Any, Mapping, Optional, Sequence, Union, Callable

from cytoolz import curry
import openai

from api_secrets import OPENAI_API_KEY, OPENAI_ORGANIZATION
from dynamic import Dynamic
from irrealis import (
    Irrealis,
    ImplicationFailure,
    EvocationFailure,
    base_evoked,
    base_implied,
)
from openai_settings import (
    CHAT_MODELS,
    DEFAULT_SETTINGS,
    CHATGPT_NO,
    IEXEC_CHAT,
    REDEF_CHAT,
)
from openai_utils import (
    chatinit,
    complete,
    getchoice,
    strip_codeblock,
)
from utilz import _strip_our_decorators, getdef, digsource, exc_report

openai.api_key = OPENAI_API_KEY
openai.organization = OPENAI_ORGANIZATION


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
            pretty_args[k] = f'"""{v}"""'
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
    for_chat = _settings["model"] in CHAT_MODELS
    prompt = construct_call_prompt(
        _func, args, kwargs, for_chat, _settings.get("system")
    )
    return complete(prompt, _settings)


def construct_call_prompt(_func, args, kwargs, for_chat=True, system=None):
    callstring = format_calltext(_func, *args, **kwargs)
    source = _strip_our_decorators(digsource(_func))
    if for_chat is True:
        prefix = IEXEC_CHAT + CHATGPT_NO + "\n###\n"
        prompt = f"{prefix}\n{source}\n{callstring}\n"
        prompt = chatinit(prompt, system)
    else:
        prefix = "# result of the function call\n>>> "
        prompt = f"{source}\n{prefix}{callstring}\n"
    return prompt


EVOCATION_PIPELINE = (getchoice, strip_codeblock, ast.literal_eval)


# TODO: this might actually be usable as a more generic `evoke` pattern.
def evoke(
    _func: FunctionType,
    *args,
    _settings: Mapping = DEFAULT_SETTINGS,
    _extended: bool = False,
    _processing_pipeline: tuple[Callable] = EVOCATION_PIPELINE,
    **kwargs,
):
    """evoke a function, producing a possible result of its execution"""
    response, prompt = request_function_call(
        _func, *args, _settings=_settings, **kwargs
    )
    exception, excstep, report = None, None, None
    result = response
    for step in _processing_pipeline:
        try:
            result = step(result)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            exception, excstep = exc, step.__name__
    if _extended is False:
        return result
    if exception is not None:
        report = exc_report(exception) | {"step": excstep}
    return result, response, prompt, report, exception


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


class OAIrrealis(Irrealis):
    def imply(self, _sideload_settings: Optional[Mapping] = None) -> str:
        step = "setup"
        _settings = self.api_settings
        if _sideload_settings is not None:
            _settings = _settings | _sideload_settings
        try:
            step = "api_call"
            if isinstance(self.description, Mapping):
                base = self.description["base"]
                res, prompt = request_function_definition(
                    _settings=_settings, **self.description
                )
            else:
                base = self.description
                res, prompt = request_function_definition(
                    self.description, _settings=_settings
                )
            self.log(prompt, res, "imply")
            step = "interpret_response"
            return reconstruct_def(res, base)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            self.errors.append(
                exc_report(exc) | {"category": "imply", "step": step}
            )
            raise ImplicationFailure(exc)

    def evoke(self, *args, _optional=None, **kwargs):
        _optional = self.optional if _optional is None else _optional
        result, res, prompt, report, exc = evoke(
            self.func, *args, _extended=True, **kwargs
        )
        self.log(prompt, res, "evoke")
        if exc is not None:
            self.evoke_fail = True
            self.errors.append(report)
            if _optional is True:
                return result
            raise EvocationFailure(exc)
        return result

    def log(self, prompt, response, category):
        self.history.append(
            {
                "prompt": prompt,
                "response": response,
                "category": category,
                "time": dt.datetime.now().isoformat()[:-3],
            }
        )

    default_api_settings = DEFAULT_SETTINGS


evoked = curry(base_evoked, irrealis=OAIrrealis)
implied = curry(base_implied, irrealis=OAIrrealis)


def reconstruct_def(response, defstem, choice_ix=0, raise_truncated=True):
    if "__name__" in dir(defstem):
        # functions and things like functions
        fname = defstem.__name__
        defstem = getdef(defstem)
    else:
        # just strings
        if (match := re.search(r"def (.+)\(", defstem)) is not None:
            fname = match.group(1)
        else:
            fname = None
    received = strip_codeblock(
        getchoice(response, choice_ix, raise_truncated), fname
    )
    if received.startswith("def"):
        # TODO: add docstring and stuff back.
        #  probably just extract the body first.
        return received
    return f"{defstem}\n{received}"
