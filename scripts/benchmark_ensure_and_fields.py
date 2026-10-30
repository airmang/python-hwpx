# SPDX-License-Identifier: Apache-2.0
"""Privacy-free #607/#576 measurements; no downstream implementation reused.

Run separately with a public wheel interpreter or PYTHONPATH pointing at an exact
source checkout. Only probe instrumentation is monkeypatched; production code is
never modified. JSON includes raw counts and timings, not a claimed speedup.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import importlib.metadata
import json
import platform
import sys
from time import perf_counter

from lxml import etree
from hwpx import HwpxDocument
from hwpx.oxml import header_part as hp
from hwpx.oxml import _document_primitives as prim
from hwpx._document import fields as native_fields

HH = '{http://www.hancom.co.kr/hwpml/2011/head}'
HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'


@contextmanager
def candidate_counts(kind):
    count = Counter()
    if kind == 'paragraph':
        old = prim._elements_structurally_equal
        def wrapped(a, b, **kwargs):
            if a.tag == f'{HH}paraPr':
                count['candidates'] += 1
            return old(a, b, **kwargs)
        prim._elements_structurally_equal = wrapped
        try:
            yield count
        finally:
            prim._elements_structurally_equal = old
    elif kind == 'run':
        old = hp.HwpxOxmlHeader.ensure_char_property
        def wrapped(self, **kwargs):
            predicate = kwargs.get('predicate')
            if predicate:
                def counted(element):
                    count['candidates'] += 1
                    return predicate(element)
                kwargs['predicate'] = counted
            return old(self, **kwargs)
        hp.HwpxOxmlHeader.ensure_char_property = wrapped
        try:
            yield count
        finally:
            hp.HwpxOxmlHeader.ensure_char_property = old
    else:
        old = hp._border_fill_matches
        def wrapped(*args, **kwargs):
            count['candidates'] += 1
            return old(*args, **kwargs)
        hp._border_fill_matches = wrapped
        try:
            yield count
        finally:
            hp._border_fill_matches = old


def style_kwargs(kind, index):
    if kind == 'paragraph':
        return {'margins': {'left': index + 1}}
    if kind == 'run':
        return {'size': 10 + index / 100}
    return {'fill_color': f'#{index + 1:06X}'}


def styles():
    records = []
    for kind in ('paragraph', 'run', 'border'):
        for n in (10, 100, 1000):
            doc = HwpxDocument.new()
            method = getattr(doc.styles, {'paragraph': 'ensure_paragraph_format', 'run': 'ensure_run', 'border': 'ensure_border_fill'}[kind])
            started = perf_counter()
            ids = [method(**style_kwargs(kind, i)) for i in range(n)]
            setup = perf_counter() - started
            registry_tag = {'paragraph': 'paraPr', 'run': 'charPr', 'border': 'borderFill'}[kind]
            actual_records = len(list(doc.oxml.headers[0].element.iter(f'{HH}{registry_tag}')))
            header_before = etree.tostring(doc.oxml.headers[0].element)
            requests = {
                'same_early': [style_kwargs(kind, 0)] * 100,
                'same_late': [style_kwargs(kind, n - 1)] * 100,
                'different_existing': [style_kwargs(kind, i * (n - 1) // 99) for i in range(100)],
            }
            if kind in ('paragraph', 'run'):
                base_key = 'base_para_pr_id' if kind == 'paragraph' else 'base_char_pr_id'
                override = {'alignment': 'CENTER'} if kind == 'paragraph' else {'bold': True}
                pairs = [{base_key: ids[i], **override} for i in (0, n - 1)]
                for pair in pairs:
                    method(**pair)
                requests['two_bases_same_override'] = [pairs[i % 2] for i in range(100)]
            for case, operations in requests.items():
                started = perf_counter()
                results = [method(**kwargs) for kwargs in operations]
                elapsed = perf_counter() - started
                with candidate_counts(kind) as counts:
                    again = [method(**kwargs) for kwargs in operations]
                assert results == again
                assert all(result for result in results)
                records.append({'api': kind, 'requested_distinct_styles': n, 'actual_records_after_setup': actual_records, 'case': case, 'requests': len(operations),
                                'seconds': elapsed, 'us_per_request': elapsed * 1e6 / len(operations),
                                'candidate_comparisons': counts['candidates'], 'setup_seconds': setup})
                print(kind, n, case, round(elapsed, 4), counts['candidates'], file=sys.stderr, flush=True)
            if kind == 'border':
                assert header_before == etree.tostring(doc.oxml.headers[0].element)
    return records


def style_preservation():
    doc = HwpxDocument.new()
    header = doc.oxml.headers[0].element
    p = next(header.iter(f'{HH}paraPr'))
    c = next(header.iter(f'{HH}charPr'))
    for element in (p, c):
        etree.SubElement(element, '{urn:benchmark:unknown}extension', marker='preserve')
        switch = etree.SubElement(element, f'{HP}switch')
        etree.SubElement(switch, f'{HP}default').text = 'unknown-preserved'
    before = [etree.tostring(p), etree.tostring(c)]
    p_id = doc.styles.ensure_paragraph_format(base_para_pr_id=p.get('id'), alignment='center')
    assert doc.styles.ensure_paragraph_format(base_para_pr_id=p.get('id'), alignment='CENTER') == p_id
    c_id = doc.styles.ensure_run(base_char_pr_id=c.get('id'), bold=True)
    assert doc.styles.ensure_run(base_char_pr_id=c.get('id'), bold=True) == c_id
    assert before == [etree.tostring(p), etree.tostring(c)]
    expected = {}
    for tag, id_ in (('paraPr', p_id), ('charPr', c_id)):
        element = next(e for e in header.iter(f'{HH}{tag}') if e.get('id') == id_)
        assert element.find('{urn:benchmark:unknown}extension') is not None
        assert element.find(f'{HP}switch') is not None
        expected[tag] = etree.tostring(element)
    reopened = HwpxDocument.open(doc.to_bytes())
    reopened_header = reopened.oxml.headers[0].element
    for tag, id_ in (('paraPr', p_id), ('charPr', c_id)):
        element = next(e for e in reopened_header.iter(f'{HH}{tag}') if e.get('id') == id_)
        assert element.find('{urn:benchmark:unknown}extension') is not None
        assert any(default.text == 'unknown-preserved' for default in element.iter(f'{HP}default'))
    other = HwpxDocument.new()
    assert not list(other.oxml.headers[0].element.iter('{urn:benchmark:unknown}extension'))
    return {'id_reuse': True, 'alignment_normalization': True, 'bases_unchanged': True,
            'unknown_child_switch_preserved_after_reopen': True, 'documents_isolated': True,
            'cache_introduced': False}


def fields():
    records = []
    for n in (10, 100, 330, 1000):
        doc = HwpxDocument.new()
        started = perf_counter()
        for index in range(n):
            doc.fields.add(f'field-{index}', prompt='placeholder', paragraph=doc.add_paragraph(''))
        setup = perf_counter() - started
        original = native_fields._iter_form_field_matches
        builder = getattr(native_fields, '_field_matches_in', None)
        counts = Counter()
        def counted_builder(*args, **kwargs):
            matches = builder(*args, **kwargs)
            counts['field_payloads'] += len(matches)
            return matches
        def counted(document):
            matches = original(document)
            counts['full_scans'] += 1
            if builder is None:
                counts['field_payloads'] += len(matches)
            return matches
        if builder is not None:
            native_fields._field_matches_in = counted_builder
        native_fields._iter_form_field_matches = counted
        times, results = [], []
        try:
            started = perf_counter()
            for index in range(n):
                tick = perf_counter()
                result = doc.fields.fill(f'value-{index}', name=f'field-{index}')
                times.append(perf_counter() - tick)
                assert result.after == f'value-{index}'
                assert result.fit is None
                assert result.before == "placeholder"
                results.append({k: v for k, v in result.to_dict().items() if k != 'field'})
            elapsed = perf_counter() - started
        finally:
            native_fields._iter_form_field_matches = original
            if builder is not None:
                native_fields._field_matches_in = builder
        public = doc.fields.all
        assert len(public) == n
        assert [field.value for field in public] == [f'value-{i}' for i in range(n)]
        begins = list(doc.oxml.sections[0].element.iter(f'{HP}fieldBegin'))
        assert len(begins) == n and all(field.get('dirty') == '1' for field in begins)
        assert all(not list(p.iter(f'{HP}linesegarray')) for p in doc.oxml.sections[0].element.findall(f'{HP}p')
                   if p.find(f'.//{HP}fieldBegin') is not None)
        data = doc.to_bytes()
        reopened = HwpxDocument.open(data)
        assert [field.value for field in reopened.fields.all] == [f'value-{i}' for i in range(n)]
        digest = hashlib.sha256(json.dumps(results, sort_keys=True).encode()).hexdigest()
        record = {'fields': n, 'setup_seconds': setup, 'fill_seconds': elapsed,
                  'ms_per_field': elapsed * 1000 / n, 'min_field_ms': min(times) * 1000,
                  'max_field_ms': max(times) * 1000, 'full_scans': counts['full_scans'],
                  'field_payloads_built': counts['field_payloads'], 'result_digest_without_random_id': digest,
                  'roundtrip_values_equal': True, 'dirty_all_one': True, 'layout_caches_absent': True,
                  'fit_none': True, 'style_preserved_true': sum(result['stylePreserved'] for result in results),
                  'style_preserved_false': sum(not result['stylePreserved'] for result in results)}
        records.append(record)
        print('fields', n, round(elapsed, 3), counts, file=sys.stderr, flush=True)
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--mode', choices=('styles', 'fields', 'all'), default='all')
    args = parser.parse_args()
    result = {'label': args.label, 'package_version': importlib.metadata.version('python-hwpx'),
              'python': sys.version, 'platform': platform.platform(), 'machine': platform.machine(),
              'instrumentation': 'style timings uninstrumented; counts measured separately. Field scan wrapper adds one Counter increment and len per full scan.',
              'whole_conversion_measured': False, 'table_cell_lookup_measured': False}
    if args.mode in ('all', 'styles'):
        result['styles'] = styles()
        result['style_invariants'] = style_preservation()
    if args.mode in ('all', 'fields'):
        result['fields'] = fields()
    with open(args.output, 'w') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
