from django.urls import path
from core import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('history/', views.history, name='history'),
    path('analyze/<int:listing_id>/', views.run_analysis_view, name='run_analysis'),
    path('result/<int:listing_id>/', views.result_detail_view, name='result_detail'),
    path('analyze-external/', views.analyze_external, name='analyze_external'),
    path('search_results/', views.search_results, name='search_results'),
]