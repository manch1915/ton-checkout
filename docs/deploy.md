# Deploying

The stack is five containers: PostgreSQL, Redis, the API, the worker and the web container (nginx with the built frontend). Only the web container talks to the outside world; it proxies `/api`, `/v1` and the TON Connect manifest to the API.

## Behind an existing Caddy

1. Copy the project to the server and create `.env` from `.env.example`:
   - `PUBLIC_URL=https://checkout.example.com`, `CORS_ORIGINS=["https://checkout.example.com"]`, `TON_PROOF_DOMAIN=checkout.example.com`
   - a random `SECRET_KEY` (48+ characters) and a `POSTGRES_PASSWORD`
   - `DEMO_WALLET_ADDRESS`, `USDT_JETTON_MASTER`, optional `TONCENTER_API_KEY`
   - `TELEGRAM_BOT_TOKEN` and `TELEGRAM_BOT_USERNAME` if the Stars bot should run
2. Start it attached to the proxy's docker network:

   ```bash
   PROXY_NETWORK=caddy_default docker compose -f compose.yaml -f deploy/compose.prod.yaml up -d --build
   ```

3. Add the block from `deploy/Caddyfile.example` to the Caddyfile, then validate and reload without restarting the proxy:

   ```bash
   docker exec caddy caddy validate --config /etc/caddy/Caddyfile
   docker exec caddy caddy reload --config /etc/caddy/Caddyfile
   ```

   Create the DNS record first, otherwise Caddy keeps retrying the certificate.

4. Point the bot's Mini App to the store: in @BotFather, `/setmenubutton` or the Main App setting, URL `https://checkout.example.com/shop?source=telegram`.

## Checks after deploy

```bash
curl https://checkout.example.com/api/health          # {"status":"ok",...}
curl https://checkout.example.com/tonconnect-manifest.json
curl -N https://checkout.example.com/api/pay/<invoice id>/events   # stays open, sends a snapshot
docker compose logs worker --tail 20                    # watcher.tick, webhooks.tick
```

## Notes

- The API trusts `X-Forwarded-For` only from the web container, and nginx in turn takes the client address only from private networks (the proxy). Do not publish the API port.
- Without a toncenter key the watcher waits about a second between requests. With many merchant wallets, get a free key at toncenter.com.
- Webhook endpoints must be public HTTPS addresses. The worker resolves the host before every delivery and refuses private networks.
