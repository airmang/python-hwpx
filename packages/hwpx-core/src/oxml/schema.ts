/**
 * Schema constants for HWPX OXML namespaces.
 * Ported from Python hwpx/oxml/schema.py
 */

export const HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph";
export const HH_NS = "http://www.hancom.co.kr/hwpml/2011/head";
export const HA_NS = "http://www.hancom.co.kr/hwpml/2011/app";
export const HC_NS = "http://www.hancom.co.kr/hwpml/2011/core";
export const HMC_NS = "http://www.hancom.co.kr/hwpml/2011/masterpage";
export const HHS_NS = "http://www.hancom.co.kr/hwpml/2011/history";
export const HV_NS = "http://www.hancom.co.kr/hwpml/2011/version";

/** Namespace prefixed URI helper: `{ns}localName` format. */
export function qn(ns: string, localName: string): string {
  return `{${ns}}${localName}`;
}

/** Shortcut for paragraph namespace. */
export function hp(localName: string): string {
  return qn(HP_NS, localName);
}

/** Shortcut for head namespace. */
export function hh(localName: string): string {
  return qn(HH_NS, localName);
}
