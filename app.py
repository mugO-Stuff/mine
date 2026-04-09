# Forçando novo deploy no Render em 09/04/2026

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text, UniqueConstraint, inspect
from datetime import datetime, date, timedelta
from collections import Counter
import calendar
import os
import json
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
app.config['SECRET_KEY'] = 'your_secret_key_here'
import os
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///agendadia.db')
app.permanent_session_lifetime = timedelta(days=30)
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

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cargo = db.Column(db.String(100), nullable=False)
    senha = db.Column(db.String(100), nullable=False)  # numeric password
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
    sala_cirurgica = db.Column(db.String(50))
    quarto = db.Column(db.String(50))
    protocolo = db.Column(db.String(50))
    comprovantes = db.relationship('Comprovante', backref='agendamento', lazy=True, cascade='all, delete-orphan')

    @property
    def esta_concluido(self):
        campos_finais = [self.protocolo, self.sala_cirurgica, self.quarto]
        return self.data < date.today() and all(valor and str(valor).strip() for valor in campos_finais)

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

@app.context_processor
def inject_user():
    current_user = None
    if 'user_id' in session:
        current_user = User.query.get(session['user_id'])
    return dict(current_user=current_user, asset_version=ASSET_VERSION)

@app.before_request
def keep_session_persistent():
    if 'user_id' in session:
        session.permanent = True

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

def user_can_manage_agendamentos(user):
    return bool(user and (user.cargo == 'admin' or user.grau in (2, 3)))

def user_can_manage_internacao(user):
    return bool(user and user.nivel in (2, 3))

def user_can_access_pagamentos(user):
    return bool(user and user.grau == 3)

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

def redirect_to_agendamento_month(agendamento, view='calendar'):
    target_date = agendamento.data if agendamento and agendamento.data else date.today()
    return redirect(url_for('index', year=target_date.year, month=target_date.month, view=view))

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
            if 'sala_cirurgica' not in agendamento_columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN sala_cirurgica VARCHAR(50)"))
            if 'quarto' not in agendamento_columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN quarto VARCHAR(50)"))
            if 'protocolo' not in agendamento_columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN protocolo VARCHAR(50)"))

        if comprovante_columns and 'arquivo_comprovante' not in comprovante_columns:
            conn.execute(text("ALTER TABLE comprovante ADD COLUMN arquivo_comprovante VARCHAR(255)"))

def ensure_admin_user(update_password=False):
    admin = User.query.filter_by(nome=DEFAULT_ADMIN_NAME).order_by(User.id).first()
    if not admin:
        admin = User.query.filter_by(cargo='admin', grau=3).order_by(User.id).first()

    created = admin is None
    if created:
        admin = User(
            nome=DEFAULT_ADMIN_NAME,
            cargo=DEFAULT_ADMIN_CARGO,
            senha=DEFAULT_ADMIN_PASSWORD,
            status='approved',
            grau=3,
        )
        db.session.add(admin)
    else:
        admin.cargo = DEFAULT_ADMIN_CARGO
        admin.status = 'approved'
        admin.grau = 3
        if update_password:
            admin.senha = DEFAULT_ADMIN_PASSWORD

    db.session.commit()
    return admin, created

def ensure_database_ready(create_default_admin=True, update_admin_password=False):
    db.create_all()
    ensure_sqlite_legacy_columns()
    normalizar_numero_procedimento()
    os.makedirs(os.path.join(app.static_folder, UPLOAD_COMPROVANTES_FOLDER), exist_ok=True)

    if create_default_admin:
        return ensure_admin_user(update_password=update_admin_password)

    return None, False

def save_comprovante_pdf(uploaded_file):
    filename = secure_filename(uploaded_file.filename or '')
    if not filename:
        return None

    if not filename.lower().endswith('.pdf'):
        raise ValueError('Somente arquivos PDF são permitidos para comprovante.')

    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    stored_name = f"comprovante_{timestamp}.pdf"
    rel_path = os.path.join(UPLOAD_COMPROVANTES_FOLDER, stored_name)
    abs_path = os.path.join(app.static_folder, rel_path)

    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    uploaded_file.save(abs_path)

    return rel_path.replace('\\', '/')

def cleanup_old_chat_messages():
    cutoff = datetime.utcnow() - timedelta(days=30)
    ChatMessage.query.filter(ChatMessage.created_at < cutoff).delete(synchronize_session=False)
    db.session.commit()

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
    month_start = date(year, month, 1)
    month_end = date(next_month_year, next_month_num, 1)
    all_appointments = []
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

    reminder_status = {}
    for appt in Agendamento.query.filter(
        Agendamento.data >= month_start,
        Agendamento.data < month_end
    ).all():
        days_until = (appt.data - today).days
        if days_until == 2:
            reminder_status[appt.id] = 'reminder-soon'
        elif days_until == 1:
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nome = request.form['nome']
        senha = request.form['senha']
        user = User.query.filter_by(nome=nome, senha=senha).first()
        if user and user.status == 'approved':
            session['user_id'] = user.id
            session.permanent = True
            return redirect(url_for('index'))
        else:
            flash('Credenciais inválidas ou conta não aprovada')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nome = request.form['nome']
        cargo = request.form['cargo']
        senha = request.form['senha']
        if len(senha) < 6 or not senha.isdigit():
            flash('Senha deve ter pelo menos 6 dígitos numéricos')
            return render_template('register.html')
        existing_user = User.query.filter_by(nome=nome).first()
        if existing_user:
            flash('Nome já cadastrado')
            return render_template('register.html')
        user = User(nome=nome, cargo=cargo, senha=senha, status='pending', grau=1)
        db.session.add(user)
        db.session.commit()
        flash('Cadastro solicitado. Aguarde aprovação do admin.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
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

            if senha_atual != user.senha:
                flash('A senha atual está incorreta.')
                return redirect(url_for('perfil'))

            if len(nova_senha) < 6 or not nova_senha.isdigit():
                flash('A nova senha deve ter pelo menos 6 dígitos numéricos.')
                return redirect(url_for('perfil'))

            if nova_senha != confirmar_senha:
                flash('A confirmação da senha não confere.')
                return redirect(url_for('perfil'))

            user.senha = nova_senha
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

            user.senha = nova_senha
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

@app.route('/admin/delete_medico/<int:medico_id>')
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

@app.route('/approve/<int:user_id>')
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

@app.route('/reject/<int:user_id>')
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
    if request.method == 'POST':
        nome_medico = request.form['nome_medico'].strip()
        submitted_crm = request.form['crm_medico'].strip()
        procedimento_name = request.form['procedimento'].strip()
        submitted_cid = request.form['cid_procedimento'].strip()

        crm_medico = resolve_medico_crm(nome_medico, submitted_crm)
        cid_val = resolve_procedimento_cid(procedimento_name, submitted_cid)

        agendamento = Agendamento(
            nome_paciente=request.form['nome_paciente'],
            nome_medico=nome_medico,
            crm_medico=crm_medico,
            procedimento=procedimento_name,
            cid_procedimento=cid_val,
            data=datetime.strptime(request.form['data'], '%Y-%m-%d').date(),
            hora=datetime.strptime(request.form['hora'], '%H:%M').time(),
            observacao=request.form['observacao']
        )
        db.session.add(agendamento)
        db.session.flush()
        agendamento.numero_procedimento = build_numero_procedimento(agendamento.id)
        db.session.commit()
        return redirect_to_agendamento_month(agendamento, view='calendar')
    return render_template('edit.html', agendamento=None, medicos=medicos, procedimentos=procedimentos, selected_date=selected_date)

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
    if request.method == 'POST':
        nome_medico = request.form['nome_medico'].strip()
        submitted_crm = request.form['crm_medico'].strip()
        procedimento_name = request.form['procedimento'].strip()
        submitted_cid = request.form['cid_procedimento'].strip()

        crm_medico = resolve_medico_crm(nome_medico, submitted_crm)
        cid_val = resolve_procedimento_cid(procedimento_name, submitted_cid)

        agendamento.nome_paciente = request.form['nome_paciente']
        agendamento.nome_medico = nome_medico
        agendamento.crm_medico = crm_medico
        agendamento.procedimento = procedimento_name
        agendamento.cid_procedimento = cid_val
        agendamento.data = datetime.strptime(request.form['data'], '%Y-%m-%d').date()
        agendamento.hora = datetime.strptime(request.form['hora'], '%H:%M').time()
        agendamento.observacao = request.form['observacao']
        db.session.commit()
        return redirect_to_agendamento_month(agendamento, view='calendar')
    return render_template('edit.html', agendamento=agendamento, medicos=medicos, procedimentos=procedimentos)

@app.route('/delete/<int:id>')
def delete(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau not in (2, 3)):
        flash('Acesso negado')
        return redirect(url_for('index'))
    agendamento = Agendamento.query.get_or_404(id)
    target_date = agendamento.data
    db.session.delete(agendamento)
    db.session.commit()
    return redirect(url_for('index', year=target_date.year, month=target_date.month, view='calendar'))

@app.route('/internacao/<int:id>', methods=['GET', 'POST'])
def internacao(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user_can_manage_internacao(user):
        flash('Acesso negado')
        return redirect(url_for('index'))
    agendamento = Agendamento.query.get_or_404(id)
    if request.method == 'POST':
        protocolo_informado = request.form.get('protocolo', '').strip().upper() or None
        if protocolo_conflita_com_outro_paciente(protocolo_informado, agendamento.nome_paciente, exclude_agendamento_id=agendamento.id):
            flash('Protocolo já cadastrado para outro paciente.')
            return render_template('internacao.html', agendamento=agendamento)

        agendamento.protocolo = protocolo_informado
        agendamento.sala_cirurgica = request.form.get('sala_cirurgica', '').strip() or None
        agendamento.quarto = request.form.get('quarto', '').strip() or None
        db.session.commit()
        flash('Dados de internação atualizados.')
        return redirect_to_agendamento_month(agendamento, view='calendar')
    return render_template('internacao.html', agendamento=agendamento)

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

    can_manage = user_can_manage_agendamentos(user)
    can_access_pagamentos = user_can_access_pagamentos(user)

    if request.method == 'POST':
        if not can_manage:
            flash('Acesso negado')
            return redirect(url_for('paciente', id=agendamento.id))

        action = request.form.get('action')

        if action == 'protocolo':
            protocolo_informado = request.form.get('protocolo', '').strip().upper() or None
            if protocolo_conflita_com_outro_paciente(protocolo_informado, agendamento.nome_paciente, exclude_agendamento_id=agendamento.id):
                flash('Protocolo já cadastrado para outro paciente.')
                return redirect(url_for('paciente', id=agendamento.id))

            for item in agendamentos_paciente:
                item.protocolo = protocolo_informado
            db.session.commit()
            flash('Protocolo atualizado com sucesso para este paciente.')
            return redirect(url_for('paciente', id=agendamento.id))

        if action == 'whatsapp':
            whatsapp_informado = request.form.get('whatsapp_paciente', '').strip() or None
            for item in agendamentos_paciente:
                item.whatsapp_paciente = whatsapp_informado
            db.session.commit()
            flash('WhatsApp do paciente atualizado com sucesso.')
            return redirect(url_for('paciente', id=agendamento.id))

        if action != 'comprovante':
            flash('Ação inválida.')
            return redirect(url_for('paciente', id=agendamento.id))

        if not can_access_pagamentos:
            flash('Acesso negado para a aba de pagamento.')
            return redirect(url_for('paciente', id=agendamento.id))

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
            return redirect(url_for('paciente', id=agendamento.id))

        agendamento_pagamento = Agendamento.query.filter_by(numero_procedimento=numero_procedimento).first()
        if not agendamento_pagamento:
            flash('Número de procedimento não encontrado.')
            return redirect(url_for('paciente', id=agendamento.id))

        if (agendamento_pagamento.nome_paciente or '').strip().lower() != (agendamento.nome_paciente or '').strip().lower():
            flash('Esse número de procedimento pertence a outro paciente.')
            return redirect(url_for('paciente', id=agendamento.id))

        try:
            data_cirurgia = datetime.strptime(data_cirurgia_raw, '%Y-%m-%d').date()
            data_pagamento = datetime.strptime(data_pagamento_raw, '%Y-%m-%d').date() if data_pagamento_raw else None
            valor = parse_currency_value(valor_raw)
            arquivo_comprovante = None
            if arquivo_pdf and arquivo_pdf.filename:
                arquivo_comprovante = save_comprovante_pdf(arquivo_pdf)
        except ValueError:
            flash('Revise os dados do comprovante. Valor, datas e arquivo PDF precisam estar válidos.')
            return redirect(url_for('paciente', id=agendamento.id))

        comprovante = Comprovante(
            agendamento_id=agendamento_pagamento.id,
            nome_medico=nome_medico,
            procedimento=procedimento,
            data_cirurgia=data_cirurgia,
            valor=valor,
            data_pagamento=data_pagamento,
            pagante=pagante,
            meio_pagamento=meio_pagamento,
            arquivo_comprovante=arquivo_comprovante,
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
            if arquivo_comprovante:
                comprovante_existente.arquivo_comprovante = arquivo_comprovante
        else:
            db.session.add(comprovante)

        duplicados = Comprovante.query.filter_by(agendamento_id=agendamento_pagamento.id).order_by(Comprovante.criado_em.desc()).all()
        for item_duplicado in duplicados[1:]:
            db.session.delete(item_duplicado)

        db.session.commit()
        flash('Pagamento da cirurgia vinculado com sucesso.')
        return redirect(url_for('paciente', id=agendamento_pagamento.id))

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

@app.route('/pacientes')
def pacientes():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        session.pop('user_id', None)
        return redirect(url_for('login'))

    search = request.args.get('q', '').strip().lower()
    agendamentos = Agendamento.query.order_by(
        Agendamento.nome_paciente.asc(),
        Agendamento.data.desc(),
        Agendamento.hora.desc(),
    ).all()

    pacientes_map = {}
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

        paciente_item = pacientes_map[key]
        paciente_item['qtd_cirurgias'] += 1

    pacientes_data = sorted(pacientes_map.values(), key=lambda p: p['nome_paciente'].lower())

    return render_template(
        'pacientes.html',
        pacientes=pacientes_data,
        search=request.args.get('q', '').strip(),
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

    medicos = [{'id': m.id, 'nome': m.nome, 'crm': m.crm, 'cor': m.cor} for m in Medico.query.order_by(Medico.nome).all()]
    procedimentos = [{'id': p.id, 'nome': p.nome, 'cid': p.cid} for p in Procedimento.query.order_by(Procedimento.nome).all()]
    selected_date = request.args.get('date', '')

    if request.method == 'POST':
        nome_colaborador = request.form.get('nome_colaborador', '').strip()
        nome_medico = request.form.get('nome_medico', '').strip()
        procedimento_name = request.form.get('procedimento', '').strip()
        submitted_crm = request.form.get('crm_medico', '').strip()
        submitted_cid = request.form.get('cid_procedimento', '').strip()

        if not nome_colaborador or not nome_medico or not procedimento_name:
            flash('Preencha colaborador, médico e procedimento.')
            return render_template('enfermagem_edit.html', registro=None, medicos=medicos, procedimentos=procedimentos, selected_date=selected_date)

        crm_medico = resolve_medico_crm(nome_medico, submitted_crm)
        cid_val = resolve_procedimento_cid(procedimento_name, submitted_cid)

        registro = EnfermagemRegistro(
            nome_colaborador=nome_colaborador,
            nome_medico=nome_medico,
            crm_medico=crm_medico,
            procedimento=procedimento_name,
            cid_procedimento=cid_val,
            data=datetime.strptime(request.form['data'], '%Y-%m-%d').date(),
            observacao=request.form.get('observacao', ''),
            created_by=session.get('user_id'),
        )
        db.session.add(registro)
        db.session.commit()
        return redirect(url_for('enfermagem'))

    return render_template('enfermagem_edit.html', registro=None, medicos=medicos, procedimentos=procedimentos, selected_date=selected_date)

@app.route('/enfermagem/edit/<int:id>', methods=['GET', 'POST'])
def enfermagem_edit(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    registro = EnfermagemRegistro.query.get_or_404(id)
    medicos = [{'id': m.id, 'nome': m.nome, 'crm': m.crm, 'cor': m.cor} for m in Medico.query.order_by(Medico.nome).all()]
    procedimentos = [{'id': p.id, 'nome': p.nome, 'cid': p.cid} for p in Procedimento.query.order_by(Procedimento.nome).all()]

    if request.method == 'POST':
        nome_colaborador = request.form.get('nome_colaborador', '').strip()
        nome_medico = request.form.get('nome_medico', '').strip()
        procedimento_name = request.form.get('procedimento', '').strip()
        submitted_crm = request.form.get('crm_medico', '').strip()
        submitted_cid = request.form.get('cid_procedimento', '').strip()

        if not nome_colaborador or not nome_medico or not procedimento_name:
            flash('Preencha colaborador, médico e procedimento.')
            return render_template('enfermagem_edit.html', registro=registro, medicos=medicos, procedimentos=procedimentos)

        registro.nome_colaborador = nome_colaborador
        registro.nome_medico = nome_medico
        registro.crm_medico = resolve_medico_crm(nome_medico, submitted_crm)
        registro.procedimento = procedimento_name
        registro.cid_procedimento = resolve_procedimento_cid(procedimento_name, submitted_cid)
        registro.data = datetime.strptime(request.form['data'], '%Y-%m-%d').date()
        registro.observacao = request.form.get('observacao', '')
        db.session.commit()
        return redirect(url_for('enfermagem'))

    return render_template('enfermagem_edit.html', registro=registro, medicos=medicos, procedimentos=procedimentos)

@app.route('/enfermagem/delete/<int:id>')
def enfermagem_delete(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    registro = EnfermagemRegistro.query.get_or_404(id)
    db.session.delete(registro)
    db.session.commit()
    return redirect(url_for('enfermagem'))

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