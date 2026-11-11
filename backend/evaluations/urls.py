from django.urls import path

from . import views

urlpatterns = [
    path('health/', views.health_check, name='health-check'),
    path('evaluations/single/', views.SingleEvaluationView.as_view(), name='evaluation-single'),
    path('evaluations/batch/', views.BatchEvaluationView.as_view(), name='evaluation-batch'),
    path(
        'evaluations/suites/<int:suite_id>/runs/<int:run_id>/status/',
        views.RunStatusView.as_view(),
        name='evaluation-run-status',
    ),
]
