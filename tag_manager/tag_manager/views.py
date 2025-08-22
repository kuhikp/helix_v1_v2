from django.shortcuts import render

def custom_404_view(request, exception):
    return render(request, 'authentication/404.html', status=404)

def custom_500_view(request):
    return render(request, 'authentication/500.html', status=500)

def custom_error_view(request, exception=None):
    return render(request, 'authentication/404.html', status=404)
