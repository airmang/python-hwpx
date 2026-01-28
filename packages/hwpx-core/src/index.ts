/**
 * @hwpx/core - TypeScript library for reading and editing HWPX documents.
 *
 * Main entry point. Re-exports all public APIs.
 */

// High-level API
export { HwpxDocument } from "./document.js";
export { HwpxPackage } from "./package.js";
export { loadSkeletonHwpx, setSkeletonHwpx } from "./templates.js";

// XML abstraction
export {
  parseXml,
  serializeXml,
  localName,
  createElement,
  getAttributes,
  childElements,
  getTextContent,
  getTailText,
  setTextContent,
} from "./xml/dom.js";

// OXML document model
export {
  HwpxOxmlDocument,
  HwpxOxmlSection,
  HwpxOxmlHeader,
  HwpxOxmlParagraph,
  HwpxOxmlRun,
  HwpxOxmlTable,
  HwpxOxmlTableCell,
  HwpxOxmlTableRow,
  HwpxOxmlMemo,
  HwpxOxmlMemoGroup,
  HwpxOxmlSectionProperties,
  HwpxOxmlSectionHeaderFooter,
  HwpxOxmlMasterPage,
  HwpxOxmlHistory,
  HwpxOxmlVersion,
} from "./oxml/document.js";

export type {
  PageSize,
  PageMargins,
  SectionStartNumbering,
  ColumnLayout,
  DocumentNumbering,
  RunStyle,
  HwpxTableGridPosition,
} from "./oxml/document.js";

// OXML body models
export type {
  Paragraph,
  Run,
  TextSpan,
  Control,
  InlineObject,
  Table,
  Section,
  TrackChangeMark,
} from "./oxml/body.js";

// OXML header models
export type {
  Style,
  ParagraphProperty,
  Bullet,
  MemoShape,
  MemoProperties,
  TrackChange,
  TrackChangeAuthor,
  Font,
  FontFace,
  Header,
  RefList,
  CharProperty,
  BorderFillList,
} from "./oxml/header.js";

// Common types
export type { GenericElement } from "./oxml/common.js";

// Parser
export { elementToModel, parseHeaderXml, parseSectionXml } from "./oxml/parser.js";

// Tools
export { TextExtractor } from "./tools/text-extractor.js";
export { ObjectFinder } from "./tools/object-finder.js";
