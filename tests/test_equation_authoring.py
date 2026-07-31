from __future__ import annotations

import io
import zipfile
from pathlib import Path

from hwpx import HwpxDocument
from hwpx.equation import (
    EquationConversionError,
    UnsupportedLatexError,
    eqedit_to_latex,
    estimate_equation_size,
    latex_to_eqedit,
)
from hwpx.equation.eqedit import MAX_SOURCE_LENGTH
from hwpx.tools.package_validator import validate_editor_open_safety

import pytest

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures"
GOLD_HANCOM = FIXTURES / "hwpxlib_corpus" / "reader_writer__SimpleEquation.hwpx"
GOLD_RENDERED = FIXTURES / "equation_preview" / "equation_p0.hwpx"


def _roundtrip(doc: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    doc.save_to_stream(buffer)
    buffer.seek(0)
    return HwpxDocument.open(buffer)


def _equations(doc: HwpxDocument):
    found = []
    for section in doc.sections:
        found.extend(section.element.iter(f"{HP}equation"))
    return found


def _scripts(doc: HwpxDocument) -> list[str]:
    return [
        (eq.find(f"{HP}script").text or "") for eq in _equations(doc)
    ]


class TestGoldContractShape:
    """The emitted XML must match the real-Hancom equation contract
    (specs/054-equation-authoring/evidence/p0/equation-contract.md)."""

    def test_equation_attributes(self) -> None:
        doc = HwpxDocument.new()
        doc.add_equation("{a} over {b}")
        (eq,) = _equations(doc)
        assert eq.get("version") == "Equation Version 60"
        assert eq.get("font") == "HYhwpEQ"
        assert eq.get("lineMode") == "CHAR"
        assert eq.get("numberingType") == "EQUATION"
        assert eq.get("baseUnit") == "1100"
        assert eq.get("textColor") == "#000000"
        assert eq.get("id")

    def test_children_order_and_inline_pos(self) -> None:
        doc = HwpxDocument.new()
        doc.add_equation("x ^{2}")
        (eq,) = _equations(doc)
        local_names = [child.tag.rsplit("}", 1)[-1] for child in eq]
        assert local_names == ["sz", "pos", "outMargin", "shapeComment", "script"]
        pos = eq.find(f"{HP}pos")
        assert pos.get("treatAsChar") == "1"
        sz = eq.find(f"{HP}sz")
        assert int(sz.get("width")) > 0 and int(sz.get("height")) > 0

    def test_script_stored_verbatim(self) -> None:
        script = "x = {-b +- sqrt{b^2 -4ac}} over {2a}"
        doc = HwpxDocument.new()
        doc.add_equation(script)
        assert _scripts(doc) == [script]

    def test_no_layout_cache_written(self) -> None:
        # Hancom re-lays-out on open; authored paragraphs must not carry a
        # stale linesegarray (P0 contract).
        doc = HwpxDocument.new()
        doc.add_equation("{1} over {2}")
        buffer = io.BytesIO()
        doc.save_to_stream(buffer)
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as package:
            section = package.read("Contents/section0.xml").decode("utf-8")
        equation_paragraph = section[section.find("<hp:equation") :]
        assert "linesegarray" not in equation_paragraph.split("</hp:p>")[0]

    def test_multiple_equations_get_unique_ids(self) -> None:
        doc = HwpxDocument.new()
        doc.add_equation("{a} over {b}")
        doc.add_equation("{c} over {d}")
        doc.add_equation("sqrt {e}")
        ids = [eq.get("id") for eq in _equations(doc)]
        assert len(set(ids)) == 3

    def test_explicit_size_and_base_unit(self) -> None:
        doc = HwpxDocument.new()
        doc.add_equation("{a} over {b}", base_unit=1200, size=(18100, 3010))
        (eq,) = _equations(doc)
        assert eq.get("baseUnit") == "1200"
        sz = eq.find(f"{HP}sz")
        assert (sz.get("width"), sz.get("height")) == ("18100", "3010")


class TestSelfRoundtrip:
    def test_create_save_reopen_reader_converts(self) -> None:
        script = "int _{0} ^{1} x^2 dx = {1} over {3}"
        doc = HwpxDocument.new()
        doc.add_equation(script)
        reopened = _roundtrip(doc)
        assert _scripts(reopened) == [script]
        assert eqedit_to_latex(_scripts(reopened)[0]) == (
            "\\int_{0}^{1} x^2 dx = \\frac{1}{3}"
        )

    def test_equation_in_table_cell(self) -> None:
        doc = HwpxDocument.new()
        table = doc.add_table(2, 2)
        cell_paragraph = table.cell(0, 0).paragraphs[0]
        doc.add_equation("{a} over {b}", paragraph=cell_paragraph)
        reopened = _roundtrip(doc)
        assert _scripts(reopened) == ["{a} over {b}"]
        # The equation must live inside the table cell, not a body paragraph.
        (eq,) = _equations(reopened)
        ancestors = []
        parent = eq.getparent()
        while parent is not None:
            ancestors.append(parent.tag.rsplit("}", 1)[-1])
            parent = parent.getparent()
        assert "tc" in ancestors

    def test_byte_preservation_of_unrelated_parts(self) -> None:
        doc = HwpxDocument.open(GOLD_HANCOM)
        with zipfile.ZipFile(GOLD_HANCOM) as package:
            before = {name: package.read(name) for name in package.namelist()}
        doc.add_equation("{new} over {eq}")
        buffer = io.BytesIO()
        doc.save_to_stream(buffer)
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as package:
            after = {name: package.read(name) for name in package.namelist()}
        changed = {
            name
            for name in before
            if name in after and before[name] != after[name]
        }
        assert "Contents/section0.xml" in changed
        assert changed <= {"Contents/section0.xml"}

    def test_open_safety(self) -> None:
        doc = HwpxDocument.new()
        doc.add_equation("x = {-b +- sqrt{b^2 -4ac}} over {2a}")
        buffer = io.BytesIO()
        doc.save_to_stream(buffer)
        report = validate_editor_open_safety(buffer.getvalue())
        assert report.ok, report

    def test_gold_fixture_scripts_still_read(self) -> None:
        # The authored contract and the reader consume the same gold corpus.
        for fixture in (GOLD_HANCOM, GOLD_RENDERED):
            doc = HwpxDocument.open(fixture)
            scripts = _scripts(doc)
            assert scripts
            for script in scripts:
                assert eqedit_to_latex(script)


class TestValidation:
    def test_blank_script_rejected(self) -> None:
        doc = HwpxDocument.new()
        with pytest.raises(ValueError):
            doc.add_equation("   ")

    def test_oversize_script_rejected(self) -> None:
        doc = HwpxDocument.new()
        with pytest.raises(ValueError):
            doc.add_equation("x " * (MAX_SOURCE_LENGTH // 2 + 1))

    def test_size_estimate_is_positive_and_scales(self) -> None:
        small = estimate_equation_size("x")
        large = estimate_equation_size("x = {-b +- sqrt{b^2 -4ac}} over {2a}")
        assert small[0] > 0 and small[1] > 0
        assert large[0] > small[0]


class TestLatexToEqedit:
    """Curated exact pairs — the verified token set, authoring direction."""

    @pytest.mark.parametrize(
        ("latex", "expected"),
        [
            (r"\frac{a}{b}", "{a} over {b}"),
            (r"x^2", "x ^{2}"),
            (r"x_{i}^{2}", "x _{i} ^{2}"),
            (
                r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}",
                "x = {- b +- sqrt {b ^{2} - 4 ac}} over {2 a}",
            ),
            (r"\sqrt[3]{x}", "root {3} of {x}"),
            (
                r"\int_{0}^{1} x^2 dx = \frac{1}{3}",
                "int _{0} ^{1} x ^{2} dx = {1} over {3}",
            ),
            (r"\sum_{k=1}^{n} k", "sum _{k = 1} ^{n} k"),
            (r"\alpha \leq \beta", "alpha leq beta"),
            (r"\Gamma + \pi", "GAMMA + pi"),
            (
                r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}",
                "pmatrix {a & b # c & d}",
            ),
            (
                r"\begin{cases} x & x > 0 \\ 0 & x \leq 0 \end{cases}",
                "cases {x & x > 0 # 0 & x leq 0}",
            ),
            (r"\left( \frac{a}{b} \right)", "LEFT ( {a} over {b} RIGHT )"),
            (r"\bar{x} + \vec{v}", "bar {x} + vec {v}"),
            (r"\text{판별식} = 0", '"판별식" = 0'),
            (r"T_{int}", 'T _{"int"}'),
            (r"$$\frac{1}{2}$$", "{1} over {2}"),
            (r"$x + 1$", "x + 1"),
            (r"\le \ge \ne", "leq geq neq"),
            (r"a \times b \cdot c \div d", "a times b cdot c div d"),
            (r"\lim_{x \to 0} \frac{1}{x}", "lim _{x -> 0} {1} over {x}"),
            (r"a \to b", "a -> b"),
            (r"x \rightarrow y , u \leftarrow v", "x -> y , u leftarrow v"),
            (r"s \leftrightarrow t , m \mapsto n", "s <-> t , m mapsto n"),
            (r"\forall x \exists y", "FORALL x exists y"),
            (r"\iint f + \iiint g", "dint f + tint g"),
            (
                r"\begin{vmatrix} a & b \\ c & d \end{vmatrix}",
                "dmatrix {a & b # c & d}",
            ),
            (r"A \cup B \cap C", "A cup B cap C"),
            (r"x \in \mathbb{R}"[:6], "x in"),  # prefix only; \mathbb rejected below
            (r"\infty", "infty"),
            (r"\mathrm{km}", '"km"'),
        ],
    )
    def test_exact_pairs(self, latex: str, expected: str) -> None:
        assert latex_to_eqedit(latex) == expected

    def test_reader_recovers_normalized_latex(self) -> None:
        # 정규화 동치: the reader's LaTeX for our EqEdit equals the reader's
        # LaTeX for the gold-style hand-written script of the same equation.
        ours = latex_to_eqedit(r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}")
        gold = "x = {-b +- sqrt{b^2 -4ac}} over {2a}"
        normalize = lambda s: s.replace(" ", "").replace("{", "").replace("}", "")
        assert normalize(eqedit_to_latex(ours)) == normalize(eqedit_to_latex(gold))


class TestRoundtripStability:
    """EqEdit is the canonical form: author → read → author is a fixed point."""

    CORPUS = [
        r"\frac{a}{b}",
        r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}",
        r"\sqrt[3]{x + 1}",
        r"\int_{0}^{1} x^2 dx = \frac{1}{3}",
        r"\sum_{k=1}^{n} k^2",
        r"\alpha \leq \beta \neq \Gamma",
        r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}",
        r"\begin{cases} x & x > 0 \\ 0 & x \leq 0 \end{cases}",
        r"\left( \frac{a}{b} \right)",
        r"\left[ x \right]",
        r"\bar{x} + \vec{v} + \hat{y}",
        r"\text{max} + \text{판별식}",
        r"T_{int}",
        r"\lim_{x \to 0} \frac{\sin x}{x}",
        r"a \to b \rightarrow c \leftrightarrow d",
        r"\forall x \exists y",
        r"\iint f + \iiint g",
        r"\begin{vmatrix} a & b \\ c & d \end{vmatrix}",
        r"\log_{2} x + \ln y",
        r"a \times b \pm c \mp d",
        r"\infty + \partial + \nabla",
    ]

    @pytest.mark.parametrize("latex", CORPUS)
    def test_fixed_point(self, latex: str) -> None:
        first = latex_to_eqedit(latex)
        recovered = eqedit_to_latex(first)
        second = latex_to_eqedit(recovered)
        assert first == second

    @pytest.mark.parametrize("latex", CORPUS)
    def test_authored_script_survives_document_roundtrip(self, latex: str) -> None:
        script = latex_to_eqedit(latex)
        doc = HwpxDocument.new()
        doc.add_equation(script)
        reopened = _roundtrip(doc)
        assert _scripts(reopened) == [script]


class TestLatexRejections:
    """Outside the verified set the converter must refuse, never approximate."""

    @pytest.mark.parametrize(
        "latex",
        [
            r"\overbrace{x}",
            r"\xrightarrow{f}",
            r"\mathbb{R}",
            r"\begin{align} x \end{align}",
            r"\begin{Bmatrix} a & b \\ c & d \end{Bmatrix}",
            r"\begin{Vmatrix} a & b \\ c & d \end{Vmatrix}",
            r"\widehat{xy}",
            r"\widetilde{uv}",
            r"\limsup_{n} a_n",
            r"\liminf_{n} a_n",
            r"\begin{array}{cc} a & b \end{array}",
            r"a & b",
            r"a \\ b",
            r"{x",
            r"x}",
            r"\frac{a}{b} }",
            r"x $ y",
            r"",
            r"   ",
            r"\left( x",
            r"\right)",
            r"\end{pmatrix}",
            r"\begin{pmatrix} a \end{bmatrix}",
            r"\text{a{b}}",
            "x € y",
            "\\",
        ],
    )
    def test_typed_refusal(self, latex: str) -> None:
        with pytest.raises(EquationConversionError):
            latex_to_eqedit(latex)

    def test_depth_guard(self) -> None:
        bomb = "{" * 70 + "x" + "}" * 70
        with pytest.raises(EquationConversionError):
            latex_to_eqedit(bomb)

    def test_size_guard(self) -> None:
        with pytest.raises(EquationConversionError):
            latex_to_eqedit("x + " * (MAX_SOURCE_LENGTH // 3))

    def test_refusal_names_the_command(self) -> None:
        with pytest.raises(UnsupportedLatexError, match="mathbb"):
            latex_to_eqedit(r"\mathbb{R}")
