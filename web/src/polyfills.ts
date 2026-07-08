import { Buffer } from "buffer";

// @ton/core expects Node's Buffer. Imported first in main.tsx, before anything touches TON.
globalThis.Buffer ??= Buffer;
