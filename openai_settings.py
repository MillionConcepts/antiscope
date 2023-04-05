from types import MappingProxyType

DEFAULT_SETTINGS = MappingProxyType(
    {
        'max_tokens': 500,
        'model': 'gpt-3.5-turbo',
        'system': 'You are an insightful and creative analysis engine.',
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

CHAT_MODELS = ('gpt-3.5-turbo', 'gpt-4')

compl_kwargs = (
    'model',
    'temperature',
    'max_tokens',
    'frequency_penalty',
    'presence_penalty',
    'top_p',
    'logprobs',
    'stop'
)

EP_KWARGS = {
    'completions': compl_kwargs,
    'chat-completions': compl_kwargs
}

# $ / 1000 tokens
PRICING = {
    'gpt-3.5-turbo':  {'prompt': 0.002, 'completion': 0.002},
    # TODO: distinguish context size
    'gpt-4': {'prompt': 0.03, 'completion': 0.06},
    'ada': {'prompt': 0.0004, 'completion': 0.0004},
    'babbage': {'prompt': 0.0005, 'completion': 0.0005},
    'curie': {'prompt': 0.002, 'completion': 0.002},
    # TODO, maybe: distinguish code etc., but they're deprecating
    'davinci': {'prompt': 0.02, 'completion': 0.02}
}
