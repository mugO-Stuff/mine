# Sistema de Agendamento - Clínica de Estética

## 🎯 Objetivo

Aplicação web simples para gerenciamento de agendamentos, com foco em
usabilidade para pessoas mais velhas, funcionando em computador e
celular.

-   Visualização livre (sem login)
-   Edição apenas com autenticação simples (ID e Senha), requisitos de cadastro: Nome e Senha númerica, minimo 6 digitos
-   Interface limpa e intuitiva
-   Tema em tons de azul cirúrgico

------------------------------------------------------------------------

## 🧱 Tecnologias

### Backend

-   Python
-   Flask
-   SQLite
-   SQLAlchemy

### Frontend

-   HTML5
-   CSS3 (responsivo)
-   JavaScript puro (sem frameworks)

------------------------------------------------------------------------

## 🗄️ Banco de Dados

### users

-   id (integer, PK)
-   nome (string)
-   cargo (string)
-   senha (string - apenas números)

### agendamentos

-   id (integer, PK)
-   nome_paciente (string)
-   nome_medico (string)
-   crm_medico (int)
-   procedimento (string)
-   cid_procedimento (string)
-   data (date)
-   hora (time)
-   observacao (text)

------------------------------------------------------------------------

## 🔐 Autenticação

-   Não exigir login para acessar
-   Entrar obrigatório para criar, editar ou excluir

### Entrar:

-   Nome
-   Senha numérica

### Regras:

-   Validar usuário existente
-   Permitir ação se válido
-   Mostrar erro se inválido

------------------------------------------------------------------------

## 🖥️ Interface

-   Tema azul cirúrgico (clean)
-   Botões medios
-   Layout simples
-   Fonte legível
-   Espaçamento confortável
-   Responsivo (mobile + desktop)

------------------------------------------------------------------------

## 📅 Funcionalidades

### Tela principal

-   Lista de agendamentos do dia mostrando uma lista todos os dias do mês, exceto sabados, domingos e feriados
-   Navegação entre datas

### Ações

-   Criar agendamento
-   Editar agendamento
-   Excluir agendamento

------------------------------------------------------------------------

## 🧩 Comportamento

## 🚀 Como Executar

1. Instale o Python (versão 3.8 ou superior) se não estiver instalado.
2. Instale as dependências: `pip install -r requirements.txt`
3. Execute o aplicativo: `python app.py`
4. Acesse http://127.0.0.1:5000 no navegador.

### Observações
- O banco de dados SQLite será criado automaticamente na primeira execução.
- Para adicionar usuários, você pode modificar o código ou usar um script separado.

### Criar

-   Formulário:
    -   Nome do cliente
    -   Procedimento
    -   Médico
    -   Data
    -   Hora
    -   Observação
-   Solicitar login antes de salvar

### Editar

-   Alterar dados
-   Solicitar login antes de salvar

### Excluir

-   Confirmar ação
-   Solicitar login

### Obs

- Médicos e Procedimentos, terão um banco de dados, podendo ser editado pelo usuario com senha.
- Cada nome de médico será vinculado ao um CRM, e cada Procedimento sera vinculado a um CID, tais informações ficarão gravadas em uma opção de mais detalhes quando clicado em um agendamento especifico.

------------------------------------------------------------------------

## ⚙️ Rotas (Flask)

-   GET / → página principal
-   GET /agendamentos → listar
-   POST /agendamentos → criar
-   PUT /agendamentos/`<id>`{=html} → editar
-   DELETE /agendamentos/`<id>`{=html} → excluir
-   POST /login → validar

------------------------------------------------------------------------

## 💡 Regras Técnicas

-   Estrutura:
    -   /templates
    -   /static
-   Usar fetch API (AJAX)
-   Evitar reload de página
-   O sistema informara a um usuario que acabou de entrar, caso algum outro usuario esteja fazendo alguma alteração na agenda, mas somente se estiver alterando algo, e o aviso sera sutil, como uma notificação pequena na parte superio da aplicação

------------------------------------------------------------------------

## ✨ Extras

-   Ordenar por data
-   Destaque de datas próximos
-   Feedback visual (sucesso/erro)

------------------------------------------------------------------------

## 🧪 Objetivo Final

Gerar um MVP funcional: - Rodar localmente - Fácil de usar - Base para
evolução futura (SaaS)
