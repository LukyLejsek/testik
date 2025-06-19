from flask import Flask, render_template, request, redirect, session, url_for
app = Flask(__name__)
app.secret_key = "hodne_tajny_klic"  # změň si na něco unikátního
import sqlite3
import uuid

# Vytvoř databázi, pokud neexistuje
def init_db():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS zapasy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            turnaj_id TEXT,
            tym1 TEXT,
            tym2 TEXT,
            score1 INTEGER,
            score2 INTEGER,
            FOREIGN KEY(turnaj_id) REFERENCES turnaje(id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS uzivatele (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jmeno TEXT,
            email TEXT UNIQUE,
            heslo TEXT
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS turnaje (
            id TEXT PRIMARY KEY,
            nazev TEXT NOT NULL,
            sport TEXT,
            datum TEXT,
            pocet_tymu INTEGER,
            popis TEXT,
            autor_id INTEGER,
            FOREIGN KEY(autor_id) REFERENCES uzivatele(id)
        )""")
        
        c.execute("""CREATE TABLE IF NOT EXISTS tymy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nazev TEXT NOT NULL,
            popis TEXT,
            kapitan_id INTEGER,
            FOREIGN KEY(kapitan_id) REFERENCES uzivatele(id)
        )""")

        # Tabulka členů týmu
        c.execute("""CREATE TABLE IF NOT EXISTS tym_clenove (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tym_id INTEGER,
            uzivatel_id INTEGER,
            FOREIGN KEY(tym_id) REFERENCES tymy(id),
            FOREIGN KEY(uzivatel_id) REFERENCES uzivatele(id)
        )""")
        
        c.execute("""
            SELECT t.id, t.nazev, t.sport, t.datum, u.jmeno
            FROM turnaje t
            LEFT JOIN uzivatele u ON t.autor_id = u.id
            ORDER BY t.datum ASC
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

        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO turnaje (id, nazev, sport, datum, pocet_tymu, popis, autor_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
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
        with sqlite3.connect("database.db") as conn:
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
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
            # Načti zápasy
        c.execute("SELECT id, tym1, tym2, score1, score2 FROM zapasy WHERE turnaj_id = ?", (turnaj_id,))
        zapasy = c.fetchall()

        # Načti informace o turnaji
        c.execute("SELECT nazev, sport, datum, pocet_tymu, popis FROM turnaje WHERE id = ?", (turnaj_id,))
        data = c.fetchone()

    if data:
        return render_template("detail_turnaje.html", id=turnaj_id, nazev=data[0], sport=data[1],
                               datum=data[2], pocet_tymu=data[3], popis=data[4], zapasy=zapasy)
    else:
        return "Turnaj nenalezen", 404





@app.route("/zadat-vysledek", methods=["POST"])
def zadat_vysledek():
    zapas_id = request.form["zapas_id"]
    score1 = request.form["score1"]
    score2 = request.form["score2"]

    with sqlite3.connect("database.db") as conn:
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

        with sqlite3.connect("database.db") as conn:
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

        with sqlite3.connect("database.db") as conn:
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
    with sqlite3.connect("database.db") as conn:
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

        with sqlite3.connect("database.db") as conn:
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
    with sqlite3.connect("database.db") as conn:
        conn.row_factory = sqlite3.Row
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

    with sqlite3.connect("database.db") as conn:
        conn.row_factory = sqlite3.Row
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







if __name__ == "__main__":
    init_db()
    app.run(debug=True)
    
    
    
    
    

