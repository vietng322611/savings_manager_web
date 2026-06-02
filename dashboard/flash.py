from typing import Literal, TypedDict

from django.http import HttpRequest

class FlashMessage(TypedDict):
    level: Literal["success", "error", "warning", "info"]
    text: str

def flash(
    request: HttpRequest,
    level: Literal["success", "error", "warning", "info"],
    text: str,
) -> None:
    request.session.setdefault("_flash", []).append({
        "level": level,
        "text": text,
    })

def flash_success(request: HttpRequest, text: str) -> None:
    flash(request, "success", text)

def flash_error(request: HttpRequest, text: str) -> None:
    flash(request, "error", text)