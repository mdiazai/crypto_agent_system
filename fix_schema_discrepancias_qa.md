# Fix — Discrepancias de schema encontradas en QA del 2026-07-09

## Contexto
El QA del Anexo A2 reveló que el schema real de la DB difiere
del schema que usaron los prompts de construcción.
Los workflows del PM Agent tienen queries con columnas/valores incorrectos.

N8N_API_KEY en /opt/crypto_agent_system/.env
Workflow PM Agent: HlY3gLWuJowyITB9
DB: lab_11mkeys

## Protocolo
1. Diagnóstico — confirmar el schema real antes de modificar
2. Mostrar el diff de cada nodo antes de aplicar
3. Sin commits sin aprobación
4. Un solo PUT con todos los fixes al PM Agent

---

## Diagnóstico previo requerido

```sql
-- Confirmar columnas reales de lab_tasks
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'lab_tasks'
ORDER BY ordinal_position;

-- Confirmar valores reales de status en lab_projects
SELECT DISTINCT status FROM lab_projects;

-- Confirmar valores reales de status en lab_tasks
SELECT DISTINCT status FROM lab_tasks;

-- Confirmar columnas de diagnostics_log
SELECT column_name FROM information_schema.columns
WHERE table_name = 'diagnostics_log'
ORDER BY ordinal_position;

-- Confirmar estructura de la FK entre lab_tasks y lab_projects
SELECT
  kcu.column_name,
  ccu.table_name AS foreign_table,
  ccu.column_name AS foreign_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_name = 'lab_tasks';
```

Reportar output completo antes de continuar.

---

## Fix 1 — /estado: status='activo' → status='active'

### Problema
El nodo SSH Read Estado usa `WHERE status='activo'`
pero los valores reales en lab_projects son `'active'`.
Resultado: /estado muestra `Proyectos activos: 0` siempre.

### Fix en nodo SSH Read Estado
Cambiar la query de conteo de proyectos:

```sql
-- ANTES (incorrecto)
SELECT COUNT(*) FROM lab_projects WHERE status='activo';

-- DESPUÉS (correcto)
SELECT COUNT(*) FROM lab_projects WHERE status='active';
```

---

## Fix 2 — /tareas: columna proyecto → project_id con JOIN

### Problema
lab_tasks no tiene columna `proyecto` (texto).
Tiene `project_id` (FK a lab_projects.id).
Queries que usen `WHERE proyecto='crypto_agent'` fallan.

### Fix en nodo Q Tareas
```sql
-- ANTES (incorrecto)
SELECT id, title, status, proyecto, created_at::date
FROM lab_tasks
WHERE status NOT IN ('done','cancelada')
ORDER BY created_at DESC;

-- DESPUÉS (correcto — con JOIN a lab_projects)
SELECT
  t.id,
  t.title,
  t.status,
  p.nombre as proyecto,
  t.created_at::date as creado,
  t.due_date::date as vence
FROM lab_tasks t
LEFT JOIN lab_projects p ON t.project_id = p.id
WHERE t.status NOT IN ('done','open_blocked')
ORDER BY t.created_at DESC;
```

### Fix en nodo Q Proyectos (para /proyectos con tareas)
```sql
SELECT
  p.nombre,
  p.titulo,
  p.status,
  p.fase,
  p.bloqueante,
  p.actualizado_en::date as actualizado,
  COUNT(t.id) as num_tareas,
  STRING_AGG('#' || t.id::text || ' ' || t.title, ' | ') as tareas
FROM lab_projects p
LEFT JOIN lab_tasks t
  ON t.project_id = p.id
  AND t.status NOT IN ('done')
WHERE p.nombre != '11mkeys_lab'
  AND p.status = 'active'
GROUP BY p.nombre, p.titulo, p.status, p.fase,
         p.bloqueante, p.actualizado_en
ORDER BY p.nombre;
```

---

## Fix 3 — /nueva: insertar con project_id en vez de proyecto texto

### Problema
El nodo Insert Task hace INSERT con columna `proyecto`
que no existe. Debe usar `project_id` con un lookup previo.

### Fix en nodo Insert Task
```sql
-- ANTES (incorrecto)
INSERT INTO lab_tasks (title, status, proyecto, created_at)
VALUES ('{title}', 'pendiente', '{proyecto}', NOW())
RETURNING id, title, proyecto;

-- DESPUÉS (correcto — lookup de project_id)
INSERT INTO lab_tasks (title, status, project_id, created_at)
SELECT
  '{title}',
  'open',
  p.id,
  NOW()
FROM lab_projects p
WHERE p.nombre = '{proyecto}'
RETURNING id, title,
  (SELECT nombre FROM lab_projects WHERE id=project_id) as proyecto;
```

Si el proyecto no existe, el INSERT devuelve 0 rows.
El nodo Fmt Nueva OK debe manejar ese caso:
"⚠️ Proyecto '{proyecto}' no encontrado. Tarea asignada a 11mkeys_lab."
Con fallback:
```sql
INSERT INTO lab_tasks (title, status, project_id, created_at)
SELECT '{title}', 'open', id, NOW()
FROM lab_projects WHERE nombre='11mkeys_lab'
RETURNING id;
```

---

## Fix 4 — /done: status 'pendiente' → 'done' (verificar valor actual)

### Problema
El UPDATE en nodo Update Done cambia status a 'done'.
Pero si el status actual es 'open' (no 'pendiente'),
puede que la query tenga una condición WHERE status='pendiente'
que impide el update.

### Fix en nodo Update Done
```sql
-- ANTES (posiblemente incorrecto)
UPDATE lab_tasks SET status='done'
WHERE id={id} AND status='pendiente';

-- DESPUÉS (correcto — sin condición de status previo)
UPDATE lab_tasks SET status='done'
WHERE id={id}
RETURNING id, title, status;
```

---

## Fix 5 — SmartDevops: created_at → run_at en diagnostics_log

### Problema
El nodo SSH del SmartDevops que lee diagnostics_log
puede usar `ORDER BY created_at` cuando la columna real es `run_at`.

### Verificar y corregir en workflow SmartDevops
Buscar cualquier query que referencie `diagnostics_log`
y cambiar `created_at` por `run_at`:

```sql
-- ANTES
SELECT diagnosis, created_at FROM diagnostics_log
ORDER BY created_at DESC LIMIT 3;

-- DESPUÉS
SELECT diagnosis, run_at FROM diagnostics_log
ORDER BY run_at DESC LIMIT 3;
```

---

## Fix 6 — Weekly Board: trigger via n8n UI, no REST API

### Problema
`POST /api/v1/workflows/{id}/run` devuelve 405.
El Weekly Board no es activable via REST en esta versión de n8n.

### Solución
Para ejecución manual del Weekly Board usar el endpoint correcto:

```bash
# Método correcto para esta versión de n8n
curl -s -X POST \
  "https://n8n.11mkeys.ai/rest/workflows/rJzmIz9h7XHDymGB/run" \
  -H "Content-Type: application/json" \
  -b "$(cat /tmp/n8n_session_cookie 2>/dev/null || echo '')" \
  -d '{}'
```

O bien via login programático:
```bash
# Obtener sesión
curl -s -X POST "https://n8n.11mkeys.ai/rest/login" \
  -H "Content-Type: application/json" \
  -d '{"emailOrLdapLoginId":"admin@11mkeys.ai","password":"[password]"}' \
  -c /tmp/n8n_session_cookie

# Ejecutar workflow
curl -s -X POST "https://n8n.11mkeys.ai/rest/workflows/rJzmIz9h7XHDymGB/run" \
  -H "Content-Type: application/json" \
  -b /tmp/n8n_session_cookie \
  -d '{}'
```

Actualizar el caso de uso 5.7 en el documento de QA con el endpoint correcto.

---

## Actualizar el documento de QA

Una vez aplicados los fixes, actualizar el archivo
`verificacion_y_reporte_casos_uso.md` con:

1. En CASO 1.1: cambiar query de `status='activo'` a `status='active'`
2. En CASO 1.2: cambiar query de `proyecto` a JOIN con `project_id`
3. En CASO 1.3: cambiar INSERT para usar `project_id`
4. En CASO 1.4: cambiar condición del UPDATE
5. En CASO 5.4: cambiar `created_at` a `run_at` en diagnostics_log
6. En CASO 5.7: actualizar endpoint del Weekly Board

---

## Verificación post-fix

```sql
-- 1. /estado debe mostrar 4 proyectos activos
SELECT COUNT(*) FROM lab_projects WHERE status='active';
-- Esperado: 4

-- 2. /tareas debe devolver tareas con nombre de proyecto
SELECT t.id, t.title, t.status, p.nombre as proyecto
FROM lab_tasks t
LEFT JOIN lab_projects p ON t.project_id = p.id
WHERE t.status != 'done'
ORDER BY t.created_at DESC LIMIT 5;

-- 3. diagnostics_log con columna correcta
SELECT LEFT(diagnosis,80), run_at
FROM diagnostics_log
ORDER BY run_at DESC LIMIT 3;
```

Simular /estado via Telegram y confirmar que muestra
`Proyectos activos: 4` (no 0).
