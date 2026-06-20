// Canvas renderer for Link sprite palette preview cards.

const BYTES_PER_TILE = 32;
const TILE_SIZE = 8;
const TILES_PER_ROW = 16;
const SNES_COLOR_MASK = 0x7fff;
const PREVIEW_PADDING = 4;
const PLAYER_ROW_PATTERN = /^(?:[A-Z]|AA|AB)$/;

export const FALLBACK_BOUNDS = { left: 0, top: 0, right: TILE_SIZE * 2, bottom: TILE_SIZE * 2 };

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

export function renderPreviewCards(cards, snapshot, editorState) {
  for (const card of cards) {
    renderPreviewCard(card, snapshot, editorState);
  }
}

export function renderPreviewCard(card, snapshot, editorState) {
  if (!editorState.previewPixels || !card.animation) {
    clearPreviewCanvas(card.canvas, card.bounds);
    return;
  }

  const rowStart = card.row.start;
  const paletteWords = editorState.values.slice(rowStart, rowStart + snapshot.row_length);
  const step = card.animation.steps[card.stepIndex] ?? card.animation.steps[0];
  renderAnimationStep(card.canvas, editorState.previewPixels, paletteWords, step, card.bounds);
}

export function renderStaticSpriteFrame(canvas, pixels, paletteWords, animation) {
  if (!pixels || !animation) {
    clearPreviewCanvas(canvas, FALLBACK_BOUNDS);
    return;
  }

  const bounds = measureAnimation(animation);
  const step = animation.steps[0];
  renderAnimationStep(canvas, pixels, paletteWords, step, bounds);
}

export function measureAnimation(animation) {
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

  return bounds.left === Infinity ? FALLBACK_BOUNDS : bounds;
}

export function advanceAnimationFrame(card) {
  card.frameCounter += 1;
  const nextStep = animationStepIndex(card.animation, card.frameCounter);

  if (nextStep === null) {
    card.frameCounter = 0;
    card.stepIndex = 0;
    return;
  }

  card.stepIndex = nextStep;
}

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

function clearPreviewCanvas(canvas, bounds) {
  const width = previewWidth(bounds);
  const height = previewHeight(bounds);
  setCanvasSize(canvas, width, height);

  const context = canvas.getContext("2d");

  if (context) {
    context.clearRect(0, 0, width, height);
  }
}

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

function baseTileIndex(rowName, column) {
  const row = rowIndex(rowName);
  return Number(column) * 2 + row * 2 * TILES_PER_ROW;
}

function rowIndex(rowName) {
  if (rowName === "AA") {
    return 26;
  }
  if (rowName === "AB") {
    return 27;
  }
  return rowName.charCodeAt(0) - "A".charCodeAt(0);
}

function isDrawablePlayerRow(rowName) {
  return typeof rowName === "string" && PLAYER_ROW_PATTERN.test(rowName);
}

function piecePosition(piece) {
  if (!Array.isArray(piece.pos) || piece.pos.length < 2) {
    return null;
  }

  const x = Number(piece.pos[0]);
  const y = Number(piece.pos[1]);

  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }

  return { x, y };
}

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

function snesWordToColor(word) {
  const colorWord = word & SNES_COLOR_MASK;
  return {
    red: snesChannelToByte(colorWord & 0x1f),
    green: snesChannelToByte((colorWord >> 5) & 0x1f),
    blue: snesChannelToByte((colorWord >> 10) & 0x1f),
    alpha: 255,
  };
}

function snesChannelToByte(value) {
  return (value << 3) | (value >> 2);
}

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
