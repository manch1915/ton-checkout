/**
 * Drop-in checkout for any website:
 *
 *   <script src="https://checkout.example/checkout.js" defer></script>
 *   <button data-ton-checkout="inv_...">Pay</button>
 *
 * Clicking the button opens the payment page in a modal. When the invoice is paid the page
 * fires `ton-checkout:paid` on window with { invoiceId } in `detail`.
 * Plain DOM, no framework, so it adds a few kilobytes to the host page.
 */

const script = document.currentScript as HTMLScriptElement | null;
const ORIGIN = script ? new URL(script.src).origin : window.location.origin;
const STYLE_ID = "ton-checkout-style";

const css = `
.tc-overlay{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;
background:rgba(12,21,30,.55);padding:16px;animation:tc-fade .15s ease-out}
.tc-frame{width:100%;max-width:464px;height:min(720px,calc(100dvh - 32px));border:0;border-radius:18px;
background:#eef2f6;box-shadow:0 24px 64px -24px rgba(0,0,0,.5)}
.tc-close{position:absolute;top:12px;right:12px;width:40px;height:40px;border:0;border-radius:999px;
background:rgba(255,255,255,.9);color:#14202e;font:600 20px/1 system-ui;cursor:pointer}
.tc-close:focus-visible{outline:2px solid #0a7bc8;outline-offset:2px}
@keyframes tc-fade{from{opacity:0}}
@media (prefers-reduced-motion:reduce){.tc-overlay{animation:none}}
`;

let overlay: HTMLDivElement | null = null;
let lastFocus: Element | null = null;

function injectStyle() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = css;
  document.head.appendChild(style);
}

function close() {
  overlay?.remove();
  overlay = null;
  document.removeEventListener("keydown", onKey);
  if (lastFocus instanceof HTMLElement) lastFocus.focus();
}

function onKey(event: KeyboardEvent) {
  if (event.key === "Escape") close();
}

export function open(invoiceId: string) {
  if (!/^inv_[a-z0-9]+$/.test(invoiceId)) throw new Error(`Not an invoice id: ${invoiceId}`);
  injectStyle();
  close();
  lastFocus = document.activeElement;

  overlay = document.createElement("div");
  overlay.className = "tc-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "Checkout");
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close();
  });

  const frame = document.createElement("iframe");
  frame.className = "tc-frame";
  frame.title = "Checkout";
  frame.src = `${ORIGIN}/pay/${invoiceId}?embed=1`;
  frame.allow = "clipboard-write";

  const button = document.createElement("button");
  button.className = "tc-close";
  button.type = "button";
  button.setAttribute("aria-label", "Close checkout");
  button.textContent = "×";
  button.addEventListener("click", close);

  overlay.append(frame, button);
  document.body.appendChild(overlay);
  document.addEventListener("keydown", onKey);
  button.focus();
}

window.addEventListener("message", (event: MessageEvent<unknown>) => {
  // Only trust messages coming from our own payment page.
  if (event.origin !== ORIGIN) return;
  const data = event.data as { type?: string; invoiceId?: string } | null;
  if (data?.type === "ton-checkout:paid" && data.invoiceId) {
    window.dispatchEvent(
      new CustomEvent("ton-checkout:paid", { detail: { invoiceId: data.invoiceId } }),
    );
  }
});

document.addEventListener("click", (event) => {
  const target = (event.target as Element | null)?.closest<HTMLElement>("[data-ton-checkout]");
  const id = target?.dataset.tonCheckout;
  if (!id) return;
  event.preventDefault();
  open(id);
});

declare global {
  interface Window {
    TonCheckout?: { open: typeof open; close: typeof close };
  }
}
window.TonCheckout = { open, close };
