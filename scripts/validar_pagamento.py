import os
import sys
import uuid

import httpx

expected = int(sys.argv[1]) if len(sys.argv) > 1 else 201
base_url = os.getenv("BASE_URL", "http://localhost:8000")
identifier = uuid.uuid4().hex

with httpx.Client(base_url=base_url, timeout=45) as client:
    registration = client.post("/auth/registro", json={
        "nome": "Teste Dia 1",
        "email": f"dia1-{identifier}@example.com",
        "senha": "senha-local-dia1",
    })
    registration.raise_for_status()

    token = registration.json()["token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": identifier,
    }
    payload = {
        "valor": 25,
        "descricao": "Pagamento de teste",
    }

    response = client.post(
        "/pagamentos", headers=headers, json=payload
    )

    print(f"HTTP {response.status_code}: {response.text}")
    assert response.status_code == expected, (
        f"Esperado HTTP {expected}"
    )

    if expected == 201:
        replay = client.post(
            "/pagamentos", headers=headers, json=payload
        )
        assert replay.status_code == 201
        assert replay.json() == response.json()
        print("Mesma chave retornou o mesmo pagamento.")