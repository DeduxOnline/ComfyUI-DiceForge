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
  "diffusion_models/flux/flux1-schnell.safetensors": { content: "schnell diffusion model" },
  "text_encoders/clip_l.safetensors": { content: "clip l" },
  "text_encoders/t5xxl_fp16.safetensors": { content: "t5xxl" },
  "vae/sdxl_vae.safetensors": { content: "sdxl vae" },
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
  images: [ // How the first image was made (Civitai's meta, shown over it in Model info); the second has none.
    { url: `http://127.0.0.1:${CIVITAI_PORT}/image/original=true/${700 + index}.png`, type: "image", nsfwLevel: 1, width: 8, height: 8, hasMeta: true,
      meta: { prompt: `${civitai.model} test prompt, 1girl`, negativePrompt: "lowres", seed: 3032258275, steps: 30, cfgScale: 4, sampler: "Euler a", Model: "e2e_base", hashes: { model: "x" } } },
    { url: `http://127.0.0.1:${CIVITAI_PORT}/image/original=true/${800 + index}.png`, type: "image", nsfwLevel: 1, width: 8, height: 8, hasMeta: false },
  ],
}]));

// LoRAs to find on Civitai (the Create of the LoRA Browser): Neon has two versions, the files the stand-in serves for download; Ink is the test
// LoRA style/ink.safetensors, already here (found by its hash).
const host = `http://127.0.0.1:${CIVITAI_PORT}`;
const DOWNLOADS = { 501: "neon lora v2", 502: "neon lora v1", 601: "studio checkpoint", 199: "ink lora v3" };
const civitaiVersion = (id, name, file, content, base, model = { name: "Neon", type: "LORA" }) => ({
  id, modelId: model.type === "LORA" ? 50 : 60, name, baseModel: base, trainedWords: model.type === "LORA" ? ["neon glow"] : [], availability: "Public", model,
  files: [{ id, name: file, sizeKB: content.length / 1024, primary: true, type: "Model", hashes: { SHA256: sha256(content).toUpperCase() }, downloadUrl: `${host}/download/${id}` }],
  images: [{ url: `${host}/image/original=true/neon.png`, type: "image", nsfwLevel: 1, width: 8, height: 8 }],
});
const CIVITAI_VERSIONS = {
  501: civitaiVersion(501, "v2", "neon_glow.safetensors", DOWNLOADS[501], "Illustrious"),
  502: civitaiVersion(502, "v1", "neon_glow_v1.safetensors", DOWNLOADS[502], "SDXL 1.0"),
  601: civitaiVersion(601, "v1", "studio_xl.safetensors", DOWNLOADS[601], "SDXL 1.0", { name: "Studio XL", type: "Checkpoint" }),
  199: civitaiVersion(199, "v3", "ink_v3.safetensors", DOWNLOADS[199], "Illustrious", { name: "Ink", type: "LORA" }), // Ink's newer version (its page names it).
};
const ink = Object.entries(CIVITAI).find(([, version]) => version.model.name === "Ink");
const CIVITAI_MODELS = [
  { id: 50, name: "Neon", type: "LORA", nsfw: false, creator: { username: "e2e" }, tags: ["style", "neon"], stats: { downloadCount: 1234, thumbsUpCount: 56 }, modelVersions: [CIVITAI_VERSIONS[501], CIVITAI_VERSIONS[502]] },
  { id: ink[1].modelId, name: "Ink", type: "LORA", nsfw: false, creator: { username: "e2e" }, stats: { downloadCount: 7, thumbsUpCount: 1 },
    modelVersions: [{ ...ink[1], files: [{ id: 9, name: "ink.safetensors", sizeKB: 1, primary: true, type: "Model", hashes: { SHA256: ink[0] }, downloadUrl: `${host}/download/9` }] }] },
  { id: 60, name: "Studio XL", type: "Checkpoint", nsfw: false, creator: { username: "e2e" }, stats: { downloadCount: 99, thumbsUpCount: 9 }, modelVersions: [CIVITAI_VERSIONS[601]] },
];

// The model pages (GET /api/v1/models/<id>): tags, counts, creator and versions, newest first. Ink has a newer version (v3) than the test file's
// (v2); Glow has only its own; Film and Base have no page (the lookup keeps the version all the same).
const glow = Object.values(CIVITAI).find((version) => version.model.name === "Glow");
const CIVITAI_PAGES = {
  [ink[1].modelId]: { id: ink[1].modelId, name: "Ink", type: "LORA", tags: ["anime", "ink", "lineart"], creator: { username: "inkmaker" },
    stats: { downloadCount: 71087, thumbsUpCount: 2770, thumbsDownCount: 2, commentCount: 0, tippedAmountCount: 920 },
    modelVersions: [{ id: 199, name: "v3", baseModel: "Illustrious", publishedAt: "2026-05-26T18:39:52.929Z", stats: { downloadCount: 52275 } },
      { id: ink[1].id, name: "v2", baseModel: "Illustrious", publishedAt: "2026-04-20T22:36:19.392Z", stats: { downloadCount: 18812 } }] },
  [glow.modelId]: { id: glow.modelId, name: "Glow", type: "LORA", tags: ["pony", "style"], creator: { username: "glower" },
    stats: { downloadCount: 900, thumbsUpCount: 40, commentCount: 3, tippedAmountCount: 0 },
    modelVersions: [{ id: glow.id, name: "v1", baseModel: "Pony", publishedAt: "2026-01-02T10:00:00.000Z", stats: { downloadCount: 900 } }] },
};
for (const model of CIVITAI_MODELS) CIVITAI_PAGES[model.id] ??= model; // The models of the search have a page too (for downloads).

// The Danbooru tag list the stand-in serves for the tag autocomplete (tagcomplete's format: tag,type,count,aliases).
const TAGS = 'long_hair,0,5000000,"longhair"\nlong_sleeves,0,1500000,\nhatsune_miku,4,90000,miku\nsmile,0,4000000,\n1girl,0,6000000,\n';

// Danbooru posts the stand-in answers random-post searches with (/posts/random.json) and by id (/posts/<id>.json), for the Danbooru Tag Enhancer.
const DANBOORU_POSTS = [
  { id: 101, rating: "g", score: 50, preview_file_url: `http://127.0.0.1:${CIVITAI_PORT}/image/danbooru/101.png`, tag_string_general: "1girl smile twintails", tag_string_character: "hatsune_miku", tag_string_copyright: "vocaloid", tag_string_artist: "e2e", tag_string_meta: "highres" },
  { id: 102, rating: "e", score: 40, preview_file_url: `http://127.0.0.1:${CIVITAI_PORT}/image/danbooru/102.png`, tag_string_general: "1girl nude", tag_string_character: "hatsune_miku", tag_string_copyright: "vocaloid", tag_string_artist: "e2e", tag_string_meta: "" },
  // A post whose picture doesn't load (the node shows a link instead). Never found by a search for hatsune_miku: 101 comes first.
  { id: 103, rating: "g", score: 30, preview_file_url: "http://127.0.0.1:9/broken.png", tag_string_general: "1girl smile", tag_string_character: "hatsune_miku",
    tag_string_copyright: "vocaloid", tag_string_artist: "e2e", tag_string_meta: "" },
];

// e621 posts the stand-in answers searches (/posts.json, order:random) and ids (/posts/<id>.json) with.
const E621_POSTS = [
  { id: 201, rating: "s", score: { total: 10 }, preview: { url: `http://127.0.0.1:${CIVITAI_PORT}/image/e621/201.png` },
    tags: { general: ["solo", "anthro", "grin"], species: ["fox", "canine"], character: [], copyright: [], artist: ["e2e"], meta: ["hi_res"] } },
  { id: 202, rating: "e", score: { total: 5 }, preview: { url: null },
    tags: { general: ["duo", "anthro", "nude"], species: ["fox"], character: [], copyright: [], artist: ["e2e"], meta: [] } },
];

// Safebooru posts the stand-in answers its API with (index.php?page=dapi: the count of a search in XML, a post at a place, or by id).
const SAFEBOORU_POSTS = [
  { id: 301, rating: "safe", score: 7, directory: "301", image: "picture.png", hash: "picture", tags: "1girl hatsune_miku smile twintails" },
];

// A zip of the given files (name: text or Buffer), stored without compression: enough for the tests' card packs.
function zip(files) {
  const zlib = require("zlib");
  const locals = [], centrals = [];
  let offset = 0;
  for (const [name, content] of Object.entries(files)) {
    const data = Buffer.isBuffer(content) ? content : Buffer.from(content), path = Buffer.from(name), crc = zlib.crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt32LE(crc, 14); local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22); local.writeUInt16LE(path.length, 26);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0); central.writeUInt16LE(20, 4); central.writeUInt16LE(20, 6); central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(data.length, 20); central.writeUInt32LE(data.length, 24); central.writeUInt16LE(path.length, 28); central.writeUInt32LE(offset, 42);
    locals.push(local, path, data);
    centrals.push(central, path);
    offset += 30 + path.length + data.length;
  }
  const directory = Buffer.concat(centrals), end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(Object.keys(files).length, 8); end.writeUInt16LE(Object.keys(files).length, 10);
  end.writeUInt32LE(directory.length, 12); end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, directory, end]);
}

module.exports = { MODELS, WILDCARDS, CIVITAI, CIVITAI_MODELS, CIVITAI_VERSIONS, CIVITAI_PAGES, DOWNLOADS, TAGS, DANBOORU_POSTS, E621_POSTS, SAFEBOORU_POSTS, png, sha256, zip };
