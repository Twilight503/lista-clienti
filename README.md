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

## SAFE

Statusul SAFE se setează din Edit / Istoric → Acțiune manuală. SAFE este ignorat de Audit listă, nu intră la Transfer MARO și rămâne până este schimbat manual sau șters.

## Detectare culori Google Sheets

Importul colorat nu mai verifică doar `#ff0000` și `#5b0f00`.
Detectează familii de culoare:
- roșu / roșu închis / vișiniu => ROȘU
- maro / brun / cafeniu / mahon => MARO
- galben, verde, albastru, cyan, magenta, portocaliu aprins, gri, alb, negru => ACTIV

## Fix detectare roșu/maro

Regulă nouă:
- ROȘU este doar roșul oficial folosit în Google Sheets: `#ff0000` / aproape identic.
- Roșu închis, vișiniu, bordo, maro-roșcat, brun, cafeniu, mahon => MARO.
- Magenta/roz neon, galben, verde, albastru, cyan, gri, alb, negru => ACTIV.

## Fix strict culori Google Sheets

Regula curentă:
- ROȘU = doar roșul aprins oficial `#ff0000`.
- MARO = doar nuanțele închise folosite ca maro: roșu închis/bordo/maro-roșcat/brun/cafeniu închis.
- Portocaliu aprins `#ff9900`, galben, magenta, verde, albastru, cyan, gri, alb, negru = ACTIV.
