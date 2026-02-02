from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import  OpenProjectListView
router = DefaultRouter()
router.register(r'profiles', views.FreelancerProfileViewSet, basename='freelancerprofile')
router.register(r'categories', views.CategoryViewSet)
router.register(r'skills', views.SkillViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('profiles/upload-resume/', views.upload_resume, name='upload-resume'),

    path('freelancer-projects/open/', OpenProjectListView.as_view(), name='open-projects'),

]

