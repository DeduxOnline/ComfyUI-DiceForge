import { app } from "../../scripts/app.js";
import { addStyleOnce, element } from "./dom.js";

// The pictures and videos of the model browsers, the Civitai search and Model info. Civitai's R-rated and stronger images (nsfwLevel 4 and up) are
// blurred until clicked, unless "Blur NSFW" is off (a switch in the browsers, and ComfyUI's settings: DiceForge → Browsers). Videos don't play by
// themselves: ▶ on one plays it (muted, looping), a second click pauses it.
const SETTING = "DiceForge.BlurNSFW";
const STYLE = `
.dfvid{position:relative;display:flex;align-items:center;justify-content:center;width:100%;height:100%}
.dfvid .play{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:46px;height:46px;border-radius:50%;border:2px solid #fffc;background:#000a;
  color:#fff;font-size:18px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0 0 0 3px;z-index:1}
.dfvid .play:hover{background:#000d}.dfvid.playing .play{opacity:0}.dfvid.playing:hover .play{opacity:1;padding:0}
.dfblur-switch{display:flex;align-items:center;gap:4px;white-space:nowrap;cursor:pointer;user-select:none}
`;

export const blurOn = () => app.extensionManager?.setting?.get?.(SETTING) !== false;
// Blurred: Civitai's R and up, with Blur NSFW on.
export const shouldBlur = (image) => blurOn() && (image?.nsfwLevel ?? 1) >= 4;
const listeners = new Set();
async function setBlur(on) {
  await app.extensionManager?.setting?.set?.(SETTING, on);
  for (const listener of listeners) listener(on);
}

// A video that waits for ▶. Returns the wrapper (to place) and the video (for the caller's own classes and events).
export function videoPreview(src) {
  addStyleOnce("dfmedia-style", STYLE);
  const video = element("video", { src, loop: "", playsinline: "", preload: "metadata" });
  video.muted = true;
  const play = element("button", { class: "play", title: "Play the video" }, "▶");
  const wrapper = element("div", { class: "dfvid" }, video, play);
  play.addEventListener("click", (event) => {
    event.stopPropagation(); // Not a click on the card or the picture.
    video.classList.remove("blur"); // Played: seen.
    if (video.paused) video.play().catch(() => {});
    else video.pause();
  });
  video.addEventListener("play", () => { wrapper.classList.add("playing"); play.textContent = "❚❚"; play.title = "Pause"; });
  video.addEventListener("pause", () => { wrapper.classList.remove("playing"); play.textContent = "▶"; play.title = "Play the video"; });
  return { wrapper, video };
}
// A picture (or a video waiting for ▶) of a Civitai image, blurred by the setting, with a click on the blur revealing it. Returns { wrapper, media }.
export function civitaiMedia(src, image, { video = image?.type === "video" } = {}) {
  const made = video ? videoPreview(src) : (() => { const img = element("img", { src, loading: "lazy" }); return { wrapper: img, video: img }; })();
  const media = made.video;
  if (shouldBlur(image)) {
    media.classList.add("blur");
    media.addEventListener("click", (event) => {
      if (!media.classList.contains("blur")) return;
      event.stopPropagation(); // The first click only reveals.
      media.classList.remove("blur");
    });
  }
  return { wrapper: made.wrapper, media };
}
// The "Blur NSFW" switch for a browser's toolbar; onChange redraws the browser's pictures.
export function blurSwitch(onChange) {
  addStyleOnce("dfmedia-style", STYLE);
  const box = element("input", { type: "checkbox" });
  box.checked = blurOn();
  const listener = (on) => { box.checked = on; onChange(on); };
  listeners.add(listener);
  box.addEventListener("change", () => { setBlur(box.checked).catch(() => {}); });
  const label = element("label", { class: "dfblur-switch", title: "Blur the previews Civitai rates R and up, until clicked (also in ComfyUI's settings: DiceForge → Browsers)" }, box, "Blur NSFW");
  label.dispose = () => listeners.delete(listener); // Called when the browser closes.
  return label;
}

app.registerExtension({
  name: "DiceForge.Media",
  settings: [{
    id: SETTING,
    category: ["DiceForge", "Browsers", "Blur"],
    name: "Blur NSFW previews in the model browsers, the Civitai search and Model info",
    tooltip: "Previews Civitai rates R and up are blurred until clicked. Off: shown as they are.",
    type: "boolean",
    defaultValue: true,
  }],
});
