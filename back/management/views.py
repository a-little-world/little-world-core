from django.shortcuts import render


def example_frontend(request):
    return render(request, "404.html", {})
