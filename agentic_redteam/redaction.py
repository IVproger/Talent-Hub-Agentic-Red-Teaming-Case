"""Credential redaction for persisted artifacts; full non-secret evidence is kept."""
import os
import re
from .llm import redact_credential_tokens


def redact_secrets(text):
    text=re.sub(r'''(?i)((?:"authorization"|'authorization'|authorization)\s*[:=]\s*)(["'])(.*?)\2''',r'\1\2[redacted]\2',text)
    text=re.sub(r'(?im)(\bauthorization\b\s*[:=]\s*)[^\r\n,;}]+',r'\1[redacted]',text)
    text=redact_credential_tokens(text)
    for name,value in os.environ.items():
        if len(value)>=4 and any(t in name.upper() for t in ('KEY','TOKEN','PASSWORD','SECRET')):
            text=text.replace(value,'[redacted]')
    return text


def redact_data(value):
    if isinstance(value,str):
        return redact_secrets(value)
    if isinstance(value,dict):
        return {k:redact_data(v) for k,v in value.items()}
    if isinstance(value,list):
        return [redact_data(v) for v in value]
    return value


def sanitize_error(exc):
    return redact_secrets(str(exc) or type(exc).__name__)[:1000]
