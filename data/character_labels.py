def label_value(label_entry) -> str:
    if not isinstance(label_entry, dict):
        return ""
    return str(label_entry.get("label", "")).strip()


def label_category(label_entry, default="Additional") -> str:
    if not isinstance(label_entry, dict):
        return default
    return str(label_entry.get("category") or default).strip() or default


def label_values(labels) -> list[str]:
    if not isinstance(labels, list):
        return []
    values = []
    for label_entry in labels:
        value = label_value(label_entry)
        if value and value not in values:
            values.append(value)
    return values


def structured_label(category: str, label: str) -> dict[str, str] | None:
    category_value = str(category or "Additional").strip() or "Additional"
    label_text = str(label or "").strip()
    if not label_text:
        return None
    return {"category": category_value, "label": label_text}
