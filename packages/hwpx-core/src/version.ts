declare const __HWPX_CORE_VERSION__: string | undefined;

export interface VersionResolveInput {
  metadataVersion?: string | null;
  envVersion?: string | null;
  injectedVersion?: string | null;
}

function normalizeVersion(value: string | null | undefined): string | null {
  if (value == null) return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function resolveLibraryVersion(input?: VersionResolveInput): string {
  const metadataVersion = normalizeVersion(input?.metadataVersion);
  if (metadataVersion) return metadataVersion;

  const envVersion = normalizeVersion(
    input?.envVersion ??
      (typeof process !== "undefined" ? process.env.npm_package_version ?? null : null),
  );
  if (envVersion) return envVersion;

  const injectedVersion = normalizeVersion(
    input?.injectedVersion ??
      (typeof __HWPX_CORE_VERSION__ !== "undefined" ? __HWPX_CORE_VERSION__ : null),
  );
  if (injectedVersion) return injectedVersion;

  return "0+unknown";
}

export const __version__ = resolveLibraryVersion();
