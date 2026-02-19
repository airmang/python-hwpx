from __future__ import annotations

import io
from zipfile import ZipFile

import pytest

from hwpx.tools.object_finder import AnnotationMatch, ObjectFinder
from hwpx.tools.text_extractor import AnnotationOptions, TextExtractor


@pytest.fixture()
def sample_archive() -> ZipFile:
    xml = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<hs:sec xmlns:hp='http://www.hancom.co.kr/hwpml/2011/paragraph'"
        " xmlns:hs='http://www.hancom.co.kr/hwpml/2011/section'>"
        "  <hp:p>"
        "    <hp:run>"
        "      <hp:t>Alpha<hp:markpenBegin color='#ffee00'/>Beta<hp:markpenEnd/>Gamma</hp:t>"
        "    </hp:run>"
        "  </hp:p>"
        "  <hp:p>"
        "    <hp:run>"
        "      <hp:footNote instId='42'>"
        "        <hp:subList>"
        "          <hp:p><hp:run><hp:t>Foot</hp:t></hp:run></hp:p>"
        "          <hp:p><hp:run><hp:t>Note</hp:t></hp:run></hp:p>"
        "        </hp:subList>"
        "      </hp:footNote>"
        "    </hp:run>"
        "  </hp:p>"
        "  <hp:p>"
        "    <hp:run>"
        "      <hp:endNote instId='99'>"
        "        <hp:subList>"
        "          <hp:p><hp:run><hp:t>Reference</hp:t></hp:run></hp:p>"
        "        </hp:subList>"
        "      </hp:endNote>"
        "    </hp:run>"
        "  </hp:p>"
        "  <hp:p>"
        "    <hp:run>"
        "      <hp:ctrl>"
        "        <hp:fieldBegin id='1' type='HYPERLINK'>"
        "          <hp:parameters cnt='1' name=''>"
        "            <hp:stringParam name='Command'>https://example.com|meta</hp:stringParam>"
        "          </hp:parameters>"
        "        </hp:fieldBegin>"
        "      </hp:ctrl>"
        "    </hp:run>"
        "    <hp:run><hp:t>Visit</hp:t></hp:run>"
        "    <hp:run>"
        "      <hp:ctrl><hp:fieldEnd beginIDRef='1'/></hp:ctrl>"
        "    </hp:run>"
        "  </hp:p>"
        "  <hp:p>"
        "    <hp:run>"
        "      <hp:ctrl><hp:colPr type='NEWSPAPER' colCount='2'/></hp:ctrl>"
        "    </hp:run>"
        "  </hp:p>"
        "</hs:sec>"
    )
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as builder:
        builder.writestr("Contents/section0.xml", xml)
    buffer.seek(0)
    archive = ZipFile(buffer)
    try:
        yield archive
    finally:
        archive.close()


def test_paragraph_text_annotation_rendering(sample_archive: ZipFile) -> None:
    options = AnnotationOptions(
        highlight="markers",
        footnote="inline",
        endnote="marker",
        note_inline_format="[{kind}:{text}]",
        note_marker_format="[{kind}:{inst_id}]",
        hyperlink="target",
        hyperlink_target_format="[LINK:{target}]",
        control="marker",
        control_marker_format="[CTRL {name} {type}]",
    )

    with TextExtractor(sample_archive) as extractor:
        paragraphs = list(extractor.iter_document_paragraphs(include_nested=False))

    assert paragraphs[0].text(annotations=options) == "Alpha[HIGHLIGHT color=#ffee00]Beta[/HIGHLIGHT]Gamma"
    assert paragraphs[1].text(annotations=options) == "[footnote:Foot Note]"
    assert paragraphs[2].text(annotations=options) == "[endnote:99]"
    assert paragraphs[3].text(annotations=options) == "[LINK:https://example.com]Visit"
    assert paragraphs[4].text(annotations=options) == "[CTRL colPr NEWSPAPER]"


def test_object_finder_iter_annotations(sample_archive: ZipFile) -> None:
    options = AnnotationOptions(
        highlight="markers",
        footnote="inline",
        endnote="marker",
        note_inline_format="[{kind}:{text}]",
        note_marker_format="[{kind}:{inst_id}]",
        hyperlink="target",
        hyperlink_target_format="[LINK:{target}]",
        control="marker",
        control_marker_format="[CTRL {name} {type}]",
    )

    finder = ObjectFinder(sample_archive)
    matches = list(finder.iter_annotations(options=options))

    kinds = [match.kind for match in matches]
    assert kinds == ["highlight", "footnote", "endnote", "hyperlink", "control"]

    values = [match.value for match in matches]
    assert values[0] == "[HIGHLIGHT color=#ffee00]"
    assert values[1] == "[footnote:Foot Note]"
    assert values[2] == "[endnote:99]"
    assert values[3] == "[LINK:https://example.com]"
    assert values[4] == "[CTRL colPr NEWSPAPER]"

    # Ensure the returned objects expose element metadata for further inspection.
    assert isinstance(matches[0], AnnotationMatch)
    assert matches[0].element.tag == "markpenBegin"
