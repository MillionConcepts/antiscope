import re
from typing import Union

import openai
from cytoolz import keyfilter

CHAT_MODELS = ('gpt-3.5-turbo',)

EP_KWARGS = {
    'completions': ('model', 'temperature', 'max_tokens'),
    'chat-completions': ('model', 'temperature', 'max_tokens')
}


def strip_codeblock(text):
    """
    crudely strip markdown codeblock formatting
    and conventional Python terminal representation
    """
    lines = tuple(filter(None, text.split("\n")))
    if re.match("```(\w+)?", lines[0]):
        lines = lines[1:]
    if re.match(">>> .*", lines[0]):
        lines = lines[1:]
    if re.match("```", lines[-1]):
        lines = lines[:-1]
    return ("\n".join(lines))


def addreply(msg, hist):
    return hist + [{'role': 'assistant', 'content': msg}]


def addmsg(msg, hist):
    return hist + [{'role': 'user', 'content': msg}]


def _call_openai_completion(prompt, _settings):
    if isinstance(prompt, (list, tuple)):
        prompt = "\n".join(prompt)
    response = openai.Completion.create(
        prompt=prompt,
        **keyfilter(lambda k: k in EP_KWARGS['completions'], _settings)
    )
    return response, prompt


def _call_openai_chat_completion(messages, _settings):
    response = openai.ChatCompletion.create(
        messages=messages,
        **keyfilter(lambda k: k in EP_KWARGS['chat-completions'], _settings)
    )
    return response, messages


# TODO: exception handling of various types. some perhaps at higher
#  levels. i.e., "your input was too long. please try defining the
#  call in a more compact way." etc.
def complete(to_complete: Union[list[dict], str], _settings):
    if _settings['model'] in CHAT_MODELS:
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
        fr = openai_response['choices'][choice_ix]['finish_reason']
        if fr != 'stop':
            raise IOError(f"Response did not terminate successfully: {fr}")
    choice = openai_response['choices'][choice_ix]
    if 'message' in choice:
        return choice['message']['content']
    return choice['text']
