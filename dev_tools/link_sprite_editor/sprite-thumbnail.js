import { LINK_SPRITE_ANIMATIONS } from "./animations.js";
import { renderStaticSpriteFrame } from "./preview-renderer.js";

const THUMBNAIL_ANIMATION_KEY = "standDown";
const THUMBNAIL_PALETTE_WORDS = 15;

export function renderSpriteThumbnail(canvas, pixelData, paletteData) {
  const pixels = Uint8Array.from(pixelData ?? []);
  const paletteWords = paletteWordsFromBytes(paletteData);
  const animation = LINK_SPRITE_ANIMATIONS[THUMBNAIL_ANIMATION_KEY] ?? LINK_SPRITE_ANIMATIONS.stand;
  renderStaticSpriteFrame(canvas, pixels, paletteWords, animation);
}

function paletteWordsFromBytes(paletteData) {
  const bytes = Uint8Array.from(paletteData ?? []);
  const words = [];

  for (let index = 0; index + 1 < bytes.length && words.length < THUMBNAIL_PALETTE_WORDS; index += 2) {
    words.push(bytes[index] | (bytes[index + 1] << 8));
  }

  while (words.length < THUMBNAIL_PALETTE_WORDS) {
    words.push(0);
  }

  return words;
}
