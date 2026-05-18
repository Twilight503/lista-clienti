# Verificare Clienți - Render + MongoDB

Aplicația salvează baza în MongoDB, în:
- DB_NAME=test
- COLLECTION_NAME=Clienti maro/rosu
- document _id=state

## Environment Variables pe Render

MONGO_URI=URI-ul tău MongoDB
DB_NAME=test
COLLECTION_NAME=Clienti maro/rosu
APP_PASSWORD=parola cu care intri pe site
SECRET_KEY=un text lung/random

## Start command

gunicorn app:app

## Local test Windows

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
set MONGO_URI=URI_UL_TAU
set DB_NAME=test
set COLLECTION_NAME=Clienti maro/rosu
set APP_PASSWORD=parola-ta
python app.py
