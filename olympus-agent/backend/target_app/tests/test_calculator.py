import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import calculate_total

def test_regular_total():
    # Test flat calculation
    assert calculate_total(100, 0) == 100

def test_discount_application():
    # Test if discount percentage is processed correctly
    assert calculate_total(100, 10) == 90

def test_negative_values():
    # Defensive programming check
    assert calculate_total(-50, 0) == 0