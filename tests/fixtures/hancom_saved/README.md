# Hancom-saved fixtures

Documents laid out and saved by Hancom's Hangul. Tests compare what python-hwpx writes, reads or estimates
with what Hangul stored in them: line layout caches (`hp:linesegarray`), table and object sizes, field and
style values.

## Saved automatically on Windows

Every file but `equation_*.hwpx` was saved automatically by Hangul's engine for Windows, not from the
Hangul window on a desktop. Such a save writes `os="2"` in `version.xml` and no `Preview/PrvImage.png`
(files saved from the desktop program carry `os="1"` and usually a preview image). `memos_in_fields.hwp`
was saved the same way.

Before a file was committed, only what names its author, the program version and the dates was removed;
every other part keeps the bytes Hangul wrote.

- `.hwpx`
  - `version.xml`: `appVersion` emptied.
  - `Contents/content.hpf`: the `creator`, `lastsaveby`, `CreatedDate`, `ModifiedDate` and `date` metas
    emptied.
  - An embedded OLE object (`BinData/*.ole`, a chart): the times of its compound file's root entry zeroed.
  - The zip repacked with its entries in the same order and compression, dated 1980-01-01 as Hangul
    dates them.
- `.hwp`
  - The summary information stream (`\x05HwpSummaryInformation`): the author, the last saver, the program
    version, the created and last saved times and the date text emptied. The last printed time is zero as
    Hangul writes it.
  - The compound file rebuilt; every other stream is as Hangul saved it.

Their document information therefore differs from that of a file saved from the desktop program, while
their content and layout caches do not.

## Equations saved on macOS

`equation_*.hwpx` were cut from documents opened and saved by Hangul for macOS (`os="10"` in
`version.xml`). Each keeps the section's first paragraph and one equation paragraph byte for byte; the
preview image was left out and the author and dates emptied (#351).

## Adding a file

A file saved from the desktop program works the same: remove the information listed above before
committing it, and say in the test what behaviour of Hangul the file shows.
