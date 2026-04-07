from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text
from datetime import datetime, date, timedelta
from collections import Counter
import calendar

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///agendamentos.db'
db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cargo = db.Column(db.String(100), nullable=False)
    senha = db.Column(db.String(100), nullable=False)  # numeric password
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    grau = db.Column(db.Integer, default=1)  # 1=view-only, 2=edit appointments, 3=admin

class Agendamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_paciente = db.Column(db.String(100), nullable=False)
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

class Medico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    crm = db.Column(db.Integer, unique=True, nullable=False)
    cor = db.Column(db.String(7), default='#004d40')  # Hex color code

class Procedimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cid = db.Column(db.String(20), unique=True, nullable=False)

@app.context_processor
def inject_user():
    current_user = None
    if 'user_id' in session:
        current_user = User.query.get(session['user_id'])
    return dict(current_user=current_user)

def normalize_month(year, month):
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month

@app.route('/')
def index():
    today = date.today()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    view_mode = request.args.get('view', 'calendar')
    year, month = normalize_month(year, month)
    cal = calendar.monthcalendar(year, month)
    appointments = {}
    all_dates = []
    for week in cal:
        for day in week:
            if day != 0:
                d = date(year, month, day)
                if d.weekday() < 5:
                    all_dates.append(d)
                    appointments[d] = Agendamento.query.filter_by(data=d).all()
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
    
    return render_template(
        'index.html',
        appointments=appointments,
        all_appointments=all_appointments,
        all_dates=all_dates,
        year=year,
        month=month,
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
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nome = request.form['nome']
        senha = request.form['senha']
        user = User.query.filter_by(nome=nome, senha=senha).first()
        if user and user.status == 'approved':
            session['user_id'] = user.id
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

@app.route('/admin/set_user_grade/<int:user_id>', methods=['POST'])
def set_user_grade(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.cargo != 'admin' and user.grau != 3):
        flash('Acesso negado')
        return redirect(url_for('index'))
    target_user = User.query.get_or_404(user_id)
    try:
        grade = int(request.form['grau'])
    except (ValueError, KeyError):
        flash('Grau inválido.')
        return redirect(url_for('admin'))
    if grade not in (1, 2, 3):
        flash('Grau inválido.')
        return redirect(url_for('admin'))
    target_user.grau = grade
    db.session.commit()
    flash(f'Grau do usuário {target_user.nome} atualizado para {grade}.')
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
    if request.method == 'POST':
        nome_medico = request.form['nome_medico'].strip()
        submitted_crm = request.form['crm_medico'].strip()
        procedimento_name = request.form['procedimento'].strip()
        submitted_cid = request.form['cid_procedimento'].strip()

        crm_medico = None
        if submitted_crm.isdigit():
            crm_medico = int(submitted_crm)
        else:
            medico = Medico.query.filter(func.lower(Medico.nome) == nome_medico.lower()).first()
            crm_medico = medico.crm if medico else 0

        procedimento_obj = Procedimento.query.filter(func.lower(Procedimento.nome) == procedimento_name.lower()).first()
        if procedimento_obj and submitted_cid and submitted_cid != procedimento_obj.cid:
            cid_val = f"{submitted_cid} - {procedimento_obj.cid}"
        elif procedimento_obj:
            cid_val = procedimento_obj.cid
        else:
            cid_val = submitted_cid

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
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('edit.html', agendamento=None, medicos=medicos, procedimentos=procedimentos)

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

        if submitted_crm.isdigit():
            crm_medico = int(submitted_crm)
        else:
            medico = Medico.query.filter(func.lower(Medico.nome) == nome_medico.lower()).first()
            crm_medico = medico.crm if medico else 0

        procedimento_obj = Procedimento.query.filter(func.lower(Procedimento.nome) == procedimento_name.lower()).first()
        if procedimento_obj and submitted_cid and submitted_cid != procedimento_obj.cid:
            cid_val = f"{submitted_cid} - {procedimento_obj.cid}"
        elif procedimento_obj:
            cid_val = procedimento_obj.cid
        else:
            cid_val = submitted_cid

        agendamento.nome_paciente = request.form['nome_paciente']
        agendamento.nome_medico = nome_medico
        agendamento.crm_medico = crm_medico
        agendamento.procedimento = procedimento_name
        agendamento.cid_procedimento = cid_val
        agendamento.data = datetime.strptime(request.form['data'], '%Y-%m-%d').date()
        agendamento.hora = datetime.strptime(request.form['hora'], '%H:%M').time()
        agendamento.observacao = request.form['observacao']
        db.session.commit()
        return redirect(url_for('index'))
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
    db.session.delete(agendamento)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/internacao/<int:id>', methods=['GET', 'POST'])
def internacao(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or user.grau not in (2, 3):
        flash('Acesso negado')
        return redirect(url_for('index'))
    agendamento = Agendamento.query.get_or_404(id)
    if request.method == 'POST':
        agendamento.sala_cirurgica = request.form.get('sala_cirurgica', '').strip() or None
        agendamento.quarto = request.form.get('quarto', '').strip() or None
        agendamento.protocolo = request.form.get('protocolo', '').strip() or None
        db.session.commit()
        flash('Dados de internação atualizados.')
        return redirect(url_for('index'))
    return render_template('internacao.html', agendamento=agendamento)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Ensure new Medico color column exists in older databases
        with db.engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info('user')")).fetchall()
            columns = [row[1] for row in result]
            if 'grau' not in columns:
                conn.execute(text("ALTER TABLE user ADD COLUMN grau INTEGER DEFAULT 1"))
        with db.engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info('medico')")).fetchall()
            columns = [row[1] for row in result]
            if 'cor' not in columns:
                conn.execute(text("ALTER TABLE medico ADD COLUMN cor VARCHAR(7) DEFAULT '#004d40'"))
        with db.engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info('agendamento')")).fetchall()
            columns = [row[1] for row in result]
            if 'sala_cirurgica' not in columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN sala_cirurgica VARCHAR(50)"))
            if 'quarto' not in columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN quarto VARCHAR(50)"))
            if 'protocolo' not in columns:
                conn.execute(text("ALTER TABLE agendamento ADD COLUMN protocolo VARCHAR(50)"))
        # Create default admin if not exists
        admin = User.query.filter_by(nome='Gestão Esplanada').first()
        if not admin:
            admin = User(nome='Gestão', cargo='admin', senha='13092026', status='approved', grau=3)
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True)