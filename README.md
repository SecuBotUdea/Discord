# Discord Microservice

Microservicio del ecosistema **SecuBot-UdeA** responsable de la integración con Discord. Mantiene una conexión permanente al Discord Gateway, expone endpoints HTTP para recibir notificaciones y acciones desde `jug-eared`, y registra slash commands para que los usuarios interactúen directamente desde Discord.

---

## Rol en la arquitectura

```
jug-eared ──► POST /webhook/notify  ──► Discord (canal del equipo o DM al usuario)
jug-eared ──► POST /webhook/action  ──► Discord ──► POST ROUTING_SERVICE_URL (jug-eared /rescan/)

Usuario Discord  ──► /rescan {alert_id}  ──► Discord ──► POST ROUTING_SERVICE_URL
```

---

## Responsabilidades

- Mantener conexión persistente con Discord Gateway (con backoff exponencial ante desconexiones).
- Registrar slash commands `/status` y `/rescan` en los servidores donde el bot está instalado.
- Crear y almacenar webhooks automáticamente al unirse a un nuevo servidor (`on_guild_join`).
- Recibir notificaciones de `jug-eared` y despacharlas al canal del equipo o por DM según `points_awarded`.
- Recibir acciones de usuarios y reenviarlas a `jug-eared` para su procesamiento.
- Deduplicar notificaciones duplicadas en ventana de 30 segundos.
- Registrar trazas de todas las entregas en `webhooks_log`.

---

## Endpoints HTTP

### `POST /webhook/notify`

Recibe una notificación desde `jug-eared` y la entrega en Discord.

**Destino del mensaje:**
- `points_awarded == false` → DM al `user_id` (requiere `user_id`).
- Cualquier otro caso → canal del equipo vía webhook almacenado (requiere `guild_id` o `team_id` en `team_guild_map.json`).

**Body (`NotifyWebhookPayload`):**
```json
{
  "team_id": "team-001",
  "guild_id": "1493710263353086043",
  "user_id": "987654321",
  "alert_id": "dependabot-pangoaguirre-learndependabot-12",
  "title": "CVE-2024-XXXX en lodash",
  "severity": "high",
  "status": "fixed",
  "component": "lodash",
  "location": "package.json",
  "source_type": "dependabot",
  "team_name": "Equipo Alpha",
  "points_awarded": true,
  "message_content": null,
  "embed_data": null
}
```

Los campos `message_content` y `embed_data` son opcionales. Si no se proveen, el servicio los construye a partir de `title`, `severity`, `status`, `component`, `location`, `source_type` y `team_name`. El embed incluye color e ícono según severidad:

| Severidad | Color | Ícono |
|---|---|---|
| `low` | Verde | 🟢 |
| `medium` | Naranja | 🟠 |
| `high` | Rojo | 🔴 |
| `informational` | Gris | ℹ️ |
| Otros | Gris | ⚪ |

**Deduplicación:** notificaciones con el mismo fingerprint (combinación de todos los campos del payload) dentro de 30 segundos se descartan y quedan registradas como `deduplicated` en `webhooks_log`.

**Respuestas:**
- `200 {"status": "delivered"}` — entregado
- `200 {"status": "duplicate_ignored"}` — deduplicado
- `500` — error de entrega

---

### `POST /webhook/action`

Recibe una acción de `jug-eared` y la reenvía a `ROUTING_SERVICE_URL`.

**Body (`ActionWebhookPayload`):**
```json
{
  "action": "rescan",
  "alert_id": "dependabot-pangoaguirre-learndependabot-12",
  "guild_id": "1493710263353086043",
  "user_id": "987654321"
}
```

**Respuestas:**
- `200 {"status": "delivered"}` — reenviado correctamente
- `200 {"status": "queued"}` — `ROUTING_SERVICE_URL` no configurado
- `500` — error de reenvío

---

### `GET /health`

```json
{
  "status": "healthy",
  "bot_connected": true,
  "database_connected": true,
  "timestamp": "2026-01-01T00:00:00+00:00"
}
```

`status` es `healthy` solo si tanto el Gateway como la base de datos están conectados. En cualquier otro caso es `degraded`.

---

## Slash commands

### `/status`

Responde con un mensaje efímero confirmando que el bot está operativo.

### `/rescan [alert_id] [user_id?]`

Solicita el reescaneo de una alerta. El bot construye un `ActionWebhookPayload` con `action: "rescan"` y lo envía a `ROUTING_SERVICE_URL` (→ `jug-eared /rescan/`). Si no se provee `user_id`, se usa el ID del usuario que ejecutó el comando.

---

## Eventos del Gateway

| Evento | Acción |
|---|---|
| `on_ready` | Log de conexión |
| `on_guild_join` | Crea webhook en el primer canal con permisos y lo persiste en BD |
| `on_guild_remove` | Marca el servidor como inactivo en BD |

---

## `team_guild_map.json`

Mapeo estático de `team_id` → `guild_id` de Discord. Se usa como fallback cuando el payload de `/webhook/notify` no incluye `guild_id` explícito.

```json
{
  "team-001": "1493710263353086043",
  "grand-noir-hotel": "1493710263353086043"
}
```

El archivo se busca primero en `app/team_guild_map.json` y luego en la raíz del repositorio. Si no se encuentra, el servicio falla al arrancar.

---

## Variables de entorno

| Variable | Requerida | Default | Descripción |
|---|---|---|---|
| `DISCORD_BOT_TOKEN` | Sí | — | Token del bot en Discord Developer Portal |
| `DATABASE_URL` | No | `memory://local` | URI MongoDB Atlas. Sin configurar, usa backend en memoria (datos no persisten entre reinicios) |
| `ROUTING_SERVICE_URL` | Sí (producción) | `null` | URL del endpoint de `jug-eared` al que reenviar acciones, ej. `http://jug-eared/rescan/` |
| `HTTP_PORT` | No | `8000` | Puerto del servidor HTTP |
| `DISCORD_LOG_LEVEL` | No | `INFO` | Nivel de logging |
| `ENVIRONMENT` | No | `development` | `development` o `production` |
| `ALLOWED_ORIGINS` | No | `""` | CSV de orígenes CORS permitidos |

---

## Instalación y ejecución local

```bash
git clone https://github.com/SecuBotUdea/Discord.git
cd Discord

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # completar con valores reales
python main.py
```

> Sin `DATABASE_URL` configurado el servicio arranca con backend en memoria. Los webhooks de servidores registrados se pierden al reiniciar.

---

## Tests

```bash
pytest -q
```

---

## Despliegue con Docker Compose (DigitalOcean / VPS)

```bash
docker compose up -d --build
```

Verificar:
```bash
docker compose ps
docker compose logs -f
curl http://localhost:8000/health
```

El bot necesita una sola instancia conectada al Gateway. Usar `restart: unless-stopped` garantiza recuperación ante reinicios del host.

---

## Despliegue en Kubernetes

Los manifiestos base están en `k8s/`:

```
k8s/
├── configmap.yaml          # variables no sensibles
├── secret.example.yaml     # plantilla de secretos
├── deployment.yaml         # 1 réplica, strategy: Recreate
├── service.yaml            # ClusterIP interno
└── ingress.yaml            # exposición opcional por dominio
```

Pasos:

```bash
# 1. Build y push de imagen
docker build -t your-registry/discord-ms:latest .
docker push your-registry/discord-ms:latest

# 2. Crear secretos
kubectl -n discord create secret generic discord-ms-secrets \
  --from-literal=DISCORD_BOT_TOKEN="tu_token" \
  --from-literal=DATABASE_URL="mongodb+srv://..."

# 3. Aplicar manifiestos
kubectl -n discord apply -f k8s/configmap.yaml
kubectl -n discord apply -f k8s/deployment.yaml
kubectl -n discord apply -f k8s/service.yaml

# 4. Verificar
kubectl -n discord get pods
kubectl -n discord logs deploy/discord-ms
```

**Importante:** mantener `replicas: 1` y `strategy: Recreate`. Dos réplicas simultáneas del bot generan conexiones duplicadas al Gateway y duplican la entrega de mensajes.

---

## Estructura del proyecto

```
app/
├── config/
│   ├── settings.py            # Settings (pydantic-settings)
│   └── team_guild_map.py      # Carga team_guild_map.json
├── core/
│   └── bot.py                 # DiscordGatewayBot, slash commands, run_bot_with_backoff
├── database/
│   └── connection.py          # DatabaseManager, InMemory/Mongo repos
├── models/
│   └── server.py              # ServerRecord
├── schemas/
│   └── common.py              # NotifyWebhookPayload, ActionWebhookPayload, HealthResponse
├── services/
│   ├── routing_service.py     # POST a ROUTING_SERVICE_URL
│   └── webhook_service.py     # process_notify, process_action, deduplicación
└── http.py                    # FastAPI app factory
team_guild_map.json
main.py                        # asyncio.gather(uvicorn, bot gateway)
```

---

## Notas

- El proceso corre `uvicorn` y el Discord Gateway en paralelo con `asyncio.gather`. Si cualquiera de los dos falla, el proceso termina.
- La deduplicación de notificaciones (`_recent_notify_fingerprints`) es en memoria por proceso, no se comparte entre reinicios ni instancias.
- Si `DATABASE_URL` falla al conectar, el servicio arranca igualmente con backend en memoria y loguea una advertencia. Los webhooks creados en ese modo se pierden al reiniciar.