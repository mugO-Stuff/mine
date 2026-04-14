# Avaliacao Tecnica Senior - AgendaDia

Data da avaliacao: 14/04/2026
Escopo: Revisao tecnica do sistema Flask (backend, frontend, seguranca, dados e operacao), sem alteracao de codigo.

## Resumo Executivo
O sistema entrega valor de negocio real e cobre fluxos importantes da clinica (agenda, internacao, pacientes, comprovantes, chat, admin). A evolucao funcional esta boa para um MVP.

Ao mesmo tempo, existem riscos relevantes de seguranca e governanca que precisam ser tratados para uso mais robusto em producao, principalmente autenticacao, segredos e protecao contra requisicoes indevidas.

Classificacao geral atual:
- Produto e funcionalidades: Bom
- Arquitetura para MVP: Bom
- Seguranca para producao: Insuficiente (itens criticos)
- Manutenibilidade: Media

## Pontos Fortes
1. Boa cobertura de fluxo operacional do negocio.
2. Regras de permissao por nivel de usuario ja implementadas.
3. Interface orientada ao uso diario, com calendario e acoes rapidas.
4. Estrutura unica de app.py simplifica entendimento inicial para time pequeno.
5. Evolucao de schema considerada com funcoes de compatibilidade para SQLite legado.

## Achados Principais (por severidade)

### Critico
1. Senhas armazenadas e comparadas em texto puro.
2. Chave de sessao hardcoded e credencial admin padrao previsivel.
3. Rotas destrutivas em GET e ausencia de protecao CSRF.

### Alto
1. Execucao com debug habilitado no ponto de inicializacao local.

### Medio
1. Modelo de Enfermagem ficou com campos obrigatorios antigos, enquanto tela/fluxo atual usa apenas data e observacao.
2. Padrao N+1 de consultas no calendario mensal.
3. Disparo de push reminders acoplado ao acesso da pagina principal (fluxo de leitura executando tarefa operacional).
4. Limpeza de mensagens de chat em rotas frequentes, podendo elevar custo no banco.
5. Upload validado apenas por extensao do arquivo (.pdf), sem validacao do conteudo.

### Baixo
1. README divergente do comportamento real de algumas rotas.
2. Ausencia de testes automatizados no repositorio.

## Analise Arquitetural
- O sistema esta centralizado em um unico arquivo principal. Isso acelera a entrega no inicio, mas aumenta risco de regressao e dificulta evolucao por equipes maiores.
- O uso de SQLAlchemy e templates server-side e adequado para o porte atual.
- Algumas responsabilidades de infraestrutura (jobs, limpeza, push dispatch) estao no ciclo de requisicao web, quando idealmente deveriam estar desacopladas.

## Analise de Produto e UX
- A aplicacao cobre o fluxo completo de agenda com foco pratico.
- A usabilidade esta alinhada ao publico operacional.
- Existem ajustes de consistencia entre telas e modelo de dados que melhorariam a previsibilidade de uso e relatorios.

## Melhorias Recomendadas (Geral)
1. Modularizar o backend por dominios:
- auth
- agendamentos
- internacao
- pacientes
- admin
- chat
- notificacoes

2. Padronizar metodos HTTP:
- GET somente leitura
- POST/PUT/DELETE para alteracoes

3. Corrigir divergencias entre modelo e regra de negocio da Enfermagem.

4. Reduzir consultas por dia no calendario usando consulta unica por intervalo e agrupamento em memoria.

5. Atualizar README para refletir o estado real do sistema.

6. Adicionar testes automatizados:
- testes de autenticacao/autorizacao
- testes de rotas criticas
- testes de regras de negocio (conclusao, internacao, confirmacao/cancelamento)

7. Criar trilha de auditoria para acoes sensiveis:
- exclusoes
- aprovacoes/rejeicoes
- alteracoes de internacao e status cirurgico

## Melhorias de Seguranca (Prioridade)
1. Substituir senha em texto puro por hash seguro com sal (ex: Werkzeug generate_password_hash/check_password_hash).

2. Remover segredos hardcoded do codigo e forcar configuracao por variavel de ambiente:
- SECRET_KEY
- senha inicial de admin
- tokens de integracao

3. Implementar protecao CSRF em todos os formularios e endpoints mutantes.

4. Migrar rotas destrutivas GET para POST/DELETE com confirmacao no frontend.

5. Desabilitar debug fora de ambiente local e formalizar configuracao por ambiente (dev/homolog/prod).

6. Fortalecer sessao e cookies:
- SESSION_COOKIE_HTTPONLY = True
- SESSION_COOKIE_SECURE = True (em HTTPS)
- SESSION_COOKIE_SAMESITE = Lax/Strict

7. Endurecer upload de arquivos:
- validar MIME real e assinatura de arquivo
- limitar tamanho
- registrar metadados de upload

8. Implementar rate limit e lockout gradual para login.

9. Registrar logs de seguranca:
- tentativas de login
- falhas de autorizacao
- operacoes administrativas

10. Definir politica de backup e recuperacao (RPO/RTO) para dados clinicos e financeiros.

## Plano de Acao Sugerido
Fase 1 (urgente - 1 a 2 semanas):
- hash de senha
- secrets via ambiente
- rotas destrutivas via POST
- CSRF
- remover debug em producao

Fase 2 (curto prazo - 2 a 4 semanas):
- modularizacao inicial
- performance de consultas
- hardening de upload
- testes de regressao para fluxos criticos

Fase 3 (medio prazo):
- auditoria completa
- observabilidade
- revisao de dados historicos e governanca

## Conclusao
Como avaliacao de lideranca tecnica: o projeto esta bem encaminhado para um MVP funcional e demonstra boa capacidade de entrega de produto. Para avancar com seguranca e confiabilidade de producao, os itens criticos de seguranca e integridade operacional precisam ser tratados como prioridade imediata.
