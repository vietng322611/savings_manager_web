from django.http import HttpRequest

from .flash import FlashMessage

def flash_context(request: HttpRequest) -> dict[str, FlashMessage | None]:
    return {
        "flashes": request.session.pop("_flash", []),
    }