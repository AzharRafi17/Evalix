from django.urls import path

from . import views

urlpatterns = [
    path('health/', views.health_check, name='health-check'),
    path('auth/token/', views.PublicTokenObtainPairView.as_view(), name='token-obtain-pair'),
    path('auth/refresh/', views.PublicTokenRefreshView.as_view(), name='token-refresh'),
    path('evaluations/single/', views.SingleEvaluationView.as_view(), name='evaluation-single'),
    path('evaluations/batch/', views.BatchEvaluationView.as_view(), name='evaluation-batch'),
    path('evaluations/suites/', views.SuiteListView.as_view(), name='evaluation-suites'),
    path('evaluations/suites/<int:suite_id>/', views.SuiteDetailView.as_view(), name='evaluation-suite-detail'),
    path(
        'evaluations/suites/<int:suite_id>/export/',
        views.SuiteExportView.as_view(),
        name='evaluation-suite-export',
    ),
    path(
        'evaluations/suites/<int:suite_id>/compare/',
        views.SuiteCompareView.as_view(),
        name='evaluation-suite-compare',
    ),
    path(
        'evaluations/suites/<int:suite_id>/runs/<int:run_id>/status/',
        views.RunStatusView.as_view(),
        name='evaluation-run-status',
    ),
]
