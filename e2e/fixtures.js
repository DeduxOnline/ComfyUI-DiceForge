// The files the end-to-end tests run with (server.js makes them in the temporary ComfyUI folder; the tests read what to expect from here).
const crypto = require("crypto");
const zlib = require("zlib");
const { CIVITAI_PORT } = require("./settings");

// A small PNG of one color, without an image library.
function png(width, height, [r, g, b]) {
  const crcTable = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc = (buffer) => { let c = 0xffffffff; for (const byte of buffer) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const chunk = (type, data) => {
    const length = Buffer.alloc(4); length.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(type), data]);
    const sum = Buffer.alloc(4); sum.writeUInt32BE(crc(body));
    return Buffer.concat([length, body, sum]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0); header.writeUInt32BE(height, 4); header[8] = 8; header[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: width }, () => [r, g, b]).flat())]);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk("IHDR", header),
    chunk("IDAT", zlib.deflateSync(Buffer.concat(Array(height).fill(row)))), chunk("IEND", Buffer.alloc(0))]);
}

// The test files. Model files are small stand-ins (never loaded as models): their content decides the sha256 the Civitai stand-in knows.
const MODELS = {
  "loras/style/ink.safetensors": { content: "ink lora", civitai: { model: "Ink", version: "v2", base: "Illustrious", words: ["ink style", "lineart"] } },
  "loras/style/pony_glow.safetensors": { content: "pony lora", civitai: { model: "Glow", version: "v1", base: "Pony", words: ["glow"] } },
  "loras/style/flux_film.safetensors": { content: "flux lora", civitai: { model: "Film", version: "v1", base: "Flux.1 D", words: ["film"] } },
  "loras/detail.safetensors": { content: "detail lora" },
  "checkpoints/illustrious_base.safetensors": { content: "checkpoint", civitai: { model: "Base", version: "v1", base: "Illustrious", words: [] } },
  "checkpoints/sdxl/other.safetensors": { content: "other checkpoint" },
  "diffusion_models/flux1-dev.safetensors": { content: "diffusion model" },
  "text_encoders/clip_l.safetensors": { content: "clip l" },
  "text_encoders/t5xxl_fp16.safetensors": { content: "t5xxl" },
};
const WILDCARDS = {
  "color.txt": "# colors\nred\nblue\ngreen\nwhite\n",
  "hair/style.txt": "bob cut\nlong hair\n",
  "hair/color.txt": "blonde hair\n",
  "цвет.txt": "красный\nсиний\n", // A name in another script: the autocomplete and the node must both know it.
  "weighted.txt": "9::common\n1::rare\n0::never\n",
  "outfit/male.txt": "suit\ntuxedo\n",
  "outfit/female.txt": "dress\nskirt\n",
  "pack.yaml": "characters:\n  alice:\n    outfit: [blue dress, white apron]\n  bob:\n    outfit: [jeans]\n",
};
const sha256 = (text) => crypto.createHash("sha256").update(text).digest("hex");
const CIVITAI = Object.fromEntries(Object.values(MODELS).filter((model) => model.civitai).map(({ content, civitai }, index) => [sha256(content), {
  id: 100 + index, modelId: 10 + index, name: civitai.version, baseModel: civitai.base, trainedWords: civitai.words,
  model: { name: civitai.model, type: "LORA" },
  images: [{ url: `http://127.0.0.1:${CIVITAI_PORT}/image/original=true/${index}.png`, type: "image", nsfwLevel: 1, width: 8, height: 8 }],
}]));


module.exports = { MODELS, WILDCARDS, CIVITAI, png, sha256 };
