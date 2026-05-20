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

## Contratos con Gloria

El microservicio usa dos contratos separados para evitar mezclar origen y destino de los eventos.

### 1. Discord -> Gloria: `action`

Se usa cuando un usuario ejecuta una acción en Discord, por ejemplo `/rescan`.

Entrada esperada:

```json
{
  "action": "rescan",
  "alert_id": "alert_123",
  "guild_id": "123456789",
  "user_id": "user_456"
}
```

Propósito:

- Gloria recibe la acción.
- Gloria valida reglas de negocio.
- Gloria decide si el rescan es válido o no.

### 2. Gloria -> Discord: `notify`

Se usa para notificar el resultado final al servidor de Discord.

Entrada esperada:

```json
{
  "guild_id": "123456789",
  "channel_id": "987654321",
  "message_content": "Rescan válido para alert_123",
  "embed_data": {
    "title": "Rescan aprobado",
    "description": "La solicitud fue validada por Gloria"
  },
  "source": "gloria",
  "event_type": "rescan_valid"
}
```

Ejemplo para rescan no válido:

```json
{
  "guild_id": "123456789",
  "channel_id": "987654321",
  "message_content": "Rescan rechazado para alert_123",
  "embed_data": {
    "title": "Rescan rechazado",
    "description": "La solicitud no cumple las condiciones requeridas"
  },
  "source": "gloria",
  "event_type": "rescan_invalid"
}
```

Propósito:

- Gloria informa el resultado.
- Discord publica el mensaje en el servidor usando el webhook almacenado.

### Contrato recomendado para Gloria

Si Gloria va a decidir si un rescan es válido o no, lo más recomendable es separar el flujo en dos eventos:

1. `action` para recibir la intención del usuario.
2. `notify` para devolver el resultado visible al servidor.

Eso mantiene el diseño simple y evita mezclar validación de negocio con entrega de mensajes.

## Testing

```bash
pytest -q
```

## Deployment (plan gratuito)

Compatible con Render, Railway, Replit y DigitalOcean App Platform usando `python main.py` como comando de inicio y variables de entorno configuradas en la plataforma.

## Deployment en Kubernetes

Este repositorio ya incluye una base de despliegue en `k8s/`.

### Archivos incluidos

- `Dockerfile`: construye la imagen del servicio.
- `k8s/configmap.yaml`: configuración no sensible.
- `k8s/secret.example.yaml`: ejemplo de secretos.
- `k8s/deployment.yaml`: despliegue con 1 réplica.
- `k8s/service.yaml`: servicio interno del clúster.
- `k8s/ingress.yaml`: exposición opcional por dominio.

### Paso a paso

1. Construye la imagen localmente.

```bash
docker build -t discord-ms:latest .
```

2. Sube la imagen a tu registry.

```bash
docker tag discord-ms:latest your-registry/discord-ms:latest
docker push your-registry/discord-ms:latest
```

3. Crea el namespace si vas a aislar el servicio.

```bash
kubectl create namespace discord
```

4. Crea el secret real con tus valores.

```bash
kubectl -n discord create secret generic discord-ms-secrets \
  --from-literal=DISCORD_BOT_TOKEN="tu_token" \
  --from-literal=DATABASE_URL="mongodb+srv://..."
```

5. Aplica el ConfigMap.

```bash
kubectl -n discord apply -f k8s/configmap.yaml
```

6. Aplica el Deployment y el Service.

```bash
kubectl -n discord apply -f k8s/deployment.yaml
kubectl -n discord apply -f k8s/service.yaml
```

7. Si quieres exposición pública, aplica el Ingress y ajusta el host.

```bash
kubectl -n discord apply -f k8s/ingress.yaml
```

8. Verifica que el pod esté arriba.

```bash
kubectl -n discord get pods
kubectl -n discord logs deploy/discord-ms
```

### Conexión entre componentes

Para que Discord funcione en Kubernetes necesitas estas conexiones:

- `DISCORD_BOT_TOKEN` debe apuntar al bot registrado en Discord Developer Portal.
- `DATABASE_URL` debe apuntar a MongoDB Atlas o a tu Mongo interno.
- `ROUTING_SERVICE_URL` debe apuntar al servicio Gloria dentro del clúster o a una URL externa.
- El puerto interno del contenedor debe coincidir con `HTTP_PORT`.
- El health check debe responder en `GET /health`.

### Recomendación operativa

- Mantén `replicas: 1` para evitar dos conexiones del bot al Gateway.
- No publiques el bot directamente al exterior salvo por HTTP/Ingress.
- Usa secretos para credenciales y ConfigMap para valores no sensibles.
