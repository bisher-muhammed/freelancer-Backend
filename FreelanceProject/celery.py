import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FreelanceProject.settings')  # change project_name to your project folder name

app = Celery('FreelanceProject')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")



