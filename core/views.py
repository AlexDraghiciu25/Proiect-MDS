from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages

# 1. Funcția de Înregistrare
def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user) # Logăm utilizatorul automat după înregistrare
            messages.success(request, "Cont creat cu succes!")
            return redirect('home') # Îl trimitem pe pagina principală
    else:
        form = UserCreationForm()
    return render(request, 'core/register.html', {'form': form})

# 2. Funcția de Login
def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('home')
    else:
        form = AuthenticationForm()
    return render(request, 'core/login.html', {'form': form})

# 3. Funcția de Logout
def logout_view(request):
    logout(request)
    return redirect('login')

# 4. O pagină principală (temporară, ca să avem unde să fim redirecționați)
def home_view(request):
    return render(request, 'core/home.html')