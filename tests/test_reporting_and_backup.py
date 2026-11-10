"""Testes de Geração de Relatório PDF (ReportLab), Logs e Backup SQLite."""

from pathlib import Path
from fastapi.testclient import TestClient


def test_pdf_report_generation_and_backup_endpoints(client: TestClient):
    pdf_resp = client.post("/api/dashboard/report-pdf")
    assert pdf_resp.status_code == 200
    pdf_data = pdf_resp.json()
    assert pdf_data["status"] == "GENERATED"
    assert Path(pdf_data["file_path"]).exists()

    backup_resp = client.post("/api/settings/backup")
    assert backup_resp.status_code == 200
    bkp_data = backup_resp.json()
    assert bkp_data["status"] == "BACKUP_CREATED"
    assert Path(bkp_data["backup_path"]).exists()

    logs_resp = client.get("/api/settings/logs")
    assert logs_resp.status_code == 200
    assert "system_logs" in logs_resp.json()
    assert "audit_logs" in logs_resp.json()

