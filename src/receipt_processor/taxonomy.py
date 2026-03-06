from __future__ import annotations

_FALLBACK = ("other", "unknown", "uncategorized")

_C3_TO_PATH = {
    # food > produce
    "fruit": ("food", "produce", "fruit"),
    "vegetables": ("food", "produce", "vegetables"),
    "herbs": ("food", "produce", "herbs"),
    "mushrooms": ("food", "produce", "mushrooms"),
    # food > meat_and_seafood
    "meat": ("food", "meat_and_seafood", "meat"),
    "poultry": ("food", "meat_and_seafood", "poultry"),
    "fish_and_seafood": ("food", "meat_and_seafood", "fish_and_seafood"),
    "processed_meat": ("food", "meat_and_seafood", "processed_meat"),
    # food > dairy_and_eggs
    "milk_and_cream": ("food", "dairy_and_eggs", "milk_and_cream"),
    "yogurt_and_quark": ("food", "dairy_and_eggs", "yogurt_and_quark"),
    "cheese": ("food", "dairy_and_eggs", "cheese"),
    "butter_and_spreads": ("food", "dairy_and_eggs", "butter_and_spreads"),
    "eggs": ("food", "dairy_and_eggs", "eggs"),
    # food > bakery
    "bread": ("food", "bakery", "bread"),
    "pastries": ("food", "bakery", "pastries"),
    "cakes_and_desserts": ("food", "bakery", "cakes_and_desserts"),
    # food > pantry
    "pasta_rice_grains": ("food", "pantry", "pasta_rice_grains"),
    "flour_and_baking": ("food", "pantry", "flour_and_baking"),
    "canned_and_jarred": ("food", "pantry", "canned_and_jarred"),
    "sauces_and_condiments": ("food", "pantry", "sauces_and_condiments"),
    "oils_and_fats": ("food", "pantry", "oils_and_fats"),
    "spices_and_seasonings": ("food", "pantry", "spices_and_seasonings"),
    # food > frozen
    "frozen_meals": ("food", "frozen", "frozen_meals"),
    "frozen_vegetables": ("food", "frozen", "frozen_vegetables"),
    "frozen_desserts": ("food", "frozen", "frozen_desserts"),
    # food > snacks_and_sweets
    "chips_and_salty_snacks": ("food", "snacks_and_sweets", "chips_and_salty_snacks"),
    "candy": ("food", "snacks_and_sweets", "candy"),
    "chocolate": ("food", "snacks_and_sweets", "chocolate"),
    "biscuits_and_cookies": ("food", "snacks_and_sweets", "biscuits_and_cookies"),
    # food > beverages
    "water": ("food", "beverages", "water"),
    "soft_drinks": ("food", "beverages", "soft_drinks"),
    "juice": ("food", "beverages", "juice"),
    "coffee": ("food", "beverages", "coffee"),
    "tea": ("food", "beverages", "tea"),
    "alcoholic_beverages": ("food", "beverages", "alcoholic_beverages"),
    "other_beverages": ("food", "beverages", "other_beverages"),
    # food > prepared_food
    "ready_meals": ("food", "prepared_food", "ready_meals"),
    "deli": ("food", "prepared_food", "deli"),
    "takeaway": ("food", "prepared_food", "takeaway"),
    # non_food > household
    "cleaning_supplies": ("non_food", "household", "cleaning_supplies"),
    "paper_products": ("non_food", "household", "paper_products"),
    "storage_and_wrapping": ("non_food", "household", "storage_and_wrapping"),
    # non_food > personal_care
    "soap_and_shower": ("non_food", "personal_care", "soap_and_shower"),
    "oral_care": ("non_food", "personal_care", "oral_care"),
    "hair_care": ("non_food", "personal_care", "hair_care"),
    "skin_care": ("non_food", "personal_care", "skin_care"),
    # non_food > baby
    "diapers": ("non_food", "baby", "diapers"),
    "baby_food": ("non_food", "baby", "baby_food"),
    "baby_care": ("non_food", "baby", "baby_care"),
    # non_food > pet
    "pet_food": ("non_food", "pet", "pet_food"),
    "pet_care": ("non_food", "pet", "pet_care"),
    # other > financial_adjustments
    "refunds_and_deposits": ("other", "financial_adjustments", "refunds_and_deposits"),
    "loyalty_discounts": ("other", "financial_adjustments", "loyalty_discounts"),
    "campaign_discounts": ("other", "financial_adjustments", "campaign_discounts"),
    # other > services
    "delivery_or_fees": ("other", "services", "delivery_or_fees"),
    "other_services": ("other", "services", "other_services"),
    # other > unknown
    "uncategorized": ("other", "unknown", "uncategorized"),
}

ALLOWED_C3 = sorted(_C3_TO_PATH.keys())


def normalize_category(category_l1: str, category_l2: str, category_l3: str) -> tuple[str, str, str, str]:
    _ = category_l1
    _ = category_l2
    l3 = (category_l3 or "uncategorized").strip().lower().replace(" ", "_")
    l1, l2, l3 = _C3_TO_PATH.get(l3, _FALLBACK)
    return l1, l2, l3, f"{l1} > {l2} > {l3}"
