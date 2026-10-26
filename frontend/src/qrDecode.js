// Read a QR code from an image, trying harder than a single pass.
//
// A passport QR holds about 1,000 characters, so its modules are small. User
// testing (26 Oct) found phone cameras only read it when zoomed in and held
// still, and a full-resolution phone photo can be too large for one pass. So
// the decoder tries, cheapest first: the whole image; the centre (a 2x
// "digital zoom", the same thing users did by hand); a downscaled copy for very
// large photos; and finally inverted colours (a QR shown on a dark screen).
import jsQR from "jsqr";

const MAX_SIDE = 1200;   // larger images are downscaled first: faster, and jsQR copes better

// Crop a rectangle out of RGBA pixels.
export function crop(img, x, y, w, h) {
  const out = new Uint8ClampedArray(w * h * 4);
  for (let row = 0; row < h; row++) {
    const src = ((y + row) * img.width + x) * 4;
    out.set(img.data.subarray(src, src + w * 4), row * w * 4);
  }
  return { data: out, width: w, height: h };
}

// Nearest-neighbour resize, enough for QR modules.
export function resize(img, w, h) {
  const out = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) {
    const sy = Math.min(img.height - 1, Math.floor((y * img.height) / h));
    for (let x = 0; x < w; x++) {
      const sx = Math.min(img.width - 1, Math.floor((x * img.width) / w));
      const s = (sy * img.width + sx) * 4, d = (y * w + x) * 4;
      out[d] = img.data[s]; out[d + 1] = img.data[s + 1]; out[d + 2] = img.data[s + 2]; out[d + 3] = 255;
    }
  }
  return { data: out, width: w, height: h };
}

function fitWithin(img, max) {
  const side = Math.max(img.width, img.height);
  if (side <= max) return img;
  const k = max / side;
  return resize(img, Math.round(img.width * k), Math.round(img.height * k));
}

function centre(img, share) {
  const w = Math.round(img.width * share), h = Math.round(img.height * share);
  return crop(img, Math.floor((img.width - w) / 2), Math.floor((img.height - h) / 2), w, h);
}

// The attempts, in order. `quick` (for live camera frames) tries only the two
// cheap ones, alternating, so the camera loop stays light.
// A whole document page (a PDF passport) passes `maxSide: Infinity`: shrinking
// an A4 page makes its QR's modules too small to read, so the page is kept at
// full size and each quarter is tried as well, since the QR isn't centred.
export function attempts(img, { quick = false, frame = 0, maxSide = MAX_SIDE } = {}) {
  const base = fitWithin(img, maxSide);
  if (quick) return frame % 2 === 0 ? [[base, "dontInvert"]] : [[centre(base, 0.5), "dontInvert"]];
  const hw = Math.floor(base.width / 2), hh = Math.floor(base.height / 2);
  const quarters = [[0, 0], [hw, 0], [0, hh], [hw, hh]].map(([x, y]) => [crop(base, x, y, hw, hh), "dontInvert"]);
  return [
    [base, "dontInvert"],
    [centre(base, 0.5), "dontInvert"],
    [centre(base, 0.75), "dontInvert"],
    ...quarters,
    [base.width > 800 ? fitWithin(base, 800) : base, "attemptBoth"],
  ];
}

// The decoded text, or null.
export function decodeQR(img, opts = {}) {
  for (const [candidate, inversion] of attempts(img, opts)) {
    const code = jsQR(candidate.data, candidate.width, candidate.height, { inversionAttempts: inversion });
    if (code?.data) return code.data;
  }
  return null;
}

// ------------------------------------------------------------ files (browser)
// Read a QR from a file a person chose: a PNG/JPG, or the PDF from Save as PDF.
// Resolves to the QR's text, or null if none was found. Shared by the verifier
// and Compare. PDF.js is loaded only when a PDF is chosen.

export function isPdf(file) {
  return file?.type === "application/pdf" || /\.pdf$/i.test(file?.name || "");
}

function imagePixels(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement("canvas");
      c.width = img.naturalWidth; c.height = img.naturalHeight;
      const ctx = c.getContext("2d");
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(img.src);
      resolve(ctx.getImageData(0, 0, c.width, c.height));
    };
    img.onerror = () => reject(new Error("Couldn't read that image file."));
    img.src = URL.createObjectURL(file);
  });
}

async function pdfQr(file) {
  const pdfjs = await import("pdfjs-dist");
  const worker = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
  pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
  let pdf;
  try {
    pdf = await pdfjs.getDocument({ data: await file.arrayBuffer(), isEvalSupported: false }).promise;
  } catch {
    throw new Error("Couldn't open that PDF. Try a screenshot of its QR code instead.");
  }
  for (let n = 1; n <= Math.min(pdf.numPages, 3); n++) {
    const page = await pdf.getPage(n);
    const viewport = page.getViewport({ scale: 3 });
    const c = document.createElement("canvas");
    c.width = viewport.width; c.height = viewport.height;
    const ctx = c.getContext("2d");
    await page.render({ canvasContext: ctx, viewport }).promise;
    const text = decodeQR(ctx.getImageData(0, 0, c.width, c.height), { maxSide: Infinity });
    if (text) return text;
  }
  return null;
}

export async function decodeQrFile(file) {
  if (isPdf(file)) return pdfQr(file);
  return decodeQR(await imagePixels(file));
}
