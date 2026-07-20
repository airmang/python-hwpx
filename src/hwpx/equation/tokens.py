# SPDX-License-Identifier: Apache-2.0
"""EqEdit → LaTeX token maps (reader direction).

Clean-room re-derivation of the HULK-style EqEdit script vocabulary used by
Hancom's equation editor.  The mapping behaviour is independently reconstructed
from the public EqEdit grammar; no third-party source was copied, translated, or
vendored.  See NOTICE for the referenced projects (hml-equation-parser,
Apache-2.0).

The maps are deliberately plain dictionaries so coverage can grow without
touching the recursive-descent converter in :mod:`hwpx.equation.eqedit`.
"""

from __future__ import annotations

# --- Greek letters ---------------------------------------------------------
# EqEdit spells lowercase Greek in lowercase and uppercase Greek in ALLCAPS.
GREEK: dict[str, str] = {
    "alpha": r"\alpha",
    "beta": r"\beta",
    "gamma": r"\gamma",
    "delta": r"\delta",
    "epsilon": r"\epsilon",
    "varepsilon": r"\varepsilon",
    "zeta": r"\zeta",
    "eta": r"\eta",
    "theta": r"\theta",
    "vartheta": r"\vartheta",
    "iota": r"\iota",
    "kappa": r"\kappa",
    "lambda": r"\lambda",
    "mu": r"\mu",
    "nu": r"\nu",
    "xi": r"\xi",
    "omicron": r"o",
    "pi": r"\pi",
    "varpi": r"\varpi",
    "rho": r"\rho",
    "varrho": r"\varrho",
    "sigma": r"\sigma",
    "varsigma": r"\varsigma",
    "tau": r"\tau",
    "upsilon": r"\upsilon",
    "phi": r"\phi",
    "varphi": r"\varphi",
    "chi": r"\chi",
    "psi": r"\psi",
    "omega": r"\omega",
    # Uppercase (EqEdit uses ALLCAPS names).
    "GAMMA": r"\Gamma",
    "DELTA": r"\Delta",
    "THETA": r"\Theta",
    "LAMBDA": r"\Lambda",
    "XI": r"\Xi",
    "PI": r"\Pi",
    "SIGMA": r"\Sigma",
    "UPSILON": r"\Upsilon",
    "PHI": r"\Phi",
    "PSI": r"\Psi",
    "OMEGA": r"\Omega",
}

# --- Binary/relational operators (word tokens) -----------------------------
OPERATORS: dict[str, str] = {
    # ± / ∓ also arrive as the symbolic "+-"/"-+" tokens (see SYMBOL_OPERATORS).
    "pm": r"\pm",
    "mp": r"\mp",
    "times": r"\times",
    "TIMES": r"\times",
    "cdot": r"\cdot",
    "div": r"\div",
    "ast": r"\ast",
    "star": r"\star",
    "circ": r"\circ",
    "bullet": r"\bullet",
    "oplus": r"\oplus",
    "otimes": r"\otimes",
    # Relations.
    "leq": r"\leq",
    "LEQ": r"\leq",
    "geq": r"\geq",
    "GEQ": r"\geq",
    "neq": r"\neq",
    "NEQ": r"\neq",
    "equiv": r"\equiv",
    "approx": r"\approx",
    "sim": r"\sim",
    "simeq": r"\simeq",
    "cong": r"\cong",
    "propto": r"\propto",
    "prop": r"\propto",
    "ll": r"\ll",
    "gg": r"\gg",
    # Set / logic.
    "in": r"\in",
    "notin": r"\notin",
    "subset": r"\subset",
    "subseteq": r"\subseteq",
    "supset": r"\supset",
    "supseteq": r"\supseteq",
    "cup": r"\cup",
    "cap": r"\cap",
    "emptyset": r"\emptyset",
    "forall": r"\forall",
    "exists": r"\exists",
    "neg": r"\neg",
    "land": r"\land",
    "lor": r"\lor",
    # Misc symbols.
    "infty": r"\infty",
    "inf": r"\infty",
    "infinity": r"\infty",
    "partial": r"\partial",
    "nabla": r"\nabla",
    "angle": r"\angle",
    "cdots": r"\cdots",
    "ldots": r"\ldots",
    "vdots": r"\vdots",
    "ddots": r"\ddots",
    "dots": r"\cdots",
    "prime": r"\prime",
    # Arrows (word tokens).
    "rightarrow": r"\rightarrow",
    "leftarrow": r"\leftarrow",
    "leftrightarrow": r"\leftrightarrow",
    "Rightarrow": r"\Rightarrow",
    "Leftarrow": r"\Leftarrow",
    "to": r"\to",
    "mapsto": r"\mapsto",
}

# --- Multi-character symbolic operators ------------------------------------
# Longest-match wins during tokenisation (see eqedit._tokenize).
SYMBOL_OPERATORS: dict[str, str] = {
    "+-": r"\pm",
    "-+": r"\mp",
    "<=": r"\leq",
    ">=": r"\geq",
    "!=": r"\neq",
    "==": r"=",
    "->": r"\rightarrow",
    "<-": r"\leftarrow",
    "<->": r"\leftrightarrow",
    "=>": r"\Rightarrow",
    "~=": r"\approx",
}

# --- Named upright functions (no structural argument) ----------------------
FUNCTIONS: dict[str, str] = {
    "sin": r"\sin",
    "cos": r"\cos",
    "tan": r"\tan",
    "cot": r"\cot",
    "sec": r"\sec",
    "csc": r"\csc",
    "sinh": r"\sinh",
    "cosh": r"\cosh",
    "tanh": r"\tanh",
    "arcsin": r"\arcsin",
    "arccos": r"\arccos",
    "arctan": r"\arctan",
    "log": r"\log",
    "ln": r"\ln",
    "lg": r"\lg",
    "exp": r"\exp",
    "det": r"\det",
    "dim": r"\dim",
    "gcd": r"\gcd",
    "max": r"\max",
    "min": r"\min",
    "mod": r"\bmod",
}

# --- Large operators that take _/^ bounds ----------------------------------
BIG_OPERATORS: dict[str, str] = {
    "int": r"\int",
    "iint": r"\iint",
    "iiint": r"\iiint",
    "oint": r"\oint",
    "sum": r"\sum",
    "prod": r"\prod",
    "coprod": r"\coprod",
    "lim": r"\lim",
    "limsup": r"\limsup",
    "liminf": r"\liminf",
    "bigcup": r"\bigcup",
    "bigcap": r"\bigcap",
}

# --- Accents (prefix, consume one atom) ------------------------------------
ACCENTS: dict[str, str] = {
    "bar": r"\bar",
    "vec": r"\vec",
    "hat": r"\hat",
    "tilde": r"\tilde",
    "dot": r"\dot",
    "ddot": r"\ddot",
    "acute": r"\acute",
    "grave": r"\grave",
    "check": r"\check",
    "breve": r"\breve",
    "widehat": r"\widehat",
    "widetilde": r"\widetilde",
    "overline": r"\overline",
    "underline": r"\underline",
}

# --- Matrix / environment builders (consume one following group) -----------
MATRIX_ENVIRONMENTS: dict[str, str] = {
    "matrix": "matrix",
    "pmatrix": "pmatrix",
    "bmatrix": "bmatrix",
    "Bmatrix": "Bmatrix",
    "vmatrix": "vmatrix",
    "Vmatrix": "Vmatrix",
    "cases": "cases",
}

# --- Delimiters usable after LEFT / RIGHT ----------------------------------
DELIMITERS: dict[str, str] = {
    "(": "(",
    ")": ")",
    "[": "[",
    "]": "]",
    "|": "|",
    "/": "/",
    ".": ".",
    "<": r"\langle",
    ">": r"\rangle",
    "{": r"\{",
    "}": r"\}",
    "LBRACE": r"\{",
    "RBRACE": r"\}",
    "LANGLE": r"\langle",
    "RANGLE": r"\rangle",
    "lfloor": r"\lfloor",
    "rfloor": r"\rfloor",
    "lceil": r"\lceil",
    "rceil": r"\rceil",
}

# Structural keywords handled directly by the parser (not simple substitution).
STRUCTURAL = frozenset({"over", "atop", "sqrt", "root", "of", "LEFT", "RIGHT", "left", "right"})


__all__ = [
    "ACCENTS",
    "BIG_OPERATORS",
    "DELIMITERS",
    "FUNCTIONS",
    "GREEK",
    "MATRIX_ENVIRONMENTS",
    "OPERATORS",
    "STRUCTURAL",
    "SYMBOL_OPERATORS",
]
