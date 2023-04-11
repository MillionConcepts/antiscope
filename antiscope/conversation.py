import datetime as dt
import re

from antiscope.openai_settings import DEFAULT_SETTINGS, CHAT_MODELS
from antiscope.openai_utils import (
    chatinit,
    addmsg,
    addreply,
    get_usage,
    get_cost,
    complete,
    getchoice,
)
from rich.errors import MarkupError


def striptags(text):
    return re.sub(r"\[.*?]", "", text)


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
        self.messages = chatinit(system=settings.get("system"))
        self.transcript = self.messages
        self.history = []
        from rich.console import Console

        self.console = Console(width=66)

    def addmsg(self, msg):
        self.messages = addmsg(msg, self.messages)

    def addreply(self, msg):
        self.messages = addreply(msg, self.messages)

    def transcribe(self, msg, role="program"):
        self.transcript.append({"role": role, "content": msg})

    def printon(self):
        self.verbose = True

    def printoff(self):
        self.verbose = False

    def print(self, msg):
        try:
            self.console.print(msg)
        except MarkupError:
            self.console.print(
                f"[i](invalid markup stripped)[/i]\n{striptags(msg)}"
            )

    def undo(self):
        self.messages = self.messages[:-2]
        self.history.append(
            {"event": "undo", "time": dt.datetime.now().isoformat()[:-3]}
        )
        self.transcript.append(
            {"role": "program", "content": "last action undone."}
        )

    def reset(self):
        self.messages = chatinit(system=self.settings.get("system"))
        self.transcript.append(
            {"role": "program", "content": "conversation reset."}
        )

    @property
    def usage(self):
        return get_usage(self.history)

    @property
    def cost(self):
        return get_cost(self.settings["model"], self.history)

    def print_transcript(self, which="transcript"):
        to_print = self.transcript if which == "transcript" else self.messages
        text = ""
        for msg in to_print:
            text += f"[bold]### {msg['role'].upper()}:[/bold]\n"
            if msg["role"] == "program":
                text += f"[italic]{msg['content']}[/italic]\n\n"
            else:
                text += f"{msg['content']}\n\n"
        self.print(text)

    def say(self, message: str, **api_kwargs):
        messages = addmsg(message, self.messages)
        response, _ = complete(messages, self.settings | api_kwargs)
        status = "ok"
        try:
            reply = getchoice(response)
            term_msg = ""
        except IOError as ioe:
            status = str(ioe)
            reply = getchoice(response, raise_truncated=False)
            term_msg = f"[dark_orange bold]\n\n{str(ioe)}"
        self.addmsg(message)
        self.addreply(reply)
        self.history.append(
            {
                "event": "api response",
                "content": response,
                "time": dt.datetime.now().isoformat()[:-3],
                "settings": self.settings | api_kwargs,
                "status": status,
            }
        )
        self.transcript = addmsg(message, self.transcript)
        self.transcript = addreply(reply, self.transcript)
        self._maybe_print(reply + term_msg)

    def _maybe_print(self, msg):
        if self.verbose is True:
            self.print(msg)

    def gettemp(self):
        return self.settings["temperature"]

    def settemp(self, temperature):
        self.settings["temperature"] = temperature

    def gettok(self):
        return self.settings["max_tokens"]

    def settok(self, tokens):
        self.settings["max_tokens"] = tokens

    verbose = True
    temperature = property(gettemp, settemp)
    temp = property(gettemp, settemp)
    max_tokens = property(gettok, settok)
