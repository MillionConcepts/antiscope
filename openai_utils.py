import re
from typing import Union

from cytoolz import keyfilter
import openai

from openai_settings import EP_KWARGS, CHAT_MODELS


def _codestrippable(line):
    if re.match(r"```(\w+)?", line):
        return True
    if re.match(r">>>", line):
        return True


def strip_codeblock(text, fname: str = None):
    """
    crudely strip markdown codeblock formatting, conventional Python terminal
    representation, and any precursor to an (undesired) function redeclaration
    """
    # TODO: extract content of """ blocks?
    lines = list(filter(None, text.split("\n")))
    if fname is not None:
        f_ix = None
        for i, line in enumerate(lines):
            if line.strip().startswith(f"def {fname}"):
                f_ix = i
                break
        if f_ix is not None:
            lines = lines[f_ix:]
    for _ in range(2):
        if _codestrippable(lines[0]):
            lines = lines[1:]
    if _codestrippable(lines[-1]):
        lines = lines[:-1]
    return "\n".join(lines)


def addreply(msg, hist):
    return hist + [{"role": "assistant", "content": msg}]


def addmsg(msg, hist):
    return hist + [{"role": "user", "content": msg}]


def _call_openai_completion(prompt, _settings):
    if isinstance(prompt, (list, tuple)):
        prompt = "\n".join(prompt)
    response = openai.Completion.create(
        prompt=prompt,
        **keyfilter(lambda k: k in EP_KWARGS["completions"], _settings),
    )
    return response, prompt


def _call_openai_chat_completion(messages, _settings):
    response = openai.ChatCompletion.create(
        messages=messages,
        **keyfilter(lambda k: k in EP_KWARGS["chat-completions"], _settings),
    )
    return response, messages


# TODO: exception handling of various types. some perhaps at higher
#  levels. i.e., "your input was too long. please try defining the
#  call in a more compact way." etc.
def complete(to_complete: Union[list[dict], str], _settings):
    if _settings["model"] in CHAT_MODELS:
        return _call_openai_chat_completion(to_complete, _settings)
    return _call_openai_completion(to_complete, _settings)


def chatinit(prompt=None, system=None):
    messages = []
    for msg, role in zip((system, prompt), ("system", "user")):
        if msg is not None:
            messages.append({"role": role, "content": msg})
    return messages


def getchoice(openai_response, choice_ix=0, raise_truncated: bool = True):
    if raise_truncated is True:
        fr = openai_response["choices"][choice_ix]["finish_reason"]
        if fr != "stop":
            raise IOError(f"Response did not terminate successfully: {fr}")
    choice = openai_response["choices"][choice_ix]
    if "message" in choice:
        return choice["message"]["content"]
    return choice["text"]


def conversation_factory(_settings, with_console=True):
    if _settings["model"] not in CHAT_MODELS:
        raise TypeError(
            f'{_settings["model"]} does not support chat completions.'
        )
    history = chatinit(system=_settings["system"])
    if with_console is True:
        from rich.console import Console

        printer = Console(width=66).print
    else:
        printer = print

    def say(
        message=None, printreply=True, extract=True, eject=False, **api_kwargs
    ):
        nonlocal history
        if eject is True:
            return history
        if message is None:
            raise TypeError("unless ejecting history, must add a message")
        history = addmsg(message, history)
        response, _ = complete(history, _settings | api_kwargs)
        text = getchoice(response)
        history = addreply(text, history)
        if printreply is True:
            printer(text)
        if extract is True:
            return text
        return response

    return say
