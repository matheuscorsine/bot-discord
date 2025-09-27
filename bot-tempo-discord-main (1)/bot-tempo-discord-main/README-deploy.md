# README-deploy.md — Passo-a-passo detalhado

## Requisitos do servidor
- Python 3.10+ (recomendado 3.11)
- Docker (opcional)
- systemd (Linux) se for usar serviço
- SQLite (já incluído no Python)

## 1) Preparar o projeto
```bash
# no servidor
git clone <repo> discord-time-bot
cd discord-time-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# editar .env com valores reais (DISCORD_TOKEN, API_TOKEN, DB_PATH)
```

## 2) Iniciar localmente
```bash
python bot.py
# em outro terminal, para API:
uvicorn api:app --host 0.0.0.0 --port 8000
```

## 3) Docker (opcional)
```bash
docker build -t discord-time-bot:1.0 .
docker run -d --env-file .env --name discord-time-bot discord-time-bot:1.0
```

## 4) Criar systemd service
Edite `discord-time-bot.service` com seu `USER` e `WorkingDirectory` e copie para `/etc/systemd/system/`.
```bash
sudo systemctl daemon-reload
sudo systemctl enable discord-time-bot
sudo systemctl start discord-time-bot
sudo journalctl -u discord-time-bot -f
```

## 5) Backup da DB
Faça backup regular:
```bash
cp data.db data.db.bak
sqlite3 data.db .dump > dump.sql
```

## 6) Regenerar Token após transferência
Após transferência de app (se aplicável), o comprador deve regenerar token no Discord Developer Portal e atualizar `.env`.

