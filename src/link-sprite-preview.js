// Link sprite palette preview renderer. Uses ZSPR's 4bpp tile layout and animation step data.

import { LINK_SPRITE_ANIMATIONS } from "./link-sprite-animations.js";

const DEFAULT_ANIMATION_KEY = "walk";
// One game frame at the SNES NTSC update rate. Animation step lengths are frame counts.
const GAME_FRAME_MS = 1000 / 60;
// SNES 4bpp tiles are 8x8 pixels stored in 32 planar bytes.
const BYTES_PER_TILE = 32;
// Every Link pose piece is assembled from hardware-sized 8x8 tiles.
const TILE_SIZE = 8;
// Link's 0x7000-byte sheet is arranged as 16 tiles per row.
const TILES_PER_ROW = 16;
// Palette words may use bit 15 for storage, but SNES BGR555 colors only use the low 15 bits.
const SNES_COLOR_MASK = 0x7fff;
// Padding keeps cropped previews from touching the canvas edge.
const PREVIEW_PADDING = 4;
// PlayerSprite.DrawTile skips anything after row AB, including shields and equipment.
const PLAYER_ROW_PATTERN = /^(?:[A-Z]|AA|AB)$/;
const FALLBACK_BOUNDS = { left: 0, top: 0, right: TILE_SIZE * 2, bottom: TILE_SIZE * 2 };

// Draw shapes mirror ZSpriteTools' TileDrawType tile selection and temp-bitmap placement.
const DRAW_SHAPES = {
  FULL: [
    [0, 0, 0, 0],
    [1, 0, 1, 0],
    [0, 1, 0, 1],
    [1, 1, 1, 1],
  ],
  TOP_HALF: [
    [0, 0, 0, 0],
    [1, 0, 1, 0],
  ],
  BOTTOM_HALF: [
    [0, 1, 0, 0],
    [1, 1, 1, 0],
  ],
  RIGHT_HALF: [
    [1, 0, 0, 0],
    [1, 1, 0, 1],
  ],
  LEFT_HALF: [
    [0, 0, 0, 0],
    [0, 1, 0, 1],
  ],
  TOP_RIGHT: [[1, 0, 0, 0]],
  TOP_LEFT: [[0, 0, 0, 0]],
  BOTTOM_RIGHT: [[1, 1, 0, 0]],
  BOTTOM_LEFT: [[0, 1, 0, 0]],
  TALL_8X24: [
    [0, 0, 0, 0],
    [0, 1, 0, 1],
    [0, 2, 0, 2],
  ],
  WIDE_24X8: [
    [0, 0, 0, 0],
    [1, 0, 1, 0],
    [2, 0, 2, 0],
  ],
  LARGE_16X24: [
    [0, 0, 0, 0],
    [1, 0, 1, 0],
    [0, 1, 0, 1],
    [1, 1, 1, 1],
    [0, 2, 0, 2],
    [1, 2, 1, 2],
  ],
  LARGE_32X24: [
    [0, 0, 0, 0],
    [1, 0, 1, 0],
    [2, 0, 2, 0],
    [3, 0, 3, 0],
    [0, 1, 0, 1],
    [1, 1, 1, 1],
    [2, 1, 2, 1],
    [3, 1, 3, 1],
    [0, 2, 0, 2],
    [1, 2, 1, 2],
    [2, 2, 2, 2],
    [3, 2, 3, 2],
  ],
};

// Creates the preview controller used by the palette editor.
export function createLinkSpritePreview(snapshot, editorState, status) {
  const cards = [];
  const shared = {
    animations: [],
    previewLabel: "",
    previewError: "",
    animationError: "",
    destroyed: false,
  };

  const controller = {
    attachRow(row, container) {
      if (shared.destroyed || !container) {
        return;
      }

      const card = buildPreviewCard(row);
      cards.push(card);
      wirePreviewCard(card, controller);
      container.append(card.element);
      renderPreviewCard(card, snapshot, editorState);
      updateCardControls(card, shared);
    },
    async load(helpers) {
      await loadPreviewPixels(helpers, editorState, shared);

      if (shared.destroyed) {
        return;
      }

      loadAnimationChoices(shared);

      if (shared.destroyed) {
        return;
      }

      for (const card of cards) {
        populateAnimationSelect(card.select, shared.animations);
        setCardAnimation(card, selectInitialAnimationKey(shared.animations), shared.animations);
        updateCardControls(card, shared);
      }

      updatePreviewStatus(status, shared);
      this.render();
    },
    setCardAnimation(card, key) {
      setCardAnimation(card, key, shared.animations);
      updateCardControls(card, shared);
      renderPreviewCard(card, snapshot, editorState);
    },
    playCard(card) {
      playCard(card, shared, () => renderPreviewCard(card, snapshot, editorState));
      updateCardControls(card, shared);
    },
    pauseCard(card) {
      pauseCard(card);
      updateCardControls(card, shared);
    },
    render() {
      renderPreviewCards(cards, snapshot, editorState);
    },
    syncControls() {
      for (const card of cards) {
        updateCardControls(card, shared);
      }
    },
    destroy() {
      shared.destroyed = true;

      for (const card of cards) {
        pauseCard(card);
      }
    },
  };

  return controller;
}

// Builds one self-contained preview card for a single armor/effect palette row.
function buildPreviewCard(row) {
  const element = document.createElement("div");
  element.className = "link-sprite-preview-card";
  element.innerHTML = `
    <button class="secondary-button link-sprite-preview-toggle" type="button" disabled>Play</button>
    <div class="link-sprite-preview-canvas-wrap">
      <canvas aria-label="${row.label} animated sprite preview"></canvas>
    </div>
    <select class="link-sprite-animation" aria-label="${row.label} animation" disabled>
      <option value="">Loading animations...</option>
    </select>
  `;

  return {
    row,
    element,
    canvas: element.querySelector("canvas"),
    toggle: element.querySelector(".link-sprite-preview-toggle"),
    select: element.querySelector(".link-sprite-animation"),
    animation: null,
    animationKey: "",
    bounds: FALLBACK_BOUNDS,
    frameCounter: 0,
    stepIndex: 0,
    timer: null,
    playing: false,
  };
}

// Wires controls for one row preview without sharing playback state with other rows.
function wirePreviewCard(card, controller) {
  card.toggle.addEventListener("click", () => {
    if (card.playing) {
      controller.pauseCard(card);
    } else {
      controller.playCard(card);
    }
  });
  card.select.addEventListener("change", () => {
    controller.setCardAnimation(card, card.select.value);
  });
}

// Reads the backend's best available Link pixels, preferring active ZSPR over compiled assets.
async function loadPreviewPixels(helpers, editorState, shared) {
  try {
    const preview = await helpers.call("read_link_sprite_preview", {
      projectPath: helpers.state.selectedPath,
    });
    const pixels = Uint8Array.from(preview.pixel_data ?? []);
    editorState.previewPixels = pixels.length ? pixels : null;
    shared.previewLabel = `${preview.label} (${preview.source})`;
    shared.previewError = editorState.previewPixels ? "" : "Preview unavailable: no sprite pixels were returned.";
  } catch (error) {
    editorState.previewPixels = null;
    shared.previewLabel = "";
    shared.previewError = `Preview unavailable: ${error}`;
  }
}

// Loads and normalizes the complete ZSpriteTools animation list.
function loadAnimationChoices(shared) {
  try {
    shared.animations = normalizeAnimations(LINK_SPRITE_ANIMATIONS);
    shared.animationError = shared.animations.length ? "" : "No animations were found.";
  } catch (error) {
    shared.animations = [];
    shared.animationError = `Animation list unavailable: ${error}`;
  }
}

// Converts raw AnimationData.json entries into the subset the renderer uses.
function normalizeAnimations(animationData) {
  if (!animationData || typeof animationData !== "object") {
    return [];
  }

  return Object.entries(animationData)
    .map(([key, rawAnimation]) => normalizeAnimation(key, rawAnimation))
    .filter(Boolean);
}

// Normalizes one animation entry while preserving ZSpriteTools' object order.
function normalizeAnimation(key, rawAnimation) {
  if (!rawAnimation || !Array.isArray(rawAnimation.steps)) {
    return null;
  }

  const steps = rawAnimation.steps.map((step) => ({
    length: normalizeStepLength(step?.length),
    sprites: Array.isArray(step?.sprites) ? step.sprites : [],
  }));

  if (steps.length === 0) {
    return null;
  }

  return {
    key,
    name: String(rawAnimation.name || key),
    steps,
  };
}

// ZSpriteTools treats step lengths as positive frame counts.
function normalizeStepLength(value) {
  const length = Number(value);
  return Number.isFinite(length) && length > 0 ? Math.floor(length) : 1;
}

// Populates one row's animation picker in ZSpriteTools' data order.
function populateAnimationSelect(select, animations) {
  select.textContent = "";

  if (animations.length === 0) {
    select.append(new Option("Animations unavailable", ""));
    select.disabled = true;
    return;
  }

  for (const animation of animations) {
    select.append(new Option(animation.name, animation.key));
  }
  select.disabled = false;
}

// Uses Walk as the initial preview when available, with the source's first entry as fallback.
function selectInitialAnimationKey(animations) {
  if (animations.some((animation) => animation.key === DEFAULT_ANIMATION_KEY)) {
    return DEFAULT_ANIMATION_KEY;
  }

  return animations[0]?.key ?? "";
}

// Changes one card's animation and resets that card to the first frame.
function setCardAnimation(card, key, animations) {
  const animation = animations.find((entry) => entry.key === key) ?? animations[0] ?? null;
  card.animation = animation;
  card.animationKey = animation?.key ?? "";
  card.bounds = animation ? measureAnimation(animation) : FALLBACK_BOUNDS;
  card.frameCounter = 0;
  card.stepIndex = 0;

  if (card.select.value !== card.animationKey) {
    card.select.value = card.animationKey;
  }
}

// Starts one row preview at game-frame speed without affecting the other rows.
function playCard(card, shared, render) {
  if (card.playing || !card.animation || shared.previewError || typeof window === "undefined") {
    return;
  }

  card.playing = true;
  card.timer = window.setInterval(() => {
    advanceAnimationFrame(card);
    render();
  }, GAME_FRAME_MS);
}

// Pauses one row preview at its current frame.
function pauseCard(card) {
  if (card.timer !== null && typeof window !== "undefined") {
    window.clearInterval(card.timer);
  }

  card.timer = null;
  card.playing = false;
}

// Keeps one row's controls in sync with preview availability and playback state.
function updateCardControls(card, shared) {
  card.select.disabled = shared.animations.length === 0;
  card.toggle.disabled = !card.animation || Boolean(shared.previewError);
  card.toggle.textContent = card.playing ? "Pause" : "Play";
}

// Renders every preview canvas from current editor values and cached Link pixels.
function renderPreviewCards(cards, snapshot, editorState) {
  for (const card of cards) {
    renderPreviewCard(card, snapshot, editorState);
  }
}

// Renders one row preview, or clears it while required preview data is unavailable.
function renderPreviewCard(card, snapshot, editorState) {
  if (!editorState.previewPixels || !card.animation) {
    clearPreviewCanvas(card.canvas, card.bounds);
    return;
  }

  const rowStart = card.row.start;
  const paletteWords = editorState.values.slice(rowStart, rowStart + snapshot.row_length);
  const step = card.animation.steps[card.stepIndex] ?? card.animation.steps[0];
  renderAnimationStep(card.canvas, editorState.previewPixels, paletteWords, step, card.bounds);
}

// Renders one animation step into one canvas using the supplied 15-color palette row.
function renderAnimationStep(canvas, pixels, paletteWords, step, bounds) {
  const width = previewWidth(bounds);
  const height = previewHeight(bounds);
  setCanvasSize(canvas, width, height);

  const context = canvas.getContext("2d");

  if (!context) {
    return;
  }

  const image = context.createImageData(width, height);
  const palette = paletteWords.map(snesWordToColor);

  for (const piece of [...step.sprites].reverse()) {
    drawPiece(image, pixels, piece, palette, bounds);
  }

  context.putImageData(image, 0, 0);
}

// Keeps empty previews sized consistently so layout does not jump while pixels load.
function clearPreviewCanvas(canvas, bounds) {
  const width = previewWidth(bounds);
  const height = previewHeight(bounds);
  setCanvasSize(canvas, width, height);

  const context = canvas.getContext("2d");

  if (context) {
    context.clearRect(0, 0, width, height);
  }
}

// Measures every drawable frame so the canvas stays stable throughout the selected animation.
function measureAnimation(animation) {
  const bounds = { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity };

  for (const step of animation.steps) {
    for (const piece of step.sprites) {
      if (!isDrawablePlayerRow(piece.row)) {
        continue;
      }

      const dimensions = shapeDimensions(DRAW_SHAPES[piece.size]);
      const pos = piecePosition(piece);

      if (!dimensions || !pos) {
        continue;
      }

      bounds.left = Math.min(bounds.left, pos.x);
      bounds.top = Math.min(bounds.top, pos.y);
      bounds.right = Math.max(bounds.right, pos.x + dimensions.width);
      bounds.bottom = Math.max(bounds.bottom, pos.y + dimensions.height);
    }
  }

  if (bounds.left === Infinity) {
    return FALLBACK_BOUNDS;
  }

  return bounds;
}

// Returns the drawn dimensions for a TileDrawType shape in pixels.
function shapeDimensions(shape) {
  if (!shape || shape.length === 0) {
    return null;
  }

  let maxDestX = 0;
  let maxDestY = 0;

  for (const [, , destX, destY] of shape) {
    maxDestX = Math.max(maxDestX, destX);
    maxDestY = Math.max(maxDestY, destY);
  }

  return {
    width: (maxDestX + 1) * TILE_SIZE,
    height: (maxDestY + 1) * TILE_SIZE,
  };
}

// Draws one sprite piece by expanding its ZSpriteTools row/column/shape into 8x8 tile draws.
function drawPiece(image, pixels, piece, palette, bounds) {
  if (!isDrawablePlayerRow(piece.row)) {
    return;
  }

  const shape = DRAW_SHAPES[piece.size] ?? [];
  const dimensions = shapeDimensions(shape);
  const pos = piecePosition(piece);
  const column = Number(piece.col);

  if (!dimensions || !pos || !Number.isFinite(column)) {
    return;
  }

  const baseTile = baseTileIndex(piece.row, column);
  const pieceX = pos.x - bounds.left + PREVIEW_PADDING;
  const pieceY = pos.y - bounds.top + PREVIEW_PADDING;

  for (const [srcX, srcY, destX, destY] of shape) {
    const tileIndex = baseTile + srcX + srcY * TILES_PER_ROW;
    drawTile(image, pixels, tileIndex, pieceX, pieceY, destX, destY, dimensions, palette, piece.trans);
  }
}

// Converts a ZSpriteTools row name and column into the top-left tile index for a 16x16 piece.
function baseTileIndex(rowName, column) {
  const row = rowIndex(rowName);
  return Number(column) * 2 + row * 2 * TILES_PER_ROW;
}

// Maps ZSpriteTools row labels A-Z, AA, and AB onto the 56-row Link tile sheet.
function rowIndex(rowName) {
  if (rowName === "AA") {
    return 26;
  }
  if (rowName === "AB") {
    return 27;
  }
  return rowName.charCodeAt(0) - "A".charCodeAt(0);
}

// Reports whether a ZSpriteTools row is one of PlayerSprite.DrawTile's drawable Link rows.
function isDrawablePlayerRow(rowName) {
  return typeof rowName === "string" && PLAYER_ROW_PATTERN.test(rowName);
}

// Converts a raw JSON position into a named point.
function piecePosition(piece) {
  if (!Array.isArray(piece.pos) || piece.pos.length < 2) {
    return null;
  }

  const x = Number(piece.pos[0]);
  const y = Number(piece.pos[1]);

  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }

  return {
    x,
    y,
  };
}

// Decodes one SNES 4bpp tile and writes non-transparent pixels into the output image.
function drawTile(image, pixels, tileIndex, pieceX, pieceY, destTileX, destTileY, dimensions, palette, flip) {
  const tileOffset = tileIndex * BYTES_PER_TILE;

  if (tileOffset + BYTES_PER_TILE > pixels.length) {
    return;
  }

  for (let y = 0; y < TILE_SIZE; y += 1) {
    const planeA = pixels[tileOffset + y * 2];
    const planeB = pixels[tileOffset + y * 2 + 1];
    const planeC = pixels[tileOffset + 16 + y * 2];
    const planeD = pixels[tileOffset + 16 + y * 2 + 1];

    for (let x = 0; x < TILE_SIZE; x += 1) {
      const bit = 7 - x;
      const colorIndex =
        ((planeA >> bit) & 1) |
        (((planeB >> bit) & 1) << 1) |
        (((planeC >> bit) & 1) << 2) |
        (((planeD >> bit) & 1) << 3);

      if (colorIndex > 0) {
        const target = transformPixel(destTileX * TILE_SIZE + x, destTileY * TILE_SIZE + y, dimensions, flip);
        setPixel(image, pieceX + target.x, pieceY + target.y, palette[colorIndex - 1]);
      }
    }
  }
}

// Applies ZSpriteTools' temporary-bitmap flip semantics to one piece-local pixel.
function transformPixel(x, y, dimensions, flip) {
  const point = { x, y };

  if (flip === "Y_FLIP" || flip === "XY_FLIP") {
    point.x = dimensions.width - 1 - point.x;
  }

  if (flip === "X_FLIP" || flip === "XY_FLIP") {
    point.y = dimensions.height - 1 - point.y;
  }

  return point;
}

// Advances by one game frame using ZSpriteTools' weighted-frame selection.
function advanceAnimationFrame(card) {
  card.frameCounter += 1;
  const nextStep = animationStepIndex(card.animation, card.frameCounter);

  if (nextStep === null) {
    card.frameCounter = 0;
    card.stepIndex = 0;
    return;
  }

  card.stepIndex = nextStep;
}

// Mirrors PlayerSprite.DrawAnimation's totalLength + step.Length > currentFrame check.
function animationStepIndex(animation, currentFrame) {
  let totalLength = 0;

  for (let index = 0; index < animation.steps.length; index += 1) {
    const step = animation.steps[index];

    if (totalLength + step.length > currentFrame) {
      return index;
    }

    totalLength += step.length;
  }

  return null;
}

// Converts a SNES BGR555 palette word into browser RGBA channel values.
function snesWordToColor(word) {
  const colorWord = word & SNES_COLOR_MASK;
  return {
    red: snesChannelToByte(colorWord & 0x1f),
    green: snesChannelToByte((colorWord >> 5) & 0x1f),
    blue: snesChannelToByte((colorWord >> 10) & 0x1f),
    alpha: 255,
  };
}

// Expands one 5-bit SNES channel to 8-bit precision by bit replication.
function snesChannelToByte(value) {
  return (value << 3) | (value >> 2);
}

// Writes one RGBA pixel into an ImageData buffer if the destination is in bounds.
function setPixel(image, x, y, color) {
  if (!color || x < 0 || y < 0 || x >= image.width || y >= image.height) {
    return;
  }

  const index = (y * image.width + x) * 4;
  image.data[index] = color.red;
  image.data[index + 1] = color.green;
  image.data[index + 2] = color.blue;
  image.data[index + 3] = color.alpha;
}

// Applies one size to the canvas backing store without triggering unnecessary clears.
function setCanvasSize(canvas, width, height) {
  if (canvas.width !== width) {
    canvas.width = width;
  }

  if (canvas.height !== height) {
    canvas.height = height;
  }
}

function previewWidth(bounds) {
  return bounds.right - bounds.left + PREVIEW_PADDING * 2;
}

function previewHeight(bounds) {
  return bounds.bottom - bounds.top + PREVIEW_PADDING * 2;
}

function updatePreviewStatus(status, shared) {
  if (!status) {
    return;
  }

  const messages = [];

  if (shared.previewError) {
    messages.push(shared.previewError);
  } else if (shared.previewLabel) {
    messages.push(shared.previewLabel);
  }

  if (shared.animationError) {
    messages.push(shared.animationError);
  } else if (shared.animations.length) {
    messages.push(`${shared.animations.length} animations`);
  }

  status.textContent = messages.join(" - ");
}
