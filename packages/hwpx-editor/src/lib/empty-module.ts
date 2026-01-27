// Empty module stub for Node.js built-ins that aren't available in the browser.
// Used by Turbopack resolve aliases to replace fs, path, url imports.
export default {};
export const readFileSync = () => {
  throw new Error("fs.readFileSync is not available in the browser");
};
export const resolve = (...args: string[]) => args.join("/");
export const dirname = (p: string) => p.split("/").slice(0, -1).join("/");
export const fileURLToPath = (url: string) => url;
