from app import app, ensure_database_ready

print("Iniciando criação do admin...")

with app.app_context():
    admin, created = ensure_database_ready(create_default_admin=True, update_admin_password=True)
    if created:
        print('Usuário admin criado com sucesso!')
    else:
        print('Usuário admin encontrado e atualizado com sucesso!')
