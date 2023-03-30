import datetime as dt
import re
from typing import Union

from cytoolz import keyfilter
import openai

from openai_settings import EP_KWARGS, CHAT_MODELS, DEFAULT_SETTINGS


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
    response = openai.Completion.create(
        prompt=prompt,
        **keyfilter(lambda k: k in EP_KWARGS["completions"], _settings),
    )
    return response, prompt


def _call_openai_chat_completion(prompt, _settings):
    if (messages := _settings.get("message_context")) is None:
        messages = chatinit(prompt, _settings.get("system"))
    else:
        messages = addmsg(prompt, messages)
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


class Conversation:
    """
    implements simple UI for interactive chat completion.
    primarily intended for dev/testing.
    """
    def __init__(self, settings=DEFAULT_SETTINGS, **api_kwargs):
        if settings["model"] not in CHAT_MODELS:
            raise TypeError(
                f'{settings["model"]} does not support chat completions.'
            )
        self.settings = settings | api_kwargs
        self.messages = chatinit(system=settings["system"])
        self.history = []
        self.printreplies = True
        from rich.console import Console

        self.console = Console(width=66)

    def addmsg(self, msg):
        self.messages = addmsg(msg, self.messages)

    def addreply(self, msg):
        self.messages = addreply(msg, self.messages)

    def printon(self):
        self.printreplies = True

    def printoff(self):
        self.printreplies = False

    def undo(self):
        self.messages = self.messages[:-2]
        self.history.append(
            {'event': 'undo', 'time': dt.datetime.now().isoformat()[:-3]}
        )

    def print_transcript(self, messages: Union[None, slice, int] = None):
        if messages is not None:
            active_messages = self.messages[messages]
        else:
            active_messages = self.messages
        text = ""
        for msg in active_messages:
            text += (
                f"[bold]### {msg['role'].upper()}:"
                f"[/bold]\n{msg['content']}\n\n"
            )
        self.console.print(text)

    def say(self, message: str, **api_kwargs):
        messages = addmsg(message, self.messages)
        response, _ = complete(messages, self.settings | api_kwargs)
        status = 'ok'
        try:
            text = getchoice(response)
            term_msg = ""
        except IOError as ioe:
            status = str(ioe)
            text = getchoice(response, raise_truncated=False)
            term_msg = f"[dark_orange bold]\n\n{str(ioe)}"
        self.messages = addreply(text, messages)
        self.history.append(
            {
                'event': 'api response',
                'content': response,
                'time': dt.datetime.now().isoformat()[:-3],
                'settings': self.settings | api_kwargs,
                'status': status
            }
        )
        if self.printreplies is True:
            self.console.print(text + term_msg)


