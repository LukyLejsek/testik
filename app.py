from flask import Flask, render_template, request, redirect, session, url_for
import os
import psycopg2
from urllib.parse import urlparse
import uuid

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
    return psycopg2.connect(**conn_params)

# Inicializace databáze

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS uzivatele (
                id SERIAL PRIMARY KEY,
                jmeno TEXT,
                email TEXT UNIQUE,
                heslo TEXT
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
                autor_id INTEGER REFERENCES uzivatele(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS zapasy (
                id SERIAL PRIMARY KEY,
                turnaj_id TEXT REFERENCES turnaje(id),
                tym1 TEXT,
                tym2 TEXT,
                score1 INTEGER,
                score2 INTEGER
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS tymy (
                id SERIAL PRIMARY KEY,
                nazev TEXT NOT NULL,
                popis TEXT,
                kapitan_id INTEGER REFERENCES uzivatele(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS tym_clenove (
                id SERIAL PRIMARY KEY,
                tym_id INTEGER REFERENCES tymy(id),
                uzivatel_id INTEGER REFERENCES uzivatele(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS prihlasene_tymy (
                id SERIAL PRIMARY KEY,
                turnaj_id TEXT REFERENCES turnaje(id),
                tym_id INTEGER REFERENCES tymy(id)
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
                VALUES (?, ?, ?, ?, ?)
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
            WHERE turnaj_id = ?
        """, (turnaj_id,))
        zapasy = c.fetchall()

        # Načti informace o turnaji
        c.execute("""
            SELECT id, nazev, sport, datum, pocet_tymu, popis 
            FROM turnaje 
            WHERE id = ?
        """, (turnaj_id,))
        turnaj = c.fetchone()

        if not turnaj:
            return "Turnaj nenalezen", 404

        # Načti přihlášené týmy
        c.execute("""
            SELECT tm.id, tm.nazev
            FROM prihlasene_tymy pt
            JOIN tymy tm ON pt.tym_id = tm.id
            WHERE pt.turnaj_id = ?
        """, (turnaj_id,))
        prihlasene_tymy = c.fetchall()

        # Pokud je uživatel přihlášený, načti jeho týmy (kapitánské)
        moje_tymy = []
        if "uzivatel_id" in session:
            c.execute("""
                SELECT id, nazev
                FROM tymy
                WHERE kapitan_id = ?
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
            SET score1 = ?, score2 = ?
            WHERE id = ?
            """, (score1, score2, zapas_id))
        conn.commit()

        # najdeme turnaj_id kvůli přesměrování zpět
        c.execute("SELECT turnaj_id FROM zapasy WHERE id = ?", (zapas_id,))
        turnaj_id = c.fetchone()[0]

    return redirect(f"/turnaj/{turnaj_id}")




@app.route("/registrace", methods=["GET", "POST"])
def registrace():
    if request.method == "POST":
        jmeno = request.form["jmeno"]
        email = request.form["email"]
        heslo = request.form["heslo"]

        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO uzivatele (jmeno, email, heslo) VALUES (?, ?, ?)", (jmeno, email, heslo))
            conn.commit()

        return redirect("/prihlaseni")
    return render_template("registrace.html")






@app.route("/prihlaseni", methods=["GET", "POST"])
def prihlaseni():
    if request.method == "POST":
        email = request.form["email"]
        heslo = request.form["heslo"]

        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id, jmeno FROM uzivatele WHERE email = ? AND heslo = ?", (email, heslo))
            user = c.fetchone()

        if user:
            session["uzivatel_id"] = user[0]
            session["jmeno"] = user[1]
            return redirect("/")
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
            # vytvoření týmu
            c.execute("INSERT INTO tymy (nazev, popis, kapitan_id) VALUES (?, ?, ?)", (nazev, popis, kapitan_id))
            tym_id = c.lastrowid

            # přidání kapitána jako člena
            c.execute("INSERT INTO tym_clenove (tym_id, uzivatel_id) VALUES (?, ?)", (tym_id, kapitan_id))
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
            WHERE t.id = ?
        """, (tym_id,))
        tym = c.fetchone()

        # Členové týmu
        c.execute("""
            SELECT u.jmeno, u.email
            FROM tym_clenove tc
            JOIN uzivatele u ON tc.uzivatel_id = u.id
            WHERE tc.tym_id = ?
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
            WHERE t.id = ?
        """, (tym_id,))
        tym = c.fetchone()

        if not tym or tym["kapitan_id"] != session["uzivatel_id"]:
            return "Nemáš oprávnění upravovat tento tým.", 403

        # Najdi uživatele
        c.execute("SELECT id FROM uzivatele WHERE email = ?", (email,))
        user = c.fetchone()
        if not user:
            # Načíst aktuální členy
            c.execute("""
                SELECT u.jmeno, u.email
                FROM tym_clenove tc
                JOIN uzivatele u ON tc.uzivatel_id = u.id
                WHERE tc.tym_id = ?
            """, (tym_id,))
            clenove = c.fetchall()
            return render_template("detail_tymu.html", tym=tym, clenove=clenove,
                                   error="Uživatel s tímto e-mailem neexistuje.")

        user_id = user["id"]

        # Kontrola, jestli už není člen
        c.execute("SELECT 1 FROM tym_clenove WHERE tym_id = ? AND uzivatel_id = ?", (tym_id, user_id))
        if c.fetchone():
            c.execute("""
                SELECT u.jmeno, u.email
                FROM tym_clenove tc
                JOIN uzivatele u ON tc.uzivatel_id = u.id
                WHERE tc.tym_id = ?
            """, (tym_id,))
            clenove = c.fetchall()
            return render_template("detail_tymu.html", tym=tym, clenove=clenove,
                                   error="Tento uživatel už je v týmu.")

        # Přidej člena
        c.execute("INSERT INTO tym_clenove (tym_id, uzivatel_id) VALUES (?, ?)", (tym_id, user_id))
        conn.commit()

    return redirect(f"/tym/{tym_id}")


@app.route("/turnaj/<turnaj_id>/prihlasit-tym", methods=["POST"])
def prihlasit_tym(turnaj_id):
    if "uzivatel_id" not in session:
        return redirect("/prihlaseni")

    tym_id = request.form.get("tym_id")

    with get_db_connection() as conn:
        c = conn.cursor()
        # Zkontroluj, jestli je uživatel kapitán
        c.execute("SELECT * FROM tymy WHERE id = ? AND kapitan_id = ?", (tym_id, session["uzivatel_id"]))
        tym = c.fetchone()
        if not tym:
            return "Nemáš oprávnění přihlásit tento tým.", 403
            # Převod na integer pro psycopg2 (PostgreSQL používá %s místo ?)
            tym_id = int(tym_id)
        # Zkontroluj, jestli už tým není přihlášen
        c.execute("SELECT 1 FROM prihlasene_tymy WHERE turnaj_id = ? AND tym_id = ?", (turnaj_id, tym_id))
        if c.fetchone():
            return "Tým už je přihlášen.", 400

        # Zapiš přihlášení
        c.execute("INSERT INTO prihlasene_tymy (turnaj_id, tym_id) VALUES (?, ?)", (turnaj_id, tym_id))
        conn.commit()

    return redirect(f"/turnaj/{turnaj_id}")





if __name__ == "__main__":
    init_db()
    app.run(debug=True)
    
    
    
    
    

