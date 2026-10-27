import uuid
from datetime import datetime, timezone

import boto3
from faker import Faker

fake = Faker("es_ES")
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
tabla = dynamodb.Table("t_candidatos-dev")

TENANTS = ["tenant_1", "tenant_2", "tenant_3"]
CANTIDAD_POR_TENANT = 10000

for tenant_id in TENANTS:
    print(f"Iniciando carga: {tenant_id}", flush=True)

    with tabla.batch_writer() as lote:
        for numero in range(1, CANTIDAD_POR_TENANT + 1):
            lote.put_item(Item={
                "tenant_id": tenant_id,
                "candidato_id": str(uuid.uuid4()),
                "nombre": fake.name(),
                "email": fake.unique.email(),
                "telefono": fake.numerify("9########"),
                "profesion": fake.job(),
                "cv_url": "",
                "estado": "activo",
                "fecha_registro": datetime.now(timezone.utc).isoformat(),
            })

            if numero % 1000 == 0:
                print(
                    f"{tenant_id}: {numero}/{CANTIDAD_POR_TENANT}",
                    flush=True,
                )

    print(f"Carga terminada: {tenant_id}", flush=True)

print("Listo: 30000 candidatos ficticios cargados.", flush=True)
