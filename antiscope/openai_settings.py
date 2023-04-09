from importlib.util import spec_from_file_location, module_from_spec
import warnings
from itertools import chain
from pathlib import Path
from types import MappingProxyType


def get_secrets():
    paths = Path(__file__).parents[0:2]
    contents = chain.from_iterable(map(lambda p: p.iterdir(), paths))
    try:
        file = next(filter(lambda f: f.name == "api_secrets.py", contents))
    except (StopIteration, OSError):
        warnings.warn(
            "No api_secrets.py. Remote API-based features won't work."
        )
        return None, None
    spec = spec_from_file_location("", file)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        return mod.OPENAI_API_KEY, mod.OPENAI_ORGANIZATION
    except AttributeError:
        warnings.warn(
            "No OpenAI API info in api_secrets.py. "
            "OpenAI API features won't work."
        )


def set_up_secrets():
    api_key, organization = get_secrets()
    import openai

    openai.api_key, openai.organization = api_key, organization


DEFAULT_SETTINGS = MappingProxyType(
    {
        "max_tokens": 500,
        "model": "gpt-3.5-turbo",
        "system": "You are an insightful and creative analysis engine.",
        "temperature": 0
    }
)

CHATGPT_FORMAT = "Format your response as valid Python. "
CHATGPT_NO = "Do not write explanations. Do not provide examples. "

IEXEC_CHAT = (
    "Show me an example of what this function execution might return. "
)

REDEF_CHAT = (
    "Show me an example of what the the body of this Python function "
    "might contain. "
)

CHAT_MODELS = ("gpt-3.5-turbo", "gpt-4")

compl_kwargs = (
    "model",
    "temperature",
    "max_tokens",
    "frequency_penalty",
    "presence_penalty",
    "top_p",
    "logprobs",
    "stop",
    "logit_bias"
)

EP_KWARGS = {"completions": compl_kwargs, "chat-completions": compl_kwargs}

# $ / 1000 tokens
PRICING = {
    "gpt-3.5-turbo": {"prompt": 0.002, "completion": 0.002},
    # TODO: distinguish context size
    "gpt-4": {"prompt": 0.03, "completion": 0.06},
    "ada": {"prompt": 0.0004, "completion": 0.0004},
    "babbage": {"prompt": 0.0005, "completion": 0.0005},
    "curie": {"prompt": 0.002, "completion": 0.002},
    # TODO, maybe: distinguish code etc., but they're deprecating
    "davinci": {"prompt": 0.02, "completion": 0.02},
}
