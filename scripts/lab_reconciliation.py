"""Valida uma janela real, falha e reexecução da DAG do laboratório."""
import json
from datetime import datetime, timedelta, timezone
import subprocess

from lab_incident import COMPOSE, ROOT


AIRFLOW = [*COMPOSE, "-f", "deploy/compose.airflow.yml", "run", "--rm", "airflow", "airflow"]


def run(*args):
    return subprocess.run([*AIRFLOW, *args], cwd=ROOT, timeout=600)


def validate():
    run("db", "migrate").check_returncode()
    start = datetime.now(timezone.utc) - timedelta(minutes=10)
    end = start + timedelta(hours=1)
    config = {"start": start.isoformat(), "end": end.isoformat()}
    directory = "__".join(config.values()).replace(":", "")
    report = f"/opt/airflow/reconciliation/{directory}/report.json"

    def execute(window):
        return run("dags", "test", "payment_reconciliation", start.isoformat(),
                   "--conf", json.dumps(window))

    if execute({"start": config["end"], "end": config["start"]}).returncode == 0:
        raise RuntimeError("Uma janela inválida foi aceita pelo Airflow")
    output = ROOT / "reports" / "lab-reconciliation.json"
    output.parent.mkdir(exist_ok=True)
    previous = None
    for _ in range(2):
        execute(config).check_returncode()
        read = subprocess.run(
            [*AIRFLOW[:-1], "bash", "-c", 'cat "$1"', "read-report", report],
            cwd=ROOT, check=True, capture_output=True, timeout=120,
        )
        current = json.loads(read.stdout[read.stdout.index(b"{"):])
        if current["matched"] < 1:
            raise RuntimeError("A DAG não encontrou o pagamento do teste de recuperação")
        if current != previous and previous is not None:
            raise RuntimeError("A reexecução mudou os resultados da mesma janela")
        previous = current
    output.write_text(json.dumps(previous, indent=2), encoding="utf-8")
    print(f"Falha e reexecução da DAG verificadas: {output}")


if __name__ == "__main__":
    validate()
