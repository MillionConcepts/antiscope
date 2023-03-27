from types import MappingProxyType

DEFAULT_SETTINGS = MappingProxyType(
    {
        'max_tokens': 250,
        'temperature': 0,
        'model': 'gpt-3.5-turbo',
        'system': 'You are an insightful and creative analysis engine.',
    }
)

CHATGPT_NO = (
    "Format your response as valid Python. Do not write explanations. "
    "Do not provide examples."
)

IEXEC_CHAT =(
    "Show me an example of what this function execution might return. "
)

REDEF_CHAT = (
    "Show me an example of what the body of this Python function "
    "might contain. Print only the body of the function."
)

