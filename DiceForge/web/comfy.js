// Talking to ComfyUI: the answer of a DiceForge route, and a message in ComfyUI's corner.
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// A route's JSON answer; when it refuses, its text is the error.
export async function request(path, options) {
  const response = await api.fetchApi(path, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

// A toast (every frontend DiceForge works with has them: e2e/contract.spec.js checks it).
export function toast(severity, summary, detail) {
  app.extensionManager.toast.add({ severity, summary, detail, life: 5000 });
}
