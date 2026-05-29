"""Math utility functions."""


def factorial(n: int) -> int:
    """Return n! for non-negative integer n."""
    if n < 0:
        raise ValueError("factorial is undefined for negative numbers")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def is_prime(n: int) -> bool:
    """Return True if n is a prime number, False otherwise.

    By definition, primes are integers greater than 1.
    """
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True


def fibonacci(n: int) -> int:
    """Return the nth Fibonacci number (0-indexed).

    fibonacci(0) == 0, fibonacci(1) == 1, fibonacci(2) == 1, ...
    """
    if n < 0:
        raise ValueError("fibonacci is undefined for negative indices")
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a