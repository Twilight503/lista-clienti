# Sită clienți Mongo + Render

## Unde salvează
Implicit:
- DB_NAME = test
- COLLECTION_NAME = Clienti maro/rosu
- document _id = state

## Rulează local Windows

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
set MONGO_URI=URI_UL_TAU
set DB_NAME=test
set COLLECTION_NAME=Clienti maro/rosu
set APP_PASSWORD=parola-ta
python app.py
```

## Render
Environment Variables:
- MONGO_URI = URI-ul tău MongoDB
- DB_NAME = test
- COLLECTION_NAME = Clienti maro/rosu
- APP_PASSWORD = parola pentru site
- SECRET_KEY = orice string lung

Start command:
```bash
gunicorn app:app
```

## Important
Aplicația are protecție simplă anti-suprascriere: dacă două persoane salvează simultan cu date vechi, pagina se reîncarcă în loc să suprascrie baza.
