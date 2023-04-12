"""
reference implementation of irrealis-mood functionality w/the OpenAI API
"""
import ast
import datetime as dt
import re
from inspect import getcallargs, get_annotations
from types import FunctionType, MappingProxyType

# noinspection PyUnresolvedReferences, PyProtectedMember
from typing import (
    Any,
    Mapping,
    Optional,
    Sequence,
    Union,
    Callable,
    _GenericAlias,
    Literal,
)

from cytoolz import curry
from tiktoken import encoding_for_model

from antiscope.dynamic import Dynamic
from antiscope.irrealis import (
    Irrealis,
    ImplicationFailure,
    EvocationFailure,
    base_evoked,
    base_implied,
    Implication,
    ImplicationWrapper,
    base_impliedobj,
    Performative,
)
from antiscope.openai_settings import (
    CHAT_MODELS,
    DEFAULT_SETTINGS,
    CHATGPT_NO,
    IEXEC_CHAT,
    REDEF_CHAT,
    CHATGPT_FORMAT,
)
from antiscope.openai_utils import (
    complete,
    getchoice,
    strip_codeblock,
    addmsg,
    addreply,
    get_usage,
    get_cost,
)
from antiscope.utilz import (
    _strip_our_decorators,
    getdef,
    digsource,
    exc_report,
    filter_assignment,
    tabtext,
    argformat_docstring, capture_call,
)

FALLBACK_STRIPPABLES = "".join(('"', "'", "`", "\n", " ", "."))


def format_type(type_):
    if isinstance(type_, type):
        return type_.__name__
    else:
        return re.sub(rf"(typing|types)\.", "", str(type_))


# TODO: add more control over chat context
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
    parts = [f"show me a possible example of a {language} function"]
    if name is not None:
        parts[0] += f" named {name}"
    if base is not None:
        parts[0] += f" that {base}"
    parts[0] += (
        ". If you have to import anything, put the import inside the "
        "function definition.\n"
    )
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
        prompt += CHATGPT_NO
    return complete(prompt, _settings)


def _eventrecord(prompt, response, category) -> dict[str]:
    return {
        "prompt": prompt,
        "response": response,
        "category": category,
        "time": dt.datetime.now().isoformat()[:-3],
    }


def _request_redefinition(
    func: FunctionType, _settings: Mapping = DEFAULT_SETTINGS
):
    prompt = getdef(func)
    if _settings["model"] in CHAT_MODELS:
        prompt = f"{REDEF_CHAT + CHATGPT_FORMAT + CHATGPT_NO}:\n{prompt}"
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


def wish_for_call(
    _func: FunctionType,
    *args,
    _settings=DEFAULT_SETTINGS,
    _csource=None,
    **kwargs,
):
    for_chat = _settings["model"] in CHAT_MODELS
    callstring = format_calltext(_func, *args, **kwargs)
    if _csource is not None:
        # TODO: dumb magic number, misses lots of context, etc., etc.
        tokens = encoding_for_model(_settings['model']).encode(callstring)
        if len(tokens) > _settings['max_tokens'] * 0.8:
            callstring = _csource
    prompt = _finalize_calltext(_func, callstring, for_chat)
    return complete(prompt, _settings)


def _finalize_calltext(func, callstring, for_chat):
    source = _strip_our_decorators(digsource(func))
    if for_chat is True:
        prefix = IEXEC_CHAT + CHATGPT_FORMAT + CHATGPT_NO + "\n###\n"
        prompt = f"{prefix}\n{source}\n{callstring}\n"
    else:
        prefix = "# result of the function call\n>>> "
        prompt = f"{source}\n{prefix}{callstring}\n"
    return prompt


def command_from_call(
    _func: FunctionType, *args, _settings: Mapping = DEFAULT_SETTINGS, **kwargs
):
    prompt = argformat_docstring(_func, *args, **kwargs)
    ftype = format_type(get_annotations(_func).get("return"))
    no_parse = True
    if ftype not in ("str", "None"):
        no_parse = False
        prompt += f"\nformat your response as a Python object of type {ftype}."
    if _settings.get("noexplain") is not False:
        prompt += "\nDo not write explanations."
    response, _ = complete(prompt, _settings)
    return response, prompt, no_parse


# noinspection PyUnboundLocalVariable
def literalizer(text: str, retry: bool = False):
    for i in range(5):
        try:
            if i == 0:
                return ast.literal_eval(text)
            if i == 1:
                return ast.literal_eval(text.strip(FALLBACK_STRIPPABLES))
            if i == 2:
                lines = tuple(
                    filter(lambda l: "print(" not in l, text.split("\n"))
                )
                lastline = lines[-1].strip(FALLBACK_STRIPPABLES)
                return ast.literal_eval(lastline)
            if i == 3:
                return ast.literal_eval(filter_assignment(lastline))
            if i == 4:
                return ast.literal_eval(re.sub(".*=", "", lastline))
        except (SyntaxError, ValueError) as exc:
            exception = exc
    if retry is False:
        return literalizer("\n".join(lines[1:]), retry=True)
    raise exception


EVOCATION_PIPELINE = MappingProxyType(
    {"choose": getchoice, "strip": strip_codeblock, "parse": literalizer}
)


# TODO: this might be usable in part as a more generic evoke pattern.
def evoke(
    _func: FunctionType,
    *args,
    _settings: Mapping = DEFAULT_SETTINGS,
    _performativity: Literal[Performative] = "wish",
    _extended: bool = False,
    _processing_pipeline: Mapping[str, Callable] = EVOCATION_PIPELINE,
    _csource: Optional[str] = None,
    **kwargs,
):
    """evoke a function, producing a possible result of its execution"""
    no_parse = False
    if _performativity == "wish":
        response, prompt = wish_for_call(
            _func, *args, _settings=_settings, _csource=_csource, **kwargs
        )
    elif _performativity == "command":
        response, prompt, no_parse = command_from_call(
            _func, *args, _settings=_settings, **kwargs
        )
    else:
        raise ValueError(
            f"This function only accepts 'wish' and 'command' performatives "
            f"(received {_performativity})"
        )
    exception, excstep, report = None, None, None
    result = response
    for name, step in _processing_pipeline.items():
        if (name == "parse") and (no_parse is True):
            # no_parse implies that we simply want to use the content of the
            # response as a string
            continue
        try:
            result = step(result)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            exception, excstep = exc, step.__name__
            break
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
    **api_kwargs,
):
    """produce a function definition through implication"""
    result, prompt = request_function_definition(
        base,
        args_like=args_like,
        return_like=return_like,
        _settings=_settings | api_kwargs,
    )
    return Dynamic(reconstruct_def(result, base), globals_=globals())


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
            self._record_event(prompt, res, "imply")
            step = "extract_response"
            return reconstruct_def(res, base)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            self.errors.append(
                exc_report(exc) | {"category": "imply", "step": step}
            )
            raise ImplicationFailure(exc)

    def evoke(self, *args, _optional=None, **kwargs):
        if _optional is None:
            if "dry_run" in self.api_settings:
                _optional = True
            else:
                _optional = self.optional
        result, res, prompt, report, exc = evoke(
            self.func,
            *args,
            _extended=True,
            _performativity=self.performativity,
            _settings=self.api_settings,
            _csource=self.csource,
            **kwargs,
        )
        self._record_event(prompt, res, "evoke")
        if exc is not None:
            self.evoke_fail = True
            self.errors.append(report)
            if _optional is True:
                try:
                    return getchoice(result, raise_truncated=False)
                except TypeError:
                    return result
            raise EvocationFailure(exc)
        return result

    def tochat(self) -> list[dict]:
        # TODO: deal with system?
        messages = []
        for entry in self.history:
            if "prompt" not in entry.keys():
                continue
            messages = addmsg(entry["prompt"], messages)
            messages = addreply(
                getchoice(entry["response"], raise_truncated=False), messages
            )
        return messages

    @property
    def usage(self):
        return get_usage(self.history)

    @property
    def cost(self):
        return get_cost(self.api_settings["model"], self.history)

    def _record_event(self, prompt, response, category):
        self.history.append(_eventrecord(prompt, response, category))

    def __call__(self, *args, _optional=None, **kwargs):
        if self.side == "evocative":
            self.csource = capture_call()
        return super().__call__(*args, _optional=_optional, **kwargs)

    performativity: Performative = "wish"
    default_api_settings = DEFAULT_SETTINGS
    csource = None


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
    # TODO: crude
    if not received.startswith("    "):
        received = tabtext(received)
    return f"{defstem}\n{received}"


def request_object_construction(
    base: Union[str, Mapping, None] = None,
    implied_type: Union[None, type, _GenericAlias] = None,
    *,
    language: str = "Python",
    _settings: Mapping = DEFAULT_SETTINGS,
):
    if _settings.get("model") not in CHAT_MODELS:
        raise NotImplementedError(
            "Base (non-chat) completions not yet implemented for "
            "request_object_construction."
        )
    if isinstance(base, Mapping):
        raise NotImplementedError(
            "Mapping expansion not yet implemented for the `base` "
            "argument of request_object_construction."
        )
    prompt = format_construction_prompt(base, implied_type, language)
    return complete(prompt, _settings)


def format_construction_prompt(base, implied_type, language="Python"):
    prompt = f"Show me example {language} code that constructs an object "
    if implied_type is not None:
        prompt += f"of type {format_type(implied_type)} "
    if base is not None:
        prompt += f"that expresses {base} "
    return prompt + ". Do not write explanations."


# TODO: can probably reuse some of this code with OAIrrealis
class OAImplication(Implication):
    def imply(self) -> str:
        step = "setup"
        try:
            step = "api_call"
            res, prompt = request_object_construction(
                self.description,
                self.implied_type,
                _settings=self.api_settings,
            )
            self._record_event(prompt, res, "imply")
            step = "extract_response"
            return strip_codeblock(getchoice(res))
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            self.errors.append(
                exc_report(exc) | {"category": "imply", "step": step}
            )
            raise ImplicationFailure(exc)

    def _record_event(self, prompt, response, category):
        self.history.append(_eventrecord(prompt, response, category))

    @property
    def usage(self):
        return get_usage(self.history)

    @property
    def cost(self):
        return get_cost(self.api_settings["model"], self.history)

    @staticmethod
    def literalize(text):
        return literalizer(text)

    default_api_settings = DEFAULT_SETTINGS


class OAImplicationWrapper(ImplicationWrapper):
    _constructor = OAImplication


evoked = curry(base_evoked, irrealis=OAIrrealis)
implied = curry(base_implied, irrealis=OAIrrealis)
commanded = curry(base_evoked, irrealis=OAIrrealis, performativity="command")
iobj = curry(base_impliedobj, implication=OAImplication)
