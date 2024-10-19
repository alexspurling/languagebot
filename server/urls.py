from django.urls import path
from django.shortcuts import render

from server.views import GetSentenceView, SubmitSentenceView


# A simple view function to return a response
def home(request):
    return render(request, 'index.html', {'sentence': "hello"})


urlpatterns = [
    path('', home),
    path('getsentence', GetSentenceView.as_view(), name="Get sentence"),
    path('submitsentence', SubmitSentenceView.as_view(), name="Submit sentence"),
]
