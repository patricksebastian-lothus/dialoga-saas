# Guia — EMG-1A: CRM operacional vertical

## Objetivo

Primeira etapa do roadmap Emagrecentro: transformar o dIAloga+ de uma base de leads/chatbot em uma operação de CRM própria, reduzindo a dependência futura de sistemas externos.

Esta fase é aditiva: cria tabelas novas e endpoints novos. Não altera colunas de tabelas existentes.

## Entregas

### Backend

Novo router:

```txt
backend/app/routers/crm.py
```

Novo prefixo de API:

```txt
/api/crm
```

Novas tabelas em `backend/app/models.py`:

```txt
crm_tags
custom_fields
custom_field_values
crm_pipelines
crm_pipeline_stages
crm_tasks
quick_replies
```

Como são tabelas novas, o `Base.metadata.create_all()` cria automaticamente no startup. Não é necessário adicionar colunas em `_ADDITIVE_COLUMNS`.

### Frontend

Novas páginas:

```txt
frontend/etiquetas.html
frontend/campos-personalizados.html
frontend/pipelines.html
frontend/tarefas.html
frontend/respostas-rapidas.html
```

Novos métodos em:

```txt
frontend/js/api.js
```

Novos itens no menu em:

```txt
frontend/js/layout.js
```

## Bootstrap Emagrecentro

Endpoint:

```txt
POST /api/crm/bootstrap/emagrecentro
```

Cria de forma idempotente:

- etiquetas padrão;
- campos personalizados padrão;
- funil Emagrecentro;
- etapas do funil;
- respostas rápidas iniciais.

Pode ser acionado pelas telas:

- Etiquetas;
- Campos personalizados;
- Pipelines;
- Respostas rápidas.

## Etiquetas padrão

Exemplos:

```txt
Lead
Agendou
Compareceu
Não compareceu
Comprou
Não comprou
Emagrecimento
Gordura localizada
Flacidez
Indicação
Desqualificado
```

## Campos personalizados padrão

Exemplos:

```txt
Unidade de interesse
Procedimento de interesse
Condição de saúde
Link do anúncio
Data da avaliação
Horário da avaliação
Gordura local - área
Emagrecimento - kg
Origem da campanha
```

## Funil padrão

```txt
Lead novo
Em conversa
Agendou avaliação
Compareceu
Não compareceu
Comprou
Não comprou
Reativação
```

## Próximas fases

### EMG-1B

Integrar campos personalizados, etiquetas gerenciadas, pipeline e tarefas diretamente na ficha do contato/lead.

### EMG-2

Evoluir agenda própria: disponibilidade, bloqueios, feriados, status de comparecimento e automações de confirmação/reagendamento.

### EMG-3

Agente de IA vertical para clínica: identidade, método, condições comerciais, regras de agendamento e limites clínicos.
