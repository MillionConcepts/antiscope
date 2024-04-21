import datetime as dt
import re
from operator import xor
from typing import Union, Mapping, Collection, Optional

from cytoolz import keyfilter
from openai import OpenAI

from antiscope.openai_settings import (
    EP_KWARGS, CHAT_MODELS, DEFAULT_SETTINGS, PRICING, get_secrets
)


client = OpenAI(**get_secrets())


def _codestrippable(line):
    # TODO: redundant
    if re.match(r"```(\w+)?", line):
        return True
    if re.match(r">>>", line):
        return True


def strip_codeblock(text, fname: str = None):
    """
    crudely strip markdown codeblock formatting, conventional Python terminal
    representation, and any precursor to an (undesired) function redeclaration
    """
    # TODO: maybe should be a separate function
    if "```" in text:
        text = re.search(r"```(\w+\n)?(.*)(```|^)", text, re.DOTALL).group(2)
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
    response = client.completions.create(prompt=prompt,
    **keyfilter(lambda k: k in EP_KWARGS["completions"], _settings))
    return response, prompt


def _call_openai_chat_completion(prompt, _settings):
    if isinstance(prompt, list):
        messages = prompt
    elif (messages := _settings.get("message_context")) is None:
        messages = chatinit(prompt, _settings.get("system"))
    else:
        messages = addmsg(prompt, messages)
    # permit people to use random additional kwargs and keys
    messages = [{'role': m['role'], 'content': m['content']} for m in messages]
    kwargs = keyfilter(lambda k: k in EP_KWARGS["chat-completions"], _settings)
    if _settings.get("dry_run") is True:
        return MockCompletion(messages, **kwargs), messages
    response = client.chat.completions.create(messages=messages, **kwargs)
    return response, messages


# TODO: exception handling of various types. some perhaps at higher
#  levels. i.e., "your input was too long. please try defining the
#  call in a more compact way." etc.
def complete(to_complete: Union[list[dict], str], _settings):
    if _settings["model"] in CHAT_MODELS:
        return _call_openai_chat_completion(to_complete, _settings)
    return _call_openai_completion(to_complete, _settings)


def chatinit(prompt=None, system=None) -> list[dict[str, str]]:
    messages = []
    for msg, role in zip((system, prompt), ("system", "user")):
        if msg is not None:
            messages.append({"role": role, "content": msg})
    return messages


def getchoice(openai_response, choice_ix=0, raise_truncated: bool = True):
    if raise_truncated is True:
        fr = openai_response.choices[choice_ix].finish_reason
        if fr != "stop":
            raise IOError(f"Response did not terminate successfully: {fr}")
    choice = openai_response.choices[choice_ix]
    if hasattr(choice, "message"):
        return choice.message.content
    return choice.text


def get_usage(history: Collection[Mapping]):
    """sum tokens used in all OpenAI API events in 'history'"""
    ptok, ctok = 0, 0
    for event in history:
        if 'response' in event.keys():
            event = event['response']
        elif 'content' in event.keys():
            event = event['content']
        if not hasattr(event, 'usage'):
            continue
        ptok += event.usage.prompt_tokens
        ctok += event.usage.completion_tokens
    return {'prompt': ptok, 'completion': ctok, 'total': ptok + ctok}


def get_cost(
    model: str = DEFAULT_SETTINGS['model'],
    history: Optional[Collection[Mapping]] = None,
    usage: Optional[Mapping] = None,
):
    """
    get price of API calls. currently lazily assumes that all calls were made
    to the same model.
    """
    if not xor((usage is None), (history is None)):
        raise TypeError("must pass exactly one of usage or history.")
    price = next(
        filter(lambda kv: model.startswith(kv[0]), PRICING.items())
    )[1]
    if history is not None:
        usage = get_usage(history)
    cost = {
        # prices given in PRICING are per 1000 tokens
        'prompt': usage['prompt'] * price['prompt'] / 1000,
        'completion': usage['completion'] * price['completion'] / 1000
    }
    return cost | {'total': cost['prompt'] + cost['completion']}


class MockCompletion:
    def __init__(self, messages, **settings):
        if "model" not in settings.keys():
            raise TypeError("completion must be initialized with a model.")
        if settings["model"] not in CHAT_MODELS:
            raise NotImplementedError(
                "Mock completion only supported for chat."
            )
        self.openai_id = "chatcmpl-mock"
        self.timestamp = dt.datetime.now().isoformat()[:-3]
        self.messages = messages
        self.settings = settings
        self.rdict = {
            # TODO: other items
            "model": settings.get("model"),
            "object": "chat.completion",
            # TODO: tiktoken
            "usage": {
                "completion_tokens": 0,
                "prompt_tokens": 0,
                "total_tokens": 0,
            },
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {
                        "content": "[mock message]",
                        "role": "assistant",
                    },
                }
            ],
        }

    def __getitem__(self, key):
        return self.rdict.__getitem__(key)

    def __str__(self):
        return (
            "MockCompletion(\n" + str(self.messages) + ",\n"
            + str(self.rdict) + "\n)"
        )

    def __repr__(self):
        return self.__str__()
