from django import forms
from allauth.account.forms import SignupForm

class CustomSignupForm(SignupForm):
    first_name = forms.CharField(max_length=150, label='Prenume', widget=forms.TextInput(attrs={'placeholder': 'Prenume'}))
    last_name = forms.CharField(max_length=150, label='Nume', widget=forms.TextInput(attrs={'placeholder': 'Nume'}))
    phone_number = forms.CharField(max_length=15, label='Telefon', widget=forms.TextInput(attrs={'placeholder': 'Telefon'}))
    address = forms.CharField(max_length=255, label='Adresă', required=False, widget=forms.TextInput(attrs={'placeholder': 'Adresă'}))

    def __init__(self, *args, **kwargs):
        super(CustomSignupForm, self).__init__(*args, **kwargs)
        if 'password1' in self.fields:
            self.fields['password1'].help_text = "Parola trebuie să aibă cel puțin 8 caractere."
        if 'password2' in self.fields:
            self.fields['password2'].label = "Confirmă Parola"

    def save(self, request):
        user = super(CustomSignupForm, self).save(request)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.phone_number = self.cleaned_data['phone_number']
        user.address = self.cleaned_data['address']
        user.save()
        return user
