# Mi Entrenador Garmin

Bot de entrenador personal de ciclismo. Cada día, vía GitHub Actions:

1. Descarga métricas de recuperación y actividades de ayer desde Garmin Connect.
2. Las guarda en Supabase (`daily_metrics`, `activities`) y calcula el ratio
   carga aguda:crónica (ACWR) en `fatigue_index`.
3. Genera un resumen motivador con Gemini, incluyendo el estado de fatiga.
4. Envía el resumen por Telegram.

Si Supabase falla por cualquier motivo, el bot sigue funcionando y el
mensaje de Telegram se envía igualmente — Supabase nunca es un punto único
de fallo.

## Variables de entorno (GitHub Secrets)

| Variable | Descripción |
|---|---|
| `GARMIN_EMAIL` | Email de la cuenta de Garmin Connect |
| `GARMIN_PASSWORD` | Contraseña de la cuenta de Garmin Connect |
| `GEMINI_API_KEY` | API key de Google AI Studio (Gemini) |
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram |
| `TELEGRAM_CHAT_ID` | Chat ID de Telegram donde se envía el resumen |
| `SUPABASE_URL` | URL del proyecto de Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key de Supabase (bypassa RLS; el bot no tiene sesión de usuario interactiva) |

Todas ya están configuradas como secretos en GitHub Actions con estos
nombres exactos.

## Servicio de envío manual a Garmin (`api/`)

Además del cron diario, este repo despliega en Vercel una función Python
independiente que sube un entrenamiento estructurado a Garmin Connect bajo
demanda -- la usa el botón "Enviar a Garmin" del dashboard de
`mi-entrenador-web`. Vive en `api/` (`send_workout.py` + `workout_builder.py`)
y **no** comparte proceso ni sesión con el cron: cada invocación hace su
propio login nativo con `GARMIN_EMAIL`/`GARMIN_PASSWORD`, igual que `main.py`.

- `POST /api/send_workout` — body `{date, session_type, planned_tss, ftp_watts}`,
  header `Authorization: Bearer <GARMIN_SEND_SECRET>`. Solo soporta
  `session_type` `z2`/`quality` (son los únicos con contenido de potencia
  traducible a un workout de Garmin). Sube el workout con
  `garmin.upload_workout()` y lo programa en `date` con `garmin.schedule_workout()`
  -- el reloj lo sincroniza en su siguiente sync normal con Garmin Connect.
- `workout_builder.py` es una función pura (sin red, sin `garminconnect`) que
  traduce `session_type`/`planned_tss`/`ftp_watts` a un workout sintético de
  ciclismo (bloque continuo Z2, o calentamiento+intervalos+enfriamiento para
  calidad). Las constantes de zona/duración están documentadas ahí y son
  ajustables -- no hay una biblioteca de entrenamientos reutilizables todavía
  en `mi-entrenador-web`, así que por ahora se sintetizan al vuelo.

### Variables de entorno adicionales (Vercel, proyecto de este repo)

| Variable | Descripción |
|---|---|
| `GARMIN_EMAIL` | La misma cuenta que usa el cron (copiar el valor) |
| `GARMIN_PASSWORD` | La misma contraseña que usa el cron (copiar el valor) |
| `GARMIN_SEND_SECRET` | Secreto compartido con `mi-entrenador-web` (env var `GARMIN_SEND_SECRET`, sin prefijo `NEXT_PUBLIC_`, ahí) -- autentica la llamada del dashboard a este endpoint |

Estas variables se configuran en el proyecto Vercel de este repo (no en
GitHub Actions) -- son dos despliegues independientes del mismo código fuente.

## Esquema de Supabase

Proyecto de un solo usuario. El `user_id` usado en todos los inserts está
fijo en `main.py` (`USER_ID`), y coincide con la fila en `profiles`.

- `daily_metrics` — una fila por día (`UNIQUE(user_id, date)`), upsert.
- `activities` — una fila por actividad de Garmin, deduplicada por
  `UNIQUE(user_id, external_id)` donde `external_id` es el `activityId` de
  Garmin (permite varias actividades del mismo tipo el mismo día).
- `fatigue_index` — una fila por día (`UNIQUE(user_id, date)`) con el ACWR
  calculado a partir de `activities.training_load`.
- `workouts`, `strength_sessions`, `ftp_history` — no se escriben todavía
  desde este bot (fases posteriores).

### Cálculo de ACWR

- Carga aguda: media de `training_load` de los últimos 7 días.
- Carga crónica: media de `training_load` de los últimos 28 días.
- `acwr_ratio = carga_aguda / carga_cronica`.
- Recomendación: `normal` (≤1.3), `precaucion` (1.3–1.5), `descanso`
  (>1.5 o sin actividades registradas en los últimos 28 días).

## Próximas fases

- Input de fuerza vía Telegram → `strength_sessions`.
- Peso corporal vía Apple Health / Shortcuts → `daily_metrics.weight_kg`.
- Dashboard en GitHub Pages leyendo Supabase con `anon key` + Supabase Auth.
