from django.urls import path,include
from.views import *

urlpatterns = [
    path("tracker/session/start/", StartSessionView.as_view()),
    path("tracker/session/<int:session_id>/stop/", StopSessionView.as_view()),
    path("tracker/screenshot/", UploadScreenshotView.as_view()),
    path("tracker/device/check-or-create/", DeviceCheckOrCreateView.as_view()),
    path("tracker/session/<int:session_id>/pause/", PauseSessionView.as_view()),
    path("tracker/session/<int:session_id>/resume/", ResumeSessionView.as_view()),
    path("tracker/session/active/",ActiveSessionView.as_view(),),
    path("freelancer-sessions/<int:session_id>/timeline/",FreelancerSessionTimelineView.as_view()),
    path("freelancer-sessions/",FreelancerSessionListView.as_view(),name="freelancer-session-list",),
    path("tracker/session/<int:session_id>/idle-flush/",IdleFlushView.as_view(),),

    path("admin/sessions/", AdminWorkSessionListView.as_view()),
    path("admin/sessions/<int:session_id>/", AdminWorkSessionDetailView.as_view()),
    path("time-blocks/explain/",TimeBlockExplanationCreateView.as_view(),name="timeblock-explanation-create",),
    path("admin/time-blocks/<int:id>/flag/",AdminTimeBlockFlagUpdateView.as_view(),name="admin-timeblock-flag-update",),
    path("admin/time-blocks/<int:block_id>/explanation/review/", AdminExplanationReviewView.as_view()),
    path("admin/activity-logs/", AdminActivityLogView.as_view()),
    path("freelancer-activity-logs/", FreelancerActivityLogView.as_view()),
    

          
]


