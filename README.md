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

## Logo / favicon

Am adăugat un favicon SVG cu logo `VC` și badge vizual în header.

## Fix audit înainte de aplicare

- În tabelul `Ce a citit` există buton `Elimină`.
- Dacă elimini un rând, preview-ul și cardurile de sus se recalculează imediat.
- Contorul `NOI` după aplicare nu mai dublează client nou + apariție nouă.


## Arhivă
- tab nou `Arhivă` în loc de `Logout`
- numerele arhivate rămân 90 zile
- după 90 zile se șterg automat definitiv
- `Audit listă` și `Adaugă numere` ignoră numerele deja arhivate
- dacă un număr arhivat reapare, se notează în arhivă
- din Arhivă poți `Reactivează` sau `Șterge definitiv`


## Fix versiune
- Arhiva se deschide corect din meniu.
- În Audit listă, cardurile ACTIV/MARO/ROȘU contorizează doar schimbările noi, nu statusurile deja existente.
- La salvare apare indicator cu rotiță și apoi bifă când update-ul a intrat în baza de date.

## Fix salvare calitativ
- Am eliminat mesajul global care rămânea în josul paginii.
- `save()` returnează promisiunea salvării în MongoDB.
- La Audit listă și Adăugare numere, spinnerul rămâne în raport până răspunde serverul MongoDB.
- După salvare reușită, spinnerul dispare și rămâne doar mesajul de succes.

## Fix logică arhivă / audit

- Arhiva nu mai blochează global numerele.
- Dacă un număr arhivat reapare în Audit sau Adaugă numere, este reactivat și istoricul vechi se păstrează.
- Dacă un număr a mai fost la agent și revine după transfer/istoric, aplicația permite adăugarea, dar afișează atenționare.
- În Audit, rândurile problematice apar primele în `Ce a citit`.
- Raportul de audit are secțiune `Atenții importante`.

## Fix sintaxă
- Corectat dublarea accidentală `async async` pe funcțiile de aplicare.
- Verificat cu `node --check` după generare.

## Fix citire paste audit

- `Audit listă` combină acum clipboard HTML, DOM-ul efectiv din zona lipită și textul plain.
- Repară cazul în care un număr se vedea în zona lipită, dar nu apărea în tabelul `Ce a citit`.
- Numerele arhivate nu sunt ignorate; dacă sunt citite, apar în preview și se reactivează la aplicare.
- Eliminarea din preview se face după telefon, nu după indexul sortat.
