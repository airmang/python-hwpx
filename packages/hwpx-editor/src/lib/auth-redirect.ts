export function redirectToLoginFromEditor(): boolean {
  if (typeof window === "undefined") return false;

  const { pathname, search } = window.location;
  const normalizedPath = pathname.replace(/\/+$/, "");
  const isEditorRoute =
    normalizedPath === "/editor" || normalizedPath.endsWith("/editor");
  if (!isEditorRoute) return false;

  const callbackUrl = encodeURIComponent(`${pathname}${search}`);
  window.location.assign(`/login?callbackUrl=${callbackUrl}`);
  return true;
}
