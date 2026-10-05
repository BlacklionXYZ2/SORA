import { deflateSync } from "node:zlib";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const iconDirectory = resolve(scriptDirectory, "../src/sora/pwa/icons");

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const name = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(Buffer.concat([name, data])));
  return Buffer.concat([length, name, data, checksum]);
}

function generateIcon(size) {
  const stride = 1 + size * 4;
  const pixels = Buffer.alloc(stride * size);
  const center = (size - 1) / 2;
  for (let y = 0; y < size; y += 1) {
    pixels[y * stride] = 0;
    for (let x = 0; x < size; x += 1) {
      const dx = (x - center) / size;
      const dy = (y - center) / size;
      const radius = Math.sqrt(dx * dx + dy * dy);
      const ring = radius > 0.235 && radius < 0.34;
      const core = radius <= 0.18;
      const offset = y * stride + 1 + x * 4;
      const glow = Math.max(0, 1 - radius * 1.8);
      pixels[offset] = Math.round(ring ? 153 : core ? 225 : 17 + glow * 24);
      pixels[offset + 1] = Math.round(ring ? 137 : core ? 225 : 24 + glow * 31);
      pixels[offset + 2] = Math.round(ring ? 255 : core ? 255 : 39 + glow * 50);
      pixels[offset + 3] = 255;
    }
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header.set([8, 6, 0, 0, 0], 8);
  return Buffer.concat([
    Buffer.from("89504e470d0a1a0a", "hex"),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(pixels, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

mkdirSync(iconDirectory, { recursive: true });
for (const size of [192, 512]) {
  const path = resolve(iconDirectory, `sora-${size}.png`);
  const expected = generateIcon(size);
  if (process.argv.includes("--check")) {
    const actual = readFileSync(path);
    if (!actual.equals(expected)) throw new Error(`${path} is stale; regenerate PWA icons.`);
  } else {
    writeFileSync(path, expected);
  }
}
