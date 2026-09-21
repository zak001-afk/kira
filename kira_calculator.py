"""Safe, local mental-arithmetic for KIRA.

Parses commands like:

    calculate 5 * (3 + 2)
    what is 15% of 200
    combien font vingt cinq fois deux
    كم يساوي ١٢ ضرب ٢

Expressions are evaluated through a strict AST whitelist — never ``eval`` on
raw input — so nothing but pure arithmetic can execute.
"""
from __future__ import annotations

import ast
import math
import operator
import re

MAX_EXPRESSION_LEN = 200
MAX_ABS_RESULT = 1e15

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_FUNCTIONS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
}

_CONSTANTS = {"pi": math.pi, "e": math.e}

# ── spoken-language normalization ────────────────────────────────────────────

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_NUMBER_WORDS = {
    # English
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000,
    # French
    "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "sept": 7,
    "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13,
    "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "trente": 30,
    "quarante": 40, "cinquante": 50, "soixante": 60,
    # Arabic (MSA)
    "صفر": 0, "واحد": 1, "اثنان": 2, "ثلاثة": 3, "أربعة": 4, "خمسة": 5,
    "ستة": 6, "سبعة": 7, "ثمانية": 8, "تسعة": 9, "عشرة": 10,
}

_TENS_WORDS = {
    "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty",
    "ninety", "trente", "quarante", "cinquante", "soixante",
}

_OPERATOR_PHRASES = [
    # longest first so multi-word phrases win
    ("multiplied by", "*"), ("multiplié par", "*"), ("times", "*"),
    ("fois", "*"), ("ضرب", "*"), ("في", "*"), ("عدد", "*"),
    ("divided by", "/"), ("divisé par", "/"), ("over", "/"),
    ("مقسوم على", "/"), ("تقسيم", "/"),
    ("to the power of", "**"), ("puissance", "**"), ("قوة", "**"),
    ("plus", "+"), ("زائد", "+"),
    ("minus", "-"), ("moins", "-"), ("ناقص", "-"),
    ("mod", "%"), ("modulo", "%"),
]

_TRIGGER_PREFIXES = (
    "calculate ", "compute ", "calc ", "calcule ", "calculer ", "احسب ",
)

_QUESTION_PREFIXES = (
    "what is ", "what's ", "whats ", "how much is ", "how much are ",
    "combien font ", "combien fait ", "كم يساوي ", "كم ناتج ",
)

_FILLER_WORDS = {"please", "s'il", "plait", "plaît", "من فضلك", "equals", "égal", "يساوي"}


def _combine_number_words(text: str) -> str:
    """'twenty five' -> '25', 'trente deux' -> '32' (tens + units pairs)."""
    tens = "|".join(sorted(_TENS_WORDS, key=len, reverse=True))
    units = "|".join(
        sorted(
            (w for w, v in _NUMBER_WORDS.items() if 1 <= v <= 9),
            key=len,
            reverse=True,
        )
    )

    def _repl(match: "re.Match") -> str:
        return str(_NUMBER_WORDS[match.group(1)] + _NUMBER_WORDS[match.group(2)])

    return re.sub(rf"\b({tens})\s+({units})\b", _repl, text)


def normalize_expression(text: str) -> str | None:
    """Convert a spoken arithmetic phrase into a sanitized expression string.

    Returns None when the text does not look like arithmetic at all.
    """
    value = (text or "").strip().lower()
    if not value:
        return None

    value = value.translate(_ARABIC_DIGITS)
    value = value.replace("’", "'")
    value = _combine_number_words(value)

    # "15% of 200" / "15 percent of 200" / "15 بالمئة من 200" -> 15/100*200
    value = re.sub(
        r"(\d+(?:\.\d+)?)\s*(?:%|percent|pourcents?|بالمئة|٪)\s*(?:of|de|من)\s*",
        r"\1/100*",
        value,
    )

    for phrase, symbol in _OPERATOR_PHRASES:
        value = re.sub(rf"\b{re.escape(phrase)}\b", symbol, value)

    # single number words -> digits
    def _word_repl(match: "re.Match") -> str:
        return str(_NUMBER_WORDS.get(match.group(0), match.group(0)))

    value = re.sub(r"[a-zA-ZÀ-ÿ]+|[\u0600-\u06FF]+", _word_repl, value)

    # drop filler leftovers and stray characters
    for filler in _FILLER_WORDS:
        value = value.replace(filler, " ")
    value = value.replace("?", " ").replace("!", " ").replace("=", " ")
    value = re.sub(r"\s+", " ", value).strip()

    if not value:
        return None

    if not any(ch.isdigit() for ch in value):
        return None
    if not any(op in value for op in "+-*/%"):
        return None

    # must at least parse as (whitelisted) arithmetic — further validated
    # by evaluate() before anything is executed
    value = value.replace(" ", "")
    try:
        ast.parse(value, mode="eval")
    except SyntaxError:
        return None
    return value


def try_parse(command: str) -> str | None:
    """Return a sanitized arithmetic expression for a spoken command, or None."""
    text = (command or "").strip().strip("?").lower()
    if not text:
        return None

    for prefix in _TRIGGER_PREFIXES:
        if text.startswith(prefix):
            return normalize_expression(text[len(prefix):])

    for prefix in _QUESTION_PREFIXES:
        if text.startswith(prefix):
            candidate = normalize_expression(text[len(prefix):])
            if candidate is not None:
                return candidate
            return None
    return None


# ── safe evaluation ──────────────────────────────────────────────────────────

def _validate(node: ast.AST, depth: int = 0) -> None:
    if depth > 25:
        raise ValueError("expression too deep")
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.BinOp):
            if type(child.op) not in _OPERATORS:
                raise ValueError("operator not allowed")
            if isinstance(child.op, ast.Pow):
                # guard against absurd exponent bombs like 9**9**9
                if not isinstance(child.right, ast.Constant) or not isinstance(
                    child.right.value, (int, float)
                ):
                    raise ValueError("exponent must be a number")
                if abs(child.right.value) > 999:
                    raise ValueError("exponent too large")
        elif isinstance(child, ast.UnaryOp):
            if not isinstance(child.op, (ast.UAdd, ast.USub)):
                raise ValueError("unary operator not allowed")
        elif isinstance(child, ast.Call):
            if not (
                isinstance(child.func, ast.Name) and child.func.id in _FUNCTIONS
            ):
                raise ValueError("function not allowed")
            if child.keywords:
                raise ValueError("keyword arguments not allowed")
        elif isinstance(child, ast.Name):
            if child.id not in _CONSTANTS and child.id not in _FUNCTIONS:
                raise ValueError("unknown name")
        elif isinstance(child, ast.Constant):
            if not isinstance(child.value, (int, float)):
                raise ValueError("constant not allowed")
        elif isinstance(
            child,
            (ast.Expression, ast.operator, ast.unaryop, ast.expr_context),
        ):
            pass  # operator nodes themselves (ast.Add, ast.Mult, ast.Load…)
        else:
            raise ValueError(f"node not allowed: {type(child).__name__}")
        _validate(child, depth + 1)


def evaluate(expression: str) -> float | int | None:
    """Evaluate a sanitized arithmetic expression. None on any failure."""
    expr = (expression or "").strip()
    if not expr or len(expr) > MAX_EXPRESSION_LEN:
        return None
    try:
        tree = ast.parse(expr, mode="eval")
        _validate(tree)
        code = compile(tree, "<kira-calc>", "eval")
        result = eval(  # noqa: S307 - AST-whitelisted arithmetic only
            code,
            {"__builtins__": {}},
            {**_CONSTANTS, **_FUNCTIONS},
        )
    except Exception:
        return None
    if not isinstance(result, (int, float)) or isinstance(result, bool):
        return None
    if isinstance(result, float) and (math.isinf(result) or math.isnan(result)):
        return None
    if abs(result) > MAX_ABS_RESULT:
        return result if isinstance(result, int) else float("inf")
    return result


def format_result(value: float | int) -> str:
    if isinstance(value, int):
        return str(value)
    if float(value).is_integer() and abs(value) < 1e16:
        return str(int(value))
    return f"{value:.6g}".rstrip("0").rstrip(".")


_FAILURE_REPLIES = {
    "en": "I could not compute that, sir.",
    "fr": "Je n'ai pas réussi à calculer cela, monsieur.",
    "ar": "لم أستطع حساب ذلك، سيدي.",
}

_SUCCESS_TEMPLATES = {
    "en": "{expr} equals {result}, sir.",
    "fr": "{expr} font {result}, monsieur.",
    "ar": "{expr} يساوي {result}، سيدي.",
}


def calculate_reply(expression: str, language: str = "en") -> str:
    result = evaluate(expression)
    if result is None:
        return _FAILURE_REPLIES.get(language, _FAILURE_REPLIES["en"])
    display = expression.replace("**", "^")
    template = _SUCCESS_TEMPLATES.get(language, _SUCCESS_TEMPLATES["en"])
    return template.format(expr=display, result=format_result(result))
