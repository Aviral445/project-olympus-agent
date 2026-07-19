def calculate_total(price, tax, discount=0):
    return price + tax - discount

print(calculate_total(100, 5))