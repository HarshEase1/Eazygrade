from django.urls import path

from institutions.views import search_documents

urlpatterns = [
    path("search/", search_documents, name="search-documents"),
]