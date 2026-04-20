# Forçando novo deploy no Render em 09/04/2026

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text, UniqueConstraint, inspect
from datetime import datetime, date, timedelta, time
from collections import Counter
import calendar
import os
import json
import secrets
import base64
import urllib.request
import urllib.error
from urllib.parse import urlencode
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

try:
    from pywebpush import webpush, WebPushException
except Exception:
    webpush = None

    class WebPushException(Exception):
        pass

PT_BR_MONTH_NAMES = {
    1: 'Janeiro',
    2: 'Fevereiro',
    3: 'Março',
    4: 'Abril',
    5: 'Maio',
    6: 'Junho',
    7: 'Julho',
    8: 'Agosto',
    9: 'Setembro',
    10: 'Outubro',
    11: 'Novembro',
    12: 'Dezembro',
}

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_secret_key_here')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///agendadia.db')
app.permanent_session_lifetime = timedelta(days=30)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '0').strip().lower() in ('1', 'true', 'yes', 'on')
db = SQLAlchemy(app)
ASSET_VERSION = os.environ.get('ASSET_VERSION', datetime.utcnow().strftime('%Y%m%d%H%M%S'))

UPLOAD_COMPROVANTES_FOLDER = os.path.join('uploads', 'comprovantes')
DEFAULT_ADMIN_NAME = os.environ.get('DEFAULT_ADMIN_NAME', 'Gestão')
DEFAULT_ADMIN_PASSWORD = os.environ.get('DEFAULT_ADMIN_PASSWORD', '13092026')
DEFAULT_ADMIN_CARGO = os.environ.get('DEFAULT_ADMIN_CARGO', 'admin')
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_CLAIMS_SUB = os.environ.get('VAPID_CLAIMS_SUB', 'mailto:admin@agendadia.local')
PUSH_DISPATCH_TOKEN = os.environ.get('PUSH_DISPATCH_TOKEN', '')
REALTIME_EVENT_RETENTION = int(os.environ.get('REALTIME_EVENT_RETENTION', '800'))
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '').strip()
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', '').strip()
GOOGLE_CALENDAR_TIMEZONE = os.environ.get('GOOGLE_CALENDAR_TIMEZONE', 'America/Sao_Paulo').strip() or 'America/Sao_Paulo'
GOOGLE_CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar.events'
GOOGLE_OAUTH_AUTHORIZE_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_OAUTH_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_CALENDAR_EVENTS_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'
LITE_PLAN_PRICE = 89
LITE_SCOPE_ITEMS = [
    {'nome': 'Cadastro de pacientes', 'status': 'ativo', 'descricao': 'Cadastro e historico por paciente.'},
    {'nome': 'Agenda basica com integracao Google', 'status': 'ativo', 'descricao': 'Atalho para enviar cirurgia ao Google Calendar.'},
    {'nome': 'Confirmacoes via WhatsApp', 'status': 'ativo', 'descricao': 'Mensagem pronta para confirmar cirurgia com o paciente.'},
    {'nome': 'Prontuario personalizavel', 'status': 'ativo', 'descricao': 'Protocolos, observacoes e dados de internacao editaveis.'},
    {'nome': 'Financeiro simples', 'status': 'ativo', 'descricao': 'Comprovantes, valores e status de pagamento.'},
    {'nome': 'Relatorios basicos', 'status': 'ativo', 'descricao': 'Visao mensal por medicos e procedimentos.'},
    {'nome': 'Backup', 'status': 'ativo', 'descricao': 'Exportacao do banco em JSON pelo admin.'},
]

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cargo = db.Column(db.String(100), nullable=False)
    senha = db.Column(db.String(255), nullable=False)  # hashed password
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    grau = db.Column(db.Integer, default=1)  # nivel: 1=view-only, 2=edit appointments, 3=admin

    @property
    def nivel(self):
        return self.grau

    @nivel.setter
    def nivel(self, value):
        self.grau = value

class Agendamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_procedimento = db.Column(db.String(40), unique=True, index=True)
    nome_paciente = db.Column(db.String(100), nullable=False)
    whatsapp_paciente = db.Column(db.String(30))
    nome_medico = db.Column(db.String(100), nullable=False)
    crm_medico = db.Column(db.Integer, nullable=False)
    procedimento = db.Column(db.String(100), nullable=False)
    cid_procedimento = db.Column(db.String(80), nullable=False)
    data = db.Column(db.Date, nullable=False)
    hora = db.Column(db.Time, nullable=False)
    observacao = db.Column(db.Text)
    cirurgia_confirmada = db.Column(db.Boolean, default=False)
    cirurgia_cancelada = db.Column(db.Boolean, default=False)
    sala_cirurgica = db.Column(db.String(50))
    quarto = db.Column(db.String(50))
    protocolo = db.Column(db.String(50))
    google_calendar_event_id = db.Column(db.String(255))
    comprovantes = db.relationship('Comprovante', backref='agendamento', lazy=True, cascade='all, delete-orphan')

    @property
    def esta_concluido(self):
        campos_finais = [self.sala_cirurgica, self.quarto]
        return self.data < date.today() and all(valor and str(valor).strip() for valor in campos_finais)

    @property
    def cirurgia_confirmavel(self):
        dias_ate = (self.data - date.today()).days
        return dias_ate >= 1 and not self.cirurgia_confirmada and not self.cirurgia_cancelada

    @property
    def cirurgia_cancelavel(self):
        dias_ate = (self.data - date.today()).days
        return dias_ate >= 1 and not self.cirurgia_cancelada

    @property
    def cirurgia_em_curso(self):
        return (
            self.data == date.today()
            and bool(self.sala_cirurgica and str(self.sala_cirurgica).strip())
            and bool(self.quarto and str(self.quarto).strip())
        )

class Medico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    crm = db.Column(db.Integer, unique=True, nullable=False)
    cor = db.Column(db.String(7), default='#004d40')  # Hex color code

class Procedimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cid = db.Column(db.String(20), unique=True, nullable=False)

class EscalaAnestesista(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, unique=True, index=True)
    nome = db.Column(db.String(100), nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

class EnfermagemRegistro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_colaborador = db.Column(db.String(100), nullable=False)
    nome_medico = db.Column(db.String(100), nullable=False)
    crm_medico = db.Column(db.Integer, nullable=False)
    procedimento = db.Column(db.String(100), nullable=False)
    cid_procedimento = db.Column(db.String(80), nullable=False)
    data = db.Column(db.Date, nullable=False, index=True)
    observacao = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Comprovante(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    agendamento_id = db.Column(db.Integer, db.ForeignKey('agendamento.id'), nullable=False)
    nome_medico = db.Column(db.String(100), nullable=False)
    procedimento = db.Column(db.String(100), nullable=False)
    data_cirurgia = db.Column(db.Date, nullable=False)
    valor = db.Column(db.Float, nullable=False)
    data_pagamento = db.Column(db.Date)
    pagante = db.Column(db.String(100), nullable=False)
    meio_pagamento = db.Column(db.String(50), nullable=False)
    arquivo_comprovante = db.Column(db.String(255))
    arquivo_comprovante_dados = db.Column(db.LargeBinary)
    status = db.Column(db.String(20), default='pendente')
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    endpoint = db.Column(db.String(512), unique=True, nullable=False)
    p256dh = db.Column(db.String(512), nullable=False)
    auth = db.Column(db.String(512), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ultimo_erro = db.Column(db.String(255))

class PushReminderLog(db.Model):
    __table_args__ = (
        UniqueConstraint('subscription_id', 'reminder_date', name='uq_push_reminder_per_day'),
    )

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('push_subscription.id'), nullable=False, index=True)
    reminder_date = db.Column(db.Date, nullable=False, index=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    sender = db.relationship('User', backref='chat_messages', lazy='joined')

class RealtimeEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(64), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    payload = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class GoogleCalendarCredential(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True, index=True)
    access_token = db.Column(db.Text)
    refresh_token = db.Column(db.Text)
    token_type = db.Column(db.String(40), default='Bearer')
    scope = db.Column(db.Text)
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

@app.context_processor
def inject_user():
    current_user = None
    if 'user_id' in session:
        current_user = User.query.get(session['user_id'])
    return dict(
        current_user=current_user,
        asset_version=ASSET_VERSION,
        build_comprovante_url=build_comprovante_url,
        build_google_calendar_url=build_google_calendar_url,
        is_google_calendar_connected=is_google_calendar_connected,
        build_whatsapp_confirmation_url=build_whatsapp_confirmation_url,
        lite_scope_items=LITE_SCOPE_ITEMS,
        lite_plan_price=LITE_PLAN_PRICE,
        csrf_token=get_csrf_token,
    )

@app.before_request
def keep_session_persistent():
    if 'user_id' in session:
        session.permanent = True

@app.after_request
def disable_html_cache(response):
    # Prevent browser back-button from showing stale authenticated pages.
    if response.mimetype == 'text/html':
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

def get_csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token

def is_csrf_exempt_request():
    return request.path in ('/api/push/dispatch', '/login', '/register')

@app.before_request
def validate_csrf_token():
    if request.method != 'POST':
        return

    if is_csrf_exempt_request():
        return

    session_token = session.get('_csrf_token', '')

    if request.path.startswith('/api/'):
        submitted_token = request.headers.get('X-CSRF-Token', '')
        if not submitted_token or not session_token or not secrets.compare_digest(submitted_token, session_token):
            return jsonify({'ok': False, 'error': 'csrf_invalid'}), 400
        return

    submitted_token = request.form.get('csrf_token', '')
    if not submitted_token or not session_token or not secrets.compare_digest(submitted_token, session_token):
        flash('Sessão expirada ou formulário inválido. Tente novamente.')
        return redirect(request.referrer or request.path or url_for('index'))

def normalize_month(year, month):
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month

def calculate_easter_date(year):
    # Anonymous Gregorian algorithm.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)

def get_brazil_holidays(year):
    easter = calculate_easter_date(year)
    holidays = {
        date(year, 1, 1): 'Confraternização Universal',
        date(year, 4, 21): 'Tiradentes',
        date(year, 5, 1): 'Dia do Trabalho',
        date(year, 9, 7): 'Independência do Brasil',
        date(year, 10, 12): 'Nossa Senhora Aparecida',
        date(year, 11, 2): 'Finados',
        date(year, 11, 15): 'Proclamação da República',
        date(year, 11, 20): 'Dia da Consciência Negra',
        date(year, 12, 25): 'Natal',
        easter - timedelta(days=2): 'Sexta-feira Santa',
        easter + timedelta(days=60): 'Corpus Christi',
    }
    return holidays

def normalize_phone_digits(raw_phone):
    raw_value = (raw_phone or '').strip()
    digits = ''.join(ch for ch in raw_value if ch.isdigit())
    if len(digits) in (10, 11):
        digits = f'55{digits}'
    return digits

def build_whatsapp_url(raw_phone, message=''):
    digits = normalize_phone_digits(raw_phone)
    if not digits:
        return ''

    if message:
        query = urlencode({'text': message})
        return f'https://wa.me/{digits}?{query}'

    return f'https://wa.me/{digits}'

def build_whatsapp_confirmation_url(agendamento):
    if not agendamento:
        return ''

    paciente = (agendamento.nome_paciente or '').strip()
    procedimento = (agendamento.procedimento or '').strip()
    protocolo = (agendamento.protocolo or '').strip()
    data_hora = f"{agendamento.data.strftime('%d/%m/%Y')} as {agendamento.hora.strftime('%H:%M')}"
    saudacao = f'Ola, {paciente}.' if paciente else 'Ola.'

    message_lines = [
        saudacao,
        f'Confirmando sua cirurgia de {procedimento} para {data_hora}.',
    ]
    if protocolo:
        message_lines.append(f'Protocolo: {protocolo}.')
    message_lines.append('Responda com CONFIRMADO para seguirmos com o preparo.')

    return build_whatsapp_url(agendamento.whatsapp_paciente, '\n'.join(message_lines))

def build_google_calendar_url(agendamento):
    if not agendamento or not agendamento.data or not agendamento.hora:
        return ''

    start_dt = datetime.combine(agendamento.data, agendamento.hora)
    end_dt = start_dt + timedelta(hours=1)
    title = f"Cirurgia - {(agendamento.nome_paciente or '').strip() or 'Paciente'}"

    detail_lines = [
        f"Paciente: {agendamento.nome_paciente or '-'}",
        f"Medico: {agendamento.nome_medico or '-'} | CRM: {agendamento.crm_medico or '-'}",
        f"Procedimento: {agendamento.procedimento or '-'}",
        f"CID: {agendamento.cid_procedimento or '-'}",
    ]
    if agendamento.protocolo:
        detail_lines.append(f"Protocolo: {agendamento.protocolo}")
    if agendamento.observacao:
        detail_lines.append(f"Observacao: {agendamento.observacao}")

    params = urlencode({
        'action': 'TEMPLATE',
        'text': title,
        'dates': f"{start_dt.strftime('%Y%m%dT%H%M%S')}/{end_dt.strftime('%Y%m%dT%H%M%S')}",
        'details': '\n'.join(detail_lines),
    })
    return f'https://calendar.google.com/calendar/render?{params}'

def get_google_oauth_redirect_uri():
    if GOOGLE_REDIRECT_URI:
        return GOOGLE_REDIRECT_URI
    return url_for('google_calendar_callback', _external=True)

def get_google_calendar_tokens():
    user_id = session.get('user_id')
    if not user_id:
        return None

    credential = GoogleCalendarCredential.query.filter_by(user_id=user_id).first()
    if not credential:
        legacy_tokens = session.get('google_calendar_tokens')
        if isinstance(legacy_tokens, dict) and (legacy_tokens.get('access_token') or '').strip():
            store_google_calendar_tokens(legacy_tokens)
            session.pop('google_calendar_tokens', None)
            credential = GoogleCalendarCredential.query.filter_by(user_id=user_id).first()
        else:
            return None

    return {
        'access_token': (credential.access_token or '').strip(),
        'refresh_token': (credential.refresh_token or '').strip(),
        'token_type': (credential.token_type or 'Bearer').strip() or 'Bearer',
        'scope': (credential.scope or '').strip(),
        'expires_at': int(credential.expires_at.timestamp()) if credential.expires_at else None,
    }

def store_google_calendar_tokens(token_payload):
    token_payload = token_payload or {}
    existing = get_google_calendar_tokens() or {}
    refresh_token = (token_payload.get('refresh_token') or '').strip() or existing.get('refresh_token')
    user_id = session.get('user_id')
    if not user_id:
        return

    try:
        expires_in = int(token_payload.get('expires_in', 0) or 0)
    except (TypeError, ValueError):
        expires_in = 0

    credential = GoogleCalendarCredential.query.filter_by(user_id=user_id).first()
    if not credential:
        credential = GoogleCalendarCredential(user_id=user_id)
        db.session.add(credential)

    credential.access_token = (token_payload.get('access_token') or '').strip()
    credential.refresh_token = refresh_token
    credential.token_type = (token_payload.get('token_type') or 'Bearer').strip() or 'Bearer'
    credential.scope = (token_payload.get('scope') or '').strip()
    credential.expires_at = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in > 0 else None
    db.session.commit()

def clear_google_calendar_tokens():
    user_id = session.get('user_id')
    if user_id:
        GoogleCalendarCredential.query.filter_by(user_id=user_id).delete()
        db.session.commit()

    session.pop('google_calendar_tokens', None)
    session.pop('google_oauth_state', None)
    session.pop('google_oauth_agendamento_id', None)
    session.pop('google_oauth_return_params', None)

def is_google_calendar_connected():
    tokens = get_google_calendar_tokens()
    return bool(tokens and (tokens.get('access_token') or '').strip())

def http_form_post_json(url, payload):
    data = urlencode(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            body = response.read().decode('utf-8')
            return json.loads(body or '{}'), None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='ignore') if exc else ''
        try:
            payload = json.loads(raw or '{}')
            message = payload.get('error_description') or payload.get('error') or raw
        except Exception:
            message = raw or str(exc)
        return None, message
    except Exception as exc:
        return None, str(exc)

def google_calendar_refresh_access_token(tokens):
    refresh_token = (tokens or {}).get('refresh_token', '').strip()
    if not refresh_token or not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return None, 'Sem refresh token ou credenciais OAuth do Google.'

    payload, error = http_form_post_json(
        GOOGLE_OAUTH_TOKEN_URL,
        {
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        },
    )
    if error:
        return None, error

    store_google_calendar_tokens(payload)
    updated = get_google_calendar_tokens() or {}
    access_token = (updated.get('access_token') or '').strip()
    if not access_token:
        return None, 'Nao foi possivel renovar o token de acesso do Google Calendar.'
    return access_token, None

def ensure_google_calendar_access_token():
    tokens = get_google_calendar_tokens()
    if not tokens:
        return None, 'Conta Google nao conectada.'

    access_token = (tokens.get('access_token') or '').strip()
    if not access_token:
        return None, 'Token de acesso ausente. Reconecte sua conta Google.'

    expires_at = tokens.get('expires_at')
    now = int(datetime.utcnow().timestamp())
    if expires_at and isinstance(expires_at, int) and (expires_at - now) <= 60:
        return google_calendar_refresh_access_token(tokens)

    return access_token, None

def google_calendar_api_post(url, access_token, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            body = response.read().decode('utf-8')
            return json.loads(body or '{}'), None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='ignore') if exc else ''
        try:
            payload = json.loads(raw or '{}')
            message = payload.get('error', {}).get('message') or raw
        except Exception:
            message = raw or str(exc)
        return None, message
    except Exception as exc:
        return None, str(exc)

def google_calendar_api_patch(url, access_token, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        },
        method='PATCH',
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            body = response.read().decode('utf-8')
            return json.loads(body or '{}'), None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='ignore') if exc else ''
        try:
            payload = json.loads(raw or '{}')
            message = payload.get('error', {}).get('message') or raw
        except Exception:
            message = raw or str(exc)
        return None, message
    except Exception as exc:
        return None, str(exc)

def build_google_calendar_event_payload(agendamento):
    start_dt = datetime.combine(agendamento.data, agendamento.hora)
    end_dt = start_dt + timedelta(hours=1)

    detail_lines = [
        f"Paciente: {agendamento.nome_paciente or '-'}",
        f"Medico: {agendamento.nome_medico or '-'} | CRM: {agendamento.crm_medico or '-'}",
        f"Procedimento: {agendamento.procedimento or '-'}",
        f"CID: {agendamento.cid_procedimento or '-'}",
    ]
    if agendamento.protocolo:
        detail_lines.append(f"Protocolo: {agendamento.protocolo}")
    if agendamento.observacao:
        detail_lines.append(f"Observacao: {agendamento.observacao}")

    location_parts = [
        f"Sala: {agendamento.sala_cirurgica}" if agendamento.sala_cirurgica else '',
        f"Quarto: {agendamento.quarto}" if agendamento.quarto else '',
    ]
    location = ' | '.join(part for part in location_parts if part)

    payload = {
        'summary': f"Cirurgia - {(agendamento.nome_paciente or '').strip() or 'Paciente'}",
        'description': '\n'.join(detail_lines),
        'start': {
            'dateTime': start_dt.isoformat(),
            'timeZone': GOOGLE_CALENDAR_TIMEZONE,
        },
        'end': {
            'dateTime': end_dt.isoformat(),
            'timeZone': GOOGLE_CALENDAR_TIMEZONE,
        },
    }
    if location:
        payload['location'] = location

    return payload

def serialize_value_for_backup(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(value).decode('ascii')
    return value

def serialize_model_backup(model_class):
    records = model_class.query.order_by(model_class.id.asc()).all()
    serialized = []
    for record in records:
        item = {}
        for column in model_class.__table__.columns:
            raw = getattr(record, column.name)
            item[column.name] = serialize_value_for_backup(raw)
        serialized.append(item)
    return serialized

def user_can_manage_agendamentos(user):
    return bool(user and (user.cargo == 'admin' or user.grau in (2, 3)))

def user_can_manage_internacao(user):
    return bool(user and user.nivel in (2, 3))

def user_can_access_pagamentos(user):
    return bool(user and user.grau == 3)

def is_password_hashed(password_value):
    value = (password_value or '').strip()
    return value.startswith('pbkdf2:') or value.startswith('scrypt:')

def set_user_password(user, raw_password):
    user.senha = generate_password_hash(raw_password)

def verify_user_password(user, raw_password):
    if not user:
        return False

    stored_password = user.senha or ''
    if not stored_password:
        return False

    if is_password_hashed(stored_password):
        return check_password_hash(stored_password, raw_password)

    # Legacy plaintext support with transparent migration on successful login.
    if stored_password == raw_password:
        set_user_password(user, raw_password)
        db.session.commit()
        return True

    return False

def parse_currency_value(raw_value):
    normalized = raw_value.strip().replace('R$', '').replace(' ', '')
    if not normalized:
        raise ValueError('Valor não informado.')
    if ',' in normalized:
        normalized = normalized.replace('.', '').replace(',', '.')
    return float(normalized)

def resolve_medico_crm(nome_medico, submitted_crm=''):
    submitted_crm = (submitted_crm or '').strip()
    if submitted_crm.isdigit():
        return int(submitted_crm)

    medico = Medico.query.filter(func.lower(Medico.nome) == (nome_medico or '').strip().lower()).first()
    return medico.crm if medico else 0

def resolve_procedimento_cid(procedimento_name, submitted_cid=''):
    procedimento_name = (procedimento_name or '').strip()
    submitted_cid = (submitted_cid or '').strip()
    procedimento_obj = Procedimento.query.filter(func.lower(Procedimento.nome) == procedimento_name.lower()).first()

    if procedimento_obj and submitted_cid and submitted_cid != procedimento_obj.cid:
        return f"{submitted_cid} - {procedimento_obj.cid}"
    if procedimento_obj:
        return procedimento_obj.cid
    return submitted_cid

def build_agendamento_return_params(agendamento=None, source=None, view='calendar'):
    source = source or request.values
    target_date = agendamento.data if agendamento and agendamento.data else date.today()

    def get_context_value(*keys):
        for key in keys:
            value = source.get(key)
            if value is not None:
                return value
        return ''

    try:
        year = int((get_context_value('context_year', 'year') or '').strip())
    except (TypeError, ValueError, AttributeError):
        year = target_date.year

    try:
        month = int((get_context_value('context_month', 'month') or '').strip())
    except (TypeError, ValueError, AttributeError):
        month = target_date.month

    year, month = normalize_month(year, month)
    params = {'year': year, 'month': month}

    requested_view = (get_context_value('context_view', 'view') or '').strip()
    params['view'] = requested_view if requested_view in ('calendar', 'line') else view

    doctor_filter = (get_context_value('context_medico', 'medico') or '').strip()
    protocol_filter = (get_context_value('context_protocolo', 'protocolo') or '').strip()
    calendar_search = (get_context_value('context_paciente_busca', 'paciente_busca') or '').strip()

    if doctor_filter:
        params['medico'] = doctor_filter
    if protocol_filter:
        params['protocolo'] = protocol_filter
    if calendar_search:
        params['paciente_busca'] = calendar_search

    return params

def redirect_to_agendamento_month(agendamento, view='calendar', source=None):
    return redirect(url_for('index', **build_agendamento_return_params(agendamento=agendamento, source=source, view=view)))

def build_paciente_return_params(agendamento=None, source=None):
    source = source or request.values
    params = build_agendamento_return_params(agendamento=agendamento, source=source, view='calendar')
    patients_search = (source.get('context_q') or source.get('q') or '').strip()
    if patients_search:
        params['q'] = patients_search
    return params

def build_enfermagem_return_params(registro=None, source=None):
    source = source or request.values
    target_date = registro.data if registro and registro.data else date.today()

    try:
        year = int((source.get('context_year') or source.get('year') or '').strip())
    except (TypeError, ValueError, AttributeError):
        year = target_date.year

    try:
        month = int((source.get('context_month') or source.get('month') or '').strip())
    except (TypeError, ValueError, AttributeError):
        month = target_date.month

    year, month = normalize_month(year, month)
    return {'year': year, 'month': month}

def build_numero_procedimento(agendamento_id):
    # Simple globally-unique number derived from agendamento ID.
    return f"P{agendamento_id:06d}"

def protocolo_conflita_com_outro_paciente(protocolo, nome_paciente, exclude_agendamento_id=None):
    protocolo_limpo = (protocolo or '').strip().upper()
    if not protocolo_limpo:
        return False

    query = Agendamento.query.filter(func.lower(Agendamento.protocolo) == protocolo_limpo.lower())
    if exclude_agendamento_id is not None:
        query = query.filter(Agendamento.id != exclude_agendamento_id)

    conflito = query.first()
    if not conflito:
        return False

    paciente_atual = (nome_paciente or '').strip().lower()
    paciente_conflito = (conflito.nome_paciente or '').strip().lower()
    return paciente_atual != paciente_conflito

def preencher_numero_procedimento_faltante():
    agendamentos_sem_numero = Agendamento.query.filter(
        Agendamento.numero_procedimento.is_(None)
    ).all()

    if not agendamentos_sem_numero:
        return 0

    for agendamento in agendamentos_sem_numero:
        agendamento.numero_procedimento = build_numero_procedimento(agendamento.id)

    db.session.commit()
    return len(agendamentos_sem_numero)

def normalizar_numero_procedimento():
    agendamentos = Agendamento.query.all()
    alterados = 0
    for agendamento in agendamentos:
        numero_esperado = build_numero_procedimento(agendamento.id)
        if agendamento.numero_procedimento != numero_esperado:
            agendamento.numero_procedimento = numero_esperado
            alterados += 1
    if alterados:
        db.session.commit()
    return alterados

def ensure_password_column_capacity(required_length=255):
    inspector = inspect(db.engine)
    try:
        user_columns = inspector.get_columns('user')
    except Exception:
        return False

    senha_column = next((col for col in user_columns if col.get('name') == 'senha'), None)
    if not senha_column:
        return False

    current_length = getattr(senha_column.get('type'), 'length', None)
    if current_length is None or current_length >= required_length:
        return False

    dialect = db.engine.dialect.name
    with db.engine.begin() as conn:
        if dialect == 'postgresql':
            conn.execute(text(f'ALTER TABLE "user" ALTER COLUMN senha TYPE VARCHAR({required_length})'))
            return True
        if dialect in ('mysql', 'mariadb'):
            conn.execute(text(f'ALTER TABLE `user` MODIFY senha VARCHAR({required_length}) NOT NULL'))
            return True

    return False

def ensure_user_password_hashes():
    users = User.query.all()
    updated = 0
    for user in users:
        if user.senha and not is_password_hashed(user.senha):
            set_user_password(user, user.senha)
            updated += 1

    if updated:
        db.session.commit()

    return updated

def ensure_sqlite_legacy_columns():
    inspector = inspect(db.engine)

    def get_columns(table_name):
        try:
            return {col['name'] for col in inspector.get_columns(table_name)}
        except Exception:
            return set()

    user_columns = get_columns('user')
    medico_columns = get_columns('medico')
    agendamento_columns = get_columns('agendamento')
    comprovante_columns = get_columns('comprovante')

    with db.engine.begin() as conn:
        if user_columns and 'grau' not in user_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN grau INTEGER DEFAULT 1"))

        if medico_columns and 'cor' not in medico_columns:
            conn.execute(text("ALTER TABLE medico ADD COLUMN cor VARCHAR(7) DEFAULT '#004d40'"))

        if agendamento_columns:
            if 'numero_procedimento' not in agendamento_columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN numero_procedimento VARCHAR(40)"))
            if 'whatsapp_paciente' not in agendamento_columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN whatsapp_paciente VARCHAR(30)"))
            if 'cirurgia_confirmada' not in agendamento_columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN cirurgia_confirmada BOOLEAN DEFAULT FALSE"))
            if 'cirurgia_cancelada' not in agendamento_columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN cirurgia_cancelada BOOLEAN DEFAULT FALSE"))
            if 'sala_cirurgica' not in agendamento_columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN sala_cirurgica VARCHAR(50)"))
            if 'quarto' not in agendamento_columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN quarto VARCHAR(50)"))
            if 'protocolo' not in agendamento_columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN protocolo VARCHAR(50)"))
            if 'google_calendar_event_id' not in agendamento_columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN google_calendar_event_id VARCHAR(255)"))

        if comprovante_columns and 'arquivo_comprovante' not in comprovante_columns:
            conn.execute(text("ALTER TABLE comprovante ADD COLUMN arquivo_comprovante VARCHAR(255)"))
        if comprovante_columns and 'arquivo_comprovante_dados' not in comprovante_columns:
            # Use BYTEA for PostgreSQL, LONGBLOB for MySQL, BLOB for SQLite
            dialect = db.engine.dialect.name.lower()
            if 'postgres' in dialect:
                binary_type = 'BYTEA'
            elif 'mysql' in dialect:
                binary_type = 'LONGBLOB'
            else:  # sqlite
                binary_type = 'BLOB'
            conn.execute(text(f"ALTER TABLE comprovante ADD COLUMN arquivo_comprovante_dados {binary_type}"))

def ensure_admin_user(update_password=False):
    admin = User.query.filter_by(nome=DEFAULT_ADMIN_NAME).order_by(User.id).first()
    if not admin:
        admin = User.query.filter_by(cargo='admin', grau=3).order_by(User.id).first()

    created = admin is None
    if created:
        admin = User(
            nome=DEFAULT_ADMIN_NAME,
            cargo=DEFAULT_ADMIN_CARGO,
            senha=generate_password_hash(DEFAULT_ADMIN_PASSWORD),
            status='approved',
            grau=3,
        )
        db.session.add(admin)
    else:
        admin.cargo = DEFAULT_ADMIN_CARGO
        admin.status = 'approved'
        admin.grau = 3
        if update_password:
            set_user_password(admin, DEFAULT_ADMIN_PASSWORD)

    db.session.commit()
    return admin, created

def ensure_database_ready(create_default_admin=True, update_admin_password=False):
    db.create_all()
    ensure_sqlite_legacy_columns()
    ensure_password_column_capacity()
    
    inspector = inspect(db.engine)
    try:
        agendamento_columns = {col['name'] for col in inspector.get_columns('agendamento')}
        if 'google_calendar_event_id' not in agendamento_columns:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN google_calendar_event_id VARCHAR(255)"))
    except Exception:
        pass
    
    normalizar_numero_procedimento()
    ensure_user_password_hashes()
    os.makedirs(os.path.join(app.static_folder, UPLOAD_COMPROVANTES_FOLDER), exist_ok=True)

    if create_default_admin:
        return ensure_admin_user(update_password=update_admin_password)

    return None, False

def save_comprovante_pdf(uploaded_file):
    filename = secure_filename(uploaded_file.filename or '')
    if not filename:
        return None, None

    if not filename.lower().endswith('.pdf'):
        raise ValueError('Somente arquivos PDF são permitidos para comprovante.')

    pdf_data = uploaded_file.read()
    uploaded_file.seek(0)

    return filename, pdf_data

def normalize_comprovante_relpath(stored_path):
    raw = (stored_path or '').strip().replace('\\', '/')
    if not raw:
        return ''

    raw = raw.lstrip('/')
    if raw.startswith('static/'):
        raw = raw[len('static/'):]

    marker = 'uploads/comprovantes/'
    if marker in raw:
        suffix = raw.split(marker, 1)[1].lstrip('/')
        return f"{marker}{suffix}" if suffix else ''

    if raw.startswith('comprovantes/'):
        suffix = raw[len('comprovantes/'):].lstrip('/')
        return f"uploads/comprovantes/{suffix}" if suffix else ''

    filename_only = os.path.basename(raw)
    if not filename_only:
        return ''

    return f"uploads/comprovantes/{filename_only}"

def build_comprovante_url(comprovante_id):
    if not comprovante_id:
        return '#'
    return url_for('comprovante_arquivo', comprovante_id=comprovante_id)

def resolve_comprovante_filename(stored_path):
    normalized = normalize_comprovante_relpath(stored_path)
    if not normalized:
        return ''
    return os.path.basename(normalized)

def cleanup_old_chat_messages():
    cutoff = datetime.utcnow() - timedelta(days=30)
    ChatMessage.query.filter(ChatMessage.created_at < cutoff).delete(synchronize_session=False)
    db.session.commit()

def emit_realtime_event(event_type, actor_id=None, payload=None):
    event_name = (event_type or '').strip()[:64]
    if not event_name:
        return None

    payload_json = None
    if payload:
        try:
            payload_json = json.dumps(payload, ensure_ascii=False)
        except Exception:
            payload_json = None

    event = RealtimeEvent(
        event_type=event_name,
        actor_id=actor_id,
        payload=payload_json,
    )
    db.session.add(event)
    db.session.flush()

    if REALTIME_EVENT_RETENTION > 0:
        threshold_id = event.id - REALTIME_EVENT_RETENTION
        if threshold_id > 0:
            RealtimeEvent.query.filter(RealtimeEvent.id <= threshold_id).delete(synchronize_session=False)

    return event

def notify_chat_message(message):
    sender_name = message.sender.nome if message.sender else 'Usuário'
    payload = {
        'title': 'Nova mensagem no chat',
        'body': f"{sender_name}: {message.content[:120]}",
        'url': url_for('chat', _external=True),
        'icon': url_for('static', filename='icons/icon-192x192.png', _external=True),
        'badge': url_for('static', filename='icons/icon-32x32.png', _external=True),
    }

    subscriptions = PushSubscription.query.filter(PushSubscription.user_id != message.sender_id).all()
    for sub in subscriptions:
        ok, error = send_push_to_subscription(sub, payload)
        if not ok:
            sub.ultimo_erro = (error or '')[:255]
            db.session.commit()

def build_push_payload(reminder_date, appointments):
    qtd = len(appointments)
    if qtd == 1:
        first = appointments[0]
        body = f"1 agendamento para {reminder_date.strftime('%d/%m/%Y')}: {first.hora.strftime('%H:%M')} - {first.nome_paciente}."
    else:
        body = f"{qtd} agendamentos para {reminder_date.strftime('%d/%m/%Y')}."

    return {
        'title': 'Lembrete de agendamento',
        'body': body,
        'url': url_for('index', _external=True),
        'icon': url_for('static', filename='icons/icon-192x192.png', _external=True),
        'badge': url_for('static', filename='icons/icon-32x32.png', _external=True),
    }

def send_push_to_subscription(subscription, payload):
    if not webpush or not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
        return False, 'webpush indisponível ou VAPID não configurado'

    subscription_info = {
        'endpoint': subscription.endpoint,
        'keys': {
            'p256dh': subscription.p256dh,
            'auth': subscription.auth,
        },
    }

    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={'sub': VAPID_CLAIMS_SUB},
        )
        return True, None
    except WebPushException as exc:
        status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
        if status_code in (404, 410):
            db.session.delete(subscription)
            db.session.commit()
            return False, 'subscription expirada'
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)

def dispatch_daily_push_reminders(target_date=None):
    if target_date is None:
        target_date = date.today() + timedelta(days=2)

    appointments = Agendamento.query.filter_by(data=target_date).order_by(Agendamento.hora).all()
    if not appointments:
        return {'sent': 0, 'skipped': 0, 'date': target_date.strftime('%Y-%m-%d'), 'reason': 'sem agendamentos'}

    payload = build_push_payload(target_date, appointments)
    sent = 0
    skipped = 0

    subscriptions = PushSubscription.query.all()
    for sub in subscriptions:
        already_sent = PushReminderLog.query.filter_by(
            subscription_id=sub.id,
            reminder_date=target_date,
        ).first()
        if already_sent:
            skipped += 1
            continue

        ok, error = send_push_to_subscription(sub, payload)
        if ok:
            db.session.add(PushReminderLog(subscription_id=sub.id, reminder_date=target_date))
            db.session.commit()
            sent += 1
        else:
            sub.ultimo_erro = (error or '')[:255]
            db.session.commit()
            skipped += 1

    return {'sent': sent, 'skipped': skipped, 'date': target_date.strftime('%Y-%m-%d')}

@app.route('/')
def index():
    today = date.today()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    view_mode = request.args.get('view', 'calendar')
    year, month = normalize_month(year, month)
    cal = calendar.monthcalendar(year, month)
    holidays_map = get_brazil_holidays(year)
    appointments = {}
    feriados_por_dia = {}
    all_dates = []
    for week in cal:
        for day in week:
            if day != 0:
                d = date(year, month, day)
                if d.weekday() < 6:
                    all_dates.append(d)
                    appointments[d] = Agendamento.query.filter_by(data=d).all()
                    if d in holidays_map:
                        feriados_por_dia[d] = holidays_map[d]
    next_month_year, next_month_num = normalize_month(year, month + 1)
    doctor_filter = request.args.get('medico', '').strip()
    protocol_filter = request.args.get('protocolo', '').strip()
    calendar_search = request.args.get('paciente_busca', '').strip()
    month_start = date(year, month, 1)
    month_end = date(next_month_year, next_month_num, 1)
    all_appointments = []
    calendar_search_results = []
    calendar_search_match_ids = set()
    query = Agendamento.query.filter(
        Agendamento.data >= month_start,
        Agendamento.data < month_end
    ).order_by(Agendamento.data, Agendamento.hora)
    if view_mode == 'line':
        if doctor_filter:
            query = query.filter_by(nome_medico=doctor_filter)
        if protocol_filter:
            query = query.filter(Agendamento.protocolo.contains(protocol_filter))
        all_appointments = query.all()

    if view_mode == 'calendar' and calendar_search:
        search_norm = calendar_search.lower()
        calendar_search_results = Agendamento.query.filter(
            (func.lower(Agendamento.nome_paciente).contains(search_norm)) |
            (func.lower(func.coalesce(Agendamento.protocolo, '')).contains(search_norm))
        ).order_by(Agendamento.data.desc(), Agendamento.hora.desc()).limit(200).all()
        calendar_search_match_ids = {item.id for item in calendar_search_results}

    reminder_status = {}
    for appt in Agendamento.query.filter(
        Agendamento.data >= month_start,
        Agendamento.data < month_end
    ).all():
        days_until = (appt.data - today).days
        if appt.cirurgia_em_curso and not appt.esta_concluido:
            reminder_status[appt.id] = 'reminder-in-progress'
        elif days_until in (1, 2) and not appt.cirurgia_confirmada and not appt.cirurgia_cancelada:
            reminder_status[appt.id] = 'reminder-immediate'
        else:
            reminder_status[appt.id] = ''

    prev_year, prev_month = normalize_month(year, month - 1)
    next_year, next_month = normalize_month(year, month + 1)
    
    # Get all medicos for color mapping and filter options
    medicos = Medico.query.order_by(Medico.nome).all()
    medico_colors = {medico.nome: medico.cor for medico in medicos}

    # Escala de anestesistas do mês para exibir no calendário principal
    escalas_mes = EscalaAnestesista.query.filter(
        EscalaAnestesista.data >= date(year, month, 1),
        EscalaAnestesista.data < date(next_year, next_month, 1),
    ).all()
    anestesista_por_dia = {e.data: e.nome for e in escalas_mes}

    # Dispara lembrete push D-2 com deduplicação por inscrição/dia.
    if session.get('user_id'):
        dispatch_daily_push_reminders()
    
    return render_template(
        'index.html',
        appointments=appointments,
        all_appointments=all_appointments,
        all_dates=all_dates,
        year=year,
        month=month,
        month_name=PT_BR_MONTH_NAMES[month],
        view_mode=view_mode,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        medico_colors=medico_colors,
        medicos=medicos,
        doctor_filter=doctor_filter,
        protocol_filter=protocol_filter,
        calendar_search=calendar_search,
        calendar_search_results=calendar_search_results,
        calendar_search_match_ids=calendar_search_match_ids,
        reminder_status=reminder_status,
        today=today,
        anestesista_por_dia=anestesista_por_dia,
        feriados_por_dia=feriados_por_dia,
    )

@app.route('/api/push/public-key', methods=['GET'])
def push_public_key():
    if 'user_id' not in session:
        return jsonify({'error': 'nao_autenticado'}), 401
    if not VAPID_PUBLIC_KEY:
        return jsonify({'error': 'vapid_nao_configurado'}), 503
    return jsonify({'publicKey': VAPID_PUBLIC_KEY})

@app.route('/api/push/subscribe', methods=['POST'])
def push_subscribe():
    if 'user_id' not in session:
        return jsonify({'error': 'nao_autenticado'}), 401

    payload = request.get_json(silent=True) or {}
    endpoint = (payload.get('endpoint') or '').strip()
    keys = payload.get('keys') or {}
    p256dh = (keys.get('p256dh') or '').strip()
    auth = (keys.get('auth') or '').strip()

    if not endpoint or not p256dh or not auth:
        return jsonify({'error': 'assinatura_invalida'}), 400

    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if not sub:
        sub = PushSubscription(
            user_id=session['user_id'],
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
        )
        db.session.add(sub)
    else:
        sub.user_id = session['user_id']
        sub.p256dh = p256dh
        sub.auth = auth
        sub.ultimo_erro = None

    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/push/unsubscribe', methods=['POST'])
def push_unsubscribe():
    if 'user_id' not in session:
        return jsonify({'error': 'nao_autenticado'}), 401

    payload = request.get_json(silent=True) or {}
    endpoint = (payload.get('endpoint') or '').strip()
    if not endpoint:
        return jsonify({'ok': True})

    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if sub:
        db.session.delete(sub)
        db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/push/dispatch', methods=['POST'])
def push_dispatch():
    token = request.headers.get('X-Dispatch-Token', '')
    if not PUSH_DISPATCH_TOKEN or token != PUSH_DISPATCH_TOKEN:
        return jsonify({'error': 'nao_autorizado'}), 401

    result = dispatch_daily_push_reminders()
    return jsonify(result)

@app.route('/service-worker.js')
def service_worker():
    return send_from_directory(app.static_folder, 'service-worker.js', mimetype='application/javascript')

@app.route('/manifest.webmanifest')
def web_manifest():
    return send_from_directory(app.static_folder, 'manifest.json', mimetype='application/manifest+json')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(app.static_folder, 'favicon.ico', mimetype='image/x-icon')

@app.route('/comprovante/arquivo/<int:comprovante_id>')
def comprovante_arquivo(comprovante_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user or not user_can_access_pagamentos(user):
        return 'Acesso negado.', 403

    comprovante = Comprovante.query.get_or_404(comprovante_id)
    
    if comprovante.arquivo_comprovante_dados:
        filename = comprovante.arquivo_comprovante or f'comprovante_{comprovante.id}.pdf'
        if not filename.endswith('.pdf'):
            filename += '.pdf'
        return comprovante.arquivo_comprovante_dados, 200, {
            'Content-Type': 'application/pdf',
            'Content-Disposition': f'inline; filename="{filename}"'
        }
    
    if comprovante.arquivo_comprovante:
        normalized = normalize_comprovante_relpath(comprovante.arquivo_comprovante)
        if normalized:
            filename = os.path.basename(normalized)
            candidate_dirs = [
                os.path.join(app.static_folder, UPLOAD_COMPROVANTES_FOLDER),
                os.path.join(app.root_path, UPLOAD_COMPROVANTES_FOLDER),
                os.path.join(app.instance_path, UPLOAD_COMPROVANTES_FOLDER),
            ]
            for directory in candidate_dirs:
                abs_path = os.path.join(directory, filename)
                if os.path.isfile(abs_path):
                    return send_from_directory(directory, filename, mimetype='application/pdf')
    
    return 'Arquivo não encontrado.', 404

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        senha = request.form.get('senha', '')

        if not nome or not senha:
            flash('Preencha nome e senha para entrar.')
            return render_template('login.html')

        user = User.query.filter(func.lower(User.nome) == nome.lower()).order_by(User.id.asc()).first()
        if not user:
            flash('Usuario nao encontrado.')
            return render_template('login.html')

        user_status = (user.status or '').strip().lower()
        if user_status != 'approved':
            if user_status == 'pending':
                flash('Conta ainda nao aprovada pelo administrador.')
            elif user_status == 'rejected':
                flash('Conta rejeitada. Solicite nova avaliacao ao administrador.')
            else:
                flash('Conta sem aprovacao. Contate o administrador.')
            return render_template('login.html')

        if not verify_user_password(user, senha):
            flash('Senha incorreta.')
            return render_template('login.html')

        session['user_id'] = user.id
        session.permanent = True
        return redirect(url_for('index'))

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        cargo = request.form.get('cargo', '').strip()
        senha = request.form.get('senha', '')

        if not nome or not cargo or not senha:
            flash('Preencha nome, cargo e senha para cadastrar.')
            return render_template('register.html')

        if len(senha) < 6 or not senha.isdigit():
            flash('Senha deve conter somente numeros e no minimo 6 digitos.')
            return render_template('register.html')

        existing_user = User.query.filter(func.lower(User.nome) == nome.lower()).order_by(User.id.asc()).first()
        if existing_user:
            flash('Nome ja cadastrado. Use exatamente este nome para login.')
            return render_template('register.html')

        user = User(nome=nome, cargo=cargo, senha=generate_password_hash(senha), status='pending', grau=1)
        db.session.add(user)
        db.session.commit()
        flash('Cadastro solicitado. Aguarde aprovacao do admin.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('google_oauth_state', None)
    session.pop('google_oauth_agendamento_id', None)
    session.pop('google_oauth_return_params', None)
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route('/google-calendar/connect/<int:agendamento_id>')
def google_calendar_connect(agendamento_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user or not user_can_manage_agendamentos(user):
        flash('Acesso negado.')
        return redirect(url_for('index'))

    agendamento = Agendamento.query.get_or_404(agendamento_id)
    return_params = build_paciente_return_params(agendamento=agendamento, source=request.args)

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        flash('Google Calendar indisponivel: configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET.')
        return redirect(url_for('paciente', id=agendamento.id, **return_params))

    state = secrets.token_urlsafe(32)
    session['google_oauth_state'] = state
    session['google_oauth_agendamento_id'] = agendamento.id
    session['google_oauth_return_params'] = return_params

    auth_params = urlencode({
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': get_google_oauth_redirect_uri(),
        'response_type': 'code',
        'scope': GOOGLE_CALENDAR_SCOPE,
        'access_type': 'offline',
        'include_granted_scopes': 'true',
        'prompt': 'consent',
        'state': state,
    })
    return redirect(f'{GOOGLE_OAUTH_AUTHORIZE_URL}?{auth_params}')

@app.route('/google-calendar/callback')
def google_calendar_callback():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    expected_state = (session.get('google_oauth_state') or '').strip()
    received_state = (request.args.get('state') or '').strip()
    if not expected_state or not received_state or not secrets.compare_digest(expected_state, received_state):
        flash('Falha na validacao da conexao com Google Calendar (state invalido).')
        return redirect(url_for('index'))

    oauth_error = (request.args.get('error') or '').strip()
    if oauth_error:
        flash(f'Conexao com Google Calendar cancelada: {oauth_error}.')
        return redirect(url_for('index'))

    code = (request.args.get('code') or '').strip()
    agendamento_id = session.pop('google_oauth_agendamento_id', None)
    return_params = session.pop('google_oauth_return_params', None) or {}
    session.pop('google_oauth_state', None)

    if not code:
        flash('Nao foi recebido codigo de autorizacao do Google.')
        if agendamento_id:
            return redirect(url_for('paciente', id=agendamento_id, **return_params))
        return redirect(url_for('index'))

    token_payload, token_error = http_form_post_json(
        GOOGLE_OAUTH_TOKEN_URL,
        {
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': get_google_oauth_redirect_uri(),
            'grant_type': 'authorization_code',
        },
    )
    if token_error:
        flash(f'Erro ao conectar Google Calendar: {token_error}')
        if agendamento_id:
            return redirect(url_for('paciente', id=agendamento_id, **return_params))
        return redirect(url_for('index'))

    store_google_calendar_tokens(token_payload)
    flash('Conta Google conectada com sucesso.')

    if agendamento_id:
        return redirect(url_for('google_calendar_create_event', agendamento_id=agendamento_id, **return_params))

    return redirect(url_for('index'))

@app.route('/google-calendar/create-event/<int:agendamento_id>')
def google_calendar_create_event(agendamento_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user or not user_can_manage_agendamentos(user):
        flash('Acesso negado.')
        return redirect(url_for('index'))

    agendamento = Agendamento.query.get_or_404(agendamento_id)
    return_params = build_paciente_return_params(agendamento=agendamento, source=request.args)

    if not is_google_calendar_connected():
        return redirect(url_for('google_calendar_connect', agendamento_id=agendamento.id, **return_params))

    access_token, token_error = ensure_google_calendar_access_token()
    if token_error:
        flash(f'Nao foi possivel autenticar no Google Calendar: {token_error}')
        clear_google_calendar_tokens()
        return redirect(url_for('google_calendar_connect', agendamento_id=agendamento.id, **return_params))

    event_payload = build_google_calendar_event_payload(agendamento)
    existing_event_id = (agendamento.google_calendar_event_id or '').strip()

    if existing_event_id:
        update_url = f'{GOOGLE_CALENDAR_EVENTS_URL}/{existing_event_id}'
        result_event, event_error = google_calendar_api_patch(update_url, access_token, event_payload)
        action_msg = 'atualizado'
    else:
        result_event, event_error = google_calendar_api_post(GOOGLE_CALENDAR_EVENTS_URL, access_token, event_payload)
        action_msg = 'criado'

    if event_error:
        flash(f'Falha ao {action_msg} evento no Google Calendar: {event_error}')
        return redirect(url_for('paciente', id=agendamento.id, **return_params))

    event_id = (result_event or {}).get('id')
    event_link = (result_event or {}).get('htmlLink')

    if event_id and event_id != existing_event_id:
        agendamento.google_calendar_event_id = event_id
        db.session.commit()

    if event_link:
        flash(f'Evento {action_msg} no Google Calendar: <a href="{event_link}" target="_blank" rel="noopener noreferrer">{event_link}</a>', 'message_with_link')
    else:
        flash(f'Evento {action_msg} no Google Calendar com sucesso.')

    return redirect(url_for('paciente', id=agendamento.id, **return_params))

@app.route('/google-calendar/disconnect', methods=['POST'])
def google_calendar_disconnect():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user or not user_can_manage_agendamentos(user):
        flash('Acesso negado.')
        return redirect(url_for('index'))

    agendamento_id = request.form.get('agendamento_id', type=int)
    clear_google_calendar_tokens()
    flash('Conta Google desconectada deste navegador.')

    if agendamento_id:
        agendamento = Agendamento.query.get(agendamento_id)
        if agendamento:
            return redirect(url_for('paciente', id=agendamento.id, **build_paciente_return_params(agendamento=agendamento, source=request.form)))

    return redirect(url_for('index'))

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cleanup_old_chat_messages()
    return render_template('chat.html')

@app.route('/api/chat/messages')
def chat_messages():
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401

    cleanup_old_chat_messages()

    after_id = request.args.get('after_id', 0, type=int)
    query = ChatMessage.query.order_by(ChatMessage.id.asc())
    if after_id:
        query = query.filter(ChatMessage.id > after_id)

    messages = query.limit(250).all()
    payload = []
    for msg in messages:
        payload.append({
            'id': msg.id,
            'sender_id': msg.sender_id,
            'sender_nome': msg.sender.nome if msg.sender else 'Usuário',
            'content': msg.content,
            'created_at': msg.created_at.strftime('%d/%m/%Y %H:%M') if msg.created_at else '',
            'is_me': msg.sender_id == session.get('user_id'),
        })

    return jsonify({'ok': True, 'messages': payload})

@app.route('/api/chat/status')
def chat_status():
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401

    cleanup_old_chat_messages()

    last_read_id = request.args.get('last_read_id', 0, type=int)
    if last_read_id < 0:
        last_read_id = 0

    latest_id = db.session.query(func.max(ChatMessage.id)).scalar() or 0
    unread_count = ChatMessage.query.filter(
        ChatMessage.id > last_read_id,
        ChatMessage.sender_id != session.get('user_id')
    ).count()

    return jsonify({
        'ok': True,
        'latest_id': latest_id,
        'has_unread': unread_count > 0,
        'unread_count': unread_count,
    })

@app.route('/api/realtime/status')
def realtime_status():
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401

    after_id = request.args.get('after_id', 0, type=int)
    if after_id < 0:
        after_id = 0

    latest_id = db.session.query(func.max(RealtimeEvent.id)).scalar() or 0
    events = []

    if latest_id > after_id:
        recent = RealtimeEvent.query.filter(RealtimeEvent.id > after_id).order_by(RealtimeEvent.id.asc()).limit(60).all()
        events = [
            {
                'id': ev.id,
                'type': ev.event_type,
                'actor_id': ev.actor_id,
                'created_at': ev.created_at.strftime('%d/%m/%Y %H:%M:%S') if ev.created_at else '',
            }
            for ev in recent
        ]

    return jsonify({
        'ok': True,
        'latest_id': latest_id,
        'events': events,
    })

@app.route('/api/chat/send', methods=['POST'])
def chat_send():
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401

    payload = request.get_json(silent=True) or {}
    content = (payload.get('content') or '').strip()
    if not content:
        return jsonify({'ok': False, 'error': 'Mensagem vazia.'}), 400

    content = content[:1500]
    cleanup_old_chat_messages()

    message = ChatMessage(
        sender_id=session['user_id'],
        content=content,
    )
    db.session.add(message)
    emit_realtime_event(
        'chat_message',
        actor_id=session.get('user_id'),
        payload={'message_preview': content[:80]},
    )
    db.session.commit()
    notify_chat_message(message)

    return jsonify({
        'ok': True,
        'message': {
            'id': message.id,
            'sender_id': message.sender_id,
            'sender_nome': message.sender.nome if message.sender else 'Usuário',
            'content': message.content,
            'created_at': message.created_at.strftime('%d/%m/%Y %H:%M') if message.created_at else '',
            'is_me': True,
        }
    })

@app.route('/perfil', methods=['GET', 'POST'])
def perfil():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        session.pop('user_id', None)
        return redirect(url_for('login'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'dados':
            nome = request.form.get('nome', '').strip()
            cargo = request.form.get('cargo', '').strip()

            if not nome or not cargo:
                flash('Nome e cargo são obrigatórios.')
                return redirect(url_for('perfil'))

            existing_user = User.query.filter(User.nome == nome, User.id != user.id).first()
            if existing_user:
                flash('Já existe outro usuário com este nome.')
                return redirect(url_for('perfil'))

            user.nome = nome
            user.cargo = cargo
            db.session.commit()
            flash('Dados do perfil atualizados com sucesso.')
            return redirect(url_for('perfil'))

        if action == 'senha':
            senha_atual = request.form.get('senha_atual', '')
            nova_senha = request.form.get('nova_senha', '')
            confirmar_senha = request.form.get('confirmar_senha', '')

            if not verify_user_password(user, senha_atual):
                flash('A senha atual está incorreta.')
                return redirect(url_for('perfil'))

            if len(nova_senha) < 6 or not nova_senha.isdigit():
                flash('A nova senha deve ter pelo menos 6 dígitos numéricos.')
                return redirect(url_for('perfil'))

            if nova_senha != confirmar_senha:
                flash('A confirmação da senha não confere.')
                return redirect(url_for('perfil'))

            set_user_password(user, nova_senha)
            db.session.commit()
            flash('Senha alterada com sucesso.')
            return redirect(url_for('perfil'))

        flash('Ação inválida.')
        return redirect(url_for('perfil'))

    return render_template('perfil.html', user=user, managed_by_admin=False)

@app.route('/admin/perfil_usuario/<int:user_id>', methods=['GET', 'POST'])
def perfil_usuario(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    admin_user = User.query.get(session['user_id'])
    if not admin_user or (admin_user.cargo != 'admin' and admin_user.grau != 3):
        flash('Acesso negado')
        return redirect(url_for('index'))

    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'dados':
            nome = request.form.get('nome', '').strip()
            cargo = request.form.get('cargo', '').strip()

            if not nome or not cargo:
                flash('Nome e cargo são obrigatórios.')
                return redirect(url_for('perfil_usuario', user_id=user.id))

            existing_user = User.query.filter(User.nome == nome, User.id != user.id).first()
            if existing_user:
                flash('Já existe outro usuário com este nome.')
                return redirect(url_for('perfil_usuario', user_id=user.id))

            user.nome = nome
            user.cargo = cargo
            db.session.commit()
            flash('Dados do perfil atualizados com sucesso.')
            return redirect(url_for('perfil_usuario', user_id=user.id))

        if action == 'senha':
            nova_senha = request.form.get('nova_senha', '')
            confirmar_senha = request.form.get('confirmar_senha', '')

            if len(nova_senha) < 6 or not nova_senha.isdigit():
                flash('A nova senha deve ter pelo menos 6 dígitos numéricos.')
                return redirect(url_for('perfil_usuario', user_id=user.id))

            if nova_senha != confirmar_senha:
                flash('A confirmação da senha não confere.')
                return redirect(url_for('perfil_usuario', user_id=user.id))

            set_user_password(user, nova_senha)
            db.session.commit()
            flash('Senha alterada com sucesso.')
            return redirect(url_for('perfil_usuario', user_id=user.id))

        flash('Ação inválida.')
        return redirect(url_for('perfil_usuario', user_id=user.id))

    return render_template('perfil.html', user=user, managed_by_admin=True)

@app.route('/admin')
def admin():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau != 3):
        flash('Acesso negado')
        return redirect(url_for('index'))
    pending_users = User.query.filter_by(status='pending').all()
    all_users = User.query.order_by(User.nome).all()
    medicos = Medico.query.order_by(Medico.nome).all()
    procedimentos = Procedimento.query.order_by(Procedimento.nome).all()
    all_appointments = Agendamento.query.all()
    current_year = date.today().year
    monthly_stats = []
    for m in range(1, 13):
        month_appts = [appt for appt in all_appointments if appt.data.year == current_year and appt.data.month == m]
        count = len(month_appts)
        top_medicos = Counter([appt.nome_medico for appt in month_appts]).most_common(3)
        top_procedures = Counter([appt.procedimento for appt in month_appts]).most_common(3)
        monthly_stats.append({
            'month': m,
            'month_name': calendar.month_name[m].capitalize(),
            'count': count,
            'top_medicos': top_medicos,
            'top_procedures': top_procedures,
        })
    return render_template(
        'admin.html',
        pending_users=pending_users,
        all_users=all_users,
        medicos=medicos,
        procedimentos=procedimentos,
        monthly_stats=monthly_stats,
        current_year=current_year,
    )

@app.route('/admin/backup/download')
def admin_backup_download():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau != 3):
        flash('Acesso negado')
        return redirect(url_for('index'))

    backup_payload = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'app': 'AgendaDia',
        'tables': {
            'user': serialize_model_backup(User),
            'medico': serialize_model_backup(Medico),
            'procedimento': serialize_model_backup(Procedimento),
            'agendamento': serialize_model_backup(Agendamento),
            'comprovante': serialize_model_backup(Comprovante),
            'escala_anestesista': serialize_model_backup(EscalaAnestesista),
            'enfermagem_registro': serialize_model_backup(EnfermagemRegistro),
            'chat_message': serialize_model_backup(ChatMessage),
            'push_subscription': serialize_model_backup(PushSubscription),
            'push_reminder_log': serialize_model_backup(PushReminderLog),
            'realtime_event': serialize_model_backup(RealtimeEvent),
        },
    }

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    response = app.response_class(
        response=json.dumps(backup_payload, ensure_ascii=False, indent=2),
        mimetype='application/json',
    )
    response.headers['Content-Disposition'] = f'attachment; filename=agendadia_backup_{timestamp}.json'
    return response

@app.route('/admin/add_medico', methods=['POST'])
def add_medico():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau != 3):
        flash('Acesso negado')
        return redirect(url_for('index'))
    nome = request.form['nome_medico']
    crm = request.form['crm']
    cor = request.form.get('cor_medico', '#004d40')
    if not nome or not crm.isdigit():
        flash('Nome e CRM devem ser preenchidos corretamente.')
        return redirect(url_for('admin'))
    existing = Medico.query.filter_by(crm=int(crm)).first()
    if existing:
        flash('CRM já cadastrado.')
        return redirect(url_for('admin'))
    medico = Medico(nome=nome, crm=int(crm), cor=cor)
    db.session.add(medico)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/edit_medico/<int:medico_id>', methods=['GET', 'POST'])
def edit_medico(medico_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau != 3):
        flash('Acesso negado')
        return redirect(url_for('index'))
    medico = Medico.query.get_or_404(medico_id)
    if request.method == 'POST':
        nome = request.form['nome_medico']
        crm = request.form['crm']
        cor = request.form.get('cor_medico', medico.cor)
        if not nome or not crm.isdigit():
            flash('Nome e CRM devem ser preenchidos corretamente.')
            return redirect(url_for('admin'))
        existing = Medico.query.filter(Medico.crm == int(crm), Medico.id != medico.id).first()
        if existing:
            flash('CRM já cadastrado.')
            return redirect(url_for('admin'))
        medico.nome = nome
        medico.crm = int(crm)
        medico.cor = cor
        db.session.commit()
        return redirect(url_for('admin'))
    return render_template('edit_medico.html', medico=medico)

@app.route('/admin/delete_medico/<int:medico_id>', methods=['POST'])
def delete_medico(medico_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau != 3):
        flash('Acesso negado')
        return redirect(url_for('index'))
    medico = Medico.query.get_or_404(medico_id)
    db.session.delete(medico)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/add_procedimento', methods=['POST'])
def add_procedimento():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau != 3):
        flash('Acesso negado')
        return redirect(url_for('index'))
    nome = request.form['nome_procedimento']
    cid = request.form['cid']
    if not nome or not cid:
        flash('Nome e CID devem ser preenchidos corretamente.')
        return redirect(url_for('admin'))
    existing = Procedimento.query.filter_by(cid=cid).first()
    if existing:
        flash('CID já cadastrado.')
        return redirect(url_for('admin'))
    procedimento = Procedimento(nome=nome, cid=cid)
    db.session.add(procedimento)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/approve/<int:user_id>', methods=['POST'])
def approve(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau != 3):
        flash('Acesso negado')
        return redirect(url_for('index'))
    pending_user = User.query.get_or_404(user_id)
    pending_user.status = 'approved'
    db.session.commit()
    flash(f'Usuário {pending_user.nome} aprovado.')
    return redirect(url_for('admin'))

@app.route('/admin/set_user_level/<int:user_id>', methods=['POST'])
@app.route('/admin/set_user_grade/<int:user_id>', methods=['POST'])
def set_user_level(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau != 3):
        flash('Acesso negado')
        return redirect(url_for('index'))
    target_user = User.query.get_or_404(user_id)
    try:
        level_raw = request.form.get('nivel', request.form.get('grau', ''))
        level = int(level_raw)
    except (ValueError, TypeError):
        flash('Nível inválido.')
        return redirect(url_for('admin'))
    if level not in (1, 2, 3):
        flash('Nível inválido.')
        return redirect(url_for('admin'))
    target_user.nivel = level
    db.session.commit()
    flash(f'Nível do usuário {target_user.nome} atualizado para {level}.')
    return redirect(url_for('admin'))

@app.route('/admin/set_user_levels_bulk', methods=['POST'])
def set_user_levels_bulk():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau != 3):
        flash('Acesso negado')
        return redirect(url_for('index'))
    
    updated_count = 0
    for key, value in request.form.items():
        if key.startswith('nivel-'):
            try:
                user_id = int(key.split('-')[1])
                level = int(value)
                if level in (1, 2, 3):
                    target_user = User.query.get(user_id)
                    if target_user:
                        target_user.nivel = level
                        updated_count += 1
            except (ValueError, IndexError):
                pass
    
    db.session.commit()
    if updated_count > 0:
        flash(f'{updated_count} nível(is) de acesso atualizado(s).')
    return redirect(url_for('admin'))

@app.route('/reject/<int:user_id>', methods=['POST'])
def reject(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau != 3):
        flash('Acesso negado')
        return redirect(url_for('index'))
    pending_user = User.query.get_or_404(user_id)
    pending_user.status = 'rejected'
    db.session.commit()
    flash(f'Usuário {pending_user.nome} rejeitado.')
    return redirect(url_for('admin'))

@app.route('/create', methods=['GET', 'POST'])
def create():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau not in (2, 3)):
        flash('Acesso negado')
        return redirect(url_for('index'))
    medicos = [{'id': m.id, 'nome': m.nome, 'crm': m.crm, 'cor': m.cor} for m in Medico.query.order_by(Medico.nome).all()]
    procedimentos = [{'id': p.id, 'nome': p.nome, 'cid': p.cid} for p in Procedimento.query.order_by(Procedimento.nome).all()]
    selected_date = request.args.get('date', '')
    return_context = build_agendamento_return_params(source=request.args, view='calendar')
    if request.method == 'POST':
        nome_medico = request.form['nome_medico'].strip()
        submitted_crm = request.form['crm_medico'].strip()
        procedimento_name = request.form['procedimento'].strip()
        submitted_cid = request.form['cid_procedimento'].strip()

        crm_medico = resolve_medico_crm(nome_medico, submitted_crm)
        cid_val = resolve_procedimento_cid(procedimento_name, submitted_cid)

        agendamento = Agendamento(
            nome_paciente=request.form['nome_paciente'],
            whatsapp_paciente=request.form.get('whatsapp_paciente', '').strip() or None,
            nome_medico=nome_medico,
            crm_medico=crm_medico,
            procedimento=procedimento_name,
            cid_procedimento=cid_val,
            data=datetime.strptime(request.form['data'], '%Y-%m-%d').date(),
            hora=datetime.strptime(request.form['hora'], '%H:%M').time(),
            observacao=request.form['observacao'],
            protocolo=request.form.get('protocolo', '').strip().upper() or None
        )
        db.session.add(agendamento)
        db.session.flush()
        agendamento.numero_procedimento = build_numero_procedimento(agendamento.id)
        emit_realtime_event('agendamento_created', actor_id=session.get('user_id'), payload={'agendamento_id': agendamento.id})
        db.session.commit()
        return redirect_to_agendamento_month(agendamento, view='calendar')
    return render_template('edit.html', agendamento=None, medicos=medicos, procedimentos=procedimentos, selected_date=selected_date, return_context=return_context)

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau not in (2, 3)):
        flash('Acesso negado')
        return redirect(url_for('index'))
    agendamento = Agendamento.query.get_or_404(id)
    medicos = [{'id': m.id, 'nome': m.nome, 'crm': m.crm, 'cor': m.cor} for m in Medico.query.order_by(Medico.nome).all()]
    procedimentos = [{'id': p.id, 'nome': p.nome, 'cid': p.cid} for p in Procedimento.query.order_by(Procedimento.nome).all()]
    return_context = build_agendamento_return_params(agendamento=agendamento, source=request.args, view='calendar')
    if request.method == 'POST':
        nome_medico = request.form['nome_medico'].strip()
        submitted_crm = request.form['crm_medico'].strip()
        procedimento_name = request.form['procedimento'].strip()
        submitted_cid = request.form['cid_procedimento'].strip()

        crm_medico = resolve_medico_crm(nome_medico, submitted_crm)
        cid_val = resolve_procedimento_cid(procedimento_name, submitted_cid)

        agendamento.nome_paciente = request.form['nome_paciente']
        agendamento.whatsapp_paciente = request.form.get('whatsapp_paciente', '').strip() or None
        agendamento.nome_medico = nome_medico
        agendamento.crm_medico = crm_medico
        agendamento.procedimento = procedimento_name
        agendamento.cid_procedimento = cid_val
        agendamento.data = datetime.strptime(request.form['data'], '%Y-%m-%d').date()
        agendamento.hora = datetime.strptime(request.form['hora'], '%H:%M').time()
        agendamento.observacao = request.form['observacao']
        agendamento.protocolo = request.form.get('protocolo', '').strip().upper() or None
        emit_realtime_event('agendamento_updated', actor_id=session.get('user_id'), payload={'agendamento_id': agendamento.id})
        db.session.commit()
        return redirect_to_agendamento_month(agendamento, view='calendar')
    return render_template('edit.html', agendamento=agendamento, medicos=medicos, procedimentos=procedimentos, return_context=return_context)

@app.route('/delete/<int:id>', methods=['POST'])
def delete(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau not in (2, 3)):
        flash('Acesso negado')
        return redirect(url_for('index'))
    agendamento = Agendamento.query.get_or_404(id)
    emit_realtime_event('agendamento_deleted', actor_id=session.get('user_id'), payload={'agendamento_id': agendamento.id})
    db.session.delete(agendamento)
    db.session.commit()
    return redirect_to_agendamento_month(agendamento, view='calendar')

@app.route('/confirmar_cirurgia/<int:id>', methods=['POST'])
def confirmar_cirurgia(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user or user.grau != 3:
        flash('Acesso negado')
        return redirect(url_for('index'))

    agendamento = Agendamento.query.get_or_404(id)
    if not agendamento.cirurgia_confirmavel and not agendamento.cirurgia_confirmada:
        flash('Cirurgia ainda não pode ser confirmada para este agendamento.')
        return redirect_to_agendamento_month(agendamento, view='calendar')

    agendamento.cirurgia_confirmada = True
    agendamento.cirurgia_cancelada = False
    emit_realtime_event('cirurgia_confirmada', actor_id=session.get('user_id'), payload={'agendamento_id': agendamento.id})
    db.session.commit()
    flash('Cirurgia confirmada com sucesso.')
    return redirect_to_agendamento_month(agendamento, view='calendar')

@app.route('/cancelar_cirurgia/<int:id>', methods=['POST'])
def cancelar_cirurgia(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user or user.grau != 3:
        flash('Acesso negado')
        return redirect(url_for('index'))

    agendamento = Agendamento.query.get_or_404(id)
    if not agendamento.cirurgia_cancelavel and not agendamento.cirurgia_cancelada:
        flash('Cirurgia ainda não pode ser cancelada para este agendamento.')
        return redirect_to_agendamento_month(agendamento, view='calendar')

    agendamento.cirurgia_cancelada = True
    agendamento.cirurgia_confirmada = False
    emit_realtime_event('cirurgia_cancelada', actor_id=session.get('user_id'), payload={'agendamento_id': agendamento.id})
    db.session.commit()
    flash('Cirurgia cancelada com sucesso.')
    return redirect_to_agendamento_month(agendamento, view='calendar')

@app.route('/internacao/<int:id>', methods=['GET', 'POST'])
def internacao(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user_can_manage_internacao(user):
        flash('Acesso negado')
        return redirect(url_for('index'))
    agendamento = Agendamento.query.get_or_404(id)
    return_context = build_agendamento_return_params(agendamento=agendamento, source=request.args, view='calendar')
    if request.method == 'POST':
        protocolo_informado = request.form.get('protocolo', '').strip().upper() or None
        if protocolo_conflita_com_outro_paciente(protocolo_informado, agendamento.nome_paciente, exclude_agendamento_id=agendamento.id):
            flash('Protocolo já cadastrado para outro paciente.')
            return render_template('internacao.html', agendamento=agendamento, return_context=build_agendamento_return_params(agendamento=agendamento, source=request.form, view='calendar'))

        agendamento.protocolo = protocolo_informado
        agendamento.sala_cirurgica = request.form.get('sala_cirurgica', '').strip() or None
        agendamento.quarto = request.form.get('quarto', '').strip() or None
        emit_realtime_event('internacao_updated', actor_id=session.get('user_id'), payload={'agendamento_id': agendamento.id})
        db.session.commit()
        flash('Dados de internação atualizados.')
        return redirect_to_agendamento_month(agendamento, view='calendar')
    return render_template('internacao.html', agendamento=agendamento, return_context=return_context)

@app.route('/paciente/<int:id>', methods=['GET', 'POST'])
def paciente(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        session.pop('user_id', None)
        return redirect(url_for('login'))

    agendamento = Agendamento.query.get_or_404(id)
    nome_paciente_base = (agendamento.nome_paciente or '').strip()
    agendamentos_paciente = Agendamento.query.filter(
        func.lower(Agendamento.nome_paciente) == nome_paciente_base.lower()
    ).order_by(Agendamento.data.desc(), Agendamento.hora.desc(), Agendamento.id.desc()).all()
    ultimo_agendamento = agendamentos_paciente[0] if agendamentos_paciente else agendamento
    protocolo_paciente = next((item.protocolo for item in agendamentos_paciente if item.protocolo), None)
    whatsapp_paciente = next((item.whatsapp_paciente for item in agendamentos_paciente if item.whatsapp_paciente), None)
    return_context = build_paciente_return_params(agendamento=agendamento, source=request.args)
    focus_pagamentos = (request.args.get('focus') or '').strip().lower() == 'pagamentos'

    can_manage = user_can_manage_agendamentos(user)
    can_access_pagamentos = user_can_access_pagamentos(user)

    if request.method == 'POST':
        if not can_manage:
            flash('Acesso negado')
            return redirect(url_for('paciente', id=agendamento.id, **build_paciente_return_params(agendamento=agendamento, source=request.form)))

        action = request.form.get('action')

        if action == 'protocolo':
            protocolo_informado = request.form.get('protocolo', '').strip().upper() or None
            if protocolo_conflita_com_outro_paciente(protocolo_informado, agendamento.nome_paciente, exclude_agendamento_id=agendamento.id):
                flash('Protocolo já cadastrado para outro paciente.')
                return redirect(url_for('paciente', id=agendamento.id, **build_paciente_return_params(agendamento=agendamento, source=request.form)))

            for item in agendamentos_paciente:
                item.protocolo = protocolo_informado
            emit_realtime_event('paciente_protocolo_updated', actor_id=session.get('user_id'), payload={'agendamento_id': agendamento.id})
            db.session.commit()
            flash('Protocolo atualizado com sucesso para este paciente.')
            return redirect(url_for('paciente', id=agendamento.id, **build_paciente_return_params(agendamento=agendamento, source=request.form)))

        if action == 'whatsapp':
            whatsapp_informado = request.form.get('whatsapp_paciente', '').strip() or None
            for item in agendamentos_paciente:
                item.whatsapp_paciente = whatsapp_informado
            emit_realtime_event('paciente_whatsapp_updated', actor_id=session.get('user_id'), payload={'agendamento_id': agendamento.id})
            db.session.commit()
            flash('Telefone do paciente atualizado com sucesso.')
            return redirect(url_for('paciente', id=agendamento.id, **build_paciente_return_params(agendamento=agendamento, source=request.form)))

        if action != 'comprovante':
            flash('Ação inválida.')
            return redirect(url_for('paciente', id=agendamento.id, **build_paciente_return_params(agendamento=agendamento, source=request.form)))

        if not can_access_pagamentos:
            flash('Acesso negado para a aba de pagamento.')
            return redirect(url_for('paciente', id=agendamento.id, **build_paciente_return_params(agendamento=agendamento, source=request.form)))

        nome_medico = request.form.get('nome_medico', '').strip()
        procedimento = request.form.get('procedimento', '').strip()
        data_cirurgia_raw = request.form.get('data_cirurgia', '').strip()
        valor_raw = request.form.get('valor', '').strip()
        data_pagamento_raw = request.form.get('data_pagamento', '').strip()
        pagante = request.form.get('pagante', '').strip()
        meio_pagamento = request.form.get('meio_pagamento', '').strip()
        numero_procedimento = request.form.get('numero_procedimento', '').strip().upper()
        arquivo_pdf = request.files.get('arquivo_comprovante')

        if not all([numero_procedimento, nome_medico, procedimento, data_cirurgia_raw, valor_raw, pagante, meio_pagamento]):
            flash('Preencha todos os campos obrigatórios do comprovante.')
            return redirect(url_for('paciente', id=agendamento.id, **build_paciente_return_params(agendamento=agendamento, source=request.form)))

        agendamento_pagamento = Agendamento.query.filter_by(numero_procedimento=numero_procedimento).first()
        if not agendamento_pagamento:
            flash('Número de procedimento não encontrado.')
            return redirect(url_for('paciente', id=agendamento.id, **build_paciente_return_params(agendamento=agendamento, source=request.form)))

        if (agendamento_pagamento.nome_paciente or '').strip().lower() != (agendamento.nome_paciente or '').strip().lower():
            flash('Esse número de procedimento pertence a outro paciente.')
            return redirect(url_for('paciente', id=agendamento.id, **build_paciente_return_params(agendamento=agendamento, source=request.form)))

        try:
            data_cirurgia = datetime.strptime(data_cirurgia_raw, '%Y-%m-%d').date()
            data_pagamento = datetime.strptime(data_pagamento_raw, '%Y-%m-%d').date() if data_pagamento_raw else None
            valor = parse_currency_value(valor_raw)
            arquivo_nome = None
            arquivo_dados = None
            if arquivo_pdf and arquivo_pdf.filename:
                arquivo_nome, arquivo_dados = save_comprovante_pdf(arquivo_pdf)
        except ValueError:
            flash('Revise os dados do comprovante. Valor, datas e arquivo PDF precisam estar válidos.')
            return redirect(url_for('paciente', id=agendamento.id, **build_paciente_return_params(agendamento=agendamento, source=request.form)))

        comprovante = Comprovante(
            agendamento_id=agendamento_pagamento.id,
            nome_medico=nome_medico,
            procedimento=procedimento,
            data_cirurgia=data_cirurgia,
            valor=valor,
            data_pagamento=data_pagamento,
            pagante=pagante,
            meio_pagamento=meio_pagamento,
            arquivo_comprovante=arquivo_nome,
            arquivo_comprovante_dados=arquivo_dados,
            status='pago' if data_pagamento else 'pendente',
        )

        # Keep exactly one payment record per surgery (agendamento) to prevent duplicates.
        comprovante_existente = Comprovante.query.filter_by(agendamento_id=agendamento_pagamento.id).first()
        if comprovante_existente:
            comprovante_existente.nome_medico = nome_medico
            comprovante_existente.procedimento = procedimento
            comprovante_existente.data_cirurgia = data_cirurgia
            comprovante_existente.valor = valor
            comprovante_existente.data_pagamento = data_pagamento
            comprovante_existente.pagante = pagante
            comprovante_existente.meio_pagamento = meio_pagamento
            comprovante_existente.status = 'pago' if data_pagamento else 'pendente'
            if arquivo_dados:
                comprovante_existente.arquivo_comprovante = arquivo_nome
                comprovante_existente.arquivo_comprovante_dados = arquivo_dados
        else:
            db.session.add(comprovante)

        duplicados = Comprovante.query.filter_by(agendamento_id=agendamento_pagamento.id).order_by(Comprovante.criado_em.desc()).all()
        for item_duplicado in duplicados[1:]:
            db.session.delete(item_duplicado)

        emit_realtime_event('pagamento_updated', actor_id=session.get('user_id'), payload={'agendamento_id': agendamento_pagamento.id})
        db.session.commit()
        flash('Pagamento da cirurgia vinculado com sucesso.')
        redirect_params = build_paciente_return_params(agendamento=agendamento_pagamento, source=request.form)
        redirect_params['focus'] = 'pagamentos'
        return redirect(url_for('paciente', id=agendamento_pagamento.id, **redirect_params))

    agendamento_ids = [item.id for item in agendamentos_paciente]
    comprovantes = Comprovante.query.filter(
        Comprovante.agendamento_id.in_(agendamento_ids)
    ).order_by(Comprovante.data_cirurgia.desc(), Comprovante.criado_em.desc()).all()

    return render_template(
        'paciente.html',
        agendamento=agendamento,
        ultimo_agendamento=ultimo_agendamento,
        total_agendamentos=len(agendamentos_paciente),
        protocolo_paciente=protocolo_paciente,
        whatsapp_paciente=whatsapp_paciente,
        comprovantes=comprovantes,
        can_manage=can_manage,
        can_access_pagamentos=can_access_pagamentos,
        focus_pagamentos=focus_pagamentos,
        return_context=return_context,
    )

@app.route('/comprovante/editar/<int:comprovante_id>', methods=['GET', 'POST'])
def editar_comprovante(comprovante_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user or not user_can_access_pagamentos(user):
        flash('Acesso negado para editar comprovantes.')
        return redirect(url_for('index'))

    comprovante = Comprovante.query.get_or_404(comprovante_id)
    agendamento = Agendamento.query.get_or_404(comprovante.agendamento_id)
    return_context = build_paciente_return_params(agendamento=agendamento, source=request.args)

    if request.method == 'POST':
        nome_medico = request.form.get('nome_medico', '').strip()
        procedimento = request.form.get('procedimento', '').strip()
        data_cirurgia_raw = request.form.get('data_cirurgia', '').strip()
        valor_raw = request.form.get('valor', '').strip()
        data_pagamento_raw = request.form.get('data_pagamento', '').strip()
        pagante = request.form.get('pagante', '').strip()
        meio_pagamento = request.form.get('meio_pagamento', '').strip()
        arquivo_pdf = request.files.get('arquivo_comprovante')

        if not all([nome_medico, procedimento, data_cirurgia_raw, valor_raw, pagante, meio_pagamento]):
            flash('Preencha todos os campos obrigatórios do comprovante.')
            return render_template(
                'edit_comprovante.html',
                comprovante=comprovante,
                agendamento=agendamento,
                return_context=build_paciente_return_params(agendamento=agendamento, source=request.form),
            )

        try:
            data_cirurgia = datetime.strptime(data_cirurgia_raw, '%Y-%m-%d').date()
            data_pagamento = datetime.strptime(data_pagamento_raw, '%Y-%m-%d').date() if data_pagamento_raw else None
            valor = parse_currency_value(valor_raw)
            arquivo_nome = None
            arquivo_dados = None
            if arquivo_pdf and arquivo_pdf.filename:
                arquivo_nome, arquivo_dados = save_comprovante_pdf(arquivo_pdf)
        except ValueError:
            flash('Revise os dados do comprovante. Valor, datas e arquivo PDF precisam estar válidos.')
            return render_template(
                'edit_comprovante.html',
                comprovante=comprovante,
                agendamento=agendamento,
                return_context=build_paciente_return_params(agendamento=agendamento, source=request.form),
            )

        comprovante.nome_medico = nome_medico
        comprovante.procedimento = procedimento
        comprovante.data_cirurgia = data_cirurgia
        comprovante.valor = valor
        comprovante.data_pagamento = data_pagamento
        comprovante.pagante = pagante
        comprovante.meio_pagamento = meio_pagamento
        comprovante.status = 'pago' if data_pagamento else 'pendente'
        if arquivo_dados:
            comprovante.arquivo_comprovante = arquivo_nome
            comprovante.arquivo_comprovante_dados = arquivo_dados

        emit_realtime_event('comprovante_updated', actor_id=session.get('user_id'), payload={'agendamento_id': agendamento.id})
        db.session.commit()
        flash('Comprovante atualizado com sucesso.')
        redirect_params = build_paciente_return_params(agendamento=agendamento, source=request.form)
        redirect_params['focus'] = 'pagamentos'
        return redirect(url_for('paciente', id=agendamento.id, **redirect_params))

    return render_template(
        'edit_comprovante.html',
        comprovante=comprovante,
        agendamento=agendamento,
        return_context=return_context,
    )

@app.route('/api/agendamento-por-procedimento')
def api_agendamento_por_procedimento():
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401

    user = User.query.get(session['user_id'])
    if not user or not user_can_access_pagamentos(user):
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    numero = request.args.get('numero', '').strip().upper()
    if not numero:
        return jsonify({'ok': False, 'error': 'missing_numero'}), 400

    agendamento = Agendamento.query.filter_by(numero_procedimento=numero).first()
    if not agendamento:
        return jsonify({'ok': False, 'error': 'not_found'}), 404

    return jsonify({
        'ok': True,
        'agendamento_id': agendamento.id,
        'numero_procedimento': agendamento.numero_procedimento,
        'nome_paciente': agendamento.nome_paciente,
        'nome_medico': agendamento.nome_medico,
        'procedimento': agendamento.procedimento,
        'data_cirurgia': agendamento.data.strftime('%Y-%m-%d'),
    })

@app.route('/api/paciente-por-protocolo')
def api_paciente_por_protocolo():
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401

    protocolo = request.args.get('protocolo', '').strip().upper()
    if not protocolo:
        return jsonify({'ok': False, 'error': 'missing_protocolo'}), 400

    agendamento = Agendamento.query.filter_by(protocolo=protocolo).order_by(Agendamento.id.desc()).first()
    if not agendamento:
        return jsonify({'ok': False, 'error': 'not_found'}), 404

    return jsonify({
        'ok': True,
        'nome_paciente': agendamento.nome_paciente,
        'whatsapp_paciente': agendamento.whatsapp_paciente or '',
    })

@app.route('/pacientes')
def pacientes():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        session.pop('user_id', None)
        return redirect(url_for('login'))

    search_raw = request.args.get('q', '').strip()
    search = search_raw.lower()
    filtro_data = (request.args.get('filtro_data', 'novas') or 'novas').strip().lower()
    if filtro_data not in ('novas', 'antigas', 'mes'):
        filtro_data = 'novas'

    mes_filtro = (request.args.get('mes') or '').strip()
    query = Agendamento.query

    if mes_filtro:
        try:
            mes_year_str, mes_month_str = mes_filtro.split('-', 1)
            mes_year = int(mes_year_str)
            mes_month = int(mes_month_str)
            mes_inicio = date(mes_year, mes_month, 1)
            prox_ano, prox_mes = normalize_month(mes_year, mes_month + 1)
            mes_fim = date(prox_ano, prox_mes, 1)
            query = query.filter(Agendamento.data >= mes_inicio, Agendamento.data < mes_fim)
        except (ValueError, TypeError):
            mes_filtro = ''

    agendamentos = query.order_by(
        Agendamento.nome_paciente.asc(),
        Agendamento.data.desc(),
        Agendamento.hora.desc(),
    ).all()

    pacientes_map = {}
    paciente_agendamento_ids = {}
    all_agendamento_ids = []
    for agendamento in agendamentos:
        nome = (agendamento.nome_paciente or '').strip()
        if not nome:
            continue

        if search:
            id_match = search in str(agendamento.id)
            protocolo_match = search in (agendamento.protocolo or '').lower()
            nome_match = search in nome.lower()
            if not (id_match or protocolo_match or nome_match):
                continue

        key = nome.lower()
        if key not in pacientes_map:
            pacientes_map[key] = {
                'nome_paciente': nome,
                'perfil_id': agendamento.id,
                'qtd_cirurgias': 0,
                'tem_comprovante': False,
                'ultimo_agendamento': {
                    'id': agendamento.id,
                    'numero_procedimento': agendamento.numero_procedimento,
                    'data': agendamento.data,
                    'hora': agendamento.hora,
                    'procedimento': agendamento.procedimento,
                    'medico': agendamento.nome_medico,
                    'protocolo': agendamento.protocolo,
                },
            }
            paciente_agendamento_ids[key] = []

        paciente_item = pacientes_map[key]
        paciente_item['qtd_cirurgias'] += 1
        paciente_agendamento_ids[key].append(agendamento.id)
        all_agendamento_ids.append(agendamento.id)

    if all_agendamento_ids:
        agendamento_ids_comprovante = {
            item[0] for item in db.session.query(Comprovante.agendamento_id)
            .filter(Comprovante.agendamento_id.in_(all_agendamento_ids))
            .distinct()
            .all()
        }
        for key, ids in paciente_agendamento_ids.items():
            if any(ag_id in agendamento_ids_comprovante for ag_id in ids):
                pacientes_map[key]['tem_comprovante'] = True

    total_pacientes_sistema = len({
        (nome or '').strip().lower()
        for (nome,) in db.session.query(Agendamento.nome_paciente).all()
        if (nome or '').strip()
    })

    pacientes_data = list(pacientes_map.values())

    def paciente_data_key(paciente_item):
        ultimo = paciente_item.get('ultimo_agendamento') or {}
        return (
            ultimo.get('data') or date.min,
            ultimo.get('hora') or datetime.min.time(),
        )

    if filtro_data == 'antigas':
        pacientes_data.sort(key=paciente_data_key)
    elif filtro_data in ('novas', 'mes'):
        pacientes_data.sort(key=paciente_data_key, reverse=True)
    else:
        pacientes_data.sort(key=lambda p: p['nome_paciente'].lower())

    total_pacientes = len(pacientes_data)

    return render_template(
        'pacientes.html',
        pacientes=pacientes_data,
        total_pacientes=total_pacientes,
        total_pacientes_sistema=total_pacientes_sistema,
        search=search_raw,
        filtro_data=filtro_data,
        mes_filtro=mes_filtro,
    )

@app.route('/enfermagem')
def enfermagem():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    today = date.today()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    year, month = normalize_month(year, month)

    cal = calendar.monthcalendar(year, month)
    registros_por_dia = {}
    all_dates = []
    for week in cal:
        for day in week:
            if day != 0:
                d = date(year, month, day)
                if d.weekday() < 6:
                    all_dates.append(d)
                    registros_por_dia[d] = EnfermagemRegistro.query.filter_by(data=d).order_by(EnfermagemRegistro.id.asc()).all()

    prev_year, prev_month = normalize_month(year, month - 1)
    next_year, next_month = normalize_month(year, month + 1)

    return render_template(
        'enfermagem.html',
        year=year,
        month=month,
        month_name=PT_BR_MONTH_NAMES[month],
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        registros_por_dia=registros_por_dia,
        all_dates=all_dates,
    )

@app.route('/enfermagem/create', methods=['GET', 'POST'])
def enfermagem_create():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    selected_date = request.args.get('date', '')
    return_context = build_enfermagem_return_params(source=request.args)

    if request.method == 'POST':
        submitted_date = request.form.get('data', '').strip()
        if not submitted_date:
            flash('Preencha a data do registro.')
            return render_template('enfermagem_edit.html', registro=None, selected_date=selected_date, return_context=build_enfermagem_return_params(source=request.form))

        registro = EnfermagemRegistro(
            nome_colaborador='',
            nome_medico='',
            crm_medico=0,
            procedimento='',
            cid_procedimento='',
            data=datetime.strptime(submitted_date, '%Y-%m-%d').date(),
            observacao=request.form.get('observacao', ''),
            created_by=session.get('user_id'),
        )
        db.session.add(registro)
        db.session.flush()
        emit_realtime_event('enfermagem_created', actor_id=session.get('user_id'), payload={'registro_id': registro.id})
        db.session.commit()
        return redirect(url_for('enfermagem', **build_enfermagem_return_params(registro=registro, source=request.form)))

    return render_template('enfermagem_edit.html', registro=None, selected_date=selected_date, return_context=return_context)

@app.route('/enfermagem/edit/<int:id>', methods=['GET', 'POST'])
def enfermagem_edit(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    registro = EnfermagemRegistro.query.get_or_404(id)
    return_context = build_enfermagem_return_params(registro=registro, source=request.args)

    if request.method == 'POST':
        submitted_date = request.form.get('data', '').strip()
        if not submitted_date:
            flash('Preencha a data do registro.')
            return render_template('enfermagem_edit.html', registro=registro, return_context=build_enfermagem_return_params(registro=registro, source=request.form))

        registro.data = datetime.strptime(submitted_date, '%Y-%m-%d').date()
        registro.observacao = request.form.get('observacao', '')
        emit_realtime_event('enfermagem_updated', actor_id=session.get('user_id'), payload={'registro_id': registro.id})
        db.session.commit()
        return redirect(url_for('enfermagem', **build_enfermagem_return_params(registro=registro, source=request.form)))

    return render_template('enfermagem_edit.html', registro=registro, return_context=return_context)

@app.route('/enfermagem/delete/<int:id>', methods=['POST'])
def enfermagem_delete(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    registro = EnfermagemRegistro.query.get_or_404(id)
    emit_realtime_event('enfermagem_deleted', actor_id=session.get('user_id'), payload={'registro_id': registro.id})
    db.session.delete(registro)
    db.session.commit()
    return redirect(url_for('enfermagem', **build_enfermagem_return_params(registro=registro, source=request.args)))

# ─── Escala de Anestesistas ───────────────────────────────────────────────────

@app.route('/anestesistas')
def anestesistas():
    today = date.today()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    year, month = normalize_month(year, month)

    cal = calendar.monthcalendar(year, month)
    prev_year, prev_month = normalize_month(year, month - 1)
    next_year, next_month = normalize_month(year, month + 1)

    month_start = date(year, month, 1)
    next_month_start = date(next_year, next_month, 1)

    escalas = EscalaAnestesista.query.filter(
        EscalaAnestesista.data >= month_start,
        EscalaAnestesista.data < next_month_start,
    ).all()
    escala_por_dia = {e.data: e for e in escalas}

    all_dates = []
    for week in cal:
        for day in week:
            if day != 0:
                all_dates.append(date(year, month, day))

    return render_template(
        'anestesistas.html',
        year=year,
        month=month,
        month_name=PT_BR_MONTH_NAMES[month],
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        all_dates=all_dates,
        escala_por_dia=escala_por_dia,
        today=today,
    )


@app.route('/anestesistas/set', methods=['POST'])
def anestesista_set():
    if 'user_id' not in session:
        flash('É necessário fazer login para editar a escala.')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user or user.grau < 2:
        flash('Acesso negado.')
        return redirect(url_for('anestesistas'))

    data_raw = request.form.get('data', '').strip()
    nome = request.form.get('nome', '').strip()
    year = request.form.get('year', type=int)
    month = request.form.get('month', type=int)

    if not data_raw or not nome:
        flash('Data e nome do anestesista são obrigatórios.')
        return redirect(url_for('anestesistas', year=year, month=month))

    try:
        dia = datetime.strptime(data_raw, '%Y-%m-%d').date()
    except ValueError:
        flash('Data inválida.')
        return redirect(url_for('anestesistas', year=year, month=month))

    escala = EscalaAnestesista.query.filter_by(data=dia).first()
    if escala:
        escala.nome = nome
        escala.updated_by = user.id
    else:
        escala = EscalaAnestesista(data=dia, nome=nome, updated_by=user.id)
        db.session.add(escala)

    emit_realtime_event('anestesista_updated', actor_id=session.get('user_id'), payload={'escala_data': dia.strftime('%Y-%m-%d')})
    db.session.commit()
    return redirect(url_for('anestesistas', year=year, month=month))


@app.route('/anestesistas/delete/<int:escala_id>', methods=['POST'])
def anestesista_delete(escala_id):
    if 'user_id' not in session:
        flash('É necessário fazer login.')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user or user.grau < 2:
        flash('Acesso negado.')
        return redirect(url_for('anestesistas'))

    escala = EscalaAnestesista.query.get_or_404(escala_id)
    year = escala.data.year
    month = escala.data.month
    emit_realtime_event('anestesista_deleted', actor_id=session.get('user_id'), payload={'escala_data': escala.data.strftime('%Y-%m-%d')})
    db.session.delete(escala)
    db.session.commit()
    return redirect(url_for('anestesistas', year=year, month=month))

# ─────────────────────────────────────────────────────────────────────────────

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau != 3):
        flash('Acesso negado')
        return redirect(url_for('admin'))
    if user.id == user_id:
        flash('Você não pode excluir a si mesmo.')
        return redirect(url_for('admin'))
    target_user = User.query.get_or_404(user_id)
    db.session.delete(target_user)
    db.session.commit()
    flash(f'Usuário {target_user.nome} excluído com sucesso.')
    return redirect(url_for('admin'))

with app.app_context():
    ensure_database_ready()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)