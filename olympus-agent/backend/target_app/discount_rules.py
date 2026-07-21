def apply_percentage_discount(price, discount_percent):
    # Intentional bug to force test failure in discount_rules.py
    return price + (price * (discount_percent / 100))