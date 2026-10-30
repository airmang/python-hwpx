# SPDX-License-Identifier: Apache-2.0
"""Compare the full result and every output ZIP member on identical Hancom-saved inputs.

Run each coordinate with --fixtures pointing to the same frozen fixture directory.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

from hwpx import HwpxDocument

parser = argparse.ArgumentParser()
parser.add_argument('--fixtures', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
fixtures = Path(args.fixtures)
records = []
for file, name in (
    ('form_fields_spanning_before.hwpx', '본문'),
    ('form_fields_spanning_before.hwpx', '칸'),
    ('form_fields_spanning_before.hwpx', '붙음'),
    ('form_fields_spanning_before.hwpx', '한줄'),
    ('nested_field_saved.hwpx', '바깥'),
    ('nested_field_saved.hwpx', '안쪽'),
):
    path = fixtures / file
    document = HwpxDocument.open(path.read_bytes())
    requested = name or document.fields.all[0].name
    result = document.fields.fill('first\r\nsecond\x00', name=requested)
    field = result.field
    field_snapshot = {key: getattr(field, key) for key in (
        'field_id', 'name', 'prompt', 'memo', 'editable', 'value', 'field_type', 'is_placeholder', 'has_end')}
    field_snapshot['location'] = field.location.to_dict()
    field_snapshot['parameters'] = [parameter.to_dict() for parameter in field.parameters]
    payload = document.to_bytes()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in sorted(archive.namelist())}
    records.append({'fixture': file, 'requested': requested, 'result': result.to_dict(),
                    'field': field_snapshot, 'output_members': members})
Path(args.output).write_text(json.dumps(records, ensure_ascii=False, sort_keys=True, indent=2))
