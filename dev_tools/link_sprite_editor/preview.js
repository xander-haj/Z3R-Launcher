// Link sprite palette preview renderer. Uses ZSPR's 4bpp tile layout and animation step data.

import { LINK_SPRITE_ANIMATIONS } from "./animations.js";
import {
  FALLBACK_BOUNDS,
  advanceAnimationFrame,
  measureAnimation,
  renderPreviewCard,
  renderPreviewCards,
} from "./preview-renderer.js";

const DEFAULT_ANIMATION_KEY = "walk";
// One game frame at the SNES NTSC update rate. Animation step lengths are frame counts.
const GAME_FRAME_MS = 1000 / 60;

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
