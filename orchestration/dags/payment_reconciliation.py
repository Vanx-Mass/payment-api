from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.exceptions import AirflowFailException
from airflow.sdk import dag, get_current_context, task
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import reconciliation as data


@dag(
    dag_id="payment_reconciliation",
    schedule="0 0 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(seconds=15),
                  "execution_timeout": timedelta(minutes=2)},
    tags=["payments", "lab"],
)
def payment_reconciliation():
    @task.sensor(poke_interval=10, timeout=120, mode="reschedule")
    def aguardar_origens():
        engine = data.connect()
        try:
            with engine.connect() as db:
                db.execute(text("SELECT 1 FROM pagamentos LIMIT 1"))
            return data.gateway_request("/health")["status"] == "ok"
        except (OSError, SQLAlchemyError):
            return False
        finally:
            engine.dispose()

    @task
    def extrair():
        context = get_current_context()
        config = context["dag_run"].conf or {}
        start = config.get("start")
        end = config.get("end")
        if bool(start) != bool(end):
            raise AirflowFailException("Informe start e end juntos")
        try:
            start = pendulum.parse(start).in_timezone("UTC") if start else context["data_interval_start"]
            end = pendulum.parse(end).in_timezone("UTC") if end else context["data_interval_end"]
        except (TypeError, ValueError) as exc:
            raise AirflowFailException("Janela inválida") from exc
        if start is None or end is None or not timedelta(0) < end - start <= timedelta(days=1):
            raise AirflowFailException("Use uma janela UTC positiva de até 24 horas")
        start, end = start.isoformat(), end.isoformat()
        window = f"{start}__{end}".replace(":", "")
        files = Path("/opt/airflow/reconciliation") / window
        provider = data.tracer_for("airflow")
        try:
            with provider.get_tracer(__name__).start_as_current_span("reconciliation.extract"):
                data.write_json(files / "api.json", data.payments(start, end))
                data.write_json(files / "gateway.json", data.gateway_request(
                    "/internal/ledger", {"start": start, "end": end},
                ))
        finally:
            provider.shutdown()
        return {"start": start, "end": end, "directory": str(files)}

    @task
    def conciliar(window):
        files = Path(window["directory"])
        provider = data.tracer_for("airflow")
        try:
            with provider.get_tracer(__name__).start_as_current_span("reconciliation.compare"):
                result = data.compare(data.read_json(files / "api.json"), data.read_json(files / "gateway.json"))
                data.write_json(files / "report.json", {
                    "start": window["start"], "end": window["end"], **result,
                })
                print(f"Relatório de conciliação gravado: {files / 'report.json'}")
        finally:
            provider.shutdown()
        return str(files / "report.json")

    extracted = extrair()
    aguardar_origens() >> extracted
    conciliar(extracted)


payment_reconciliation()
