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

Sovellus käyttää muistissa olevaa 6 tunnin cachea per SteamID. Cache vähentää Steam API -kutsuja refreshien ja toistuvien hakujen aikana. Cache tyhjenee, kun palvelin käynnistetään uudelleen.

## Deploy Linux-palvelimelle

Esimerkit olettavat Ubuntu/Debian-palvelimen, systemd:n ja Nginxin.

Asenna tarvittavat paketit:

```bash
sudo apt update
sudo apt install python3 python3-venv
```

Kopioi projekti palvelimelle esimerkiksi hakemistoon `/opt/steamfriends`:

```bash
sudo mkdir -p /opt/steamfriends
sudo chown "$USER":"$USER" /opt/steamfriends
cd /opt/steamfriends
git clone <repo-url> .
```

Luo virtuaaliympäristö ja asenna riippuvuudet:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Luo `.env`:

```bash
cp .env.example .env
nano .env
```

Täytä tiedostoon oma Steam Web API -avain:

```text
STEAM_API_KEY=oma_api_avain_tähän
```

Luo systemd-palvelu:

```bash
sudo nano /etc/systemd/system/steamfriends.service
```

Sisältö:

```ini
[Unit]
Description=SteamFriends timeline app
After=network.target

[Service]
WorkingDirectory=/opt/steamfriends
ExecStart=/opt/steamfriends/.venv/bin/python app.py
Restart=always
RestartSec=5
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

Anna palvelun käyttäjälle lukuoikeus projektiin ja käynnistä palvelu:

```bash
sudo chown -R www-data:www-data /opt/steamfriends
sudo systemctl daemon-reload
sudo systemctl enable --now steamfriends
sudo systemctl status steamfriends
```

Tässä vaiheessa sovellus kuuntelee paikallisesti portissa `8000`.

### Nginx

Asenna nginx:

```bash
sudo apt install nginx
```

Luo reverse proxy -konfiguraatio:

```bash
sudo nano /etc/nginx/sites-available/steamfriends
```

Sisältö, vaihda `example.com` omaan domainiin:

```nginx
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Ota sivusto käyttöön:

```bash
sudo ln -s /etc/nginx/sites-available/steamfriends /etc/nginx/sites-enabled/steamfriends
sudo nginx -t
sudo systemctl reload nginx
```

HTTPS kannattaa ottaa käyttöön Certbotilla:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d example.com
```

### Apache

Asenna Apache ja ota käyttöön tarvittavat proxy-moduulit:

```bash
sudo apt install apache2
sudo a2enmod proxy proxy_http
```

Luo virtuaalihostin konfiguraatio:

```bash
sudo nano /etc/apache2/sites-available/steamfriends.conf
```

Sisältö, vaihda `example.com` omaan domainiin:

```apache
<VirtualHost *:80>
    ServerName example.com

    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:8000/
    ProxyPassReverse / http://127.0.0.1:8000/
</VirtualHost>
```

Ota sivusto käyttöön:

```bash
sudo a2ensite steamfriends
sudo apachectl configtest
sudo systemctl reload apache2
```

HTTPS kannattaa ottaa käyttöön Certbotilla:

```bash
sudo apt install certbot python3-certbot-apache
sudo certbot --apache -d example.com
```

API-avain pysyy palvelimen `.env`-tiedostossa. Älä lisää `.env`-tiedostoa versionhallintaan.
