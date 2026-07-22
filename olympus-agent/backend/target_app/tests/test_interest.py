import pytest
from app import calculate_interest

def test_standard_interest():
    assert calculate_interest(1000, 5, 2) == 100.0

def test_invalid_principal():
    with pytest.raises(ValueError):
        calculate_interest(-500, 5, 2)

def test_invalid_rate():
    with pytest.raises(ValueError):
        calculate_interest(1000, -2, 2)

def test_zero_time():
    with pytest.raises(ValueError):
        calculate_interest(1000, 5, 0)