# Experimental preview scenes

`hwpx.layout.body_scene` and `hwpx.layout.object_scene` produce an experimental,
cache-independent page scene from HWPX bytes. A caller supplies glyph metrics;
core does not discover fonts, rasterize images, start workers or load an office
application. No native rendering dependency is added to the default install.

`build_body_scene(data, provider)` handles the bounded body slice.
`build_document_scene(data, provider)` also handles supported tables, pictures
and page stories. `BodySceneSession(provider)` can reuse owned paragraph
measurements across edits; returned scenes are detached from its cache.

The provider implements `shape(text, attributes, style)` and `manifest()`.
Page-number stories additionally use `font_metrics(family, height)`, and pictures
use `inspect_picture(raw_bytes)`. Font metrics and picture decoding belong to the
application layer. Missing fonts and unsupported controls must produce an
unsupported result with no partial pages. Requested font substitutions remain an
explicit application decision.

Coordinates use HWPUNIT. The returned dictionary includes `status`, `pages`,
`unsupported`, `errors`, source/layout hashes and `qualityValidated=False`.
Saved line-segment arrays and cell sub-list measurements are excluded before
measurement. The `ignore`, `remove` and `poison` cache modes support metamorphic
testing; none authorizes using source layout caches as measurements.

This is a versioned experimental scene format, not a fidelity guarantee or a
replacement for an independent office-rendering oracle. Unsupported layout
policies fail closed. The existing HTML preview and save-gate APIs are unchanged.
