from celery import Celery
from src.apps.core.config import settings
from src.apps.core.logging import configure_logging

configure_logging()

celery_app = Celery(
    settings.APP_INSTANCE_NAME,
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        'src.apps.core.tasks',
        'src.apps.iam.tasks',
        'src.apps.notification.tasks',
        'src.postbase.tasks',
    ]
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    result_expires=settings.CELERY_RESULT_EXPIRES,
    task_default_queue=settings.CELERY_QUEUE_DEFAULT,
    # In development, run tasks inline (no worker / broker needed) unless overridden.
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=settings.CELERY_TASK_ALWAYS_EAGER,

    beat_schedule={
        'postbase-webhook-delivery-drain': {
            'task': 'postbase_process_webhook_delivery_jobs_task',
            'schedule': 60.0,
            'args': (200,),
        },
    },
)

if __name__ == '__main__':
    celery_app.start()
