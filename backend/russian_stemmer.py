"""
Russian Stemmer for BestPrice v12 Catalog Search
Lightweight stemmer for basic Russian morphology (singular/plural, case endings)
"""

import re
from typing import List, Set

# Russian vowels for stemming
VOWELS = set('аеёиоуыэюя')

# Common Russian noun/adjective endings to strip (ordered by length, longest first)
NOUN_ENDINGS = [
    # Plural endings
    'ами', 'ями', 'ов', 'ев', 'ей', 'ий',
    'ах', 'ях', 'ом', 'ем', 'ём',
    # Diminutive/special forms - ВАЖНО: 'цы' удалён чтобы "курицы" → "куриц" а не "кури"
    'ец', 'ца', 'цу', 'це', 'цов',
    # Basic endings - ВАЖНО: порядок важен для правильного стемминга
    'ы', 'и', 'а', 'я', 'у', 'ю', 'е', 'о',
]

# Adjective endings (including participle endings)
ADJ_ENDINGS = [
    # Participles (причастия) - must be first
    'ованные', 'еванные', 'анные', 'енные', 'нные',
    'ованный', 'еванный', 'анный', 'енный', 'нный',
    'ованная', 'еванная', 'анная', 'енная', 'нная',
    'ованное', 'еванное', 'анное', 'енное', 'нное',
    'ующий', 'ющий', 'ащий', 'ящий',
    'ующая', 'ющая', 'ащая', 'ящая',
    'ующее', 'ющее', 'ащее', 'ящее',
    'ующие', 'ющие', 'ащие', 'ящие',
    # Standard adjective endings
    'ого', 'его', 'ому', 'ему',
    'ым', 'им', 'ой', 'ей', 'ую', 'юю',
    'ые', 'ие', 'ая', 'яя', 'ое', 'ее',
    'ый', 'ий',
]

# Verb endings (basic)
VERB_ENDINGS = [
    'ать', 'ять', 'еть', 'ить', 'уть', 'ыть',
    'ал', 'ял', 'ел', 'ил', 'ул', 'ыл',
    'ала', 'яла', 'ела', 'ила',
    'али', 'яли', 'ели', 'или',
    'ет', 'ит', 'ут', 'ют', 'ат', 'ят',
]

# All endings combined
ALL_ENDINGS = sorted(
    set(NOUN_ENDINGS + ADJ_ENDINGS + VERB_ENDINGS),
    key=len,
    reverse=True
)

# Minimum stem length after stripping
MIN_STEM_LENGTH = 2


def russian_stem(word: str) -> str:
    """
    Simple Russian stemmer - strips common endings.
    Returns the stem of the word.
    
    Examples:
    - огурцы → огурц
    - огурец → огурец (no change, would be too short)
    - анчоусы → анчоус
    - анчоус → анчоус
    - маринованные → маринован
    - креветки → креветк
    - креветка → креветк
    """
    if not word or len(word) <= MIN_STEM_LENGTH:
        return word
    
    word = word.lower()
    
    # Try to strip endings
    for ending in ALL_ENDINGS:
        if word.endswith(ending):
            stem = word[:-len(ending)]
            # Check minimum length
            if len(stem) >= MIN_STEM_LENGTH:
                # Check that stem has at least one vowel
                if any(c in VOWELS for c in stem):
                    return stem
    
    return word


def stem_tokens(tokens: List[str]) -> List[str]:
    """
    Apply Russian stemming to a list of tokens.
    Returns list of stemmed tokens (unique, sorted).
    """
    stemmed = set()
    for token in tokens:
        stem = russian_stem(token)
        if stem:
            stemmed.add(stem)
    return sorted(list(stemmed))


# Special patterns that should NOT be stemmed
SPECIAL_PATTERNS = [
    re.compile(r'^\d+/\d+$'),  # Size/caliber like 31/40
    re.compile(r'^\d+$'),      # Pure numbers
    re.compile(r'^\d+[.,]\d+$'),  # Decimal numbers
]


def is_special_token(token: str) -> bool:
    """Check if token is a special pattern that should not be stemmed."""
    return any(p.match(token) for p in SPECIAL_PATTERNS)


def stem_token_safe(token: str) -> str:
    """
    Stem a single token, preserving special patterns.
    """
    if is_special_token(token):
        return token
    return russian_stem(token)


def generate_lemma_tokens(tokens: List[str]) -> List[str]:
    """
    Generate lemma tokens from regular tokens.
    - Applies Russian stemming
    - Preserves special patterns (numbers, calibers like 31/40)
    """
    lemmas = set()
    for token in tokens:
        lemma = stem_token_safe(token)
        if lemma:
            lemmas.add(lemma)
    return sorted(list(lemmas))


# === TESTS ===

def test_stemmer():
    """Run basic tests for the Russian stemmer."""
    test_cases = [
        # (input, expected_stem)
        ('огурцы', 'огурц'),
        ('огурец', 'огурец'),  # Too short after stripping
        ('анчоусы', 'анчоус'),
        ('анчоус', 'анчоус'),
        ('маринованные', 'маринован'),
        ('маринованный', 'маринован'),
        ('креветки', 'креветк'),
        ('креветка', 'креветк'),
        ('масло', 'масл'),
        ('масле', 'масл'),
        ('соус', 'соус'),
        ('соусы', 'соус'),
        ('филе', 'фил'),
        ('31/40', '31/40'),  # Special - preserved
        ('145гр', '145гр'),  # Mixed - not stemmed much
    ]
    
    print("Testing Russian stemmer:")
    print("-" * 50)
    
    passed = 0
    failed = 0
    
    for word, expected in test_cases:
        result = stem_token_safe(word)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"  {status} '{word}' → '{result}' (expected '{expected}')")
    
    print("-" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    
    return failed == 0


if __name__ == '__main__':
    test_stemmer()
