"""Presentation metadata for capabilities already authorized by the caller."""
from django.templatetags.static import static


def entity_action(kind, label, *, url=None, name=None, value=None):
    if kind not in ("add", "view", "edit", "delete"):
        raise ValueError("Unsupported action icon")
    return {"icon_url": static("core/icons/" + kind + ".svg"), "label": label,
            "url": url, "name": name, "value": value}
