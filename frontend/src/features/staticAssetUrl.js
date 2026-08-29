export const GLB_ASSET_CACHE_REVISION = "2026-08-24-1";

export function withAssetCacheRevision(url, revision = GLB_ASSET_CACHE_REVISION) {
  if (!url || !revision) return url;
  const fragmentIndex = url.indexOf("#");
  const resourceUrl = fragmentIndex === -1 ? url : url.slice(0, fragmentIndex);
  const fragment = fragmentIndex === -1 ? "" : url.slice(fragmentIndex);
  const separator = resourceUrl.includes("?") ? "&" : "?";
  return `${resourceUrl}${separator}asset-revision=${encodeURIComponent(revision)}${fragment}`;
}
