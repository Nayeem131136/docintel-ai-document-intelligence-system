from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("documents", views.DocumentViewSet, basename="document")
router.register("results", views.ResultViewSet, basename="result")

urlpatterns = [
    path("health/", views.health, name="health"),
    path("auth/token/", views.LoginView.as_view(), name="login"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("stats/", views.StatsView.as_view(), name="stats"),
    path("issues/<int:pk>/resolve/", views.ResolveIssueView.as_view(), name="issue-resolve"),
    path("", include(router.urls)),
]
