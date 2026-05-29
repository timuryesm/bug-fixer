from src.math_utils import factorial, is_prime, fibonacci


def test_factorial_basic():
    assert factorial(0) == 1
    assert factorial(1) == 1
    assert factorial(5) == 120


def test_is_prime_small_numbers():
    assert is_prime(0) is False
    assert is_prime(1) is False
    assert is_prime(2) is True
    assert is_prime(3) is True
    assert is_prime(4) is False


def test_is_prime_larger():
    assert is_prime(17) is True
    assert is_prime(25) is False


def test_fibonacci_sequence():
    assert fibonacci(0) == 0
    assert fibonacci(1) == 1
    assert fibonacci(2) == 1
    assert fibonacci(3) == 2
    assert fibonacci(7) == 13