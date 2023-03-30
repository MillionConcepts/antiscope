from types import MappingProxyType

DEFAULT_SETTINGS = MappingProxyType(
    {
        'max_tokens': 250,
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
    "Show me an example of what the body of this Python function "
    "might contain. Print only the body of the function."
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

