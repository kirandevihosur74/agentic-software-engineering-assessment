import secrets
import string

ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 7


def generate_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
