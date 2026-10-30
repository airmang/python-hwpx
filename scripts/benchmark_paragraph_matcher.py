# SPDX-License-Identifier: Apache-2.0
"""Five-repeat uninstrumented timings plus separate actual comparison counts."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter
import zipfile

from collections import Counter
from contextlib import contextmanager

from hwpx import HwpxDocument
from hwpx.oxml import _document_primitives as primitives


@contextmanager
def candidate_counts():
    counts = Counter()
    if hasattr(primitives, '_compile_element_matcher'):
        original = primitives._compile_element_matcher
        def prepare(target, **kwargs):
            counts['pattern_nodes_prepared'] += 1
            matcher = original(target, **kwargs)
            if target.tag != '{http://www.hancom.co.kr/hwpml/2011/head}paraPr':
                return matcher
            counts['pattern_compilations'] += 1
            def match(candidate):
                counts['candidates'] += 1
                return matcher(candidate)
            return match
        primitives._compile_element_matcher = prepare
        try:
            yield counts
        finally:
            primitives._compile_element_matcher = original
    else:
        original = primitives._elements_structurally_equal
        def compare(candidate, target, **kwargs):
            if candidate.tag == '{http://www.hancom.co.kr/hwpml/2011/head}paraPr':
                counts['candidates'] += 1
            return original(candidate, target, **kwargs)
        primitives._elements_structurally_equal = compare
        try:
            yield counts
        finally:
            primitives._elements_structurally_equal = original


parser = argparse.ArgumentParser()
parser.add_argument('--label', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--fixtures', required=True)
args = parser.parse_args()
records = []
for n in (10, 100, 1000):
    doc = HwpxDocument.new()
    ids = [doc.styles.ensure_paragraph_format(margins={'left': index + 1}) for index in range(n)]
    source = doc.to_bytes()
    cases = {
        'same_late': [{'margins': {'left': n}}] * 100,
        'distinct_existing': [{'margins': {'left': 1 + index * (n - 1) // 99}} for index in range(100)],
        'new_distinct': [{'margins': {'left': 10000 + index}} for index in range(100)],
        'two_bases_override': [{'base_para_pr_id': ids[(n - 1) * (index % 2)], 'alignment': 'CENTER'} for index in range(100)],
    }
    for name, requests in cases.items():
        times, checksums = [], []
        for repeat in range(5):
            document = HwpxDocument.open(source)
            if name == 'two_bases_override':
                for request in requests[:2]:
                    document.styles.ensure_paragraph_format(**request)
            started = perf_counter()
            returned = [document.styles.ensure_paragraph_format(**request) for request in requests]
            times.append(perf_counter() - started)
            checksums.append(hashlib.sha256(json.dumps(returned).encode()).hexdigest())
        assert len(set(checksums)) == 1
        document = HwpxDocument.open(source)
        if name == 'two_bases_override':
            for request in requests[:2]:
                document.styles.ensure_paragraph_format(**request)
        with candidate_counts() as counts:
            returned = [document.styles.ensure_paragraph_format(**request) for request in requests]
        assert hashlib.sha256(json.dumps(returned).encode()).hexdigest() == checksums[0]
        records.append({'requested_shapes': n, 'case': name, 'requests': len(requests),
                        'seconds': times, 'median_seconds': median(times), 'counts': dict(counts),
                        'returned_ids_sha256': checksums[0]})
        print(n, name, [round(value, 4) for value in times], 'median', round(median(times), 4), dict(counts), flush=True)

# A real public corpus input, independently authored and kept byte-identical between both coordinates.
fixture = Path(args.fixtures) / 'hwpxlib_corpus' / 'error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx'
source = fixture.read_bytes()
document = HwpxDocument.open(source)
document.styles.apply_paragraph_format(paragraph_index=5, alignment='CENTER')
payload = document.to_bytes()
with zipfile.ZipFile(io.BytesIO(payload)) as archive:
    members = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in sorted(archive.namelist())}
external = {'source_sha256': hashlib.sha256(source).hexdigest(), 'output_members': members,
            'paragraph_style_ids': [paragraph.para_pr_id_ref for paragraph in document.paragraphs]}
Path(args.output).write_text(json.dumps({'label': args.label, 'python': sys.version, 'platform': platform.platform(),
    'matrix': records, 'external': external}, ensure_ascii=False, indent=2))
