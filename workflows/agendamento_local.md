# Agendamento local (sem GitHub Actions)

Para rodar o agente todo dia na própria máquina, use o agendador do sistema
operacional. O agente lê as variáveis do arquivo `.env`.

## Linux / macOS (cron)

Editar o crontab:

```bash
crontab -e
```

Adicionar (08:00 todos os dias):

```cron
0 8 * * * cd /caminho/para/analytical-force && /usr/bin/python3 main.py >> logs/cron.log 2>&1
```

## Windows (Agendador de Tarefas)

1. Abra o "Agendador de Tarefas".
2. Crie uma tarefa básica, gatilho "Diariamente" às 08:00.
3. Ação: "Iniciar um programa".
   - Programa: `python`
   - Argumentos: `main.py`
   - Iniciar em: caminho do projeto `analytical-force`.

## Observações

- Para usar o Ollama local, garanta que o serviço esteja ativo (`ollama serve`)
  antes do horário agendado. Caso contrário, o agente cai automaticamente para
  o modo `template`.
- Valide a configuração antes de agendar: `python main.py --check`.
