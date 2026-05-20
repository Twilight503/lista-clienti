# Verificare Clienți - Render + MongoDB

Aplicația salvează baza în MongoDB, nu în localStorage.

## Environment Variables pe Render

MONGO_URI=URI-ul tău MongoDB
DB_NAME=test
COLLECTION_NAME=Clienti maro/rosu
APP_PASSWORD=parola cu care intri pe site
SECRET_KEY=un text lung/random

## Deploy pe Render

Build Command:
pip install -r requirements.txt

Start Command:
gunicorn app:app

## Import backup

După deploy:
1. intri pe site cu parola
2. mergi la Backup
3. Importă backup JSON
4. poți importa backup_compatibil_local_usor.json sau backup-ul exportat din aplicație


## Optimizare Mongo inclusă

- Ștergerile sunt definitive; `deletedRecords` este golit automat.
- Backup-urile automate sunt limitate la ultimele 3 copii complete.
- Există protecție `_rev` ca două persoane să nu suprascrie baza simultan.
- Feedback-ul autosalvat folosește debounce în frontend.
