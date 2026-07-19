def calculate_total(price, tax):
    # Intentional bug: 'discount' is not defined anywhere!
    return price + tax - discount

print(calculate_total(100, 5))