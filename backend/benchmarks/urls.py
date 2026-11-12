from django.urls import path

from benchmarks.views import BenchmarkDatasetListView, BenchmarkDetailView, BenchmarkStartView


urlpatterns = [
    path('run/', BenchmarkStartView.as_view(), name='benchmark-start'),
    path('datasets/', BenchmarkDatasetListView.as_view(), name='benchmark-datasets'),
    path('<int:benchmark_id>/', BenchmarkDetailView.as_view(), name='benchmark-detail'),
]