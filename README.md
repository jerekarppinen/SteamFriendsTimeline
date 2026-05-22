# SteamFriends

Pieni Python-sovellus, joka hakee Steam-kaverilistan Steam Web API:sta ja tekee interaktiivisen aikajanan siitä, milloin kaveruudet ovat alkaneet.

## Tiedostot

- `app.py` käynnistää selaimessa käytettävän aikajanasivun ja pitää Steam API -avaimen backendissä.
- `.env.example` näyttää tarvittavat ympäristömuuttujat ilman oikeaa API-avainta.
- `requirements.txt` listaa Python-riippuvuudet.

## Asennus

Luo projektiin Python-virtuaaliympäristö:

```powershell
python -m venv .venv
```

Aktivoi virtuaaliympäristö:

```powershell
.\.venv\Scripts\Activate.ps1
```

Asenna riippuvuudet:

```powershell
pip install -r requirements.txt
```

## Steam-asetukset

`.env`-tiedostoon pitää laittaa oma Steam Web API -avain. Avaimen voi luoda Steamissa osoitteessa https://steamcommunity.com/dev/apikey.

Kopioi ensin esimerkkitiedosto:

```powershell
Copy-Item .env.example .env
```

Täytä sitten `.env`:

```text
STEAM_API_KEY=oma_api_avain_tähän
```

Käyttäjä syöttää Steam-profiilin URL:n sivun input-kenttään. URL voi olla numeerinen profiili tai vanity-osoite, esimerkiksi `https://steamcommunity.com/id/oma-nimi/`.

Lisäksi Steam-profiilin kaverilistan pitää olla julkinen:

1. Avaa https://steamcommunity.com/my/edit/settings
2. Aseta oma profiili julkiseksi.
3. Aseta kaverilista julkiseksi.
4. Tallenna muutokset.

Jos kaverilista ei ole julkinen, Steam palauttaa `401 Unauthorized`.

## Käyttö

Käynnistä selainversio projektin juuressa:

```powershell
.\.venv\Scripts\python.exe app.py
```

Sivu avautuu osoitteessa:

```text
http://127.0.0.1:8000
```

Aluksi sivu pyytää syöttämään Steam-profiilin URL:n. Kun kenttään tulee validi profiili, kenttä välähtää vihreäksi ja data haetaan. Ryhmävalikolla voi suodattaa näkyviin vain tietyn Steam-ryhmän kaverit.

## Huomiot

Steam palauttaa joillekin kavereille `friend_since`-arvoksi `0`. Skripti suodattaa nämä pois kuvaajasta, koska muuten ne näkyisivät virheellisesti vuoden 1970 kohdalla.
