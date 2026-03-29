"""Samba Fête — WTForms for input validation + CSRF protection.

All forms use Flask-WTF for automatic CSRF tokens.
Validators enforce data integrity before hitting the database.
"""
from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, FloatField, IntegerField,
    SelectField, TextAreaField, DateField, BooleanField,
    HiddenField, SubmitField,
)
from wtforms.validators import (
    DataRequired, Email, Length, NumberRange, Optional,
    Regexp, ValidationError,
)
from app.models import User


# ══════════════════════════════════════════════════════════════════════
# Auth Forms
# ══════════════════════════════════════════════════════════════════════

class LoginForm(FlaskForm):
    username = StringField("Nom d'utilisateur", validators=[
        DataRequired(message="Le nom d'utilisateur est requis"),
        Length(min=2, max=80),
    ])
    password = PasswordField("Mot de passe", validators=[
        DataRequired(message="Le mot de passe est requis"),
    ])
    submit = SubmitField("Se connecter")


class UserForm(FlaskForm):
    username = StringField("Nom d'utilisateur", validators=[
        DataRequired(message="Le nom d'utilisateur est requis"),
        Length(min=2, max=80, message="Entre 2 et 80 caractères"),
        Regexp(r"^[a-zA-Z0-9_]+$", message="Lettres, chiffres et _ seulement"),
    ])
    password = PasswordField("Mot de passe", validators=[
        Length(min=8, message="Minimum 8 caractères"),
    ])
    role = SelectField("Rôle", choices=[("manager", "Manager"), ("admin", "Admin")])
    is_active = BooleanField("Actif", default=True)
    submit = SubmitField("Enregistrer")


class UserEditForm(FlaskForm):
    username = StringField("Nom d'utilisateur", validators=[
        DataRequired(message="Le nom d'utilisateur est requis"),
        Length(min=2, max=80),
        Regexp(r"^[a-zA-Z0-9_]+$", message="Lettres, chiffres et _ seulement"),
    ])
    password = PasswordField("Nouveau mot de passe (laisser vide pour garder)", validators=[
        Optional(),
        Length(min=8, message="Minimum 8 caractères"),
    ])
    role = SelectField("Rôle", choices=[("manager", "Manager"), ("admin", "Admin")])
    is_active = BooleanField("Actif", default=True)
    submit = SubmitField("Mettre à jour")


# ══════════════════════════════════════════════════════════════════════
# Booking / Event Forms
# ══════════════════════════════════════════════════════════════════════

class EventForm(FlaskForm):
    title = StringField("Titre", validators=[
        DataRequired(message="Le titre est requis"),
        Length(min=2, max=200),
    ])
    client_name = StringField("Nom du client", validators=[
        DataRequired(message="Le nom du client est requis"),
        Length(min=2, max=200),
    ])
    client_phone = StringField("Téléphone", validators=[
        DataRequired(message="Le téléphone est requis"),
        Regexp(r"^[0-9 +\-()]+$", message="Numéro invalide"),
        Length(min=8, max=20),
    ])
    client_phone2 = StringField("Téléphone 2", validators=[
        Optional(),
        Regexp(r"^[0-9 +\-()]*$", message="Numéro invalide"),
    ])
    client_email = StringField("Email", validators=[Optional(), Email(message="Email invalide")])
    client_address = TextAreaField("Adresse", validators=[Optional(), Length(max=500)])
    venue_id = IntegerField("Lieu", validators=[DataRequired(message="Le lieu est requis")])
    venue_id2 = IntegerField("Lieu 2", validators=[Optional()])
    event_type = SelectField("Type", choices=[
        ("Mariage", "Mariage"), ("Fiançailles", "Fiançailles"),
        ("Anniversaire", "Anniversaire"), ("Conférence", "Conférence"), ("Autre", "Autre"),
    ])
    event_date = StringField("Date", validators=[
        DataRequired(message="La date est requise"),
        Regexp(r"^\d{4}-\d{2}-\d{2}$", message="Format: AAAA-MM-JJ"),
    ])
    time_slot = SelectField("Créneau", choices=[
        ("Déjeuner", "Déjeuner"), ("Après-midi", "Après-midi"), ("Dîner", "Dîner"),
    ])
    guests_men = IntegerField("Hommes", validators=[NumberRange(min=0, max=9999)], default=0)
    guests_women = IntegerField("Femmes", validators=[NumberRange(min=0, max=9999)], default=0)
    total_amount = FloatField("Montant total (DA)", validators=[
        DataRequired(), NumberRange(min=0, message="Le montant doit être positif"),
    ])
    deposit_required = FloatField("Avance (DA)", validators=[
        NumberRange(min=0), Optional(),
    ], default=0)
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Enregistrer")


class PaymentForm(FlaskForm):
    amount = FloatField("Montant (DA)", validators=[
        DataRequired(message="Le montant est requis"),
        NumberRange(min=1, message="Le montant doit être supérieur à 0"),
    ])
    method = SelectField("Méthode", choices=[
        ("espèces", "Espèces"), ("chèque", "Chèque"),
        ("virement", "Virement"), ("carte", "Carte"),
    ])
    payment_type = SelectField("Type", choices=[
        ("acompte", "Acompte"), ("solde", "Solde"), ("avance", "Avance"),
    ])
    reference = StringField("Référence", validators=[Optional(), Length(max=100)])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Enregistrer le paiement")


class RefundForm(FlaskForm):
    refund_reason = TextAreaField("Motif du remboursement", validators=[
        DataRequired(message="Le motif est requis pour la piste d'audit"),
        Length(min=3, max=500),
    ])
    submit = SubmitField("Confirmer le remboursement")


class StatusForm(FlaskForm):
    status = SelectField("Nouveau statut", choices=[
        ("en attente", "En attente"), ("confirmé", "Confirmé"),
        ("changé de date", "Changé de date"), ("terminé", "Terminé"),
        ("annulé", "Annulé"),
    ])
    new_date = StringField("Nouvelle date", validators=[
        Optional(),
        Regexp(r"^\d{4}-\d{2}-\d{2}$", message="Format: AAAA-MM-JJ"),
    ])
    submit = SubmitField("Mettre à jour le statut")


# ══════════════════════════════════════════════════════════════════════
# Finance Forms
# ══════════════════════════════════════════════════════════════════════

class ExpenseForm(FlaskForm):
    expense_date = StringField("Date", validators=[
        DataRequired(),
        Regexp(r"^\d{4}-\d{2}-\d{2}$", message="Format: AAAA-MM-JJ"),
    ])
    category = SelectField("Catégorie", choices=[
        ("Serveurs", "Serveurs"), ("Nettoyeurs", "Nettoyeurs"),
        ("Sécurité", "Sécurité"), ("Autre", "Autre"),
    ])
    description = StringField("Description", validators=[Optional(), Length(max=200)])
    amount = FloatField("Montant (DA)", validators=[
        DataRequired(), NumberRange(min=1, message="Le montant doit être > 0"),
    ])
    event_id = IntegerField("Événement", validators=[Optional()])
    method = SelectField("Méthode", choices=[
        ("espèces", "Espèces"), ("chèque", "Chèque"), ("virement", "Virement"),
    ])
    reference = StringField("Référence", validators=[Optional(), Length(max=100)])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Ajouter la dépense")


# ══════════════════════════════════════════════════════════════════════
# Settings Forms
# ══════════════════════════════════════════════════════════════════════

class VenueForm(FlaskForm):
    name = StringField("Nom du lieu", validators=[
        DataRequired(), Length(min=2, max=100),
    ])
    capacity_men = IntegerField("Capacité hommes", validators=[
        NumberRange(min=0, max=9999),
    ], default=0)
    capacity_women = IntegerField("Capacité femmes", validators=[
        NumberRange(min=0, max=9999),
    ], default=0)
    submit = SubmitField("Ajouter le lieu")
