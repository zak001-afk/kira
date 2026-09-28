"""
KIRA Plugin: Calculator

Provides mathematical calculation capabilities.
Supports natural language math expressions and basic arithmetic.
"""

import re
import math

PLUGIN_NAME = "Calculator"
PLUGIN_VERSION = "1.1"
PLUGIN_DESCRIPTION = "Evaluate mathematical expressions and perform calculations."
PLUGIN_AUTHOR = "KIRA"

# Managed-registry metadata: where the tool lives and how it is called.
PLUGIN_AGENT = "research"
PLUGIN_DESCRIPTIONS = {
    "calculate": "Evaluate a mathematical expression (e.g. '12*7+sqrt(2)'). "
                 "Supports + - * / % ^ **, parentheses, pi, e, sqrt, sin, "
                 "cos, tan, log, log2, log10, exp, ceil, floor, factorial, gcd.",
}
PLUGIN_ARGS = {
    "calculate": {"expression": {"type": str, "required": True}},
}


# Safe math environment
_SAFE_MATH_ENV = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": pow,
    "int": int,
    "float": float,
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "exp": math.exp,
    "ceil": math.ceil,
    "floor": math.floor,
    "factorial": math.factorial,
    "gcd": math.gcd,
}


def _safe_eval(expression: str):
    """Safely evaluate a mathematical expression."""
    # Block dangerous operations
    dangerous = ["import", "exec", "eval", "open", "__", "os.", "sys.",
                 "subprocess", "compile", "globals", "locals", "getattr"]
    if any(d in expression for d in dangerous):
        raise ValueError("Expression contains disallowed operations")

    # Normalize expression
    expr = expression.strip()
    expr = expr.replace("^", "**")  # Support ^ for exponentiation
    expr = expr.replace("×", "*").replace("÷", "/")
    expr = expr.replace("π", "pi")

    try:
        result = eval(expr, {"__builtins__": {}}, _SAFE_MATH_ENV)
        if isinstance(result, float):
            # Round to reasonable precision
            if result == int(result):
                return int(result)
            return round(result, 10)
        return result
    except Exception as e:
        raise ValueError(f"Cannot evaluate: {expression}") from e


def _is_math_expression(text: str) -> bool:
    """Check if text looks like a math expression."""
    lower = text.strip().lower()

    # "calculate X", "what is X + Y", "compute X"
    for prefix in ["calculate ", "compute ", "what is ", "what's ", "solve "]:
        if lower.startswith(prefix):
            return True

    # Pure math expression: digits, operators, parentheses
    if re.match(r'^[\d\s+\-*/().^%]+$', text.strip()):
        return True

    return False


def handle_calculate(action_data: dict) -> bool:
    """Execute a calculation."""
    expression = str(action_data.get("expression", "")).strip()
    if not expression:
        expression = str(action_data.get("target", "")).strip()

    if not expression:
        return False

    try:
        result = _safe_eval(expression)
        return True
    except ValueError:
        return False


def match_math_command(text: str) -> bool:
    """Matcher for math commands."""
    return _is_math_expression(text)


def parse_math_command(text: str) -> dict:
    """Parser for math commands."""
    lower = text.strip().lower()

    # Strip prefix
    for prefix in ["calculate ", "compute ", "what is ", "what's ", "solve "]:
        if lower.startswith(prefix):
            lower = lower[len(prefix):]
            break

    return {"action": "calculate", "expression": lower.strip()}


# ─────────────────────────────────────────────
# Plugin Registration
# ─────────────────────────────────────────────

def register(kira_plugins_module):
    """Register this plugin's actions."""
    kira_plugins_module.register_action("calculate", handle_calculate)
    kira_plugins_module.register_command_parser(match_math_command, parse_math_command)


try:
    import kira_plugins
    register(kira_plugins)
except ImportError:
    pass
