// Browser-side SFC selection and base64 upload helpers.

export function createRomUploader(call) {
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = ".sfc";
  fileInput.hidden = true;
  document.body.append(fileInput);

  return {
    async storeSelectedRom() {
      const file = await chooseRomFile(fileInput);

      if (!file) {
        return null;
      }

      if (!file.name.toLowerCase().endsWith(".sfc")) {
        throw new Error("Select a .sfc ROM file.");
      }

      const bytes = new Uint8Array(await file.arrayBuffer());
      return call("store_rom_upload", {
        fileName: file.name,
        dataBase64: bytesToBase64(bytes),
      });
    },
  };
}

async function chooseRomFile(fileInput) {
  if (window.showOpenFilePicker) {
    try {
      const [handle] = await window.showOpenFilePicker({
        multiple: false,
        types: [
          {
            description: "SNES ROM",
            accept: {
              "application/octet-stream": [".sfc"],
            },
          },
        ],
      });
      return handle.getFile();
    } catch (error) {
      if (error?.name === "AbortError") {
        return null;
      }
      throw error;
    }
  }

  return new Promise((resolve) => {
    let settled = false;

    function finish(file) {
      if (settled) {
        return;
      }
      settled = true;
      fileInput.removeEventListener("change", onChange);
      window.removeEventListener("focus", onFocus);
      resolve(file);
    }

    function onChange() {
      finish(fileInput.files?.[0] ?? null);
    }

    function onFocus() {
      window.setTimeout(() => {
        if (!fileInput.files?.length) {
          finish(null);
        }
      }, 200);
    }

    fileInput.value = "";
    fileInput.addEventListener("change", onChange);
    window.addEventListener("focus", onFocus);
    fileInput.click();
  });
}

function bytesToBase64(bytes) {
  const chunkSize = 0x8000;
  let binary = "";

  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }

  return btoa(binary);
}
