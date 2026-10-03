import { element } from "./dom.js";

// What the model's page on Civitai says about it (model_info.civitai_details), as the model browsers and Model info show it: the counts (2.8K, 71.1K),
// the date of the latest version, the tags.
export function compact(count) {
  if (count >= 1e6) return `${(count / 1e6).toFixed(count >= 1e7 ? 0 : 1).replace(/\.0$/, "")}M`;
  if (count >= 1e3) return `${(count / 1e3).toFixed(1).replace(/\.0$/, "")}K`;
  return String(count ?? 0);
}
const STATS = [["likes", "👍", "likes"], ["downloads", "⬇", "downloads"], ["tips", "⚡", "tips (Buzz)"], ["comments", "💬", "comments"]];
// The counts as small labeled chips; the ones at 0 are left out (most models have no comments), likes and downloads always shown.
export function statsChips(stats, className = "stat") {
  if (!stats) return [];
  return STATS.filter(([key]) => stats[key] || key === "likes" || key === "downloads").map(([key, icon, label]) =>
    element("span", { class: className, title: `${(stats[key] ?? 0).toLocaleString()} ${label} on Civitai` }, `${icon} ${compact(stats[key] ?? 0)}`));
}
export function dateText(iso) {
  const date = iso ? new Date(iso) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "";
}
