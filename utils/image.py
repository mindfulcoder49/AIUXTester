import base64


def to_base64_png(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("utf-8")
