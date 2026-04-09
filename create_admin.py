from app import app, db, User

print("Iniciando criação do admin...")

with app.app_context():
    admin = User.query.filter_by(nome='Gestão').first()
    if not admin:
        admin = User(
            nome='Gestão',
            cargo='Gerencia',
            senha='13092026',  # senha em texto puro, igual ao sistema atual
            status='approved',
            grau=3
        )
        db.session.add(admin)
        db.session.commit()
        print('Usuário admin criado com sucesso!')
    else:
        print('Usuário admin já existe.')
