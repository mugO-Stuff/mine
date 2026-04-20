# AgendaDia

Sistema web para gestao de agendamentos cirurgicos, internacao, pacientes, enfermagem, escala de anestesistas, comprovantes e chat interno.

## Visao Geral

- Backend em Flask com SQLAlchemy.
- Frontend server-side com Jinja2, CSS e JavaScript puro.
- Banco principal via SQLAlchemy (SQLite por padrao, com suporte a DATABASE_URL).
- PWA com manifest e service worker.
- Notificacoes push (quando configuradas com VAPID).

## Principais Funcionalidades

1. Agenda mensal em modo calendario e lista.
2. Cadastro, edicao e exclusao de agendamentos.
3. Confirmacao e cancelamento de cirurgia (nivel admin).
4. Internacao por agendamento (protocolo, sala cirurgica e quarto).
5. Perfil consolidado do paciente com historico e comprovantes.
6. Tela de pacientes com busca por nome, protocolo e ID.
7. Modulo de enfermagem (registro por data e observacao).
8. Escala mensal de anestesistas.
9. Painel administrativo para usuarios, medicos e procedimentos.
10. Chat interno com limpeza automatica de historico antigo.

## Niveis de Acesso

- Grau 1: visualizacao.
- Grau 2: gestao de agendamentos e modulos operacionais.
- Grau 3: administracao completa.

O status do usuario pode ser pending, approved ou rejected.

## Autenticacao e Senhas

- Login por nome e senha.
- Senhas sao armazenadas com hash seguro (Werkzeug).
- Contas antigas com senha em texto puro sao migradas automaticamente para hash no primeiro login valido e tambem no bootstrap da aplicacao.
- Cadastro e alteracao de senha (usuario e admin) ja salvam senha com hash.

## Estrutura do Projeto

- app.py: aplicacao principal, modelos, rotas e regras de negocio.
- create_admin.py: utilitario para criar/atualizar usuario admin padrao.
- templates/: paginas HTML (Jinja2).
- static/: CSS, JS, icones, service worker e manifest.
- instance/: arquivos locais da instancia.

## Setup Local

1. Instale Python 3.8+.
2. Instale dependencias:

```bash
pip install -r requirements.txt
```

3. Execute a aplicacao:

```bash
python app.py
```

4. Acesse:

http://127.0.0.1:5000

## Variaveis de Ambiente

- DATABASE_URL: string de conexao do banco.
- SECRET_KEY: chave secreta da aplicacao para sessao e CSRF.
- ASSET_VERSION: versao de cache busting de assets.
- SESSION_COOKIE_SECURE: forca cookie seguro em HTTPS (1/true para ativar).
- SESSION_COOKIE_SAMESITE: politica SameSite do cookie de sessao (padrao Lax).
- DEFAULT_ADMIN_NAME: nome do admin inicial.
- DEFAULT_ADMIN_PASSWORD: senha do admin inicial.
- DEFAULT_ADMIN_CARGO: cargo do admin inicial.
- VAPID_PUBLIC_KEY: chave publica para push.
- VAPID_PRIVATE_KEY: chave privada para push.
- VAPID_CLAIMS_SUB: identificacao do emissor de push.
- PUSH_DISPATCH_TOKEN: token para rota de disparo de push.
- GOOGLE_CLIENT_ID: Client ID OAuth 2.0 do Google.
- GOOGLE_CLIENT_SECRET: Client Secret OAuth 2.0 do Google.
- GOOGLE_REDIRECT_URI: URL de callback OAuth (opcional). Se vazio, usa /google-calendar/callback com URL externa automatica.
- GOOGLE_CALENDAR_TIMEZONE: timezone usada ao criar eventos (padrao America/Sao_Paulo).

Observacao: os tokens do Google Calendar ficam persistidos por usuario no banco e so sao removidos quando a conta e desconectada manualmente.

## Rotas Principais

### Publicas

- GET /: pagina principal da agenda (acesso de leitura).
- GET/POST /login
- GET/POST /register
- GET /logout

### Agenda e Pacientes

- GET/POST /create
- GET/POST /edit/<int:id>
- POST /delete/<int:id>
- POST /confirmar_cirurgia/<int:id>
- POST /cancelar_cirurgia/<int:id>
- GET/POST /internacao/<int:id>
- GET/POST /paciente/<int:id>
- GET/POST /comprovante/editar/<int:comprovante_id>
- GET /pacientes
- GET /api/agendamento-por-procedimento
- GET /google-calendar/connect/<int:agendamento_id>
- GET /google-calendar/callback
- GET /google-calendar/create-event/<int:agendamento_id>
- POST /google-calendar/disconnect

### Admin

- GET /admin
- GET/POST /admin/perfil_usuario/<int:user_id>
- POST /admin/add_medico
- GET/POST /admin/edit_medico/<int:medico_id>
- POST /admin/delete_medico/<int:medico_id>
- POST /admin/add_procedimento
- POST /approve/<int:user_id>
- POST /reject/<int:user_id>
- POST /admin/set_user_level/<int:user_id>
- POST /admin/set_user_grade/<int:user_id>
- POST /admin/set_user_levels_bulk
- POST /admin/delete_user/<int:user_id>

### Enfermagem

- GET /enfermagem
- GET/POST /enfermagem/create
- GET/POST /enfermagem/edit/<int:id>
- POST /enfermagem/delete/<int:id>

### Anestesistas

- GET /anestesistas
- POST /anestesistas/set
- POST /anestesistas/delete/<int:escala_id>

### Chat e Push

- GET /chat
- GET /api/chat/messages
- POST /api/chat/send
- GET /api/push/public-key
- POST /api/push/subscribe
- POST /api/push/unsubscribe
- POST /api/push/dispatch

### Assets PWA

- GET /service-worker.js
- GET /manifest.webmanifest
- GET /favicon.ico

## Modelos de Dados (Resumo)

- User
- Agendamento
- Medico
- Procedimento
- EscalaAnestesista
- EnfermagemRegistro
- Comprovante
- PushSubscription
- PushReminderLog
- ChatMessage

## Observacoes Tecnicas

1. O app cria/ajusta o banco na inicializacao para manter compatibilidade com estrutura legada.
2. O numero de procedimento e normalizado automaticamente no bootstrap.
3. Comprovantes aceitam upload de PDF e sao armazenados em static/uploads/comprovantes.

## Status Atual do Projeto

Este repositorio representa um MVP funcional em operacao, com modulos clinicos e administrativos ativos.

Melhorias recomendadas para a proxima etapa:

1. Endurecimento de seguranca (CSRF e rotas destrutivas em POST).
2. Modularizacao do backend por dominio.
3. Suite de testes automatizados para rotas e regras criticas.
