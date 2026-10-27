# Microservicio de Candidatos

Proyecto CRM de Empleabilidad — CS2032.
Responsable: Santiago Davila.

## Tecnologías

- AWS Lambda con Python 3.11.
- API Gateway.
- DynamoDB.
- S3 para CV privados.
- Serverless Framework v3.

## API desplegada en dev

https://4kl8vspasb.execute-api.us-east-1.amazonaws.com/dev

Todas las rutas requieren:

Authorization: Bearer <token>

El token se obtiene mediante el servicio de Usuarios:

POST https://pglyu1afmg.execute-api.us-east-1.amazonaws.com/dev/usuarios/login

Body de login:

```json
{
  "tenant_id": "tenant_1",
  "email": "EMAIL_REGISTRADO",
  "password": "PASSWORD"
}
```

## Rutas

| Método | Ruta | Operación |
|---|---|---|
| GET | /candidatos | Listar candidatos de la empresa |
| POST | /candidatos | Crear candidato |
| GET | /candidatos/{candidato_id} | Buscar candidato |
| PUT | /candidatos/{candidato_id} | Modificar candidato |
| DELETE | /candidatos/{candidato_id} | Eliminar candidato |
| POST | /candidatos/{candidato_id}/cv-url | Solicitar subida o confirmar CV |

## Ejemplos con curl

Configurar en la terminal:

```bash
API='https://4kl8vspasb.execute-api.us-east-1.amazonaws.com/dev'
TOKEN='REEMPLAZAR_CON_TOKEN'
CANDIDATO_ID='REEMPLAZAR_CON_ID'
```

Crear:

```bash
curl -X POST "$API/candidatos" \
-H "Authorization: Bearer $TOKEN" \
-H 'Content-Type: application/json' \
-d '{"nombre":"Ana Torres","email":"ana@example.com","telefono":"999333444","profesion":"Ingeniera"}'
```

Respuesta: HTTP 201 y `{"candidato": {...}}`.

Listar:

```bash
curl "$API/candidatos" -H "Authorization: Bearer $TOKEN"
```

Respuesta: HTTP 200 y `{"candidatos":[...],"ultimo_id":null}`.

Cada consulta devuelve hasta 100 candidatos.
Si ultimo_id contiene un valor, solicitar la siguiente página:

```bash
curl "$API/candidatos?ultimo_id=ULTIMO_ID" \
-H "Authorization: Bearer $TOKEN"
```

Buscar:

```bash
curl "$API/candidatos/$CANDIDATO_ID" \
-H "Authorization: Bearer $TOKEN"
```

Respuesta: HTTP 200 y `{"candidato": {...}}`.

Modificar:

```bash
curl -X PUT "$API/candidatos/$CANDIDATO_ID" \
-H "Authorization: Bearer $TOKEN" \
-H 'Content-Type: application/json' \
-d '{"telefono":"900111222","estado":"inactivo"}'
```

Campos modificables: nombre, email, telefono, profesion, estado.
Estados permitidos: activo, inactivo.
Respuesta: HTTP 200, mensaje y candidato actualizado.

Eliminar:

```bash
curl -X DELETE "$API/candidatos/$CANDIDATO_ID" \
-H "Authorization: Bearer $TOKEN"
```

Respuesta: HTTP 200 y `{"mensaje":"Candidato eliminado"}`.

## Subida de CV

1. Solicitar enlace:

```bash
curl -X POST "$API/candidatos/$CANDIDATO_ID/cv-url" \
-H "Authorization: Bearer $TOKEN" \
-H 'Content-Type: application/json' \
-d '{}'
```

Respuesta: url_subida, key y expira_en_segundos.
El enlace dura 300 segundos.

2. Subir un PDF al enlace recibido:

```bash
curl -X PUT 'URL_SUBIDA_RECIBIDA' \
-H 'Content-Type: application/pdf' \
--data-binary @cv_prueba.pdf
```

Respuesta de S3: HTTP 200.

3. Confirmar la subida:

```bash
curl -X POST "$API/candidatos/$CANDIDATO_ID/cv-url" \
-H "Authorization: Bearer $TOKEN" \
-H 'Content-Type: application/json' \
-d '{"confirmar":true}'
```

Respuesta: HTTP 200, mensaje "CV registrado" y cv_url.
La función comprueba que el archivo exista antes de guardar cv_url.
cv_url almacena la clave del archivo, no una dirección pública.
Los archivos quedan privados en S3.
La implementación actual admite CV en PDF.

## Diseño de DynamoDB

Tabla: t_candidatos-<stage>.
Clave de partición: tenant_id, string.
Clave de ordenación: candidato_id, string UUID4.

Ejemplo completo:

```json
{
  "tenant_id": "tenant_1",
  "candidato_id": "a8ecdea6-fd60-4045-81be-32ec8dc51921",
  "nombre": "Ana Torres",
  "email": "ana.candidata@example.com",
  "telefono": "999333444",
  "profesion": "Ingeniera de sistemas",
  "cv_url": "tenant_1/a8ecdea6-fd60-4045-81be-32ec8dc51921/cv.pdf",
  "estado": "activo",
  "fecha_registro": "2026-10-27T02:22:46.322606+00:00"
}
```

## Separación de empresas

tenant_id se obtiene exclusivamente del token.
Los valores enviados por el cliente no cambian la empresa de la operación.
Cada consulta usa tenant_id como parte de la clave.
La ruta del CV incluye tenant_id y candidato_id.

## Variables de entorno

| Variable | Valor |
|---|---|
| CANDIDATOS_TABLE | t_candidatos-<stage> |
| TOKENS_TABLE | t_tokens_acceso-<stage> |
| BUCKET_CVS | Referencia al bucket creado por Serverless |

Bucket: cs2032-candidatos-cv-<cuenta AWS>-<stage>.

## Despliegue

Desde la carpeta del proyecto:

```bash
serverless deploy --stage dev
```

Región: us-east-1.
Se usa LabRole de AWS Academy.
El servicio de Usuarios debe existir en la misma cuenta y stage.
Sus tokens deben estar en t_tokens_acceso-<stage>.

## Datos ficticios

Dependencias locales:

```bash
pip3 install boto3 faker
```

Carga:

```bash
python3 scripts/cargar_datos.py
```

El programa carga 10000 candidatos por empresa:
tenant_1, tenant_2 y tenant_3.
Total: 30000 candidatos ficticios en t_candidatos-dev.
Usa batch_writer y Faker en español es_ES.

La carga ya se ejecutó.
Ejecutarla otra vez agrega otros 30000 candidatos.
Los candidatos creados manualmente se conservan.

## Resultados comprobados en dev

- Crear, listar, buscar, modificar y eliminar.
- Rechazo sin token: HTTP 401.
- Búsqueda después de eliminar: HTTP 404.
- tenant_2 no puede consultar al candidato de tenant_1.
- Creación de candidatos en tenant_1 y tenant_2.
- Carga finalizada de 30000 candidatos ficticios.
- Subida de PDF a S3.
- Confirmación del CV y actualización de cv_url.

## Errores de la API

- 400: datos inválidos o CV pendiente de subir.
- 401: token ausente, inválido o expirado.
- 404: candidato inexistente dentro de la empresa.
