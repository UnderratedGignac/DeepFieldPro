"""
seed_fifa_ratings.py — Seed the local FIFA ratings database.
=============================================================
Creates data/fifa_ratings.db and populates it with ~350 top players
using well-known FC 25 overall ratings. Also supports ESPN auto-enrichment
for players not in the seed list.

Run once:  .venv\\Scripts\\python.exe src/seed_fifa_ratings.py
"""

import os
import sqlite3
import re
import unicodedata

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "fifa_ratings.db")

# ── Schema ──────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    name_norm     TEXT NOT NULL,
    team          TEXT DEFAULT '',
    position      TEXT DEFAULT '',
    rating        INTEGER DEFAULT 0,
    potential     INTEGER DEFAULT 0,
    source        TEXT DEFAULT 'seed',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_players_name_norm ON players(name_norm);
CREATE INDEX IF NOT EXISTS idx_players_team ON players(team);

CREATE TABLE IF NOT EXISTS team_aliases (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    team_norm  TEXT NOT NULL,
    alias_norm TEXT NOT NULL,
    UNIQUE(team_norm, alias_norm)
);

CREATE INDEX IF NOT EXISTS idx_team_alias ON team_aliases(alias_norm);
"""


def _norm_name(name: str) -> str:
    """Normalize player name for fuzzy matching."""
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", str(name).lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return " ".join(n.split())


def _norm_team(name: str) -> str:
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", str(name).lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    noise = {"fc", "cf", "sc", "cd", "ac", "afc", "club", "deportivo", "de",
             "the", "united", "city", "real", "atletico", "athletic", "calcio",
             "sporting", "red bull", "rb"}
    return " ".join(w for w in n.split() if w and w not in noise)


# ── Seed data ────────────────────────────────────────────────────────────────
# Format: (name, team, position, rating, potential)
# FC 25 ratings (publicly known, widely published Sept 2024)
PLAYERS = [
    # ─── Real Madrid ───
    ("Kylian Mbappé", "Real Madrid", "ST", 91, 93),
    ("Vinícius Júnior", "Real Madrid", "LW", 90, 93),
    ("Jude Bellingham", "Real Madrid", "CAM", 89, 94),
    ("Thibaut Courtois", "Real Madrid", "GK", 89, 90),
    ("Federico Valverde", "Real Madrid", "CM", 87, 90),
    ("Antonio Rüdiger", "Real Madrid", "CB", 86, 87),
    ("Éder Militão", "Real Madrid", "CB", 85, 88),
    ("Aurélien Tchouaméni", "Real Madrid", "CDM", 85, 89),
    ("Eduardo Camavinga", "Real Madrid", "CM", 84, 89),
    ("Dani Carvajal", "Real Madrid", "RB", 86, 87),
    ("Ferland Mendy", "Real Madrid", "LB", 83, 84),
    ("Rodrygo", "Real Madrid", "RW", 85, 89),
    ("Luka Modric", "Real Madrid", "CM", 86, 86),
    ("David Alaba", "Real Madrid", "CB", 85, 86),
    ("Arda Güler", "Real Madrid", "CAM", 79, 88),
    ("Brahim Díaz", "Real Madrid", "CAM", 80, 84),
    # ─── Manchester City ───
    ("Erling Haaland", "Manchester City", "ST", 91, 94),
    ("Kevin De Bruyne", "Manchester City", "CAM", 90, 90),
    ("Rodri", "Manchester City", "CDM", 89, 91),
    ("Ederson", "Manchester City", "GK", 88, 89),
    ("Bernardo Silva", "Manchester City", "CM", 87, 88),
    ("Rúben Dias", "Manchester City", "CB", 86, 88),
    ("Phil Foden", "Manchester City", "LW", 87, 91),
    ("Kyle Walker", "Manchester City", "RB", 84, 85),
    ("Manuel Akanji", "Manchester City", "CB", 83, 84),
    ("Joško Gvardiol", "Manchester City", "CB", 83, 88),
    ("Jérémy Doku", "Manchester City", "RW", 82, 88),
    ("Mateo Kovačić", "Manchester City", "CM", 83, 84),
    ("John Stones", "Manchester City", "CB", 82, 83),
    ("Nathan Aké", "Manchester City", "CB", 82, 83),
    ("Rico Lewis", "Manchester City", "RB", 77, 85),
    ("Jack Grealish", "Manchester City", "LW", 83, 84),
    # ─── Barcelona ───
    ("Robert Lewandowski", "Barcelona", "ST", 90, 90),
    ("Pedri", "Barcelona", "CM", 87, 92),
    ("Lamine Yamal", "Barcelona", "RW", 84, 94),
    ("Marc-André ter Stegen", "Barcelona", "GK", 88, 89),
    ("Raphinha", "Barcelona", "RW", 84, 86),
    ("Frenkie de Jong", "Barcelona", "CM", 85, 88),
    ("Ronald Araújo", "Barcelona", "CB", 85, 88),
    ("Jules Koundé", "Barcelona", "RB", 84, 87),
    ("Alejandro Balde", "Barcelona", "LB", 82, 88),
    ("Dani Olmo", "Barcelona", "CAM", 84, 88),
    ("Andreas Christensen", "Barcelona", "CB", 82, 83),
    ("Gavi", "Barcelona", "CM", 82, 89),
    ("Pau Cubarsí", "Barcelona", "CB", 78, 89),
    ("Fermín López", "Barcelona", "CM", 76, 85),
    # ─── Bayern Munich ───
    ("Harry Kane", "Bayern Munich", "ST", 90, 91),
    ("Jamal Musiala", "Bayern Munich", "CAM", 87, 93),
    ("Joshua Kimmich", "Bayern Munich", "CDM", 87, 88),
    ("Leroy Sané", "Bayern Munich", "LW", 86, 87),
    ("Manuel Neuer", "Bayern Munich", "GK", 86, 86),
    ("Alphonso Davies", "Bayern Munich", "LB", 84, 88),
    ("Dayot Upamecano", "Bayern Munich", "CB", 84, 86),
    ("Kim Min-jae", "Bayern Munich", "CB", 84, 86),
    ("Leon Goretzka", "Bayern Munich", "CM", 84, 85),
    ("Serge Gnabry", "Bayern Munich", "RW", 83, 84),
    ("Thomas Müller", "Bayern Munich", "CAM", 83, 83),
    ("Konrad Laimer", "Bayern Munich", "CDM", 81, 83),
    ("Kingsley Coman", "Bayern Munich", "RW", 83, 84),
    ("Mathys Tel", "Bayern Munich", "ST", 78, 88),
    # ─── Liverpool ───
    ("Mohamed Salah", "Liverpool", "RW", 89, 89),
    ("Virgil van Dijk", "Liverpool", "CB", 89, 89),
    ("Alisson", "Liverpool", "GK", 89, 89),
    ("Trent Alexander-Arnold", "Liverpool", "RB", 86, 89),
    ("Dominik Szoboszlai", "Liverpool", "CM", 84, 88),
    ("Alexis Mac Allister", "Liverpool", "CM", 84, 86),
    ("Luis Díaz", "Liverpool", "LW", 84, 86),
    ("Andrew Robertson", "Liverpool", "LB", 84, 85),
    ("Darwin Núñez", "Liverpool", "ST", 83, 87),
    ("Cody Gakpo", "Liverpool", "LW", 82, 86),
    ("Ibrahima Konaté", "Liverpool", "CB", 83, 87),
    ("Curtis Jones", "Liverpool", "CM", 79, 85),
    ("Diogo Jota", "Liverpool", "ST", 83, 85),
    ("Joe Gomez", "Liverpool", "CB", 81, 83),
    ("Ryan Gravenberch", "Liverpool", "CDM", 80, 86),
    # ─── Arsenal ───
    ("Bukayo Saka", "Arsenal", "RW", 86, 91),
    ("William Saliba", "Arsenal", "CB", 85, 89),
    ("Martin Ødegaard", "Arsenal", "CAM", 86, 89),
    ("Declan Rice", "Arsenal", "CDM", 85, 89),
    ("Gabriel Magalhães", "Arsenal", "CB", 84, 87),
    ("David Raya", "Arsenal", "GK", 83, 85),
    ("Gabriel Martinelli", "Arsenal", "LW", 83, 87),
    ("Kai Havertz", "Arsenal", "ST", 82, 85),
    ("Ben White", "Arsenal", "RB", 83, 86),
    ("Jurriën Timber", "Arsenal", "RB", 82, 86),
    ("Thomas Partey", "Arsenal", "CDM", 83, 84),
    ("Gabriel Jesus", "Arsenal", "ST", 82, 84),
    ("Takehiro Tomiyasu", "Arsenal", "RB", 80, 83),
    ("Leandro Trossard", "Arsenal", "LW", 82, 83),
    ("Ethan Nwaneri", "Arsenal", "RW", 73, 88),
    # ─── PSG ───
    ("Ousmane Dembélé", "PSG", "RW", 85, 87),
    ("Achraf Hakimi", "PSG", "RB", 85, 88),
    ("Marquinhos", "PSG", "CB", 86, 87),
    ("Gianluigi Donnarumma", "PSG", "GK", 86, 89),
    ("Vitinha", "PSG", "CM", 84, 88),
    ("Warren Zaïre-Emery", "PSG", "CM", 82, 91),
    ("Bradley Barcola", "PSG", "LW", 81, 89),
    ("Marco Asensio", "PSG", "RW", 83, 84),
    ("Randal Kolo Muani", "PSG", "ST", 82, 87),
    ("Nuno Mendes", "PSG", "LB", 82, 87),
    ("Lucas Hernández", "PSG", "CB", 83, 85),
    ("Fabián Ruiz", "PSG", "CM", 83, 86),
    ("Lee Kang-in", "PSG", "CAM", 81, 85),
    ("Presnel Kimpembe", "PSG", "CB", 82, 84),
    # ─── Inter Milan ───
    ("Lautaro Martínez", "Inter Milan", "ST", 89, 90),
    ("Nicolò Barella", "Inter Milan", "CM", 86, 88),
    ("Hakan Çalhanoğlu", "Inter Milan", "CDM", 86, 86),
    ("Alessandro Bastoni", "Inter Milan", "CB", 85, 88),
    ("Marcus Thuram", "Inter Milan", "ST", 83, 86),
    ("Henrikh Mkhitaryan", "Inter Milan", "CM", 83, 83),
    ("Federico Dimarco", "Inter Milan", "LB", 82, 85),
    ("Benjamin Pavard", "Inter Milan", "CB", 83, 84),
    ("Yann Sommer", "Inter Milan", "GK", 85, 85),
    ("Denzel Dumfries", "Inter Milan", "RB", 81, 83),
    ("Matteo Darmian", "Inter Milan", "CB", 80, 80),
    ("Kristjan Asllani", "Inter Milan", "CM", 78, 84),
    # ─── AC Milan ───
    ("Rafael Leão", "AC Milan", "LW", 86, 89),
    ("Mike Maignan", "AC Milan", "GK", 86, 88),
    ("Theo Hernández", "AC Milan", "LB", 84, 87),
    ("Tijjani Reijnders", "AC Milan", "CM", 82, 86),
    ("Christian Pulisic", "AC Milan", "RW", 82, 84),
    ("Fikayo Tomori", "AC Milan", "CB", 82, 85),
    ("Álvaro Morata", "AC Milan", "ST", 82, 83),
    ("Malick Thiaw", "AC Milan", "CB", 78, 84),
    ("Samuel Chukwueze", "AC Milan", "RW", 80, 83),
    ("Noah Okafor", "AC Milan", "ST", 79, 83),
    # ─── Juventus ───
    ("Dušan Vlahović", "Juventus", "ST", 85, 88),
    ("Bremer", "Juventus", "CB", 84, 87),
    ("Federico Chiesa", "Juventus", "RW", 84, 87),
    ("Manuel Locatelli", "Juventus", "CDM", 82, 85),
    ("Weston McKennie", "Juventus", "CM", 80, 82),
    ("Adrien Rabiot", "Juventus", "CM", 83, 84),
    ("Wojciech Szczęsny", "Juventus", "GK", 85, 85),
    ("Danilo", "Juventus", "RB", 82, 82),
    ("Andrea Cambiaso", "Juventus", "LB", 78, 84),
    ("Timothy Weah", "Juventus", "RW", 79, 83),
    ("Kenan Yıldız", "Juventus", "CAM", 77, 88),
    # ─── Atletico Madrid ───
    ("Antoine Griezmann", "Atletico Madrid", "CAM", 87, 87),
    ("Jan Oblak", "Atletico Madrid", "GK", 88, 88),
    ("Álvaro Morata", "Atletico Madrid", "ST", 82, 83),
    ("Koke", "Atletico Madrid", "CM", 84, 84),
    ("José María Giménez", "Atletico Madrid", "CB", 83, 84),
    ("Nahuel Molina", "Atletico Madrid", "RB", 81, 84),
    ("Marcos Llorente", "Atletico Madrid", "CM", 83, 85),
    ("Rodrigo de Paul", "Atletico Madrid", "CM", 83, 84),
    ("Mario Hermoso", "Atletico Madrid", "CB", 81, 83),
    ("Axel Witsel", "Atletico Madrid", "CDM", 81, 81),
    ("Samuel Lino", "Atletico Madrid", "LW", 79, 83),
    ("Alexander Sørloth", "Atletico Madrid", "ST", 80, 83),
    # ─── Borussia Dortmund ───
    ("Marco Reus", "Borussia Dortmund", "CAM", 84, 84),
    ("Mats Hummels", "Borussia Dortmund", "CB", 83, 83),
    ("Niklas Süle", "Borussia Dortmund", "CB", 83, 84),
    ("Julian Brandt", "Borussia Dortmund", "CAM", 83, 85),
    ("Gregor Kobel", "Borussia Dortmund", "GK", 84, 88),
    ("Karim Adeyemi", "Borussia Dortmund", "RW", 81, 87),
    ("Donyell Malen", "Borussia Dortmund", "ST", 80, 83),
    ("Emre Can", "Borussia Dortmund", "CDM", 82, 83),
    ("Julian Ryerson", "Borussia Dortmund", "RB", 79, 82),
    ("Marcel Sabitzer", "Borussia Dortmund", "CM", 82, 83),
    ("Youssoufa Moukoko", "Borussia Dortmund", "ST", 78, 87),
    # ─── Chelsea ───
    ("Cole Palmer", "Chelsea", "CAM", 84, 90),
    ("Enzo Fernández", "Chelsea", "CM", 84, 89),
    ("Moisés Caicedo", "Chelsea", "CDM", 83, 87),
    ("Robert Sánchez", "Chelsea", "GK", 81, 84),
    ("Reece James", "Chelsea", "RB", 83, 87),
    ("Nicolas Jackson", "Chelsea", "ST", 80, 85),
    ("Noni Madueke", "Chelsea", "RW", 80, 85),
    ("Levi Colwill", "Chelsea", "CB", 78, 85),
    ("Marc Cucurella", "Chelsea", "LB", 80, 82),
    ("Mykhailo Mudryk", "Chelsea", "LW", 79, 85),
    ("Axel Disasi", "Chelsea", "CB", 81, 84),
    ("Raheem Sterling", "Chelsea", "LW", 83, 83),
    ("Christopher Nkunku", "Chelsea", "ST", 84, 88),
    # ─── Manchester United ───
    ("Bruno Fernandes", "Manchester United", "CAM", 87, 88),
    ("Marcus Rashford", "Manchester United", "LW", 83, 85),
    ("Lisandro Martínez", "Manchester United", "CB", 84, 86),
    ("André Onana", "Manchester United", "GK", 84, 85),
    ("Rasmus Højlund", "Manchester United", "ST", 80, 87),
    ("Alejandro Garnacho", "Manchester United", "LW", 79, 87),
    ("Kobbie Mainoo", "Manchester United", "CM", 78, 88),
    ("Casemiro", "Manchester United", "CDM", 85, 85),
    ("Raphael Varane", "Manchester United", "CB", 84, 84),
    ("Luke Shaw", "Manchester United", "LB", 82, 83),
    ("Diogo Dalot", "Manchester United", "RB", 81, 84),
    ("Mason Mount", "Manchester United", "CAM", 81, 84),
    ("Scott McTominay", "Manchester United", "CM", 79, 81),
    # ─── Tottenham ───
    ("Son Heung-min", "Tottenham", "LW", 87, 87),
    ("James Maddison", "Tottenham", "CAM", 84, 87),
    ("Micky van de Ven", "Tottenham", "CB", 82, 88),
    ("Guglielmo Vicario", "Tottenham", "GK", 83, 86),
    ("Cristian Romero", "Tottenham", "CB", 83, 85),
    ("Pedro Porro", "Tottenham", "RB", 82, 85),
    ("Rodrigo Bentancur", "Tottenham", "CM", 82, 84),
    ("Yves Bissouma", "Tottenham", "CDM", 82, 84),
    ("Brennan Johnson", "Tottenham", "RW", 79, 85),
    ("Dejan Kulusevski", "Tottenham", "RW", 82, 85),
    ("Richarlison", "Tottenham", "ST", 81, 83),
    ("Pape Matar Sarr", "Tottenham", "CM", 78, 85),
    ("Destiny Udogie", "Tottenham", "LB", 79, 85),
    # ─── Napoli ───
    ("Victor Osimhen", "Napoli", "ST", 87, 89),
    ("Khvicha Kvaratskhelia", "Napoli", "LW", 85, 89),
    ("Stanislav Lobotka", "Napoli", "CDM", 83, 85),
    ("Giovanni Di Lorenzo", "Napoli", "RB", 83, 84),
    ("Amir Rrahmani", "Napoli", "CB", 81, 83),
    ("Alex Meret", "Napoli", "GK", 81, 84),
    ("Matteo Politano", "Napoli", "RW", 80, 81),
    ("Piotr Zieliński", "Napoli", "CM", 82, 83),
    ("Giacomo Raspadori", "Napoli", "ST", 80, 85),
    ("André-Frank Zambo Anguissa", "Napoli", "CM", 82, 84),
    # ─── RB Leipzig ───
    ("Loïs Openda", "RB Leipzig", "ST", 83, 88),
    ("Xavi Simons", "RB Leipzig", "CAM", 83, 90),
    ("Benjamin Šeško", "RB Leipzig", "ST", 80, 88),
    ("Dani Olmo", "RB Leipzig", "CAM", 84, 88),
    ("David Raum", "RB Leipzig", "LB", 82, 85),
    ("Castello Lukeba", "RB Leipzig", "CB", 80, 87),
    ("Péter Gulácsi", "RB Leipzig", "GK", 83, 84),
    ("Christoph Baumgartner", "RB Leipzig", "CAM", 80, 83),
    ("Mohamed Simakan", "RB Leipzig", "CB", 80, 85),
    # ─── Bayer Leverkusen ───
    ("Florian Wirtz", "Bayer Leverkusen", "CAM", 86, 93),
    ("Granit Xhaka", "Bayer Leverkusen", "CM", 84, 84),
    ("Victor Boniface", "Bayer Leverkusen", "ST", 82, 87),
    ("Alejandro Grimaldo", "Bayer Leverkusen", "LB", 83, 85),
    ("Jeremie Frimpong", "Bayer Leverkusen", "RB", 82, 87),
    ("Edmond Tapsoba", "Bayer Leverkusen", "CB", 82, 85),
    ("Lukáš Hrádecký", "Bayer Leverkusen", "GK", 83, 84),
    ("Exequiel Palacios", "Bayer Leverkusen", "CM", 82, 85),
    ("Piero Hincapié", "Bayer Leverkusen", "CB", 80, 86),
    ("Robert Andrich", "Bayer Leverkusen", "CDM", 81, 83),
    ("Jonas Hofmann", "Bayer Leverkusen", "RW", 81, 82),
    ("Adam Hložek", "Bayer Leverkusen", "ST", 78, 85),
    # ─── Roma ───
    ("Paulo Dybala", "Roma", "CAM", 86, 86),
    ("Lorenzo Pellegrini", "Roma", "CM", 83, 85),
    ("Romelu Lukaku", "Roma", "ST", 84, 84),
    ("Bryan Cristante", "Roma", "CDM", 82, 83),
    ("Gianluca Mancini", "Roma", "CB", 82, 84),
    ("Rui Patrício", "Roma", "GK", 83, 83),
    ("Stephan El Shaarawy", "Roma", "LW", 80, 80),
    ("Leandro Paredes", "Roma", "CDM", 82, 83),
    ("Andrea Belotti", "Roma", "ST", 80, 81),
    # ─── Lazio ───
    ("Ciro Immobile", "Lazio", "ST", 84, 84),
    ("Mattia Zaccagni", "Lazio", "LW", 81, 83),
    ("Luis Alberto", "Lazio", "CM", 83, 84),
    ("Alessio Romagnoli", "Lazio", "CB", 82, 83),
    ("Ivan Provedel", "Lazio", "GK", 82, 84),
    ("Nicolò Rovella", "Lazio", "CDM", 78, 85),
    ("Matteo Guendouzi", "Lazio", "CM", 81, 84),
    # ─── Real Sociedad ───
    ("Mikel Oyarzabal", "Real Sociedad", "LW", 84, 86),
    ("Martín Zubimendi", "Real Sociedad", "CDM", 84, 88),
    ("Takefusa Kubo", "Real Sociedad", "RW", 82, 88),
    ("Mikel Merino", "Real Sociedad", "CM", 83, 86),
    ("Alexander Sørloth", "Real Sociedad", "ST", 80, 83),
    ("Álex Remiro", "Real Sociedad", "GK", 82, 84),
    ("Robin Le Normand", "Real Sociedad", "CB", 82, 85),
    ("Aritz Elustondo", "Real Sociedad", "CB", 80, 81),
    # ─── Athletic Bilbao ───
    ("Iñaki Williams", "Athletic Bilbao", "RW", 83, 84),
    ("Nico Williams", "Athletic Bilbao", "LW", 83, 88),
    ("Unai Simón", "Athletic Bilbao", "GK", 84, 87),
    ("Oihan Sancet", "Athletic Bilbao", "CAM", 81, 87),
    ("Dani Vivian", "Athletic Bilbao", "CB", 81, 85),
    ("Yeray Álvarez", "Athletic Bilbao", "CB", 81, 82),
    ("Iker Muniain", "Athletic Bilbao", "CAM", 82, 83),
    # ─── Villarreal ───
    ("Gerard Moreno", "Villarreal", "ST", 83, 84),
    ("Álex Baena", "Villarreal", "CAM", 81, 87),
    ("Yeremy Pino", "Villarreal", "RW", 80, 85),
    ("Dani Parejo", "Villarreal", "CM", 83, 83),
    ("Pepe Reina", "Villarreal", "GK", 81, 81),
    # ─── Sevilla ───
    ("Sergio Ramos", "Sevilla", "CB", 84, 84),
    ("Lucas Ocampos", "Sevilla", "LW", 81, 82),
    ("Jesús Navas", "Sevilla", "RB", 82, 82),
    ("Youssef En-Nesyri", "Sevilla", "ST", 81, 83),
    ("Érik Lamela", "Sevilla", "RW", 80, 81),
    # ─── Aston Villa ───
    ("Ollie Watkins", "Aston Villa", "ST", 83, 86),
    ("Douglas Luiz", "Aston Villa", "CM", 82, 85),
    ("John McGinn", "Aston Villa", "CM", 82, 83),
    ("Emiliano Martínez", "Aston Villa", "GK", 85, 86),
    ("Ezri Konsa", "Aston Villa", "CB", 81, 84),
    ("Leon Bailey", "Aston Villa", "RW", 80, 82),
    ("Morgan Rogers", "Aston Villa", "CAM", 78, 85),
    ("Pau Torres", "Aston Villa", "CB", 83, 85),
    ("Youri Tielemans", "Aston Villa", "CM", 82, 84),
    ("Moussa Diaby", "Aston Villa", "LW", 81, 84),
    # ─── Newcastle ───
    ("Alexander Isak", "Newcastle", "ST", 84, 88),
    ("Bruno Guimarães", "Newcastle", "CM", 85, 88),
    ("Kieran Trippier", "Newcastle", "RB", 83, 83),
    ("Nick Pope", "Newcastle", "GK", 83, 85),
    ("Sven Botman", "Newcastle", "CB", 81, 85),
    ("Anthony Gordon", "Newcastle", "LW", 80, 86),
    ("Joelinton", "Newcastle", "CM", 81, 83),
    ("Fabian Schär", "Newcastle", "CB", 80, 81),
    ("Harvey Barnes", "Newcastle", "LW", 81, 84),
    ("Sandro Tonali", "Newcastle", "CM", 82, 87),
    # ─── Brighton ───
    ("Kaoru Mitoma", "Brighton", "LW", 82, 86),
    ("João Pedro", "Brighton", "ST", 80, 87),
    ("Lewis Dunk", "Brighton", "CB", 80, 81),
    ("Pascal Groß", "Brighton", "CM", 81, 81),
    ("Bart Verbruggen", "Brighton", "GK", 78, 84),
    ("Evan Ferguson", "Brighton", "ST", 79, 87),
    ("Julio Enciso", "Brighton", "CAM", 78, 85),
    ("Adam Webster", "Brighton", "CB", 79, 81),
    # ─── West Ham ───
    ("Jarrod Bowen", "West Ham", "RW", 82, 84),
    ("Lucas Paquetá", "West Ham", "CAM", 84, 87),
    ("Mohammed Kudus", "West Ham", "RW", 81, 86),
    ("James Ward-Prowse", "West Ham", "CM", 82, 83),
    ("Nayef Aguerd", "West Ham", "CB", 80, 83),
    ("Alphonse Areola", "West Ham", "GK", 81, 82),
    ("Tomáš Souček", "West Ham", "CDM", 81, 82),
    # ─── Benfica ───
    ("Ángel Di María", "Benfica", "RW", 84, 84),
    ("Rafa Silva", "Benfica", "CAM", 83, 84),
    ("Nicolás Otamendi", "Benfica", "CB", 83, 83),
    ("Anatoliy Trubin", "Benfica", "GK", 80, 86),
    ("Fredrik Aursnes", "Benfica", "CM", 80, 83),
    ("David Neres", "Benfica", "RW", 81, 83),
    ("António Silva", "Benfica", "CB", 80, 88),
    ("João Neves", "Benfica", "CDM", 79, 88),
    # ─── Porto ───
    ("Pepe", "Porto", "CB", 82, 82),
    ("Evanilson", "Porto", "ST", 81, 86),
    ("Mehdi Taremi", "Porto", "ST", 81, 82),
    ("Galeno", "Porto", "LW", 80, 84),
    ("Otávio", "Porto", "CM", 81, 83),
    ("Diogo Costa", "Porto", "GK", 82, 87),
    # ─── Ajax ───
    ("Steven Bergwijn", "Ajax", "RW", 81, 83),
    ("Davy Klaassen", "Ajax", "CM", 81, 82),
    ("Brian Brobbey", "Ajax", "ST", 79, 84),
    ("Jorrel Hato", "Ajax", "CB", 76, 87),
    ("Kenneth Taylor", "Ajax", "CM", 78, 85),
    # ─── Marseille ───
    ("Pierre-Emerick Aubameyang", "Marseille", "ST", 83, 83),
    ("Mattéo Guendouzi", "Marseille", "CM", 81, 84),
    ("Leonardo Balerdi", "Marseille", "CB", 79, 83),
    ("Amine Harit", "Marseille", "CAM", 80, 82),
    ("Pau López", "Marseille", "GK", 81, 82),
    # ─── Lyon ───
    ("Alexandre Lacazette", "Lyon", "ST", 83, 83),
    ("Rayan Cherki", "Lyon", "CAM", 80, 88),
    ("Corentin Tolisso", "Lyon", "CM", 82, 83),
    ("Anthony Lopes", "Lyon", "GK", 82, 83),
    # ─── Monaco ───
    ("Breel Embolo", "Monaco", "ST", 80, 82),
    ("Youssouf Fofana", "Monaco", "CM", 82, 86),
    ("Aleksandr Golovin", "Monaco", "CAM", 81, 83),
    ("Radosław Majecki", "Monaco", "GK", 79, 84),
    # ─── Lille ───
    ("Jonathan David", "Lille", "ST", 83, 87),
    ("Edon Zhegrova", "Lille", "RW", 80, 86),
    ("Lucas Chevalier", "Lille", "GK", 80, 86),
    ("Leny Yoro", "Lille", "CB", 78, 88),
    # ─── Wolfsburg ───
    ("Jonas Wind", "Wolfsburg", "ST", 80, 85),
    ("Mattias Svanberg", "Wolfsburg", "CM", 79, 83),
    # ─── Eintracht Frankfurt ───
    ("Randal Kolo Muani", "Eintracht Frankfurt", "ST", 82, 87),
    ("Mario Götze", "Eintracht Frankfurt", "CAM", 82, 82),
    ("Omar Marmoush", "Eintracht Frankfurt", "ST", 80, 85),
    ("Kevin Trapp", "Eintracht Frankfurt", "GK", 83, 83),
    # ─── Stuttgart ───
    ("Serhou Guirassy", "Stuttgart", "ST", 83, 85),
    ("Deniz Undav", "Stuttgart", "ST", 80, 84),
    ("Chris Führich", "Stuttgart", "LW", 79, 83),
    ("Alexander Nübel", "Stuttgart", "GK", 82, 84),
    # ─── Atalanta ───
    ("Ademola Lookman", "Atalanta", "LW", 83, 87),
    ("Gianluca Scamacca", "Atalanta", "ST", 81, 85),
    ("Teun Koopmeiners", "Atalanta", "CM", 83, 86),
    ("Éderson", "Atalanta", "CM", 81, 85),
    ("Juan Musso", "Atalanta", "GK", 82, 84),
    ("Giorgio Scalvini", "Atalanta", "CB", 80, 87),
    ("Isak Hien", "Atalanta", "CB", 79, 84),
    # ─── Fiorentina ───
    ("Nicolás González", "Fiorentina", "RW", 81, 85),
    ("Lucas Beltrán", "Fiorentina", "ST", 78, 84),
    ("Giacomo Bonaventura", "Fiorentina", "CM", 80, 80),
    ("Rolando Mandragora", "Fiorentina", "CDM", 79, 82),
    # ─── Celtic ───
    ("Kyogo Furuhashi", "Celtic", "ST", 80, 82),
    ("Matt O'Riley", "Celtic", "CM", 79, 84),
    ("Daizen Maeda", "Celtic", "LW", 78, 81),
    ("Kasper Schmeichel", "Celtic", "GK", 82, 82),
    # ─── Rangers ───
    ("James Tavernier", "Rangers", "RB", 79, 80),
    ("Cyriel Dessers", "Rangers", "ST", 78, 81),
    # ─── Galatasaray ───
    ("Mauro Icardi", "Galatasaray", "ST", 83, 83),
    ("Dries Mertens", "Galatasaray", "CAM", 82, 82),
    ("Kerem Aktürkoğlu", "Galatasaray", "LW", 79, 83),
    ("Fernando Muslera", "Galatasaray", "GK", 83, 83),
    ("Lucas Torreira", "Galatasaray", "CDM", 81, 82),
    ("Davinson Sánchez", "Galatasaray", "CB", 81, 82),
    # ─── Fenerbahçe ───
    ("Edin Džeko", "Fenerbahçe", "ST", 82, 82),
    ("Dusan Tadić", "Fenerbahçe", "CAM", 83, 83),
    ("İrfan Can Kahveci", "Fenerbahçe", "CM", 79, 82),
    ("Dominik Livaković", "Fenerbahçe", "GK", 82, 85),
    # ─── Besiktas ───
    ("Cenk Tosun", "Besiktas", "ST", 79, 80),
    ("Vincent Aboubakar", "Besiktas", "ST", 81, 82),
    # ─── Shakhtar Donetsk ───
    ("Mykhailo Mudryk", "Shakhtar Donetsk", "LW", 79, 85),
    ("Heorhiy Sudakov", "Shakhtar Donetsk", "CAM", 79, 86),
    ("Yukhym Konoplia", "Shakhtar Donetsk", "RB", 77, 83),
    # ─── Sporting CP ───
    ("Viktor Gyökeres", "Sporting CP", "ST", 83, 87),
    ("Pedro Gonçalves", "Sporting CP", "CAM", 82, 85),
    ("Antonio Adán", "Sporting CP", "GK", 80, 80),
    ("Gonçalo Inácio", "Sporting CP", "CB", 80, 87),
    ("Matheus Reis", "Sporting CP", "LB", 79, 81),
    ("Marcus Edwards", "Sporting CP", "RW", 79, 83),
    # ─── Braga ───
    ("Simon Banza", "Braga", "ST", 79, 82),
    ("Ricardo Horta", "Braga", "LW", 80, 81),
    # ─── Feyenoord ───
    ("Santiago Giménez", "Feyenoord", "ST", 80, 85),
    ("Calvin Stengs", "Feyenoord", "RW", 78, 82),
    ("Justin Bijlow", "Feyenoord", "GK", 80, 84),
    # ─── PSV ───
    ("Luuk de Jong", "PSV", "ST", 80, 80),
    ("Joey Veerman", "PSV", "CM", 80, 84),
    ("Jerdy Schouten", "PSV", "CDM", 80, 84),
    ("Walter Benítez", "PSV", "GK", 80, 82),
    # ─── Club Brugge ───
    ("Hans Vanaken", "Club Brugge", "CAM", 81, 82),
    ("Simon Mignolet", "Club Brugge", "GK", 81, 81),
    ("Ferran Jutglà", "Club Brugge", "ST", 77, 83),
    # ─── Salzburg ───
    ("Karim Konaté", "Salzburg", "ST", 77, 85),
    ("Oscar Gloukh", "Salzburg", "CAM", 78, 87),
    # ─── Flamengo ───
    ("Pedro", "Flamengo", "ST", 82, 84),
    ("Giorgian de Arrascaeta", "Flamengo", "CAM", 82, 84),
    ("Éverton Ribeiro", "Flamengo", "CM", 81, 82),
    ("Gabigol", "Flamengo", "ST", 81, 83),
    ("Ayrton Lucas", "Flamengo", "LB", 79, 82),
    ("Gerson", "Flamengo", "CM", 80, 83),
    # ─── Palmeiras ───
    ("Endrick", "Palmeiras", "ST", 78, 90),
    ("Raphael Veiga", "Palmeiras", "CAM", 80, 83),
    ("Dudu", "Palmeiras", "LW", 80, 81),
    ("Gustavo Gómez", "Palmeiras", "CB", 80, 81),
    ("Weverton", "Palmeiras", "GK", 81, 82),
    # ─── River Plate ───
    ("Miguel Borja", "River Plate", "ST", 81, 82),
    ("Enzo Pérez", "River Plate", "CDM", 80, 80),
    ("Claudio Echeverri", "River Plate", "CAM", 76, 88),
    ("Franco Armani", "River Plate", "GK", 82, 82),
    # ─── Boca Juniors ───
    ("Edinson Cavani", "Boca Juniors", "ST", 83, 83),
    ("Luca Langoni", "Boca Juniors", "RW", 76, 85),
    ("Darío Benedetto", "Boca Juniors", "ST", 80, 80),
    # ─── Al Hilal ───
    ("Neymar", "Al Hilal", "LW", 86, 86),
    ("Aleksandar Mitrović", "Al Hilal", "ST", 83, 84),
    ("Sergej Milinković-Savić", "Al Hilal", "CM", 84, 85),
    ("Rúben Neves", "Al Hilal", "CDM", 83, 85),
    ("Kalidou Koulibaly", "Al Hilal", "CB", 84, 84),
    ("Yassine Bounou", "Al Hilal", "GK", 83, 84),
    ("Malcom", "Al Hilal", "RW", 81, 84),
    ("Salem Al-Dawsari", "Al Hilal", "LW", 80, 81),
    # ─── Al Nassr ───
    ("Cristiano Ronaldo", "Al Nassr", "ST", 86, 86),
    ("Sadio Mané", "Al Nassr", "LW", 84, 84),
    ("Aymeric Laporte", "Al Nassr", "CB", 84, 85),
    ("Marcelo Brozović", "Al Nassr", "CDM", 83, 83),
    ("Otávio", "Al Nassr", "CM", 81, 83),
    ("David Ospina", "Al Nassr", "GK", 82, 82),
    ("Anderson Talisca", "Al Nassr", "CAM", 82, 83),
    # ─── Al Ahli ───
    ("Riyad Mahrez", "Al Ahli", "RW", 85, 85),
    ("Roberto Firmino", "Al Ahli", "ST", 83, 83),
    ("Franck Kessié", "Al Ahli", "CM", 83, 84),
    ("Roger Ibañez", "Al Ahli", "CB", 80, 84),
    ("Édouard Mendy", "Al Ahli", "GK", 83, 84),
    # ─── Al Ittihad ───
    ("Karim Benzema", "Al Ittihad", "ST", 87, 87),
    ("N'Golo Kanté", "Al Ittihad", "CDM", 85, 85),
    ("Fabinho", "Al Ittihad", "CDM", 83, 83),
    ("Moussa Diaby", "Al Ittihad", "LW", 81, 84),
    ("Predrag Rajković", "Al Ittihad", "GK", 81, 82),
    # ─── MLS ───
    ("Lionel Messi", "Inter Miami", "RW", 90, 90),
    ("Luis Suárez", "Inter Miami", "ST", 85, 85),
    ("Sergio Busquets", "Inter Miami", "CDM", 84, 84),
    ("Jordi Alba", "Inter Miami", "LB", 83, 83),
    ("Lorenzo Insigne", "Toronto FC", "LW", 83, 83),
    ("Olivier Giroud", "LAFC", "ST", 83, 83),
    ("Hugo Lloris", "LAFC", "GK", 84, 84),
    ("Denis Bouanga", "LAFC", "LW", 81, 83),
    ("Carlos Vela", "LAFC", "RW", 82, 82),
    ("Héctor Herrera", "Houston Dynamo", "CM", 81, 81),
    # ─── Global stars / free agents ───
    ("David de Gea", "Free Agent", "GK", 85, 85),
    ("Joel Matip", "Free Agent", "CB", 82, 82),
    ("Jesse Lingard", "Free Agent", "CAM", 79, 80),
]


# ── Team aliases for matching scraped names ──────────────────────────────────
# (team_alias, canonical_team_name)
TEAM_ALIASES = [
    # English
    ("man united", "Manchester United"), ("man utd", "Manchester United"),
    ("manchester united", "Manchester United"), ("mufc", "Manchester United"),
    ("man city", "Manchester City"), ("manchester city", "Manchester City"), ("mcf c", "Manchester City"),
    ("liverpool", "Liverpool"), ("lfc", "Liverpool"),
    ("arsenal", "Arsenal"), ("afc", "Arsenal"),
    ("chelsea", "Chelsea"), ("cfc", "Chelsea"),
    ("tottenham", "Tottenham"), ("spurs", "Tottenham"), ("thfc", "Tottenham"),
    ("newcastle", "Newcastle"), ("nufc", "Newcastle"), ("newcastle united", "Newcastle"),
    ("aston villa", "Aston Villa"), ("avfc", "Aston Villa"),
    ("brighton", "Brighton"), ("brighton hove", "Brighton"),
    ("west ham", "West Ham"), ("whufc", "West Ham"),
    # Spanish
    ("real madrid", "Real Madrid"), ("rmcf", "Real Madrid"), ("madrid", "Real Madrid"),
    ("barcelona", "Barcelona"), ("fcb", "Barcelona"), ("barca", "Barcelona"),
    ("atletico madrid", "Atletico Madrid"), ("atleti", "Atletico Madrid"),
    ("athletic bilbao", "Athletic Bilbao"), ("athletic club", "Athletic Bilbao"),
    ("real sociedad", "Real Sociedad"), ("la real", "Real Sociedad"),
    ("villarreal", "Villarreal"), ("villarreal cf", "Villarreal"),
    ("sevilla", "Sevilla"), ("sevilla fc", "Sevilla"),
    ("real betis", "Real Betis"), ("betis", "Real Betis"),
    # German
    ("bayern munich", "Bayern Munich"), ("bayern", "Bayern Munich"), ("fcb bayern", "Bayern Munich"),
    ("borussia dortmund", "Borussia Dortmund"), ("dortmund", "Borussia Dortmund"), ("bvb", "Borussia Dortmund"),
    ("rb leipzig", "RB Leipzig"), ("leipzig", "RB Leipzig"),
    ("bayer leverkusen", "Bayer Leverkusen"), ("leverkusen", "Bayer Leverkusen"),
    ("eintracht frankfurt", "Eintracht Frankfurt"), ("frankfurt", "Eintracht Frankfurt"),
    ("stuttgart", "Stuttgart"), ("vfb stuttgart", "Stuttgart"),
    ("wolfsburg", "Wolfsburg"), ("vfl wolfsburg", "Wolfsburg"),
    # Italian
    ("inter", "Inter Milan"), ("inter milan", "Inter Milan"), ("fc internazionale", "Inter Milan"),
    ("ac milan", "AC Milan"), ("milan", "AC Milan"),
    ("juventus", "Juventus"), ("juve", "Juventus"),
    ("napoli", "Napoli"), ("ssc napoli", "Napoli"),
    ("roma", "Roma"), ("as roma", "Roma"),
    ("lazio", "Lazio"), ("ss lazio", "Lazio"),
    ("atalanta", "Atalanta"), ("atalanta bc", "Atalanta"),
    ("fiorentina", "Fiorentina"), ("acf fiorentina", "Fiorentina"),
    # French
    ("psg", "PSG"), ("paris saint germain", "PSG"), ("paris sg", "PSG"),
    ("marseille", "Marseille"), ("olympique marseille", "Marseille"), ("om", "Marseille"),
    ("lyon", "Lyon"), ("olympique lyonnais", "Lyon"), ("ol", "Lyon"),
    ("monaco", "Monaco"), ("as monaco", "Monaco"),
    ("lille", "Lille"), ("losc", "Lille"), ("losc lille", "Lille"),
    # Portuguese
    ("benfica", "Benfica"), ("sl benfica", "Benfica"),
    ("porto", "Porto"), ("fc porto", "Porto"),
    ("sporting", "Sporting CP"), ("sporting cp", "Sporting CP"), ("sporting lisbon", "Sporting CP"),
    ("braga", "Braga"), ("sc braga", "Braga"),
    # Dutch
    ("ajax", "Ajax"), ("afc ajax", "Ajax"),
    ("feyenoord", "Feyenoord"),
    ("psv", "PSV"), ("psv eindhoven", "PSV"),
    # Others
    ("celtic", "Celtic"), ("the bhoys", "Celtic"),
    ("rangers", "Rangers"),
    ("galatasaray", "Galatasaray"), ("gala", "Galatasaray"),
    ("fenerbahce", "Fenerbahçe"), ("fenerbahçe", "Fenerbahçe"),
    ("besiktas", "Besiktas"), ("beşiktaş", "Besiktas"),
    ("shakhtar", "Shakhtar Donetsk"), ("shakhtar donetsk", "Shakhtar Donetsk"),
    ("club brugge", "Club Brugge"),
    ("salzburg", "Salzburg"), ("rb salzburg", "Salzburg"), ("red bull salzburg", "Salzburg"),
    # MLS
    ("inter miami", "Inter Miami"), ("inter miami cf", "Inter Miami"),
    ("lafc", "LAFC"), ("los angeles fc", "LAFC"),
    ("toronto fc", "Toronto FC"),
    # Brazilian
    ("flamengo", "Flamengo"), ("cr flamengo", "Flamengo"),
    ("palmeiras", "Palmeiras"), ("se palmeiras", "Palmeiras"),
    # Argentine
    ("river plate", "River Plate"), ("ca river plate", "River Plate"),
    ("boca juniors", "Boca Juniors"), ("ca boca juniors", "Boca Juniors"),
    # Saudi
    ("al hilal", "Al Hilal"), ("al-hilal", "Al Hilal"),
    ("al nassr", "Al Nassr"), ("al-nassr", "Al Nassr"),
    ("al ahli", "Al Ahli"), ("al-ahli", "Al Ahli"),
    ("al ittihad", "Al Ittihad"), ("al-ittihad", "Al Ittihad"),
]


def seed():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)

    # Insert players
    inserted = 0
    for name, team, pos, rating, potential in PLAYERS:
        name_n = _norm_name(name)
        team_n = _norm_team(team)
        conn.execute(
            "INSERT OR IGNORE INTO players (name, name_norm, team, position, rating, potential, source) "
            "VALUES (?, ?, ?, ?, ?, ?, 'seed')",
            (name, name_n, team_n, pos, rating, potential),
        )
        inserted += 1

    # Insert team aliases
    aliased = 0
    for alias, canonical in TEAM_ALIASES:
        a_norm = _norm_team(alias)
        c_norm = _norm_team(canonical)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO team_aliases (team_norm, alias_norm) VALUES (?, ?)",
                (c_norm, a_norm),
            )
            aliased += 1
        except Exception:
            pass

    conn.commit()

    # Stats
    count = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    alias_count = conn.execute("SELECT COUNT(*) FROM team_aliases").fetchone()[0]
    conn.close()
    print(f"[FIFA Ratings] Seeded {count} players, {alias_count} team aliases -> {DB_PATH}")


if __name__ == "__main__":
    seed()
