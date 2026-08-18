# Bot examples

Two small ticket bots that sell through TON Checkout. Each one does the same three things:

1. `/buy` creates an invoice with `POST /v1/invoices` and replies with the payment link (a Mini App button when the checkout runs on HTTPS).
2. A tiny HTTP server receives the webhook and verifies its signature with the official [Standard Webhooks](https://www.standardwebhooks.com) library.
3. On `invoice.paid` the bot sends the buyer a door code, once per invoice.

## Setup

In the dashboard:

- **API keys**: create a test key (`sk_test_...`).
- **Webhooks**: add `https://<your bot host>/webhooks/ton` and copy the signing secret (`whsec_...`).

For local runs, expose the webhook port with a tunnel such as `cloudflared tunnel --url http://localhost:8081`.

| Variable | Meaning |
|---|---|
| `BOT_TOKEN` | Token from @BotFather |
| `CHECKOUT_URL` | Where TON Checkout runs, for example `http://localhost:8010` |
| `CHECKOUT_API_KEY` | Secret key from the dashboard |
| `CHECKOUT_WEBHOOK_SECRET` | Signing secret of your endpoint |
| `PORT` | Port of the webhook server (8081 for aiogram, 8082 for grammY) |

## aiogram (Python)

```bash
cd examples/aiogram-bot
pip install -r requirements.txt
python bot.py
```

## grammY (TypeScript)

```bash
cd examples/grammy-bot
npm install
npm start
```

Both examples keep fulfilled invoices in memory to stay short. In production, store them in your database: a webhook can be delivered more than once, and fulfilment has to be idempotent.
