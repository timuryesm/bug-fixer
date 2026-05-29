from src.string_utils import reverse_string, is_palindrome, count_vowels


def test_reverse_string():
    assert reverse_string("hello") == "olleh"
    assert reverse_string("") == ""


def test_is_palindrome_case_insensitive():
    assert is_palindrome("racecar") is True
    assert is_palindrome("Racecar") is True
    assert is_palindrome("A man a plan a canal Panama") is True
    assert is_palindrome("hello") is False


def test_count_vowels_mixed_case():
    assert count_vowels("hello") == 2
    assert count_vowels("HELLO") == 2
    assert count_vowels("AeIoU") == 5
    assert count_vowels("xyz") == 0