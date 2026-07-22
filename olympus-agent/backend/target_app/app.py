def calculate_interest(principal: float, rate: float, time_years: float) -> float:
    if principal < 0 or rate < 0 or time_years <= 0:
        raise ValueError("Invalid input values")
    return principal * (rate / 100) * time_years

def calculate_total(price: float, discount_percent: float = 0) -> float:
    if price < 0:
        return 0
    discount_amount = price * (discount_percent / 100)
    return price - discount_amount

def main():
    price = 100
    discount = 20
    total = calculate_total(price, discount)
    print(f"Total after discount: {total}")

if __name__ == "__main__":
    main()