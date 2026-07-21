def calculate_total(price, discount):
    return max(0, price - discount)

def main():
    price = 100
    discount = 20
    total = calculate_total(price, discount)
    print(f"Total after discount: {total}")

if __name__ == "__main__":
    main()