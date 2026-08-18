// Ticket bot on grammY that takes payments through TON Checkout.
// /buy creates an invoice and sends the link; the HTTP server below receives the signed webhook.
import { createServer } from "node:http";
import { randomBytes } from "node:crypto";

import { Bot, InlineKeyboard } from "grammy";
import { Webhook } from "standardwebhooks";

const env = (name: string, fallback?: string): string => {
  const value = process.env[name] ?? fallback;
  if (!value) throw new Error(`${name} is not set`);
  return value;
};

const bot = new Bot(env("BOT_TOKEN"));
const checkoutUrl = env("CHECKOUT_URL", "http://localhost:8010");
const apiKey = env("CHECKOUT_API_KEY");
const webhook = new Webhook(env("CHECKOUT_WEBHOOK_SECRET"));
// Webhooks can arrive twice; a real bot checks its database instead of this set.
const fulfilled = new Set<string>();

interface Invoice {
  id: string;
  reference: string;
  pay_url: string;
  metadata: { chat_id?: number };
}

bot.command("buy", async (ctx) => {
  const response = await fetch(`${checkoutUrl}/v1/invoices`, {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      amount: "24.00",
      description: "Neon Harbor live, 21 Nov",
      product_kind: "offline_service",
      channel: "telegram_mini_app",
      order_id: `tg-${ctx.from?.id}-${randomBytes(3).toString("hex")}`,
      metadata: { chat_id: ctx.chat.id },
    }),
  });
  if (!response.ok) {
    await ctx.reply("Could not create the order, try again in a minute.");
    return;
  }
  const invoice = (await response.json()) as Invoice;
  const keyboard = invoice.pay_url.startsWith("https://")
    ? new InlineKeyboard().webApp("Pay with Gram or USDT", invoice.pay_url)
    : new InlineKeyboard().url("Pay with Gram or USDT", invoice.pay_url);
  await ctx.reply(`Ticket reserved for 30 minutes. Payment code: ${invoice.reference}`, {
    reply_markup: keyboard,
  });
});

createServer(async (req, res) => {
  if (req.method !== "POST" || req.url !== "/webhooks/ton") {
    res.writeHead(404).end();
    return;
  }
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  const body = Buffer.concat(chunks).toString("utf8");

  let event: { type: string; data: { invoice: Invoice } };
  try {
    event = webhook.verify(body, req.headers as Record<string, string>) as typeof event;
  } catch {
    res.writeHead(401).end();
    return;
  }

  const invoice = event.data.invoice;
  if (event.type === "invoice.paid" && !fulfilled.has(invoice.id)) {
    fulfilled.add(invoice.id);
    const chatId = invoice.metadata.chat_id;
    if (chatId) {
      const code = randomBytes(4).toString("hex").toUpperCase();
      await bot.api.sendMessage(chatId, `Paid, thank you. Your door code: ${code}`);
    }
  }
  res.writeHead(200, { "Content-Type": "application/json" }).end('{"ok":true}');
}).listen(Number(env("PORT", "8082")));

void bot.start();
