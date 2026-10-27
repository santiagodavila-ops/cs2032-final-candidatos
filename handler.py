import json
import os
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")


def _respuesta(codigo, datos):
    return {
        "statusCode": codigo,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(datos, default=str),
    }


def validar_token(event):
    headers = event.get("headers") or {}
    auth_header = headers.get("Authorization") or headers.get("authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return None, _respuesta(401, {"error": "Token no enviado"})

    token = auth_header.replace("Bearer ", "").strip()
    tabla_tokens = dynamodb.Table(os.environ["TOKENS_TABLE"])
    item = tabla_tokens.get_item(Key={"token": token}).get("Item")

    if not item:
        return None, _respuesta(401, {"error": "Token inválido"})

    if datetime.now(timezone.utc).isoformat() > item["fecha_expiracion"]:
        return None, _respuesta(401, {"error": "Token expirado"})

    return item["tenant_id"], None


def _tabla():
    return dynamodb.Table(os.environ["CANDIDATOS_TABLE"])


def _leer_body(event):
    try:
        datos = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return None, _respuesta(400, {"error": "El contenido no es JSON válido"})

    if not isinstance(datos, dict):
        return None, _respuesta(400, {"error": "Se esperaba un objeto JSON"})

    return datos, None


def _clave(event, tenant_id):
    candidato_id = (event.get("pathParameters") or {}).get("candidato_id")
    if not candidato_id:
        return None, _respuesta(400, {"error": "Falta candidato_id"})

    return {
        "tenant_id": tenant_id,
        "candidato_id": candidato_id,
    }, None


def listar_candidatos(event, context):
    tenant_id, error = validar_token(event)
    if error:
        return error

    parametros = event.get("queryStringParameters") or {}
    consulta = {
        "KeyConditionExpression": Key("tenant_id").eq(tenant_id),
        "Limit": 100,
    }

    ultimo_id = parametros.get("ultimo_id")
    if ultimo_id:
        consulta["ExclusiveStartKey"] = {
            "tenant_id": tenant_id,
            "candidato_id": ultimo_id,
        }

    resultado = _tabla().query(**consulta)
    siguiente = resultado.get("LastEvaluatedKey", {}).get("candidato_id")

    return _respuesta(200, {
        "candidatos": resultado["Items"],
        "ultimo_id": siguiente,
    })


def crear_candidato(event, context):
    tenant_id, error = validar_token(event)
    if error:
        return error

    datos, error = _leer_body(event)
    if error:
        return error

    obligatorios = ("nombre", "email", "telefono", "profesion")
    for campo in obligatorios:
        if not isinstance(datos.get(campo), str) or not datos[campo].strip():
            return _respuesta(400, {"error": f"Falta un valor válido para {campo}"})

    candidato = {
        "tenant_id": tenant_id,
        "candidato_id": str(uuid.uuid4()),
        "nombre": datos["nombre"].strip(),
        "email": datos["email"].strip(),
        "telefono": datos["telefono"].strip(),
        "profesion": datos["profesion"].strip(),
        "cv_url": "",
        "estado": "activo",
        "fecha_registro": datetime.now(timezone.utc).isoformat(),
    }

    _tabla().put_item(Item=candidato)
    return _respuesta(201, {"candidato": candidato})


def buscar_candidato(event, context):
    tenant_id, error = validar_token(event)
    if error:
        return error

    clave, error = _clave(event, tenant_id)
    if error:
        return error

    candidato = _tabla().get_item(
        Key=clave,
        ConsistentRead=True,
    ).get("Item")

    if not candidato:
        return _respuesta(404, {"error": "Candidato no encontrado"})

    return _respuesta(200, {"candidato": candidato})


def modificar_candidato(event, context):
    tenant_id, error = validar_token(event)
    if error:
        return error

    clave, error = _clave(event, tenant_id)
    if error:
        return error

    datos, error = _leer_body(event)
    if error:
        return error

    permitidos = ("nombre", "email", "telefono", "profesion", "estado")
    cambios = {campo: datos[campo] for campo in permitidos if campo in datos}

    if not cambios:
        return _respuesta(400, {"error": "No hay campos válidos para modificar"})

    for campo, valor in cambios.items():
        if not isinstance(valor, str) or not valor.strip():
            return _respuesta(400, {"error": f"Valor inválido para {campo}"})
        cambios[campo] = valor.strip()

    if "estado" in cambios and cambios["estado"] not in ("activo", "inactivo"):
        return _respuesta(400, {"error": "Estado permitido: activo o inactivo"})

    nombres = {}
    valores = {}
    asignaciones = []

    for numero, (campo, valor) in enumerate(cambios.items()):
        nombre = f"#campo{numero}"
        parametro = f":valor{numero}"
        nombres[nombre] = campo
        valores[parametro] = valor
        asignaciones.append(f"{nombre} = {parametro}")

    try:
        resultado = _tabla().update_item(
            Key=clave,
            UpdateExpression="SET " + ", ".join(asignaciones),
            ExpressionAttributeNames=nombres,
            ExpressionAttributeValues=valores,
            ConditionExpression="attribute_exists(candidato_id)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _respuesta(404, {"error": "Candidato no encontrado"})
        raise

    return _respuesta(200, {
        "mensaje": "Candidato modificado",
        "candidato": resultado["Attributes"],
    })


def eliminar_candidato(event, context):
    tenant_id, error = validar_token(event)
    if error:
        return error

    clave, error = _clave(event, tenant_id)
    if error:
        return error

    try:
        _tabla().delete_item(
            Key=clave,
            ConditionExpression="attribute_exists(candidato_id)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _respuesta(404, {"error": "Candidato no encontrado"})
        raise

    return _respuesta(200, {"mensaje": "Candidato eliminado"})


def generar_url_subida(event, context):
    tenant_id, error = validar_token(event)
    if error:
        return error

    clave, error = _clave(event, tenant_id)
    if error:
        return error

    tabla = _tabla()
    candidato = tabla.get_item(
        Key=clave,
        ConsistentRead=True,
    ).get("Item")

    if not candidato:
        return _respuesta(404, {"error": "Candidato no encontrado"})

    datos, error = _leer_body(event)
    if error:
        return error

    from botocore.config import Config

    s3 = boto3.client(
        "s3",
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )

    bucket = os.environ["BUCKET_CVS"]
    key = f"{tenant_id}/{clave['candidato_id']}/cv.pdf"

    if datos.get("confirmar") is True:
        try:
            s3.head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return _respuesta(400, {"error": "Primero debes subir el CV"})
            raise

        try:
            tabla.update_item(
                Key=clave,
                UpdateExpression="SET cv_url = :ubicacion",
                ExpressionAttributeValues={":ubicacion": key},
                ConditionExpression="attribute_exists(candidato_id)",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return _respuesta(404, {"error": "Candidato no encontrado"})
            raise

        return _respuesta(200, {
            "mensaje": "CV registrado",
            "cv_url": key,
        })

    url = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": "application/pdf",
        },
        ExpiresIn=300,
    )

    return _respuesta(200, {
        "url_subida": url,
        "key": key,
        "expira_en_segundos": 300,
    })
