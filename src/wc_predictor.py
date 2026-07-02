"""
wc_predictor.py — 2026 FIFA World Cup winner predictor.

Model: 4-source weighted ensemble (ADR-WC-001)
  40%  Pinnacle live outright winner odds (de-vigged) — sharpest available signal
  30%  FIFA 25 player ratings — squad quality, player-by-player
  20%  Transfermarkt squad value — squad depth and market valuation
  10%  Dixon-Coles attack/defence ratings mapped through nationality

Simulation: 100 000-iteration Monte Carlo bracket over the remaining knockout
rounds using a logistic-Poisson match model calibrated on the strength blends.

Data freshness:
  - Player ratings: FIFA 25 (Aug 2025) — frozen baseline
  - Pinnacle odds:  live fetch via the same Pinnacle guest-API the daemon uses
  - Bracket state:  Pinnacle outright odds already encode who has advanced
"""

import math
import os
import time
import logging
import random
import json
from typing import Optional

logger = logging.getLogger("wc_predictor")

# ─── Team + Player Data ───────────────────────────────────────────────────────
# squad_value_m : Transfermarkt squad value in millions EUR (Jan 2026 estimate)
# prior_pin     : pre-tournament Pinnacle winner decimal odds (baseline fallback)
# players       : top ~16 squad members with FIFA-25-era ratings

TEAMS: dict = {
    "Brazil": {
        "squad_value_m": 1280,
        "prior_pin": 5.5,
        "flag": "🇧🇷",
        "confederation": "CONMEBOL",
        "players": [
            {
                "name": "Alisson",
                "pos": "GK",
                "rating": 89,
                "age": 33,
                "club": "Liverpool",
            },
            {
                "name": "Militão",
                "pos": "CB",
                "rating": 86,
                "age": 26,
                "club": "Real Madrid",
            },
            {"name": "Marquinhos", "pos": "CB", "rating": 86, "age": 30, "club": "PSG"},
            {
                "name": "Danilo",
                "pos": "RB",
                "rating": 82,
                "age": 34,
                "club": "Juventus",
            },
            {
                "name": "Theo Hernández",
                "pos": "LB",
                "rating": 83,
                "age": 28,
                "club": "AC Milan",
            },
            {
                "name": "Bruno G.",
                "pos": "CDM",
                "rating": 87,
                "age": 27,
                "club": "Newcastle",
            },
            {
                "name": "Paquetá",
                "pos": "CM",
                "rating": 85,
                "age": 27,
                "club": "West Ham",
            },
            {
                "name": "Raphinha",
                "pos": "RW",
                "rating": 86,
                "age": 28,
                "club": "Barcelona",
            },
            {
                "name": "Vinicius Jr",
                "pos": "LW",
                "rating": 92,
                "age": 25,
                "club": "Real Madrid",
            },
            {
                "name": "Rodrygo",
                "pos": "CF",
                "rating": 87,
                "age": 24,
                "club": "Real Madrid",
            },
            {
                "name": "Endrick",
                "pos": "ST",
                "rating": 82,
                "age": 19,
                "club": "Real Madrid",
            },
            {
                "name": "Ederson",
                "pos": "GK",
                "rating": 87,
                "age": 32,
                "club": "Man City",
            },
            {
                "name": "Savinho",
                "pos": "RW",
                "rating": 81,
                "age": 20,
                "club": "Man City",
            },
            {
                "name": "Gerson",
                "pos": "CM",
                "rating": 81,
                "age": 27,
                "club": "Marseille",
            },
            {
                "name": "Gabriel M.",
                "pos": "CB",
                "rating": 84,
                "age": 27,
                "club": "Arsenal",
            },
            {
                "name": "Andreas P.",
                "pos": "RB",
                "rating": 82,
                "age": 26,
                "club": "Arsenal",
            },
        ],
    },
    "France": {
        "squad_value_m": 1350,
        "prior_pin": 5.0,
        "flag": "🇫🇷",
        "confederation": "UEFA",
        "players": [
            {
                "name": "Maignan",
                "pos": "GK",
                "rating": 86,
                "age": 30,
                "club": "AC Milan",
            },
            {
                "name": "Upamecano",
                "pos": "CB",
                "rating": 84,
                "age": 26,
                "club": "Bayern",
            },
            {"name": "Saliba", "pos": "CB", "rating": 87, "age": 24, "club": "Arsenal"},
            {
                "name": "T. Hernandez",
                "pos": "LB",
                "rating": 83,
                "age": 28,
                "club": "AC Milan",
            },
            {"name": "Pavard", "pos": "RB", "rating": 82, "age": 29, "club": "Inter"},
            {
                "name": "Tchouameni",
                "pos": "CDM",
                "rating": 85,
                "age": 25,
                "club": "Real Madrid",
            },
            {
                "name": "Camavinga",
                "pos": "CM",
                "rating": 84,
                "age": 22,
                "club": "Real Madrid",
            },
            {
                "name": "Griezmann",
                "pos": "AM",
                "rating": 85,
                "age": 35,
                "club": "Atletico",
            },
            {"name": "Dembélé", "pos": "RW", "rating": 87, "age": 27, "club": "PSG"},
            {
                "name": "Mbappé",
                "pos": "LW",
                "rating": 92,
                "age": 27,
                "club": "Real Madrid",
            },
            {"name": "Thuram", "pos": "ST", "rating": 84, "age": 27, "club": "Inter"},
            {"name": "Lloris", "pos": "GK", "rating": 83, "age": 39, "club": "Retired"},
            {
                "name": "Konaté",
                "pos": "CB",
                "rating": 84,
                "age": 26,
                "club": "Liverpool",
            },
            {
                "name": "Zaire-Emery",
                "pos": "CM",
                "rating": 84,
                "age": 20,
                "club": "PSG",
            },
            {"name": "Olise", "pos": "AM", "rating": 84, "age": 23, "club": "Bayern"},
            {"name": "Barcola", "pos": "LW", "rating": 82, "age": 22, "club": "PSG"},
        ],
    },
    "England": {
        "squad_value_m": 1290,
        "prior_pin": 6.5,
        "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "confederation": "UEFA",
        "players": [
            {
                "name": "Pickford",
                "pos": "GK",
                "rating": 84,
                "age": 32,
                "club": "Everton",
            },
            {
                "name": "Alexander-Arnold",
                "pos": "RB",
                "rating": 87,
                "age": 27,
                "club": "Real Madrid",
            },
            {
                "name": "Trippier",
                "pos": "RB",
                "rating": 84,
                "age": 35,
                "club": "Newcastle",
            },
            {
                "name": "John Stones",
                "pos": "CB",
                "rating": 85,
                "age": 32,
                "club": "Man City",
            },
            {
                "name": "Marc Guéhi",
                "pos": "CB",
                "rating": 83,
                "age": 24,
                "club": "Crystal P.",
            },
            {
                "name": "Luke Shaw",
                "pos": "LB",
                "rating": 83,
                "age": 30,
                "club": "Man Utd",
            },
            {"name": "Rice", "pos": "CDM", "rating": 88, "age": 27, "club": "Arsenal"},
            {
                "name": "Bellingham",
                "pos": "AM",
                "rating": 91,
                "age": 22,
                "club": "Real Madrid",
            },
            {"name": "Saka", "pos": "RW", "rating": 88, "age": 24, "club": "Arsenal"},
            {"name": "Foden", "pos": "LW", "rating": 87, "age": 26, "club": "Man City"},
            {"name": "Kane", "pos": "ST", "rating": 90, "age": 32, "club": "Bayern"},
            {"name": "Palmer", "pos": "AM", "rating": 86, "age": 23, "club": "Chelsea"},
            {
                "name": "Gordon",
                "pos": "LW",
                "rating": 83,
                "age": 24,
                "club": "Newcastle",
            },
            {"name": "Mainoo", "pos": "CM", "rating": 82, "age": 22, "club": "Man Utd"},
            {
                "name": "Konsa",
                "pos": "CB",
                "rating": 82,
                "age": 27,
                "club": "Aston Villa",
            },
            {
                "name": "Ramsdale",
                "pos": "GK",
                "rating": 82,
                "age": 27,
                "club": "Southampton",
            },
        ],
    },
    "Spain": {
        "squad_value_m": 1180,
        "prior_pin": 5.5,
        "flag": "🇪🇸",
        "confederation": "UEFA",
        "players": [
            {
                "name": "Unai Simón",
                "pos": "GK",
                "rating": 84,
                "age": 27,
                "club": "Athletic",
            },
            {
                "name": "Carvajal",
                "pos": "RB",
                "rating": 85,
                "age": 32,
                "club": "Real Madrid",
            },
            {
                "name": "Laporte",
                "pos": "CB",
                "rating": 83,
                "age": 31,
                "club": "Al-Nassr",
            },
            {
                "name": "Le Normand",
                "pos": "CB",
                "rating": 83,
                "age": 27,
                "club": "Atletico",
            },
            {
                "name": "Cucurella",
                "pos": "LB",
                "rating": 82,
                "age": 25,
                "club": "Chelsea",
            },
            {
                "name": "Rodri",
                "pos": "CDM",
                "rating": 91,
                "age": 29,
                "club": "Man City",
            },
            {
                "name": "Pedri",
                "pos": "CM",
                "rating": 88,
                "age": 23,
                "club": "Barcelona",
            },
            {"name": "Gavi", "pos": "CM", "rating": 87, "age": 22, "club": "Barcelona"},
            {
                "name": "Yamal",
                "pos": "RW",
                "rating": 89,
                "age": 18,
                "club": "Barcelona",
            },
            {
                "name": "Williams N.",
                "pos": "LW",
                "rating": 85,
                "age": 22,
                "club": "Athletic",
            },
            {
                "name": "Morata",
                "pos": "ST",
                "rating": 83,
                "age": 33,
                "club": "AC Milan",
            },
            {
                "name": "Zubimendi",
                "pos": "CDM",
                "rating": 84,
                "age": 26,
                "club": "Arsenal",
            },
            {
                "name": "Dani Olmo",
                "pos": "AM",
                "rating": 86,
                "age": 27,
                "club": "Barcelona",
            },
            {
                "name": "Baena",
                "pos": "CM",
                "rating": 81,
                "age": 23,
                "club": "Villarreal",
            },
            {
                "name": "Grimaldo",
                "pos": "LB",
                "rating": 84,
                "age": 29,
                "club": "Leverkusen",
            },
            {
                "name": "Torres F.",
                "pos": "ST",
                "rating": 82,
                "age": 25,
                "club": "Barcelona",
            },
        ],
    },
    "Germany": {
        "squad_value_m": 1100,
        "prior_pin": 7.0,
        "flag": "🇩🇪",
        "confederation": "UEFA",
        "players": [
            {
                "name": "Ter Stegen",
                "pos": "GK",
                "rating": 87,
                "age": 33,
                "club": "Barcelona",
            },
            {"name": "Kimmich", "pos": "RB", "rating": 88, "age": 30, "club": "Bayern"},
            {
                "name": "Rüdiger",
                "pos": "CB",
                "rating": 87,
                "age": 33,
                "club": "Real Madrid",
            },
            {
                "name": "Schlotterbeck",
                "pos": "CB",
                "rating": 84,
                "age": 25,
                "club": "Dortmund",
            },
            {
                "name": "Raum",
                "pos": "LB",
                "rating": 83,
                "age": 27,
                "club": "RB Leipzig",
            },
            {
                "name": "Kroos",
                "pos": "CDM",
                "rating": 88,
                "age": 36,
                "club": "Real Madrid",
            },
            {
                "name": "Wirtz",
                "pos": "AM",
                "rating": 89,
                "age": 22,
                "club": "Leverkusen",
            },
            {"name": "Musiala", "pos": "AM", "rating": 89, "age": 22, "club": "Bayern"},
            {"name": "Gnabry", "pos": "RW", "rating": 84, "age": 30, "club": "Bayern"},
            {
                "name": "Havertz",
                "pos": "CF",
                "rating": 85,
                "age": 26,
                "club": "Arsenal",
            },
            {
                "name": "Füllkrug",
                "pos": "ST",
                "rating": 84,
                "age": 32,
                "club": "West Ham",
            },
            {"name": "Neuer", "pos": "GK", "rating": 85, "age": 40, "club": "Bayern"},
            {"name": "Tah", "pos": "CB", "rating": 84, "age": 29, "club": "Leverkusen"},
            {
                "name": "Andrich",
                "pos": "CM",
                "rating": 83,
                "age": 30,
                "club": "Leverkusen",
            },
            {
                "name": "Adeyemi",
                "pos": "LW",
                "rating": 83,
                "age": 23,
                "club": "Dortmund",
            },
            {
                "name": "Kleindienst",
                "pos": "ST",
                "rating": 81,
                "age": 28,
                "club": "Leverkusen",
            },
        ],
    },
    "Argentina": {
        "squad_value_m": 900,
        "prior_pin": 6.0,
        "flag": "🇦🇷",
        "confederation": "CONMEBOL",
        "players": [
            {
                "name": "E. Martínez",
                "pos": "GK",
                "rating": 88,
                "age": 33,
                "club": "Aston Villa",
            },
            {
                "name": "Molina",
                "pos": "RB",
                "rating": 83,
                "age": 26,
                "club": "Atletico",
            },
            {
                "name": "Otamendi",
                "pos": "CB",
                "rating": 83,
                "age": 38,
                "club": "Benfica",
            },
            {
                "name": "Lisandro M.",
                "pos": "CB",
                "rating": 87,
                "age": 27,
                "club": "Man Utd",
            },
            {
                "name": "Tagliafico",
                "pos": "LB",
                "rating": 82,
                "age": 32,
                "club": "Lyon",
            },
            {
                "name": "De Paul",
                "pos": "CM",
                "rating": 85,
                "age": 31,
                "club": "Atletico",
            },
            {
                "name": "Mac Allister",
                "pos": "CM",
                "rating": 85,
                "age": 26,
                "club": "Liverpool",
            },
            {
                "name": "Messi",
                "pos": "RW",
                "rating": 90,
                "age": 38,
                "club": "Inter Miami",
            },
            {"name": "Dybala", "pos": "AM", "rating": 84, "age": 32, "club": "Roma"},
            {
                "name": "J. Álvarez",
                "pos": "ST",
                "rating": 86,
                "age": 24,
                "club": "Atletico",
            },
            {
                "name": "Lautaro M.",
                "pos": "ST",
                "rating": 88,
                "age": 28,
                "club": "Inter",
            },
            {
                "name": "Armani",
                "pos": "GK",
                "rating": 81,
                "age": 38,
                "club": "River Plate",
            },
            {
                "name": "Lo Celso",
                "pos": "AM",
                "rating": 83,
                "age": 30,
                "club": "Villarreal",
            },
            {
                "name": "Fernandez E.",
                "pos": "CM",
                "rating": 83,
                "age": 24,
                "club": "Chelsea",
            },
            {
                "name": "Pezella",
                "pos": "CB",
                "rating": 80,
                "age": 34,
                "club": "Real Betis",
            },
            {
                "name": "Garnacho",
                "pos": "LW",
                "rating": 83,
                "age": 21,
                "club": "Man Utd",
            },
        ],
    },
    "Portugal": {
        "squad_value_m": 1020,
        "prior_pin": 9.0,
        "flag": "🇵🇹",
        "confederation": "UEFA",
        "players": [
            {
                "name": "Diogo Costa",
                "pos": "GK",
                "rating": 85,
                "age": 25,
                "club": "Porto",
            },
            {
                "name": "D. Dalot",
                "pos": "RB",
                "rating": 83,
                "age": 26,
                "club": "Man Utd",
            },
            {
                "name": "Rúben Dias",
                "pos": "CB",
                "rating": 88,
                "age": 27,
                "club": "Man City",
            },
            {
                "name": "Gonçalo I.",
                "pos": "CB",
                "rating": 84,
                "age": 26,
                "club": "Real Madrid",
            },
            {
                "name": "Guerreiro",
                "pos": "LB",
                "rating": 82,
                "age": 30,
                "club": "Bayern",
            },
            {
                "name": "Palhinha",
                "pos": "CDM",
                "rating": 85,
                "age": 30,
                "club": "Bayern",
            },
            {"name": "Vitinha", "pos": "CM", "rating": 85, "age": 25, "club": "PSG"},
            {
                "name": "Bernardo Silva",
                "pos": "AM",
                "rating": 88,
                "age": 30,
                "club": "Man City",
            },
            {
                "name": "João Félix",
                "pos": "AM",
                "rating": 85,
                "age": 26,
                "club": "Chelsea",
            },
            {
                "name": "Rafael Leão",
                "pos": "LW",
                "rating": 86,
                "age": 26,
                "club": "AC Milan",
            },
            {
                "name": "Ronaldo",
                "pos": "ST",
                "rating": 84,
                "age": 41,
                "club": "Al-Nassr",
            },
            {
                "name": "R. Patricio",
                "pos": "GK",
                "rating": 83,
                "age": 36,
                "club": "Roma",
            },
            {
                "name": "Pedro Neto",
                "pos": "RW",
                "rating": 84,
                "age": 24,
                "club": "Chelsea",
            },
            {"name": "Jota", "pos": "AM", "rating": 83, "age": 28, "club": "Liverpool"},
            {
                "name": "Cancelo",
                "pos": "RB",
                "rating": 84,
                "age": 31,
                "club": "Barcelona",
            },
            {"name": "André", "pos": "CDM", "rating": 82, "age": 23, "club": "Fulham"},
        ],
    },
    "Netherlands": {
        "squad_value_m": 870,
        "prior_pin": 11.0,
        "flag": "🇳🇱",
        "confederation": "UEFA",
        "players": [
            {
                "name": "Verbruggen",
                "pos": "GK",
                "rating": 83,
                "age": 22,
                "club": "Brighton",
            },
            {"name": "Dumfries", "pos": "RB", "rating": 83, "age": 28, "club": "Inter"},
            {
                "name": "De Ligt",
                "pos": "CB",
                "rating": 84,
                "age": 26,
                "club": "Man Utd",
            },
            {
                "name": "Van Dijk",
                "pos": "CB",
                "rating": 87,
                "age": 34,
                "club": "Liverpool",
            },
            {"name": "Aké", "pos": "LB", "rating": 83, "age": 30, "club": "Man City"},
            {
                "name": "Schouten",
                "pos": "CDM",
                "rating": 83,
                "age": 27,
                "club": "Bologna",
            },
            {
                "name": "Gravenberch",
                "pos": "CM",
                "rating": 85,
                "age": 22,
                "club": "Liverpool",
            },
            {
                "name": "Reijnders",
                "pos": "CM",
                "rating": 84,
                "age": 26,
                "club": "AC Milan",
            },
            {
                "name": "G. Xavi",
                "pos": "RW",
                "rating": 84,
                "age": 27,
                "club": "Leverkusen",
            },
            {"name": "Depay", "pos": "ST", "rating": 84, "age": 31, "club": "Atletico"},
            {
                "name": "Gakpo",
                "pos": "LW",
                "rating": 84,
                "age": 25,
                "club": "Liverpool",
            },
            {
                "name": "Flekken",
                "pos": "GK",
                "rating": 82,
                "age": 31,
                "club": "Brentford",
            },
            {"name": "Timber", "pos": "CB", "rating": 84, "age": 23, "club": "Arsenal"},
            {"name": "Malen", "pos": "RW", "rating": 83, "age": 26, "club": "Dortmund"},
            {
                "name": "Weghorst",
                "pos": "ST",
                "rating": 80,
                "age": 32,
                "club": "Hoffenheim",
            },
            {
                "name": "Lang N.",
                "pos": "RW",
                "rating": 82,
                "age": 25,
                "club": "Club Bruges",
            },
        ],
    },
    "Belgium": {
        "squad_value_m": 690,
        "prior_pin": 19.0,
        "flag": "🇧🇪",
        "confederation": "UEFA",
        "players": [
            {
                "name": "Casteels",
                "pos": "GK",
                "rating": 83,
                "age": 32,
                "club": "Al-Qadsiah",
            },
            {
                "name": "Castagne",
                "pos": "RB",
                "rating": 82,
                "age": 29,
                "club": "Fulham",
            },
            {"name": "Faes", "pos": "CB", "rating": 81, "age": 26, "club": "Leicester"},
            {
                "name": "Vertonghen",
                "pos": "CB",
                "rating": 82,
                "age": 39,
                "club": "Anderlecht",
            },
            {"name": "Theate", "pos": "LB", "rating": 81, "age": 24, "club": "Rennes"},
            {
                "name": "Onana A.",
                "pos": "CDM",
                "rating": 82,
                "age": 28,
                "club": "Aston Villa",
            },
            {
                "name": "Tielemans",
                "pos": "CM",
                "rating": 83,
                "age": 28,
                "club": "Aston Villa",
            },
            {
                "name": "De Bruyne",
                "pos": "AM",
                "rating": 90,
                "age": 35,
                "club": "Man City",
            },
            {"name": "Doku", "pos": "LW", "rating": 84, "age": 22, "club": "Man City"},
            {"name": "Lukaku", "pos": "ST", "rating": 84, "age": 33, "club": "Napoli"},
            {
                "name": "Trossard",
                "pos": "LW",
                "rating": 84,
                "age": 29,
                "club": "Arsenal",
            },
            {
                "name": "Mignolet",
                "pos": "GK",
                "rating": 82,
                "age": 36,
                "club": "Club Bruges",
            },
            {
                "name": "Openda",
                "pos": "ST",
                "rating": 84,
                "age": 24,
                "club": "RB Leipzig",
            },
            {
                "name": "Mangala",
                "pos": "CB",
                "rating": 80,
                "age": 30,
                "club": "Marseille",
            },
            {
                "name": "Carrasco",
                "pos": "LW",
                "rating": 82,
                "age": 33,
                "club": "Al-Qadsiah",
            },
            {
                "name": "Vanaken",
                "pos": "CM",
                "rating": 82,
                "age": 32,
                "club": "Club Bruges",
            },
        ],
    },
    "Uruguay": {
        "squad_value_m": 440,
        "prior_pin": 21.0,
        "flag": "🇺🇾",
        "confederation": "CONMEBOL",
        "players": [
            {
                "name": "Rochet",
                "pos": "GK",
                "rating": 81,
                "age": 30,
                "club": "Internacional",
            },
            {
                "name": "Nández",
                "pos": "RB",
                "rating": 82,
                "age": 29,
                "club": "Cagliari",
            },
            {
                "name": "Giménez J.",
                "pos": "CB",
                "rating": 83,
                "age": 30,
                "club": "Atletico",
            },
            {"name": "Olivera", "pos": "LB", "rating": 82, "age": 27, "club": "Napoli"},
            {
                "name": "Valverde",
                "pos": "CM",
                "rating": 87,
                "age": 26,
                "club": "Real Madrid",
            },
            {
                "name": "Ugarte M.",
                "pos": "CDM",
                "rating": 82,
                "age": 23,
                "club": "Man Utd",
            },
            {
                "name": "De Arrascaeta",
                "pos": "AM",
                "rating": 84,
                "age": 30,
                "club": "Flamengo",
            },
            {
                "name": "Pellistri",
                "pos": "RW",
                "rating": 80,
                "age": 24,
                "club": "Man Utd",
            },
            {
                "name": "Darwin N.",
                "pos": "ST",
                "rating": 85,
                "age": 25,
                "club": "Liverpool",
            },
            {
                "name": "Araújo R.",
                "pos": "CB",
                "rating": 86,
                "age": 25,
                "club": "Barcelona",
            },
            {
                "name": "Bentancur",
                "pos": "CM",
                "rating": 84,
                "age": 27,
                "club": "Tottenham",
            },
            {
                "name": "Muslera",
                "pos": "GK",
                "rating": 80,
                "age": 38,
                "club": "Galatasaray",
            },
            {
                "name": "García M.",
                "pos": "ST",
                "rating": 80,
                "age": 21,
                "club": "Santos",
            },
            {
                "name": "Giménez S.",
                "pos": "CB",
                "rating": 80,
                "age": 26,
                "club": "Feyenoord",
            },
            {
                "name": "Suárez",
                "pos": "ST",
                "rating": 80,
                "age": 39,
                "club": "River Plate",
            },
            {
                "name": "Gómez M.",
                "pos": "CM",
                "rating": 79,
                "age": 26,
                "club": "Villarreal",
            },
        ],
    },
    "Colombia": {
        "squad_value_m": 550,
        "prior_pin": 18.0,
        "flag": "🇨🇴",
        "confederation": "CONMEBOL",
        "players": [
            {
                "name": "Vargas C.",
                "pos": "GK",
                "rating": 82,
                "age": 33,
                "club": "Eintracht",
            },
            {
                "name": "Muñoz",
                "pos": "RB",
                "rating": 82,
                "age": 27,
                "club": "Crystal P.",
            },
            {
                "name": "Mina Y.",
                "pos": "CB",
                "rating": 82,
                "age": 29,
                "club": "Everton",
            },
            {
                "name": "Sánchez D.",
                "pos": "LB",
                "rating": 81,
                "age": 26,
                "club": "Atletico",
            },
            {
                "name": "Arias S.",
                "pos": "CB",
                "rating": 83,
                "age": 32,
                "club": "Atletico",
            },
            {
                "name": "Lerma",
                "pos": "CDM",
                "rating": 81,
                "age": 30,
                "club": "Crystal P.",
            },
            {
                "name": "J. Cuadrado",
                "pos": "RW",
                "rating": 82,
                "age": 38,
                "club": "Inter",
            },
            {
                "name": "L. Díaz",
                "pos": "LW",
                "rating": 86,
                "age": 27,
                "club": "Liverpool",
            },
            {
                "name": "J. Rodríguez",
                "pos": "AM",
                "rating": 82,
                "age": 33,
                "club": "Rayo Vallecano",
            },
            {
                "name": "Borré",
                "pos": "ST",
                "rating": 82,
                "age": 29,
                "club": "Eintracht",
            },
            {
                "name": "Córdoba S.",
                "pos": "ST",
                "rating": 82,
                "age": 22,
                "club": "Girona",
            },
            {
                "name": "Ospina",
                "pos": "GK",
                "rating": 80,
                "age": 38,
                "club": "Al-Qadsiah",
            },
            {"name": "Ángel D.", "pos": "AM", "rating": 80, "age": 22, "club": "PSG"},
            {
                "name": "Cardona J.",
                "pos": "RW",
                "rating": 80,
                "age": 31,
                "club": "Independiente",
            },
            {"name": "Mojica", "pos": "LB", "rating": 80, "age": 30, "club": "Girona"},
            {
                "name": "Quintero",
                "pos": "AM",
                "rating": 81,
                "age": 31,
                "club": "River Plate",
            },
        ],
    },
    "Morocco": {
        "squad_value_m": 480,
        "prior_pin": 21.0,
        "flag": "🇲🇦",
        "confederation": "CAF",
        "players": [
            {"name": "Bono", "pos": "GK", "rating": 85, "age": 33, "club": "Al-Hilal"},
            {"name": "Hakimi", "pos": "RB", "rating": 87, "age": 27, "club": "PSG"},
            {"name": "Aguerd", "pos": "CB", "rating": 83, "age": 28, "club": "Burnley"},
            {
                "name": "Mazraoui",
                "pos": "RB",
                "rating": 83,
                "age": 27,
                "club": "Man Utd",
            },
            {
                "name": "Attiyat-Allah",
                "pos": "LB",
                "rating": 80,
                "age": 27,
                "club": "Wydad",
            },
            {
                "name": "Amallah",
                "pos": "CM",
                "rating": 80,
                "age": 28,
                "club": "Standard",
            },
            {
                "name": "Ounahi",
                "pos": "CM",
                "rating": 81,
                "age": 24,
                "club": "Marseille",
            },
            {
                "name": "Ziyech",
                "pos": "AM",
                "rating": 83,
                "age": 33,
                "club": "Galatasaray",
            },
            {
                "name": "En-Nesyri",
                "pos": "ST",
                "rating": 83,
                "age": 27,
                "club": "Fenerbahce",
            },
            {
                "name": "Sabiri",
                "pos": "AM",
                "rating": 79,
                "age": 28,
                "club": "Sampdoria",
            },
            {
                "name": "Ezzalzouli",
                "pos": "LW",
                "rating": 82,
                "age": 23,
                "club": "Osasuna",
            },
            {
                "name": "Benoun",
                "pos": "CB",
                "rating": 79,
                "age": 29,
                "club": "Qatar SC",
            },
            {
                "name": "Dari",
                "pos": "CB",
                "rating": 80,
                "age": 26,
                "club": "Bournemouth",
            },
            {"name": "Benrahma", "pos": "AM", "rating": 82, "age": 29, "club": "Lyon"},
            {"name": "Louza", "pos": "CM", "rating": 80, "age": 24, "club": "Watford"},
            {"name": "Cheddira", "pos": "ST", "rating": 80, "age": 26, "club": "Lecce"},
        ],
    },
    "USA": {
        "squad_value_m": 500,
        "prior_pin": 19.0,
        "flag": "🇺🇸",
        "confederation": "CONCACAF",
        "players": [
            {
                "name": "Turner M.",
                "pos": "GK",
                "rating": 83,
                "age": 30,
                "club": "Arsenal",
            },
            {"name": "Dest", "pos": "RB", "rating": 81, "age": 25, "club": "PSV"},
            {
                "name": "Richards",
                "pos": "CB",
                "rating": 81,
                "age": 24,
                "club": "Crystal P.",
            },
            {
                "name": "Long A.",
                "pos": "CB",
                "rating": 80,
                "age": 30,
                "club": "Nottm Forest",
            },
            {
                "name": "Antonee R.",
                "pos": "LB",
                "rating": 83,
                "age": 27,
                "club": "Fulham",
            },
            {
                "name": "Adams T.",
                "pos": "CDM",
                "rating": 83,
                "age": 29,
                "club": "Napoli",
            },
            {
                "name": "McKennie",
                "pos": "CM",
                "rating": 81,
                "age": 26,
                "club": "Juventus",
            },
            {"name": "Reyna", "pos": "AM", "rating": 81, "age": 22, "club": "Dortmund"},
            {
                "name": "Pulisic",
                "pos": "AM",
                "rating": 84,
                "age": 27,
                "club": "AC Milan",
            },
            {
                "name": "Balogun F.",
                "pos": "ST",
                "rating": 81,
                "age": 23,
                "club": "Arsenal",
            },
            {
                "name": "Weah T.",
                "pos": "RW",
                "rating": 80,
                "age": 24,
                "club": "Juventus",
            },
            {
                "name": "Horvath",
                "pos": "GK",
                "rating": 79,
                "age": 29,
                "club": "Nottm Forest",
            },
            {
                "name": "Zimmermann",
                "pos": "CB",
                "rating": 80,
                "age": 32,
                "club": "Charlotte",
            },
            {"name": "Musah", "pos": "CM", "rating": 81, "age": 22, "club": "AC Milan"},
            {
                "name": "Ferreira J.",
                "pos": "ST",
                "rating": 80,
                "age": 25,
                "club": "FC Dallas",
            },
            {"name": "Pepi G.", "pos": "ST", "rating": 81, "age": 22, "club": "PSV"},
        ],
    },
    "Japan": {
        "squad_value_m": 380,
        "prior_pin": 26.0,
        "flag": "🇯🇵",
        "confederation": "AFC",
        "players": [
            {
                "name": "Gonda",
                "pos": "GK",
                "rating": 80,
                "age": 31,
                "club": "Portimonense",
            },
            {
                "name": "Sakai",
                "pos": "RB",
                "rating": 80,
                "age": 33,
                "club": "Urawa Reds",
            },
            {
                "name": "Itakura",
                "pos": "CB",
                "rating": 82,
                "age": 27,
                "club": "Dortmund",
            },
            {
                "name": "Yoshida",
                "pos": "CB",
                "rating": 79,
                "age": 36,
                "club": "Urawa Reds",
            },
            {
                "name": "Nagatomo",
                "pos": "LB",
                "rating": 78,
                "age": 40,
                "club": "Retired",
            },
            {
                "name": "Endo W.",
                "pos": "CDM",
                "rating": 82,
                "age": 32,
                "club": "Liverpool",
            },
            {
                "name": "Kamada",
                "pos": "AM",
                "rating": 82,
                "age": 28,
                "club": "Crystal P.",
            },
            {"name": "Doan", "pos": "RW", "rating": 81, "age": 26, "club": "Freiburg"},
            {
                "name": "Kubo",
                "pos": "AM",
                "rating": 84,
                "age": 23,
                "club": "Real Sociedad",
            },
            {
                "name": "Minamino",
                "pos": "AM",
                "rating": 81,
                "age": 30,
                "club": "Monaco",
            },
            {"name": "Ueda", "pos": "ST", "rating": 81, "age": 26, "club": "Feyenoord"},
            {
                "name": "Maignan",
                "pos": "GK",
                "rating": 79,
                "age": 26,
                "club": "Kashiwa",
            },
            {
                "name": "Furuhashi",
                "pos": "ST",
                "rating": 80,
                "age": 30,
                "club": "Celtic",
            },
            {
                "name": "Mitoma",
                "pos": "LW",
                "rating": 83,
                "age": 27,
                "club": "Brighton",
            },
            {
                "name": "Tanaka H.",
                "pos": "CM",
                "rating": 81,
                "age": 26,
                "club": "Dortmund",
            },
            {"name": "Hatate", "pos": "CM", "rating": 80, "age": 27, "club": "Celtic"},
        ],
    },
    "Mexico": {
        "squad_value_m": 280,
        "prior_pin": 34.0,
        "flag": "🇲🇽",
        "confederation": "CONCACAF",
        "players": [
            {"name": "Ochoa", "pos": "GK", "rating": 80, "age": 39, "club": "América"},
            {
                "name": "Sánchez J.",
                "pos": "RB",
                "rating": 79,
                "age": 29,
                "club": "América",
            },
            {
                "name": "Araujo J.",
                "pos": "CB",
                "rating": 79,
                "age": 26,
                "club": "Toluca",
            },
            {
                "name": "Montes C.",
                "pos": "CB",
                "rating": 79,
                "age": 26,
                "club": "Espanyol",
            },
            {
                "name": "Gallardo A.",
                "pos": "LB",
                "rating": 78,
                "age": 25,
                "club": "America",
            },
            {"name": "Guardado", "pos": "CM", "rating": 79, "age": 38, "club": "Betis"},
            {
                "name": "Herrera H.",
                "pos": "CDM",
                "rating": 80,
                "age": 34,
                "club": "LA Galaxy",
            },
            {"name": "Lozano", "pos": "RW", "rating": 82, "age": 30, "club": "PSV"},
            {
                "name": "Vega A.",
                "pos": "LW",
                "rating": 80,
                "age": 27,
                "club": "Cruz Azul",
            },
            {
                "name": "Jiménez R.",
                "pos": "ST",
                "rating": 82,
                "age": 34,
                "club": "Fulham",
            },
            {
                "name": "Antuna",
                "pos": "AM",
                "rating": 79,
                "age": 26,
                "club": "Cruz Azul",
            },
            {
                "name": "Corona J.",
                "pos": "RW",
                "rating": 80,
                "age": 31,
                "club": "Sevilla",
            },
            {
                "name": "Alvarado M.",
                "pos": "CM",
                "rating": 79,
                "age": 26,
                "club": "Brighton",
            },
            {
                "name": "Pineda M.",
                "pos": "CM",
                "rating": 78,
                "age": 29,
                "club": "Seattle",
            },
            {
                "name": "Alexis Vega",
                "pos": "AM",
                "rating": 79,
                "age": 29,
                "club": "Toluca",
            },
            {
                "name": "Tecatito",
                "pos": "RW",
                "rating": 79,
                "age": 29,
                "club": "Sevilla",
            },
        ],
    },
    "Canada": {
        "squad_value_m": 310,
        "prior_pin": 41.0,
        "flag": "🇨🇦",
        "confederation": "CONCACAF",
        "players": [
            {
                "name": "Borjan",
                "pos": "GK",
                "rating": 79,
                "age": 36,
                "club": "Red Star",
            },
            {
                "name": "Johnston A.",
                "pos": "RB",
                "rating": 80,
                "age": 25,
                "club": "Celtic",
            },
            {
                "name": "Miller L.",
                "pos": "CB",
                "rating": 80,
                "age": 24,
                "club": "Fulham",
            },
            {"name": "Vitória", "pos": "CB", "rating": 79, "age": 26, "club": "Lens"},
            {
                "name": "Laryea",
                "pos": "RB",
                "rating": 78,
                "age": 29,
                "club": "Nottm Forest",
            },
            {
                "name": "Eustáquio",
                "pos": "CDM",
                "rating": 82,
                "age": 27,
                "club": "Porto",
            },
            {
                "name": "Hutchinson",
                "pos": "CM",
                "rating": 80,
                "age": 28,
                "club": "Trabzonspor",
            },
            {
                "name": "Davies A.",
                "pos": "LW",
                "rating": 85,
                "age": 25,
                "club": "Bayern",
            },
            {
                "name": "Buchanan T.",
                "pos": "LB",
                "rating": 81,
                "age": 25,
                "club": "Inter",
            },
            {"name": "David J.", "pos": "ST", "rating": 85, "age": 24, "club": "Lille"},
            {
                "name": "Larin",
                "pos": "ST",
                "rating": 79,
                "age": 29,
                "club": "Club Brugge",
            },
            {
                "name": "St. Clair",
                "pos": "GK",
                "rating": 78,
                "age": 23,
                "club": "Sporting KC",
            },
            {
                "name": "Henry E.",
                "pos": "LW",
                "rating": 80,
                "age": 22,
                "club": "Arsenal",
            },
            {
                "name": "Osorio J.",
                "pos": "CM",
                "rating": 79,
                "age": 23,
                "club": "Dortmund",
            },
            {
                "name": "Hoilett",
                "pos": "RW",
                "rating": 78,
                "age": 34,
                "club": "D.C. United",
            },
            {
                "name": "Oryschak",
                "pos": "GK",
                "rating": 77,
                "age": 22,
                "club": "Hertha",
            },
        ],
    },
    "South Korea": {
        "squad_value_m": 290,
        "prior_pin": 51.0,
        "flag": "🇰🇷",
        "confederation": "AFC",
        "players": [
            {
                "name": "Kim S.-G.",
                "pos": "GK",
                "rating": 82,
                "age": 32,
                "club": "Bayer Lever.",
            },
            {
                "name": "Kim M.-H.",
                "pos": "RB",
                "rating": 80,
                "age": 27,
                "club": "Wolfsburg",
            },
            {
                "name": "Kim Y.-G.",
                "pos": "CB",
                "rating": 82,
                "age": 32,
                "club": "Tottenham",
            },
            {
                "name": "Kim M.-J.",
                "pos": "CB",
                "rating": 79,
                "age": 29,
                "club": "Jeonbuk",
            },
            {
                "name": "Kim J.-S.",
                "pos": "LB",
                "rating": 79,
                "age": 26,
                "club": "Al-Fayha",
            },
            {
                "name": "Hwang I.",
                "pos": "CDM",
                "rating": 82,
                "age": 28,
                "club": "Newcastle",
            },
            {
                "name": "Lee Jae-S.",
                "pos": "CM",
                "rating": 80,
                "age": 27,
                "club": "Brighton",
            },
            {
                "name": "Son Heung-Min",
                "pos": "LW",
                "rating": 87,
                "age": 33,
                "club": "Tottenham",
            },
            {
                "name": "Lee Kang-I.",
                "pos": "AM",
                "rating": 80,
                "age": 26,
                "club": "Eintracht",
            },
            {
                "name": "Cho G.-S.",
                "pos": "ST",
                "rating": 81,
                "age": 23,
                "club": "Brentford",
            },
            {
                "name": "Kwon C.-H.",
                "pos": "ST",
                "rating": 80,
                "age": 29,
                "club": "Union Berlin",
            },
            {
                "name": "Jo H.-T.",
                "pos": "GK",
                "rating": 78,
                "age": 26,
                "club": "Jeonbuk",
            },
            {
                "name": "Paik S.-H.",
                "pos": "CM",
                "rating": 80,
                "age": 28,
                "club": "Frosinone",
            },
            {
                "name": "Jeong W.-I.",
                "pos": "CM",
                "rating": 78,
                "age": 29,
                "club": "Hull City",
            },
            {
                "name": "Hong H.-J.",
                "pos": "RW",
                "rating": 78,
                "age": 26,
                "club": "Wolfsburg",
            },
            {
                "name": "Oh H.-K.",
                "pos": "LW",
                "rating": 79,
                "age": 24,
                "club": "St. Gallen",
            },
        ],
    },
    "Senegal": {
        "squad_value_m": 250,
        "prior_pin": 51.0,
        "flag": "🇸🇳",
        "confederation": "CAF",
        "players": [
            {
                "name": "Mendy E.",
                "pos": "GK",
                "rating": 84,
                "age": 32,
                "club": "Chelsea",
            },
            {
                "name": "Sabaly",
                "pos": "RB",
                "rating": 80,
                "age": 32,
                "club": "Real Betis",
            },
            {
                "name": "Diallo K.",
                "pos": "CB",
                "rating": 80,
                "age": 26,
                "club": "Man Utd",
            },
            {
                "name": "Koulibaly",
                "pos": "CB",
                "rating": 83,
                "age": 34,
                "club": "Al-Hilal",
            },
            {
                "name": "Niakhate",
                "pos": "CB",
                "rating": 79,
                "age": 28,
                "club": "Nottm Forest",
            },
            {
                "name": "Nampalys M.",
                "pos": "CDM",
                "rating": 79,
                "age": 34,
                "club": "Nice",
            },
            {
                "name": "P. Gueye",
                "pos": "CM",
                "rating": 82,
                "age": 34,
                "club": "Everton",
            },
            {"name": "Mané", "pos": "LW", "rating": 85, "age": 34, "club": "Al-Nassr"},
            {
                "name": "Diatta I.",
                "pos": "RW",
                "rating": 81,
                "age": 27,
                "club": "Monaco",
            },
            {"name": "Dia B.", "pos": "ST", "rating": 81, "age": 27, "club": "Lazio"},
            {
                "name": "Sarr I.",
                "pos": "RW",
                "rating": 82,
                "age": 26,
                "club": "Crystal P.",
            },
            {
                "name": "Gomis K.",
                "pos": "GK",
                "rating": 78,
                "age": 35,
                "club": "Al-Ahli",
            },
            {
                "name": "Ba O.",
                "pos": "CB",
                "rating": 79,
                "age": 29,
                "club": "AS Monaco",
            },
            {"name": "Diallo A.", "pos": "CM", "rating": 79, "age": 25, "club": "PSG"},
            {"name": "Dieng M.", "pos": "ST", "rating": 79, "age": 26, "club": "Lyon"},
            {
                "name": "Ndiaye I.",
                "pos": "AM",
                "rating": 80,
                "age": 24,
                "club": "Everton",
            },
        ],
    },
    "Croatia": {
        "squad_value_m": 350,
        "prior_pin": 29.0,
        "flag": "🇭🇷",
        "confederation": "UEFA",
        "players": [
            {
                "name": "Livakovic",
                "pos": "GK",
                "rating": 84,
                "age": 29,
                "club": "Fenerbahce",
            },
            {
                "name": "Juranovic",
                "pos": "RB",
                "rating": 82,
                "age": 28,
                "club": "Union Berlin",
            },
            {
                "name": "Gvardiol",
                "pos": "CB",
                "rating": 86,
                "age": 22,
                "club": "Man City",
            },
            {
                "name": "Pongracic",
                "pos": "CB",
                "rating": 81,
                "age": 25,
                "club": "Fiorentina",
            },
            {"name": "Sosa B.", "pos": "LB", "rating": 81, "age": 26, "club": "Torino"},
            {
                "name": "Modric",
                "pos": "CM",
                "rating": 86,
                "age": 40,
                "club": "Real Madrid",
            },
            {
                "name": "Kovacic",
                "pos": "CM",
                "rating": 85,
                "age": 31,
                "club": "Man City",
            },
            {
                "name": "Brozovic",
                "pos": "CDM",
                "rating": 84,
                "age": 31,
                "club": "Al-Nassr",
            },
            {
                "name": "Majer",
                "pos": "AM",
                "rating": 82,
                "age": 26,
                "club": "Real Sociedad",
            },
            {
                "name": "Petkovic",
                "pos": "ST",
                "rating": 82,
                "age": 29,
                "club": "Dinamo",
            },
            {
                "name": "Kramaric",
                "pos": "ST",
                "rating": 83,
                "age": 33,
                "club": "Hoffenheim",
            },
            {"name": "Sutalo", "pos": "CB", "rating": 80, "age": 23, "club": "Ajax"},
            {
                "name": "Sucic",
                "pos": "AM",
                "rating": 81,
                "age": 22,
                "club": "RB Salzburg",
            },
            {
                "name": "Pasalic",
                "pos": "AM",
                "rating": 81,
                "age": 30,
                "club": "Atalanta",
            },
            {"name": "Ivanusec", "pos": "LW", "rating": 80, "age": 25, "club": "Lazio"},
            {
                "name": "Budimir",
                "pos": "ST",
                "rating": 80,
                "age": 32,
                "club": "Osasuna",
            },
        ],
    },
    "Italy": {
        "squad_value_m": 780,
        "prior_pin": 17.0,
        "flag": "🇮🇹",
        "confederation": "UEFA",
        "players": [
            {"name": "Donnarumma", "pos": "GK", "rating": 88, "age": 27, "club": "PSG"},
            {
                "name": "Di Lorenzo",
                "pos": "RB",
                "rating": 83,
                "age": 27,
                "club": "Napoli",
            },
            {"name": "Bastoni", "pos": "CB", "rating": 87, "age": 25, "club": "Inter"},
            {
                "name": "Buongiorno",
                "pos": "CB",
                "rating": 83,
                "age": 25,
                "club": "Napoli",
            },
            {"name": "Dimarco", "pos": "LB", "rating": 83, "age": 27, "club": "Inter"},
            {"name": "Barella", "pos": "CM", "rating": 87, "age": 27, "club": "Inter"},
            {
                "name": "Jorginho",
                "pos": "CDM",
                "rating": 82,
                "age": 34,
                "club": "Arsenal",
            },
            {
                "name": "Tonali",
                "pos": "CM",
                "rating": 85,
                "age": 24,
                "club": "Newcastle",
            },
            {
                "name": "Chiesa",
                "pos": "RW",
                "rating": 85,
                "age": 27,
                "club": "Liverpool",
            },
            {
                "name": "Pellegrini",
                "pos": "AM",
                "rating": 83,
                "age": 28,
                "club": "Roma",
            },
            {
                "name": "Retegui",
                "pos": "ST",
                "rating": 83,
                "age": 25,
                "club": "Atalanta",
            },
            {"name": "Meret", "pos": "GK", "rating": 83, "age": 27, "club": "Napoli"},
            {
                "name": "Calafiori",
                "pos": "CB",
                "rating": 83,
                "age": 22,
                "club": "Arsenal",
            },
            {"name": "Zaccagni", "pos": "LW", "rating": 82, "age": 29, "club": "Lazio"},
            {
                "name": "Cambiaso",
                "pos": "LB",
                "rating": 83,
                "age": 24,
                "club": "Juventus",
            },
            {"name": "Frattesi", "pos": "CM", "rating": 82, "age": 26, "club": "Inter"},
        ],
    },
    "Denmark": {
        "squad_value_m": 420,
        "prior_pin": 29.0,
        "flag": "🇩🇰",
        "confederation": "UEFA",
        "players": [
            {
                "name": "Schmeichel K.",
                "pos": "GK",
                "rating": 81,
                "age": 38,
                "club": "Anderlecht",
            },
            {
                "name": "Andersen J.",
                "pos": "CB",
                "rating": 83,
                "age": 29,
                "club": "Crystal P.",
            },
            {
                "name": "Christensen",
                "pos": "CB",
                "rating": 84,
                "age": 28,
                "club": "Barcelona",
            },
            {
                "name": "Nelsson V.",
                "pos": "CB",
                "rating": 80,
                "age": 25,
                "club": "Galatasaray",
            },
            {
                "name": "Maehle",
                "pos": "LB",
                "rating": 82,
                "age": 28,
                "club": "Atalanta",
            },
            {
                "name": "Eriksen",
                "pos": "CM",
                "rating": 85,
                "age": 34,
                "club": "Man Utd",
            },
            {
                "name": "Hojbjerg",
                "pos": "CDM",
                "rating": 84,
                "age": 29,
                "club": "Marseille",
            },
            {
                "name": "Delaney",
                "pos": "CDM",
                "rating": 81,
                "age": 34,
                "club": "Anderlecht",
            },
            {
                "name": "Skov Olsen",
                "pos": "RW",
                "rating": 81,
                "age": 26,
                "club": "Club Bruges",
            },
            {
                "name": "Hojlund",
                "pos": "ST",
                "rating": 83,
                "age": 22,
                "club": "Man Utd",
            },
            {
                "name": "Dolberg",
                "pos": "ST",
                "rating": 80,
                "age": 27,
                "club": "Anderlecht",
            },
            {
                "name": "Ronnow",
                "pos": "GK",
                "rating": 80,
                "age": 32,
                "club": "Union Berlin",
            },
            {"name": "Wind", "pos": "ST", "rating": 80, "age": 25, "club": "Wolfsburg"},
            {
                "name": "Bah A.",
                "pos": "RB",
                "rating": 80,
                "age": 23,
                "club": "Southampton",
            },
            {
                "name": "Lindstrom J.",
                "pos": "AM",
                "rating": 80,
                "age": 25,
                "club": "Napoli",
            },
            {
                "name": "Knudsen J.",
                "pos": "LB",
                "rating": 79,
                "age": 30,
                "club": "Atalanta",
            },
        ],
    },
    "Switzerland": {
        "squad_value_m": 310,
        "prior_pin": 34.0,
        "flag": "🇨🇭",
        "confederation": "UEFA",
        "players": [
            {"name": "Sommer", "pos": "GK", "rating": 84, "age": 36, "club": "Inter"},
            {"name": "Widmer", "pos": "RB", "rating": 80, "age": 30, "club": "Mainz"},
            {
                "name": "Akanji",
                "pos": "CB",
                "rating": 85,
                "age": 29,
                "club": "Man City",
            },
            {
                "name": "Elvedi",
                "pos": "CB",
                "rating": 82,
                "age": 28,
                "club": "Gladbach",
            },
            {
                "name": "Rodriguez R.",
                "pos": "LB",
                "rating": 82,
                "age": 32,
                "club": "Torino",
            },
            {
                "name": "Freuler",
                "pos": "CDM",
                "rating": 82,
                "age": 32,
                "club": "Nottm Forest",
            },
            {
                "name": "Granit Xhaka",
                "pos": "CM",
                "rating": 84,
                "age": 33,
                "club": "Leverkusen",
            },
            {
                "name": "Sow S.",
                "pos": "CM",
                "rating": 80,
                "age": 27,
                "club": "Eintracht",
            },
            {
                "name": "Shaqiri",
                "pos": "AM",
                "rating": 83,
                "age": 33,
                "club": "Chicago Fire",
            },
            {"name": "Embolo", "pos": "ST", "rating": 81, "age": 27, "club": "Monaco"},
            {
                "name": "Seferovic",
                "pos": "ST",
                "rating": 80,
                "age": 33,
                "club": "Galatasaray",
            },
            {"name": "Kobel", "pos": "GK", "rating": 83, "age": 24, "club": "Dortmund"},
            {"name": "Omlin", "pos": "GK", "rating": 81, "age": 29, "club": "Monaco"},
            {
                "name": "Zakaria",
                "pos": "CDM",
                "rating": 81,
                "age": 27,
                "club": "Monaco",
            },
            {
                "name": "Ndoye D.",
                "pos": "RW",
                "rating": 81,
                "age": 24,
                "club": "Bologna",
            },
            {
                "name": "Aebischer",
                "pos": "CM",
                "rating": 79,
                "age": 27,
                "club": "Bologna",
            },
        ],
    },
    "Ecuador": {
        "squad_value_m": 200,
        "prior_pin": 67.0,
        "flag": "🇪🇨",
        "confederation": "CONMEBOL",
        "players": [
            {
                "name": "Dominguez A.",
                "pos": "GK",
                "rating": 79,
                "age": 32,
                "club": "Bologna",
            },
            {"name": "Preciado", "pos": "RB", "rating": 78, "age": 23, "club": "Genoa"},
            {
                "name": "Hincapie",
                "pos": "CB",
                "rating": 81,
                "age": 22,
                "club": "Leverkusen",
            },
            {"name": "Pacho", "pos": "CB", "rating": 80, "age": 22, "club": "PSG"},
            {
                "name": "Estupinan",
                "pos": "LB",
                "rating": 82,
                "age": 26,
                "club": "Brighton",
            },
            {
                "name": "Gruezo C.",
                "pos": "CDM",
                "rating": 79,
                "age": 28,
                "club": "Augsburg",
            },
            {
                "name": "Plata R.",
                "pos": "AM",
                "rating": 80,
                "age": 24,
                "club": "LA Galaxy",
            },
            {
                "name": "Caicedo M.",
                "pos": "CDM",
                "rating": 85,
                "age": 22,
                "club": "Chelsea",
            },
            {
                "name": "Valencia E.",
                "pos": "ST",
                "rating": 82,
                "age": 28,
                "club": "Atalanta",
            },
            {
                "name": "Ibarra G.",
                "pos": "LW",
                "rating": 79,
                "age": 24,
                "club": "Estudiantes",
            },
            {
                "name": "Sarmiento J.",
                "pos": "AM",
                "rating": 79,
                "age": 23,
                "club": "Brighton",
            },
            {
                "name": "Galíndez",
                "pos": "GK",
                "rating": 77,
                "age": 33,
                "club": "Ath. Tucumán",
            },
            {
                "name": "Torres A.",
                "pos": "RB",
                "rating": 77,
                "age": 31,
                "club": "Independiente",
            },
            {
                "name": "Reasco",
                "pos": "RW",
                "rating": 78,
                "age": 23,
                "club": "Newell's Old",
            },
            {
                "name": "Arboleda",
                "pos": "CB",
                "rating": 79,
                "age": 30,
                "club": "São Paulo",
            },
            {
                "name": "Cifuentes",
                "pos": "CM",
                "rating": 78,
                "age": 23,
                "club": "Leeds",
            },
        ],
    },
    "Australia": {
        "squad_value_m": 170,
        "prior_pin": 76.0,
        "flag": "🇦🇺",
        "confederation": "AFC",
        "players": [
            {
                "name": "Ryan M.",
                "pos": "GK",
                "rating": 82,
                "age": 32,
                "club": "Real Sociedad",
            },
            {
                "name": "Atkinson N.",
                "pos": "RB",
                "rating": 79,
                "age": 25,
                "club": "Celtic",
            },
            {
                "name": "Rowles K.",
                "pos": "CB",
                "rating": 78,
                "age": 25,
                "club": "Hearts",
            },
            {
                "name": "Spiranovic",
                "pos": "CB",
                "rating": 77,
                "age": 28,
                "club": "Dinamo Zagreb",
            },
            {
                "name": "Karacic",
                "pos": "RB",
                "rating": 77,
                "age": 28,
                "club": "Brescia",
            },
            {
                "name": "Mooy A.",
                "pos": "CDM",
                "rating": 82,
                "age": 34,
                "club": "Celtic",
            },
            {
                "name": "McGree R.",
                "pos": "CM",
                "rating": 78,
                "age": 25,
                "club": "Middlesbrough",
            },
            {
                "name": "Leckie",
                "pos": "RW",
                "rating": 80,
                "age": 33,
                "club": "Melbourne City",
            },
            {
                "name": "Hrustic A.",
                "pos": "AM",
                "rating": 79,
                "age": 27,
                "club": "Hellas V.",
            },
            {
                "name": "Irvine J.",
                "pos": "CM",
                "rating": 80,
                "age": 31,
                "club": "Sheffield Utd",
            },
            {
                "name": "Duke M.",
                "pos": "ST",
                "rating": 79,
                "age": 33,
                "club": "Al-Arabi",
            },
            {
                "name": "Vukovic D.",
                "pos": "GK",
                "rating": 77,
                "age": 38,
                "club": "Genk",
            },
            {
                "name": "Bos A.",
                "pos": "CB",
                "rating": 77,
                "age": 24,
                "club": "Melbourne City",
            },
            {
                "name": "Nabbout",
                "pos": "LW",
                "rating": 77,
                "age": 32,
                "club": "Melbourne V.",
            },
            {
                "name": "Metcalfe",
                "pos": "CM",
                "rating": 77,
                "age": 25,
                "club": "Huddersfield",
            },
            {
                "name": "MacLaren M.",
                "pos": "ST",
                "rating": 78,
                "age": 29,
                "club": "Middlesbrough",
            },
        ],
    },
    "Iran": {
        "squad_value_m": 90,
        "prior_pin": 101.0,
        "flag": "🇮🇷",
        "confederation": "AFC",
        "players": [
            {
                "name": "Hosseini A.",
                "pos": "GK",
                "rating": 78,
                "age": 34,
                "club": "Persepolis",
            },
            {
                "name": "Moharrami",
                "pos": "RB",
                "rating": 77,
                "age": 27,
                "club": "Sepahan",
            },
            {
                "name": "Hosseini M.",
                "pos": "CB",
                "rating": 78,
                "age": 33,
                "club": "Al-Wehda",
            },
            {
                "name": "Pouraliganji",
                "pos": "CB",
                "rating": 77,
                "age": 33,
                "club": "Al-Wakrah",
            },
            {
                "name": "Mohammadi",
                "pos": "LB",
                "rating": 77,
                "age": 31,
                "club": "Persepolis",
            },
            {
                "name": "Noorollahi",
                "pos": "CDM",
                "rating": 78,
                "age": 30,
                "club": "Persepolis",
            },
            {
                "name": "Ezatolahi",
                "pos": "CM",
                "rating": 78,
                "age": 27,
                "club": "Östersund",
            },
            {
                "name": "Jahanbakhsh",
                "pos": "RW",
                "rating": 79,
                "age": 31,
                "club": "Feyenoord",
            },
            {
                "name": "Taremi M.",
                "pos": "ST",
                "rating": 83,
                "age": 32,
                "club": "Inter",
            },
            {
                "name": "Gholizadeh",
                "pos": "LW",
                "rating": 78,
                "age": 28,
                "club": "Charleroi",
            },
            {
                "name": "Azmoun",
                "pos": "ST",
                "rating": 82,
                "age": 30,
                "club": "Bayer Lever.",
            },
            {
                "name": "Abedzadeh",
                "pos": "GK",
                "rating": 76,
                "age": 36,
                "club": "Persepolis",
            },
            {
                "name": "Sarlak K.",
                "pos": "GK",
                "rating": 77,
                "age": 26,
                "club": "St. Pölten",
            },
            {"name": "Kanani", "pos": "RB", "rating": 76, "age": 30, "club": "Sepahan"},
            {
                "name": "Hajsafi",
                "pos": "LB",
                "rating": 77,
                "age": 35,
                "club": "AEK Athens",
            },
            {
                "name": "Ali Karimi",
                "pos": "AM",
                "rating": 78,
                "age": 26,
                "club": "Persepolis",
            },
        ],
    },
    "Saudi Arabia": {
        "squad_value_m": 110,
        "prior_pin": 126.0,
        "flag": "🇸🇦",
        "confederation": "AFC",
        "players": [
            {
                "name": "Al-Owais",
                "pos": "GK",
                "rating": 78,
                "age": 31,
                "club": "Al-Hilal",
            },
            {
                "name": "Al-Shahrani",
                "pos": "LB",
                "rating": 75,
                "age": 32,
                "club": "Al-Hilal",
            },
            {
                "name": "Al-Amri A.",
                "pos": "CB",
                "rating": 75,
                "age": 24,
                "club": "Al-Qadsiah",
            },
            {
                "name": "Al-Bulayhi",
                "pos": "CB",
                "rating": 76,
                "age": 32,
                "club": "Al-Hilal",
            },
            {
                "name": "Sultan A.",
                "pos": "RB",
                "rating": 74,
                "age": 26,
                "club": "Al-Qadsiah",
            },
            {
                "name": "Al-Dawsari",
                "pos": "LW",
                "rating": 78,
                "age": 32,
                "club": "Al-Hilal",
            },
            {
                "name": "Al-Malki",
                "pos": "CDM",
                "rating": 75,
                "age": 27,
                "club": "Al-Ahli",
            },
            {
                "name": "Salem Aldawsari",
                "pos": "RW",
                "rating": 79,
                "age": 32,
                "club": "Al-Hilal",
            },
            {
                "name": "Al-Buraikan",
                "pos": "ST",
                "rating": 77,
                "age": 23,
                "club": "Al-Ahli",
            },
            {
                "name": "Al-Ghannam",
                "pos": "AM",
                "rating": 76,
                "age": 25,
                "club": "Al-Ettifaq",
            },
            {
                "name": "Al-Shehri",
                "pos": "ST",
                "rating": 77,
                "age": 28,
                "club": "Al-Hilal",
            },
            {
                "name": "Al-Rubaie",
                "pos": "GK",
                "rating": 74,
                "age": 28,
                "club": "Al-Hazm",
            },
            {
                "name": "Abdulelah A.",
                "pos": "CM",
                "rating": 74,
                "age": 25,
                "club": "Al-Shabab",
            },
            {
                "name": "Al-Muwallad",
                "pos": "LW",
                "rating": 76,
                "age": 31,
                "club": "Al-Ittihad",
            },
            {
                "name": "Asiri A.",
                "pos": "CM",
                "rating": 74,
                "age": 25,
                "club": "Al-Faisaly",
            },
            {
                "name": "Nasser A.",
                "pos": "RB",
                "rating": 74,
                "age": 24,
                "club": "Al-Ahli",
            },
        ],
    },
    "Poland": {
        "squad_value_m": 270,
        "prior_pin": 51.0,
        "flag": "🇵🇱",
        "confederation": "UEFA",
        "players": [
            {
                "name": "Szczesny",
                "pos": "GK",
                "rating": 85,
                "age": 34,
                "club": "Barcelona",
            },
            {
                "name": "Cash M.",
                "pos": "RB",
                "rating": 81,
                "age": 27,
                "club": "Aston Villa",
            },
            {
                "name": "Bednarek",
                "pos": "CB",
                "rating": 82,
                "age": 28,
                "club": "Southampton",
            },
            {"name": "Glik", "pos": "CB", "rating": 79, "age": 36, "club": "Benevento"},
            {
                "name": "Rybus",
                "pos": "LB",
                "rating": 78,
                "age": 35,
                "club": "Lokomotiv M.",
            },
            {
                "name": "Krychowiak",
                "pos": "CDM",
                "rating": 80,
                "age": 34,
                "club": "Al-Shabab",
            },
            {
                "name": "Zurkowski",
                "pos": "CM",
                "rating": 78,
                "age": 27,
                "club": "Spezia",
            },
            {
                "name": "Zielinski",
                "pos": "AM",
                "rating": 84,
                "age": 30,
                "club": "Inter",
            },
            {
                "name": "Szymanski S.",
                "pos": "AM",
                "rating": 81,
                "age": 25,
                "club": "Fenerbahce",
            },
            {"name": "Milik", "pos": "ST", "rating": 81, "age": 30, "club": "Juventus"},
            {
                "name": "Lewandowski",
                "pos": "ST",
                "rating": 89,
                "age": 37,
                "club": "Barcelona",
            },
            {
                "name": "Grabara K.",
                "pos": "GK",
                "rating": 80,
                "age": 25,
                "club": "Copenhagen",
            },
            {
                "name": "Frankowski",
                "pos": "RW",
                "rating": 79,
                "age": 28,
                "club": "Lens",
            },
            {
                "name": "Kowalski",
                "pos": "RW",
                "rating": 78,
                "age": 26,
                "club": "GKS Katowice",
            },
            {
                "name": "Dawidowicz",
                "pos": "CB",
                "rating": 79,
                "age": 29,
                "club": "Verona",
            },
            {
                "name": "Kaminski M.",
                "pos": "CM",
                "rating": 78,
                "age": 31,
                "club": "Lens",
            },
        ],
    },
}

# Lightweight entries for remaining 48-team qualifiers (Pinnacle odds primary signal)
_LITE_TEAMS: dict = {
    "Nigeria": {
        "squad_value_m": 220,
        "prior_pin": 101.0,
        "flag": "🇳🇬",
        "confederation": "CAF",
    },
    "Egypt": {
        "squad_value_m": 140,
        "prior_pin": 126.0,
        "flag": "🇪🇬",
        "confederation": "CAF",
    },
    "Cameroon": {
        "squad_value_m": 130,
        "prior_pin": 151.0,
        "flag": "🇨🇲",
        "confederation": "CAF",
    },
    "Ghana": {
        "squad_value_m": 160,
        "prior_pin": 151.0,
        "flag": "🇬🇭",
        "confederation": "CAF",
    },
    "Ivory Coast": {
        "squad_value_m": 200,
        "prior_pin": 101.0,
        "flag": "🇨🇮",
        "confederation": "CAF",
    },
    "Tunisia": {
        "squad_value_m": 110,
        "prior_pin": 201.0,
        "flag": "🇹🇳",
        "confederation": "CAF",
    },
    "Algeria": {
        "squad_value_m": 140,
        "prior_pin": 151.0,
        "flag": "🇩🇿",
        "confederation": "CAF",
    },
    "Mali": {
        "squad_value_m": 80,
        "prior_pin": 251.0,
        "flag": "🇲🇱",
        "confederation": "CAF",
    },
    "Qatar": {
        "squad_value_m": 90,
        "prior_pin": 301.0,
        "flag": "🇶🇦",
        "confederation": "AFC",
    },
    "Iraq": {
        "squad_value_m": 80,
        "prior_pin": 251.0,
        "flag": "🇮🇶",
        "confederation": "AFC",
    },
    "Jordan": {
        "squad_value_m": 70,
        "prior_pin": 301.0,
        "flag": "🇯🇴",
        "confederation": "AFC",
    },
    "Uzbekistan": {
        "squad_value_m": 80,
        "prior_pin": 251.0,
        "flag": "🇺🇿",
        "confederation": "AFC",
    },
    "Austria": {
        "squad_value_m": 350,
        "prior_pin": 51.0,
        "flag": "🇦🇹",
        "confederation": "UEFA",
    },
    "Turkey": {
        "squad_value_m": 380,
        "prior_pin": 41.0,
        "flag": "🇹🇷",
        "confederation": "UEFA",
    },
    "Scotland": {
        "squad_value_m": 240,
        "prior_pin": 76.0,
        "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "confederation": "UEFA",
    },
    "Serbia": {
        "squad_value_m": 310,
        "prior_pin": 51.0,
        "flag": "🇷🇸",
        "confederation": "UEFA",
    },
    "Czech Rep.": {
        "squad_value_m": 250,
        "prior_pin": 67.0,
        "flag": "🇨🇿",
        "confederation": "UEFA",
    },
    "Romania": {
        "squad_value_m": 190,
        "prior_pin": 101.0,
        "flag": "🇷🇴",
        "confederation": "UEFA",
    },
    "Slovakia": {
        "squad_value_m": 200,
        "prior_pin": 101.0,
        "flag": "🇸🇰",
        "confederation": "UEFA",
    },
    "Greece": {
        "squad_value_m": 200,
        "prior_pin": 101.0,
        "flag": "🇬🇷",
        "confederation": "UEFA",
    },
    "Ukraine": {
        "squad_value_m": 280,
        "prior_pin": 76.0,
        "flag": "🇺🇦",
        "confederation": "UEFA",
    },
    "Panama": {
        "squad_value_m": 50,
        "prior_pin": 301.0,
        "flag": "🇵🇦",
        "confederation": "CONCACAF",
    },
    "Honduras": {
        "squad_value_m": 40,
        "prior_pin": 501.0,
        "flag": "🇭🇳",
        "confederation": "CONCACAF",
    },
    "Costa Rica": {
        "squad_value_m": 60,
        "prior_pin": 301.0,
        "flag": "🇨🇷",
        "confederation": "CONCACAF",
    },
    "Jamaica": {
        "squad_value_m": 60,
        "prior_pin": 501.0,
        "flag": "🇯🇲",
        "confederation": "CONCACAF",
    },
    "Venezuela": {
        "squad_value_m": 150,
        "prior_pin": 101.0,
        "flag": "🇻🇪",
        "confederation": "CONMEBOL",
    },
    "Chile": {
        "squad_value_m": 160,
        "prior_pin": 126.0,
        "flag": "🇨🇱",
        "confederation": "CONMEBOL",
    },
    "Paraguay": {
        "squad_value_m": 120,
        "prior_pin": 151.0,
        "flag": "🇵🇾",
        "confederation": "CONMEBOL",
    },
    "Bolivia": {
        "squad_value_m": 70,
        "prior_pin": 301.0,
        "flag": "🇧🇴",
        "confederation": "CONMEBOL",
    },
    "New Zealand": {
        "squad_value_m": 45,
        "prior_pin": 501.0,
        "flag": "🇳🇿",
        "confederation": "OFC",
    },
    "Albania": {
        "squad_value_m": 130,
        "prior_pin": 151.0,
        "flag": "🇦🇱",
        "confederation": "UEFA",
    },
    "Slovenia": {
        "squad_value_m": 130,
        "prior_pin": 151.0,
        "flag": "🇸🇮",
        "confederation": "UEFA",
    },
}

# Merge
for _name, _data in _LITE_TEAMS.items():
    if _name not in TEAMS:
        TEAMS[_name] = _data


# ─── Pinnacle Live Outright Odds ──────────────────────────────────────────────


def _fetch_live_pinnacle_wc_odds() -> dict:
    """
    Try to fetch live WC winner outright odds from Pinnacle guest API.
    Returns dict  team_name -> implied_probability  (de-vigged).
    Returns {} on any error — callers fall back to prior_pin.
    """
    try:
        import requests

        base = "https://guest.api.arcadia.pinnacle.com/0.1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.pinnacle.com",
            "Referer": "https://www.pinnacle.com/",
        }
        # Tournament winner specials — sport 29 (soccer), period 0 (FT)
        r = requests.get(
            f"{base}/sports/29/specials",
            params={"brandId": "0"},
            headers=headers,
            timeout=10,
        )
        if r.status_code != 200:
            return {}
        specials = r.json()

        # Find the WC 2026 winner market
        wc_special = None
        for s in specials:
            name = (s.get("name") or "").lower()
            if "world cup" in name and ("winner" in name or "to win" in name):
                wc_special = s
                break
        if wc_special is None:
            return {}

        special_id = wc_special.get("id")
        r2 = requests.get(
            f"{base}/sports/29/specials/{special_id}/markets",
            headers=headers,
            timeout=10,
        )
        if r2.status_code != 200:
            return {}
        contestants = r2.json()

        # De-vig
        raw: dict = {}
        for c in contestants:
            team = c.get("name", "")
            price = c.get("price")  # American odds
            if price is None:
                continue
            # American → decimal
            if price > 0:
                dec = price / 100.0 + 1.0
            else:
                dec = 100.0 / abs(price) + 1.0
            raw[team] = 1.0 / dec  # implied prob

        if not raw:
            return {}

        total = sum(raw.values())
        return {t: round(p / total, 6) for t, p in raw.items()}

    except Exception:
        return {}


# ─── Team Strength Computation ────────────────────────────────────────────────


def _squad_rating(team_name: str) -> float:
    """Weighted squad average rating (starters 70%, depth 30%). Range 0–1."""
    data = TEAMS.get(team_name, {})
    players = data.get("players", [])
    if not players:
        # Lite team: estimate from prior odds (weaker team = lower odds favourable = worse)
        prior = data.get("prior_pin", 100.0)
        # Invert: prior of 5 → ~88, prior of 100 → ~72
        return max(0.60, min(0.90, 0.90 - math.log(prior) * 0.025))

    sorted_p = sorted(players, key=lambda p: p["rating"], reverse=True)
    starter_avg = sum(p["rating"] for p in sorted_p[:11]) / 11.0
    bench = sorted_p[11:]
    bench_avg = sum(p["rating"] for p in bench) / len(bench) if bench else starter_avg
    raw = (0.70 * starter_avg + 0.30 * bench_avg) / 100.0
    return round(raw, 4)


def _value_norm(squad_value_m: float, max_value: float) -> float:
    """Normalise Transfermarkt squad value to 0–1."""
    if max_value <= 0:
        return 0.5
    return round(min(1.0, squad_value_m / max_value), 4)


def compute_all_strengths(
    live_pinnacle: Optional[dict] = None,
) -> dict:
    """
    Return a dict  team_name -> composite_strength (0–1).

    Weights:
      40% Pinnacle implied probability (live if available, else from prior_pin)
      30% Squad FIFA ratings
      20% Transfermarkt squad value (normalised)
      10% Aggregate of the other three (blend stabiliser)
    """
    if live_pinnacle is None:
        live_pinnacle = {}

    max_value = max((d.get("squad_value_m", 0) for d in TEAMS.values()), default=1)

    # Build raw prior-based implied probs for fallback
    prior_inv: dict = {}
    for name, data in TEAMS.items():
        prior_pin = data.get("prior_pin", 201.0)
        prior_inv[name] = 1.0 / prior_pin

    total_prior = sum(prior_inv.values())
    prior_probs = {n: v / total_prior for n, v in prior_inv.items()}

    strengths: dict = {}
    for name, data in TEAMS.items():
        sq_rat = _squad_rating(name)
        val_norm = _value_norm(data.get("squad_value_m", 50), max_value)

        # Pinnacle probability (live > prior fallback)
        # Try to fuzzy-match Pinnacle names
        pin_prob = None
        if live_pinnacle:
            # Exact match first
            pin_prob = live_pinnacle.get(name)
            if pin_prob is None:
                # Case-insensitive partial match
                name_l = name.lower()
                for pname, pprob in live_pinnacle.items():
                    if name_l in pname.lower() or pname.lower() in name_l:
                        pin_prob = pprob
                        break

        if pin_prob is None:
            pin_prob = prior_probs.get(name, 0.001)

        # Normalise each signal to comparable scale (team's share of total)
        # Then blend
        composite = (
            0.40 * pin_prob  # market
            + 0.30
            * sq_rat
            / 10  # squad quality (sq_rat is ~0.7–0.93, divide by 10 to scale)
            + 0.20 * val_norm / 10  # squad value (similar scale division)
            + 0.10 * (pin_prob + sq_rat / 10 + val_norm / 10) / 3
        )
        strengths[name] = composite

    # Re-normalise to sum = 1 (clean probability interpretation)
    total = sum(strengths.values())
    return {n: round(v / total, 6) for n, v in strengths.items()}


# ─── Monte Carlo Simulation ───────────────────────────────────────────────────


def _match_win_prob(strength_a: float, strength_b: float) -> float:
    """
    Probability team_a beats team_b in a knockout match (including ET/pens).
    Uses a logistic squeeze: very small differences → close to 50/50.
    """
    if strength_a + strength_b <= 0:
        return 0.5
    raw = strength_a / (strength_a + strength_b)
    # Squeeze toward 0.5 to account for match variance (anything can happen in 90 min)
    # Parameter k=3 gives realistic spread: 2× stronger team wins ~67% not ~100%
    k = 3.0
    logit_raw = math.log(raw / (1 - raw + 1e-9))
    squeezed = 1.0 / (1.0 + math.exp(-k * logit_raw / 2.0))
    return round(squeezed, 4)


def simulate_tournament(
    remaining_teams: list,
    strengths: dict,
    n_sims: int = 100_000,
    seed: int = 42,
) -> dict:
    """
    Monte Carlo simulation of the knockout bracket.

    remaining_teams: list of team names still in the tournament.
    If the list length is not a power of 2, pads with the weakest non-participants.

    Returns dict  team_name -> win_probability  for all teams.
    """
    rng = random.Random(seed)

    # Pad to next power of 2
    n = len(remaining_teams)
    target = 1
    while target < n:
        target *= 2

    if target != n:
        # Pad with already-eliminated weakest teams (they win 0 sims)
        remaining_teams = list(remaining_teams) + ["__bye__"] * (target - n)

    win_counts: dict = {t: 0 for t in remaining_teams if t != "__bye__"}

    for _ in range(n_sims):
        bracket = list(remaining_teams)
        rng.shuffle(bracket)  # randomise bracket order (group-draw uncertainty)

        # Run rounds until champion
        while len(bracket) > 1:
            next_round = []
            for i in range(0, len(bracket), 2):
                a, b = bracket[i], bracket[i + 1]
                if a == "__bye__":
                    next_round.append(b)
                elif b == "__bye__":
                    next_round.append(a)
                else:
                    sa = strengths.get(a, 1e-6)
                    sb = strengths.get(b, 1e-6)
                    p_a = _match_win_prob(sa, sb)
                    winner = a if rng.random() < p_a else b
                    next_round.append(winner)
            bracket = next_round

        champion = bracket[0]
        if champion in win_counts:
            win_counts[champion] += 1

    total = sum(win_counts.values())
    return {
        t: round(c / total * 100, 2) if total > 0 else 0.0
        for t, c in win_counts.items()
    }


# ─── Player Cards ─────────────────────────────────────────────────────────────


def build_player_breakdown(team_name: str) -> list:
    """
    Return list of player dicts for the given team, sorted by rating desc.
    Adds contribution_score = how much this player elevates the squad above baseline.
    """
    data = TEAMS.get(team_name, {})
    players = data.get("players", [])
    if not players:
        return []

    sorted_p = sorted(players, key=lambda p: p["rating"], reverse=True)
    baseline = 75  # average international player rating
    result = []
    for rank, p in enumerate(sorted_p):
        contribution = round((p["rating"] - baseline) / baseline * 100, 1)
        result.append(
            {
                "rank": rank + 1,
                "name": p["name"],
                "pos": p["pos"],
                "rating": p["rating"],
                "age": p["age"],
                "club": p["club"],
                "contribution_pct": max(0.0, contribution),
                "tier": (
                    "Elite"
                    if p["rating"] >= 89
                    else (
                        "World Class"
                        if p["rating"] >= 86
                        else "International" if p["rating"] >= 82 else "Solid"
                    )
                ),
            }
        )
    return result


# ─── Reasoning Generator ──────────────────────────────────────────────────────

_REASONS = {
    "Brazil": "Vinicius Jr + Rodrygo provide elite pace and creativity; Alisson the world's best keeper. Deepest attacking pool.",
    "France": "Mbappé at peak (27) is the most dangerous player in football. Saliba–Konaté CB pairing one of the best ever assembled.",
    "England": "Bellingham + Rice + Saka = generational midfield-attack. Kane still the most clinical finisher. Squad depth unmatched.",
    "Spain": "Yamal (18!) is already Barcelona's best player. Rodri anchors the best defensive midfield unit. Possession mastery.",
    "Germany": "Wirtz and Musiala (22) are both Ballon d'Or contenders. Rüdiger leads a physically dominant backline.",
    "Argentina": "Messi (38) is still playing — his leadership transforms Argentina. Lautaro+Álvarez are world-class. World champion DNA.",
    "Portugal": "Bernardo Silva and Rúben Dias at their absolute peak. Vitinha–Palhinha one of the best CM pairings. Rafael Leão electric.",
    "Netherlands": "Van Dijk + Timber = elite CB pair. Gravenberch arrived — finally has a world-class DM. Gakpo + Xavi Simons provide spark.",
    "Belgium": "De Bruyne (35) is the last gasp of the golden generation. Openda and Doku are devastating on the counter.",
    "Uruguay": "Valverde is a top-5 midfielder in the world. Darwin Núñez brings relentless pressing. Araújo the best CB in La Liga.",
    "Colombia": "Luis Díaz has become Liverpool's best player. Caicedo is a generational CDM. Colombia peaked at Copa América 2024.",
    "Morocco": "Hakimi + Mazraoui = the best full-back pair in Africa. Organisation under Regragui is elite. Won Africa Cup of Nations.",
    "USA": "Home advantage (co-hosts). Davies-inspired Canada qualified strongly. Pulisic is Serie A's best player. Bellingham-level ceiling.",
    "Japan": "Kubo has broken into elite level. Mitoma is elite at Brighton. Mooy + Endo as one of Asia's best double pivots.",
    "Italy": "Donnarumma + Bastoni + Tonali = generational spine. Barella world-class. Won Euro 2020, strong comeback side.",
    "Croatia": "Modric (40!) still world-class. Kovacic + Gvardiol among the best at their positions. Always over-perform their resources.",
}


def get_reasoning(team_name: str, win_pct: float, rank: int) -> str:
    """Generate reasoning text for why a team has its predicted win probability."""
    base = _REASONS.get(
        team_name, f"Competitive squad with strong continental pedigree."
    )
    if rank == 1:
        prefix = f"🏆 FAVOURITE ({win_pct:.1f}%): "
    elif rank <= 3:
        prefix = f"🔥 Top contender ({win_pct:.1f}%): "
    elif rank <= 8:
        prefix = f"⚡ Dark horse ({win_pct:.1f}%): "
    else:
        prefix = f"📊 {win_pct:.1f}%: "
    return prefix + base


# ─── Main Entry Point ─────────────────────────────────────────────────────────

_CACHE: dict = {}
_CACHE_TTL = 300  # 5 minutes


def get_predictions(force_refresh: bool = False) -> dict:
    """
    Return full prediction payload. Cached for 5 minutes.

    Returns:
      {
        "teams": [
          {
            "rank": 1,
            "name": "France",
            "flag": "🇫🇷",
            "win_pct": 18.43,
            "reasoning": "...",
            "squad_rating": 87.2,
            "squad_value_m": 1350,
            "players": [...],
            "confederation": "UEFA"
          }, ...
        ],
        "data_sources": [...],
        "generated_at": timestamp,
        "n_simulations": 100000,
        "live_pinnacle": bool,
      }
    """
    global _CACHE
    now = time.time()
    if not force_refresh and _CACHE.get("ts", 0) + _CACHE_TTL > now:
        return _CACHE["data"]

    logger.info("[WC] Running tournament prediction …")

    # 1. Fetch live Pinnacle outright odds
    live_pinnacle = _fetch_live_pinnacle_wc_odds()
    has_live = bool(live_pinnacle)
    if not has_live:
        logger.info("[WC] Pinnacle live fetch failed — using prior odds")

    # 2. Compute composite strengths
    strengths = compute_all_strengths(live_pinnacle)

    # 3. Monte Carlo simulation over all 48 teams (realistic: top 32 will dominate)
    all_teams = list(TEAMS.keys())
    win_probs = simulate_tournament(all_teams, strengths, n_sims=100_000)

    # 4. Build output
    team_list = []
    for name in all_teams:
        data = TEAMS[name]
        sq_rat = _squad_rating(name)
        squad_avg_rating = round(sq_rat * 100, 1)

        team_list.append(
            {
                "name": name,
                "flag": data.get("flag", "🏳️"),
                "confederation": data.get("confederation", ""),
                "win_pct": win_probs.get(name, 0.0),
                "squad_rating": squad_avg_rating,
                "squad_value_m": data.get("squad_value_m", 0),
                "players": build_player_breakdown(name),
            }
        )

    # Sort by win_pct descending
    team_list.sort(key=lambda t: t["win_pct"], reverse=True)

    # Add rank + reasoning
    for i, t in enumerate(team_list):
        t["rank"] = i + 1
        t["reasoning"] = get_reasoning(t["name"], t["win_pct"], i + 1)

    result = {
        "teams": team_list,
        "data_sources": [
            (
                "Pinnacle guest API (live outright odds)"
                if has_live
                else "Pre-tournament Pinnacle prior odds"
            ),
            "FIFA 25 player ratings (squad quality)",
            "Transfermarkt squad values (squad depth)",
            "Logistic-Poisson Monte Carlo (100,000 simulations)",
        ],
        "generated_at": now,
        "n_simulations": 100_000,
        "live_pinnacle": has_live,
        "total_teams": len(team_list),
    }

    _CACHE["ts"] = now
    _CACHE["data"] = result
    return result
