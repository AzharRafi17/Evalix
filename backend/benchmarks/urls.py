from django.urls import path

from benchmarks.views import BenchmarkDetailView, BenchmarkStartView


urlpatterns = [
    path('run/', BenchmarkStartView.as_view(), name='benchmark-start'),
    path('<int:benchmark_id>/', BenchmarkDetailView.as_view(), name='benchmark-detail'),
]