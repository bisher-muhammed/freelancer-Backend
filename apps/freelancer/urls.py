from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import  OpenProjectListView, PortfolioProjectViewSet
router = DefaultRouter()
router.register(r'profiles', views.FreelancerProfileViewSet, basename='freelancerprofile')
router.register(r'categories', views.CategoryViewSet)
router.register("freelancer/portfolio", PortfolioProjectViewSet, basename="portfolio")
router.register(r'skills', views.SkillViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('freelancer-projects/open/', OpenProjectListView.as_view(), name='open-projects'),
    path('related-projects/<int:freelancer_id>/', views.RelatedProjectsView.as_view(), name='related-projects'),

]

