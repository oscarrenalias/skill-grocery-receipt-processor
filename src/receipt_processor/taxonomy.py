from __future__ import annotations

_ALLOWED_L1 = {"food", "non_food", "other"}


def normalize_category(category_l1: str, category_l2: str, category_l3: str) -> tuple[str, str, str, str]:
    l1 = (category_l1 or "other").strip().lower()
    l2 = (category_l2 or "unknown").strip().lower().replace(" ", "_")
    l3 = (category_l3 or "uncategorized").strip().lower().replace(" ", "_")
    if l1 not in _ALLOWED_L1:
        l1, l2, l3 = "other", "unknown", "uncategorized"
    return l1, l2, l3, f"{l1} > {l2} > {l3}"
