# Sită clienți Mongo v13

Versiune pentru Render + MongoDB.

## Flux import listă agent
Lipești lista actuală completă a agentului.
- Numerele lipite devin ACTIV/MARO/ROȘU după culoare sau text.
- Numerele care erau ACTIV la agent, dar nu mai apar în lista lipită, devin DISPĂRUT.
- Numerele care erau deja MARO/ROȘU nu mai sunt așteptate în listă.

## Environment Variables pe Render
- MONGO_URI = URI-ul tău MongoDB
- DB_NAME = test
- COLLECTION_NAME = Clienti maro/rosu
- APP_PASSWORD = parola pentru site
- SECRET_KEY = orice string lung

## Start command
gunicorn app:app
