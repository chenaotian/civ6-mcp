"""Project visible UI content; hidden controls and callback objects never escape."""
from .policy import PolicyError, envelope, integer


def public_popup(raw: dict, expected: str) -> dict | None:
    from .actions import validate_action
    envelope(raw)
    popup = raw.get("popup")
    if type(popup) is not dict:
        raise PolicyError("invalid_response")
    # Ignore hidden content before validating anything it contains.
    if popup.get("visible") is not True:
        return None
    if popup.get("id") != expected:
        raise PolicyError("invalid_response")
    interactive = popup.get("interactive") is True
    modal = popup.get("modal") is True
    content, buttons = popup.get("content"), popup.get("buttons")
    if type(content) is not list or len(content) > 512 or type(buttons) is not list or len(buttons) > 128:
        raise PolicyError("invalid_response")
    texts = []
    for text in content:
        if type(text) is not str or len(text) > 16384 or "\x00" in text:
            raise PolicyError("invalid_response")
        texts.append(text)
    projected = []
    for button in buttons:
        if type(button) is not dict or type(button.get("enabled")) is not bool:
            raise PolicyError("invalid_response")
        index = integer(button.get("id"), 0, 4096)
        label = button.get("label")
        if type(label) is not str or len(label) > 1024 or "\x00" in label:
            raise PolicyError("invalid_response")
        supported = button.get("supported") is True
        item = {"id": index, "label": label, "enabled": button["enabled"], "supported": supported}
        if "input" in button:
            if button["input"] not in {"button", "escape"}:
                raise PolicyError("invalid_response")
            item["input"] = button["input"]
        if button["enabled"] and supported and interactive:
            try:
                item["action"] = validate_action({"type": "popup_action", "popup": expected,
                    "button_id": index, "revision": popup.get("revision")})
            except (ValueError, TypeError, KeyError):
                raise PolicyError("invalid_response") from None
        projected.append(item)
    result = {"id": expected, "visible": True, "content": texts, "buttons": projected,
              "modal": modal, "interactive": interactive}
    hint = popup.get("decision_hint")
    if type(hint) is str and len(hint) <= 2048:
        result["decision_hint"] = hint
    return result
