"""String utility functions."""


def reverse_string(s: str) -> str:
    """Return the reverse of the input string."""
    return s[::-1]


def is_palindrome(s: str) -> bool:
    """Return True if s reads the same forwards and backwards.

    Comparison is case-insensitive and ignores spaces.
    """
    cleaned = s.replace(" ", "").lower()  # Lowercase for case-insensitivity
    return cleaned == cleaned[::-1]


def count_vowels(s: str) -> int:
    """Return the number of vowels (a, e, i, o, u) in s.

    Counts both uppercase and lowercase vowels.
    """
    vowels = "aeiouAEIOU"  # Include uppercase vowels
    return sum(1 for c in s if c in vowels)