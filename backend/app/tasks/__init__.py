from celery import Celery

from app.config import settings

celery_app = Celery("cap", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_serializer = "json"
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    task_publish_retry=False,
    broker_connection_timeout=2,
    broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
)

# Import tasks to register them
from app.tasks import extraction  # noqa: F401, E402

from app.tasks import requirement_quality  # noqa: F401, E402
