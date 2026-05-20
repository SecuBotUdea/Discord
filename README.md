# Discord Microservice

Microservicio independiente para integración con Discord en arquitectura de microservicios.

## Responsabilidades

- Mantiene conexión persistente con Discord Gateway.
- Registra slash commands `/rescan` y `/status`.
- Escucha eventos `on_ready`, `on_guild_join`, `on_guild_remove`.
- Expone endpoints HTTP:
  - `POST /webhook/notify`
  - `POST /webhook/action`
  - `GET /health`
- Guarda configuración de webhooks por servidor en `servers`.
- Registra trazas de entradas HTTP en `webhooks_log`.

## Requisitos

- Python 3.10+
- MongoDB Atlas (o fallback en memoria para desarrollo/pruebas)

## Variables de entorno

Requeridas:

- `DISCORD_BOT_TOKEN`
- `DATABASE_URL`

Opcionales:

- `HTTP_PORT` (default `8000`)
- `DISCORD_LOG_LEVEL` (default `INFO`)
- `ROUTING_SERVICE_URL`
- `ENVIRONMENT` (`development`/`production`)
- `ALLOWED_ORIGINS` (CSV)

Consulta `.env.example` para un ejemplo completo.

## Instalación

```bash
pip install -r requirements.txt
```

## Ejecución

```bash
python main.py
```

## Endpoints

### `POST /webhook/notify`

Entrada:

```json
{
  "guild_id": "123456789",
  "channel_id": "987654321",
  "message_content": "...",
  "embed_data": {"title": "Opcional"}
}
```

### `POST /webhook/action`

Entrada:

```json
{
  "action": "rescan_initiated",
  "alert_id": "alert_123",
  "guild_id": "123456789",
  "user_id": "user_456"
}
```

### `GET /health`

Respuesta:

```json
{
  "status": "healthy",
  "bot_connected": true,
  "database_connected": true,
  "timestamp": "2026-01-01T00:00:00+00:00"
}
```

## Testing

```bash
pytest -q
```

## Deployment (plan gratuito)

Compatible con Render, Railway, Replit y DigitalOcean App Platform usando `python main.py` como comando de inicio y variables de entorno configuradas en la plataforma.
