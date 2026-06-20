import { renderSpriteThumbnail } from "./sprite-thumbnail.js";

const THUMBNAIL_ROOT_MARGIN = "180px";

export function createSpriteGrid({ options, selectedValue, helpers, onChoose, onClose }) {
  const element = document.createElement("section");
  element.className = "link-sprite-browser";
  element.innerHTML = `
    <div class="link-sprite-browser-bar">
      <h3>ZSPR Sprite Browser</h3>
      <button class="secondary-button" type="button">Close</button>
    </div>
    <div class="link-sprite-browser-grid"></div>
  `;

  const closeButton = element.querySelector("button");
  const grid = element.querySelector(".link-sprite-browser-grid");
  let observer = null;
  let disposed = false;

  closeButton.addEventListener("click", onClose);

  return {
    element,
    filter(query) {
      render(query);
    },
    destroy() {
      disposed = true;
      observer?.disconnect();
    },
  };

  function render(query) {
    observer?.disconnect();
    observer = buildObserver(element, loadThumbnail);
    grid.textContent = "";

    const matches = filterOptions(options, query);
    if (matches.length === 0) {
      const empty = document.createElement("p");
      empty.className = "features-empty link-sprite-browser-empty";
      empty.textContent = "No matching sprites.";
      grid.append(empty);
      return;
    }

    for (const option of matches) {
      const card = buildSpriteCard(option, selectedValue, () => onChoose(option));
      grid.append(card.element);
      queueThumbnail(card, observer, loadThumbnail);
    }
  }

  async function loadThumbnail(card) {
    if (disposed || card.loaded || card.loading || !card.element.isConnected) {
      return;
    }

    card.loading = true;
    card.status.textContent = "";

    try {
      const data = await helpers.call("read_sprite_preview", {
        projectPath: helpers.state.selectedPath,
        spritePath: card.option.value,
      });
      if (!disposed && card.element.isConnected) {
        renderSpriteThumbnail(card.canvas, data.pixel_data, data.palette_data);
        card.loaded = true;
      }
    } catch (error) {
      if (!disposed && card.element.isConnected) {
        card.status.textContent = "Preview unavailable";
      }
    } finally {
      card.loading = false;
    }
  }
}

function buildObserver(root, loadThumbnail) {
  if (typeof IntersectionObserver !== "function") {
    return null;
  }

  return new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) {
          continue;
        }

        const card = entry.target.__spriteCard;
        if (card) {
          loadThumbnail(card);
          entry.target.__spriteCardObserver?.unobserve(entry.target);
        }
      }
    },
    { root, rootMargin: THUMBNAIL_ROOT_MARGIN },
  );
}

function buildSpriteCard(option, selectedValue, onChoose) {
  const button = document.createElement("button");
  const title = spriteTitle(option);
  const author = spriteAuthor(option);
  button.className = `link-sprite-grid-card${option.value === selectedValue ? " selected" : ""}`;
  button.type = "button";
  button.title = option.value;
  button.innerHTML = `
    <span class="link-sprite-grid-title"></span>
    <span class="link-sprite-grid-author"></span>
    <canvas></canvas>
    <span class="link-sprite-grid-status"></span>
  `;

  button.querySelector(".link-sprite-grid-title").textContent = title;
  button.querySelector(".link-sprite-grid-author").textContent = author;
  button.querySelector("canvas").setAttribute("aria-label", `${title} sprite preview`);
  button.addEventListener("click", onChoose);

  const card = {
    option,
    element: button,
    canvas: button.querySelector("canvas"),
    status: button.querySelector(".link-sprite-grid-status"),
    loaded: false,
    loading: false,
  };
  button.__spriteCard = card;
  return card;
}

function queueThumbnail(card, observer, loadThumbnail) {
  if (!observer) {
    loadWhenIdle(card, loadThumbnail);
    return;
  }

  card.element.__spriteCardObserver = observer;
  observer.observe(card.element);
}

function loadWhenIdle(card, loadThumbnail) {
  const load = () => loadThumbnail(card);

  if (typeof window !== "undefined" && typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(load, { timeout: 250 });
  } else {
    window.setTimeout(load, 0);
  }
}

function filterOptions(options, query) {
  const normalized = String(query).trim().toLowerCase();
  if (!normalized) {
    return options;
  }

  return options.filter((option) => searchableText(option).includes(normalized));
}

function searchableText(option) {
  return [
    option.label,
    option.value,
    option.source,
    option.author,
    option.author_rom_display,
  ].join(" ").toLowerCase();
}

function spriteTitle(option) {
  return option.label || option.value;
}

function spriteAuthor(option) {
  return option.author || option.author_rom_display || option.source;
}
