// In-launcher renderer for selected Link .zspr files.

const TILE_SIZE = 8;
const BYTES_PER_TILE = 32;
const TILES_PER_ROW = 16;

// Adds a local preview button that renders the sprite currently selected in the picker.
export function appendSpritePreview(section, picker, helpers) {
  const preview = document.createElement("div");
  preview.className = "features-sprite-preview";
  preview.innerHTML = `
    <button class="secondary-button" type="button">Preview</button>
    <div class="features-preview-panel" hidden>
      <div class="features-preview-meta">
        <strong></strong>
        <span></span>
      </div>
      <canvas aria-label="Selected sprite preview"></canvas>
      <p class="features-preview-status"></p>
    </div>
  `;

  const button = preview.querySelector("button");
  const panel = preview.querySelector(".features-preview-panel");
  const title = preview.querySelector("strong");
  const detail = preview.querySelector("span");
  const canvas = preview.querySelector("canvas");
  const status = preview.querySelector(".features-preview-status");

  button.addEventListener("click", async () => {
    const spritePath = picker.resolveValue().trim();

    if (!spritePath) {
      showPreviewMessage(panel, status, "Select a sprite before previewing.");
      return;
    }

    button.disabled = true;
    showPreviewMessage(panel, status, "Loading preview...");
    title.textContent = "";
    detail.textContent = spritePath;

    try {
      const data = await helpers.call("read_sprite_preview", {
        projectPath: helpers.state.selectedPath,
        spritePath,
      });
      title.textContent = data.label;
      detail.textContent = spritePath;
      renderSpriteCanvas(canvas, data.pixel_data, data.palette_data);
      status.textContent = "";
    } catch (error) {
      canvas.width = 1;
      canvas.height = 1;
      showPreviewMessage(panel, status, `Preview unavailable: ${error}`);
    } finally {
      button.disabled = false;
    }
  });

  section.append(preview);
}

function showPreviewMessage(panel, status, message) {
  panel.hidden = false;
  status.textContent = message;
}

function renderSpriteCanvas(canvas, pixelData, paletteData) {
  const pixels = Uint8Array.from(pixelData ?? []);
  const tileCount = Math.floor(pixels.length / BYTES_PER_TILE);

  if (tileCount === 0) {
    throw new Error("sprite has no complete tiles");
  }

  const width = TILES_PER_ROW * TILE_SIZE;
  const height = Math.ceil(tileCount / TILES_PER_ROW) * TILE_SIZE;
  canvas.width = width;
  canvas.height = height;

  const context = canvas.getContext("2d");
  const image = context.createImageData(width, height);
  const colors = decodePalette(paletteData);

  for (let tileIndex = 0; tileIndex < tileCount; tileIndex += 1) {
    drawTile(image, pixels, tileIndex, colors);
  }

  context.putImageData(image, 0, 0);
}

function drawTile(image, pixels, tileIndex, colors) {
  const tileOffset = tileIndex * BYTES_PER_TILE;
  const tileX = (tileIndex % TILES_PER_ROW) * TILE_SIZE;
  const tileY = Math.floor(tileIndex / TILES_PER_ROW) * TILE_SIZE;

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
      const color = colors[colorIndex] ?? colors[0];
      setPixel(image, tileX + x, tileY + y, color);
    }
  }
}

function decodePalette(paletteData) {
  const bytes = Uint8Array.from(paletteData ?? []);
  const colors = [{ red: 0, green: 0, blue: 0, alpha: 0 }];

  for (let index = 0; index + 1 < bytes.length && colors.length < 16; index += 2) {
    const word = bytes[index] | (bytes[index + 1] << 8);
    colors.push({
      red: snesColorToByte(word & 0x1f),
      green: snesColorToByte((word >> 5) & 0x1f),
      blue: snesColorToByte((word >> 10) & 0x1f),
      alpha: 255,
    });
  }

  while (colors.length < 16) {
    const value = colors.length * 17;
    colors.push({
      red: value,
      green: value,
      blue: value,
      alpha: 255,
    });
  }

  return colors;
}

function snesColorToByte(value) {
  return Math.round((value * 255) / 31);
}

function setPixel(image, x, y, color) {
  const index = (y * image.width + x) * 4;
  image.data[index] = color.red;
  image.data[index + 1] = color.green;
  image.data[index + 2] = color.blue;
  image.data[index + 3] = color.alpha;
}
