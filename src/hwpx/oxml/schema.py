from __future__ import annotations

import logging
from pathlib import Path
from typing import Union
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

from lxml import etree


SchemaPath = Union[str, Path]


class _LocalSchemaResolver(etree.Resolver):
    """Resolver that maps relative schema imports to local filesystem paths."""

    def __init__(self, base_dir: Path) -> None:
        super().__init__()
        self._base_dir = base_dir

    def resolve(self, system_url: str, public_id: str, context: object):
        parsed = urlparse(system_url)

        if parsed.scheme in {"", "file"}:
            if parsed.scheme == "file":
                target = Path(unquote(parsed.path))
            else:
                target = self._base_dir / system_url

            if target.exists():
                return self.resolve_filename(str(target), context)
        return None


def load_schema(path: SchemaPath) -> etree.XMLSchema:
    """Load an XML schema from *path* using :mod:`lxml`."""

    schema_path = Path(path)
    parser = etree.XMLParser()
    parser.resolvers.add(_LocalSchemaResolver(schema_path.parent))
    document = etree.parse(str(schema_path), parser)
    return etree.XMLSchema(document)
