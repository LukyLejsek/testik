from flask import Flask, render_template, request, redirect, session, url_for
import os
import psycopg2
from urllib.parse import urlparse
import uuid
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "hodne_tajny_klic"  # změň si na něco unikátního

# Připojení k databázi PostgreSQL
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
url = urlparse(DATABASE_URL)

conn_params = {
    "dbname": url.path[1:],
    "user": url.username,
    "password": url.password,
    "host": url.hostname,
    "port": url.port,
}

def get_db_connection():
    result = urlparse(os.environ.get("DATABASE_URL"))
    username = result.username
    password = result.password
    database = result.path[1:]
    hostname = result.hostname
    port = result.port

    return psycopg2.connect(
        dbname=database,
        user=username,
        password=password,
        host=hostname,
        port=port,
        cursor_factory=psycopg2.extras.DictCursor  # <-- tohle přidáš
    )

# Inicializace databáze

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS uzivatele (
                id SERIAL PRIMARY KEY,
                jmeno TEXT,
                email TEXT UNIQUE,
                heslo TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS turnaje (
                id TEXT PRIMARY KEY,
                nazev TEXT NOT NULL,
                sport TEXT,
                datum TEXT,
                pocet_tymu INTEGER,
                popis TEXT,
                format TEXT,
                autor_id INTEGER REFERENCES uzivatele(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS zapasy (
                id SERIAL PRIMARY KEY,
                turnaj_id TEXT REFERENCES turnaje(id),
                tym1 TEXT,
                tym2 TEXT,
                score1 INTEGER,
                score2 INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS tymy (
                id SERIAL PRIMARY KEY,
                nazev TEXT NOT NULL,
                popis TEXT,
                kapitan_id INTEGER REFERENCES uzivatele(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS tym_clenove (
                id SERIAL PRIMARY KEY,
                tym_id INTEGER REFERENCES tymy(id),
                uzivatel_id INTEGER REFERENCES uzivatele(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS prihlasene_tymy (
                id SERIAL PRIMARY KEY,
                turnaj_id TEXT REFERENCES turnaje(id),
                tym_id INTEGER REFERENCES tymy(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()



@app.route("/vytvorit", methods=["GET", "POST"])
def vytvorit():
    if "uzivatel_id" not in session:
        return redirect("/prihlaseni")

    if request.method == "POST":
        # získání dat z formuláře
        nazev = request.form["nazev"]
        sport = request.form["sport"]
        datum = request.form["datum"]
        pocet_tymu = request.form["pocet_tymu"]
        popis = request.form["popis"]
        turnaj_id = str(uuid.uuid4())[:8]
        autor_id = session["uzivatel_id"]

        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO turnaje (id, nazev, sport, datum, pocet_tymu, popis, autor_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (turnaj_id, nazev, sport, datum, pocet_tymu, popis, autor_id))
            conn.commit()

            
            # Vygeneruj týmy podle počtu
        tymy = [f"Tým {i+1}" for i in range(int(pocet_tymu))]

        # Vygeneruj dvojice zápasů (round-robin)
        zapasy = []
        for i in range(len(tymy)):
            for j in range(i + 1, len(tymy)):
                zapasy.append((turnaj_id, tymy[i], tymy[j], None, None))  # None pro skóre

    # Ulož zápasy do DB
        with get_db_connection() as conn:
            c = conn.cursor()
            c.executemany("""
                INSERT INTO zapasy (turnaj_id, tym1, tym2, score1, score2)
                VALUES (%s, %s, %s, %s, %s)
            """, zapasy)
            conn.commit()

        return redirect(f"/turnaj/{turnaj_id}")

    return render_template("vytvor_turnaj.html")



@app.route("/turnaj/<turnaj_id>")   
def zobraz_turnaj(turnaj_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        # Načti zápasy
        c.execute("""
            SELECT id, tym1, tym2, score1, score2 
            FROM zapasy 
            WHERE turnaj_id = %s
        """, (turnaj_id,))
        zapasy = c.fetchall()

        # Načti informace o turnaji
        c.execute("""
            SELECT id, nazev, sport, datum, pocet_tymu, popis 
            FROM turnaje 
            WHERE id = %s
        """, (turnaj_id,))
        turnaj = c.fetchone()

        if not turnaj:
            return "Turnaj nenalezen", 404

        # Načti přihlášené týmy
        c.execute("""
            SELECT tm.id, tm.nazev
            FROM prihlasene_tymy pt
            JOIN tymy tm ON pt.tym_id = tm.id
            WHERE pt.turnaj_id = %s
        """, (turnaj_id,))
        prihlasene_tymy = c.fetchall()

        # Pokud je uživatel přihlášený, načti jeho týmy (kapitánské)
        moje_tymy = []
        if "uzivatel_id" in session:
            c.execute("""
                SELECT id, nazev
                FROM tymy
                WHERE kapitan_id = %s
            """, (session["uzivatel_id"],))
            moje_tymy = c.fetchall()

    return render_template(
        "detail_turnaje.html",
        turnaj=turnaj,
        nazev=turnaj["nazev"],
        sport=turnaj["sport"],
        datum=turnaj["datum"],
        pocet_tymu=turnaj["pocet_tymu"],
        popis=turnaj["popis"],
        zapasy=zapasy,
        prihlasene_tymy=prihlasene_tymy,
        moje_tymy=moje_tymy,
    )






@app.route("/zadat-vysledek", methods=["POST"])
def zadat_vysledek():
    zapas_id = request.form["zapas_id"]
    score1 = request.form["score1"]
    score2 = request.form["score2"]

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE zapasy
            SET score1 = %s, score2 = %s
            WHERE id = %s
            """, (score1, score2, zapas_id))
        conn.commit()

        # najdeme turnaj_id kvůli přesměrování zpět
        c.execute("SELECT turnaj_id FROM zapasy WHERE id = %s", (zapas_id,))
        turnaj_id = c.fetchone()[0]

    return redirect(f"/turnaj/{turnaj_id}")




@app.route("/registrace", methods=["GET", "POST"])
def registrace():
    if request.method == "POST":
        jmeno = request.form["jmeno"]
        email = request.form["email"]
        heslo = request.form["heslo"]
        
        # Hash hesla pro bezpečnost
        heslo_hash = generate_password_hash(heslo)
        
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO uzivatele (jmeno, email, heslo) VALUES (%s, %s, %s)", (jmeno, email, heslo_hash))
            conn.commit()

        return redirect("/prihlaseni")
    return render_template("registrace.html")






@app.route("/prihlaseni", methods=["GET", "POST"])
def prihlaseni():
    if request.method == "POST":
        email = request.form["email"]
        zadane_heslo = request.form["heslo"]

        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id, jmeno, heslo FROM uzivatele WHERE email = %s", (email,))
            user = c.fetchone()

        if user:
            ulozene_heslo = user[2]  # heslo je na 3. pozici v SELECTu
            if check_password_hash(ulozene_heslo, zadane_heslo):
                session["uzivatel_id"] = user[0]
                session["jmeno"] = user[1]
                return redirect("/")
            else:
                return "Špatný e-mail nebo heslo"
        else:
            return "Špatný e-mail nebo heslo"

    return render_template("prihlaseni.html")




@app.route("/odhlasit")
def odhlasit():
    session.clear()
    return redirect("/")





@app.route("/")
def index():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT t.id, t.nazev, t.sport, t.datum, u.jmeno
            FROM turnaje t
            JOIN uzivatele u ON t.autor_id = u.id
            ORDER BY t.datum ASC
        """)
        turnaje = c.fetchall()

    return render_template("index.html", turnaje=turnaje)



@app.route("/vytvorit-tym", methods=["GET", "POST"])
def vytvorit_tym():
    if "uzivatel_id" not in session:
        return redirect("/prihlaseni")

    if request.method == "POST":
        nazev = request.form["nazev"]
        popis = request.form["popis"]
        kapitan_id = session["uzivatel_id"]

        with get_db_connection() as conn:
            c = conn.cursor()
            # Vložení týmu + získání jeho ID
            c.execute(
                "INSERT INTO tymy (nazev, popis, kapitan_id) VALUES (%s, %s, %s) RETURNING id",
            (nazev, popis, kapitan_id)
            )
            tym_id = c.fetchone()[0]

            # Přidání kapitána jako člena
            c.execute(
                "INSERT INTO tym_clenove (tym_id, uzivatel_id) VALUES (%s, %s)",
            (tym_id, kapitan_id))

        conn.commit()

        return redirect(f"/tym/{tym_id}")

    return render_template("vytvor_tym.html")



@app.route("/tym/<int:tym_id>")
def detail_tymu(tym_id):
    with get_db_connection() as conn:
        c = conn.cursor()

        # Detail týmu
        c.execute("""
            SELECT t.id, t.nazev, t.popis, t.kapitan_id, u.jmeno AS kapitan
            FROM tymy t
            JOIN uzivatele u ON t.kapitan_id = u.id
            WHERE t.id = %s
        """, (tym_id,))
        tym = c.fetchone()

        # Členové týmu
        c.execute("""
            SELECT u.jmeno, u.email
            FROM tym_clenove tc
            JOIN uzivatele u ON tc.uzivatel_id = u.id
            WHERE tc.tym_id = %s
        """, (tym_id,))
        clenove = c.fetchall()

    return render_template("detail_tymu.html", tym=tym, clenove=clenove)


@app.route("/tym/<int:tym_id>/pridat-clena", methods=["POST"])
def pridat_clena(tym_id):
    if "uzivatel_id" not in session:
        return redirect("/prihlaseni")

    email = request.form["email"]

    with get_db_connection() as conn:
        c = conn.cursor()

        # Získání týmu
        c.execute("""
            SELECT t.id, t.nazev, t.popis, t.kapitan_id, u.jmeno AS kapitan
            FROM tymy t
            JOIN uzivatele u ON t.kapitan_id = u.id
            WHERE t.id = %s
        """, (tym_id,))
        tym = c.fetchone()

        if not tym or tym["kapitan_id"] != session["uzivatel_id"]:
            return "Nemáš oprávnění upravovat tento tým.", 403

        # Najdi uživatele
        c.execute("SELECT id FROM uzivatele WHERE email = %s", (email,))
        user = c.fetchone()
        if not user:
            # Načíst aktuální členy
            c.execute("""
                SELECT u.jmeno, u.email
                FROM tym_clenove tc
                JOIN uzivatele u ON tc.uzivatel_id = u.id
                WHERE tc.tym_id = %s
            """, (tym_id,))
            clenove = c.fetchall()
            return render_template("detail_tymu.html", tym=tym, clenove=clenove,
                                   error="Uživatel s tímto e-mailem neexistuje.")

        user_id = user["id"]

        # Kontrola, jestli už není člen
        c.execute("SELECT 1 FROM tym_clenove WHERE tym_id = %s AND uzivatel_id = %s", (tym_id, user_id))
        if c.fetchone():
            c.execute("""
                SELECT u.jmeno, u.email
                FROM tym_clenove tc
                JOIN uzivatele u ON tc.uzivatel_id = u.id
                WHERE tc.tym_id = %s
            """, (tym_id,))
            clenove = c.fetchall()
            return render_template("detail_tymu.html", tym=tym, clenove=clenove,
                                   error="Tento uživatel už je v týmu.")

        # Přidej člena
        c.execute("INSERT INTO tym_clenove (tym_id, uzivatel_id) VALUES (%s, %s)", (tym_id, user_id))
        conn.commit()

    return redirect(f"/tym/{tym_id}")


@app.route("/turnaj/<turnaj_id>/prihlasit-tym", methods=["POST"])
def prihlasit_tym(turnaj_id):
    if "uzivatel_id" not in session:
        return redirect("/prihlaseni")

    tym_id = request.form.get("tym_id")

    with get_db_connection() as conn:
        c = conn.cursor()

        # Získat max. počet týmů pro daný turnaj
        c.execute("SELECT pocet_tymu FROM turnaje WHERE id = %s", (turnaj_id,))
        vysledek = c.fetchone()
        if not vysledek:
            return "Turnaj neexistuje", 404
        max_pocet = vysledek[0]

        # Spočítat aktuálně přihlášené týmy
        c.execute("SELECT COUNT(*) FROM prihlasene_tymy WHERE turnaj_id = %s", (turnaj_id,))
        aktualni_pocet = c.fetchone()[0]

        if aktualni_pocet >= max_pocet:
            return "Turnaj je již plný.", 400

        # Zkontroluj, jestli je tým už přihlášen
        c.execute("SELECT 1 FROM tymy WHERE id = %s AND kapitan_id = %s", (tym_id, session["uzivatel_id"]))
        if not c.fetchone():
            return "Nemáš oprávnění přihlásit tento tým.", 403

        c.execute("SELECT 1 FROM prihlasene_tymy WHERE turnaj_id = %s AND tym_id = %s", (turnaj_id, tym_id))
        if c.fetchone():
            return "Tým už je přihlášen.", 400

        # Přihlásit tým
        c.execute("INSERT INTO prihlasene_tymy (turnaj_id, tym_id) VALUES (%s, %s)", (turnaj_id, tym_id))
        conn.commit()

    return redirect(f"/turnaj/{turnaj_id}")













@app.route("/init-db")
def init_db_route():
    init_db()
    return "Databáze byla vytvořena."



if __name__ == "__main__":
    init_db()
    app.run(debug=True)
    
    
    
    
    

