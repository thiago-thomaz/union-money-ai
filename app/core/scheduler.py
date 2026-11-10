"""Agendador de tarefas nativo em Python com APScheduler (100% autônomo, sem n8n)."""

from typing import Any, Callable, Dict, List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.core.logging import logger


class UnionScheduler:
    """Gerenciador de jobs em segundo plano nativos da aplicação."""

    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self._started = False

    def start(self) -> None:
        """Inicia o agendador caso ainda não esteja em execução."""
        if not self._started and not self.scheduler.running:
            self.scheduler.start()
            self._started = True
            logger.info("Agendador nativo APScheduler iniciado com sucesso.")

    def shutdown(self) -> None:
        """Encerra o agendador de forma limpa."""
        if self._started and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            self._started = False
            logger.info("Agendador nativo APScheduler encerrado.")

    def register_interval_job(
        self,
        job_id: str,
        func: Callable[..., Any],
        minutes: int,
        replace_existing: bool = True,
    ) -> None:
        """Registra um job recorrente por intervalo de minutos."""
        self.scheduler.add_job(
            func,
            trigger=IntervalTrigger(minutes=minutes),
            id=job_id,
            replace_existing=replace_existing,
            max_instances=1,
            coalesce=True,
        )
        logger.info("Job '%s' registrado a cada %d minuto(s).", job_id, minutes)

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Lista todos os jobs registrados e seu próximo horário de execução."""
        jobs_info = []
        for job in self.scheduler.get_jobs():
            next_run = getattr(job, "next_run_time", None)
            jobs_info.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": next_run.isoformat() if next_run else None,
                }
            )
        return jobs_info


union_scheduler = UnionScheduler()

