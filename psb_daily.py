#!/usr/bin/env python3
"""
pSB Daily Report — MLB Stolen Base Probability Model
Poisson model: pSB% = 1 - exp(-pos × par × bsr × PIF × CIF)
Run with --preview to save output/preview.html instead of emailing.
"""

import argparse
import datetime
import json
import math
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    ET = datetime.timezone(datetime.timedelta(hours=-4))  # EDT fallback

try:
    import requests as _req
    def _get(url, params=None):
        r = _req.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
except ImportError:
    import urllib.request, urllib.parse
    def _get(url, params=None):
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "pSB/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

MLB = "https://statsapi.mlb.com/api/v1"

# ─────────────────────────────────────────────────────────────────────────────
# BATTER_PROFILES  →  (pos, par, bsr)
# pos : avg times reaching base (non-HR) per game
# par : steal-attempt rate when on base
# bsr : base-stealing success rate
# Values derived from 2024-25 season stats
# ─────────────────────────────────────────────────────────────────────────────
BATTER_PROFILES = {
    # ARI
    "Corbin Carroll":               (1.15, 0.32, 0.85),
    "Ketel Marte":                  (1.20, 0.08, 0.78),
    "Lourdes Gurriel Jr.":          (0.95, 0.06, 0.74),
    "Christian Walker":             (0.95, 0.02, 0.67),
    "Eugenio Suarez":               (0.85, 0.02, 0.60),
    "Geraldo Perdomo":              (1.00, 0.12, 0.80),
    "Jake McCarthy":                (0.90, 0.18, 0.82),
    "Gabriel Moreno":               (0.75, 0.03, 0.67),
    "Joc Pederson":                 (0.95, 0.03, 0.68),
    # ATL
    "Ronald Acuna Jr.":             (1.35, 0.33, 0.87),
    "Ozzie Albies":                 (1.10, 0.14, 0.80),
    "Austin Riley":                 (1.10, 0.04, 0.70),
    "Matt Olson":                   (1.10, 0.01, 0.60),
    "Michael Harris II":            (0.95, 0.18, 0.83),
    "Marcell Ozuna":                (1.00, 0.02, 0.65),
    "Sean Murphy":                  (0.80, 0.02, 0.65),
    "Travis d'Arnaud":              (0.70, 0.01, 0.60),
    "Eddie Rosario":                (0.85, 0.04, 0.70),
    # BAL
    "Gunnar Henderson":             (1.25, 0.12, 0.82),
    "Cedric Mullins":               (1.00, 0.20, 0.83),
    "Ryan Mountcastle":             (1.00, 0.02, 0.65),
    "Adley Rutschman":              (1.15, 0.04, 0.72),
    "Anthony Santander":            (1.00, 0.04, 0.70),
    "Colton Cowser":                (0.95, 0.08, 0.76),
    "Jordan Westburg":              (1.00, 0.06, 0.74),
    "Ramon Urias":                  (0.80, 0.03, 0.68),
    "Austin Hays":                  (0.90, 0.07, 0.76),
    # BOS
    "Jarren Duran":                 (1.10, 0.22, 0.84),
    "Rafael Devers":                (1.10, 0.04, 0.70),
    "Masataka Yoshida":             (1.05, 0.02, 0.65),
    "Triston Casas":                (1.00, 0.01, 0.60),
    "Connor Wong":                  (0.70, 0.06, 0.73),
    "Wilyer Abreu":                 (0.95, 0.14, 0.81),
    "Ceddanne Rafaela":             (0.85, 0.10, 0.78),
    "David Hamilton":               (0.85, 0.20, 0.84),
    "Rob Refsnyder":                (0.85, 0.06, 0.73),
    # CHC
    "Nico Hoerner":                 (1.10, 0.18, 0.84),
    "Ian Happ":                     (1.10, 0.10, 0.78),
    "Dansby Swanson":               (1.00, 0.08, 0.76),
    "Cody Bellinger":               (1.00, 0.10, 0.79),
    "Pete Crow-Armstrong":          (0.90, 0.16, 0.82),
    "Christopher Morel":            (0.85, 0.08, 0.75),
    "Miguel Amaya":                 (0.70, 0.02, 0.65),
    "Seiya Suzuki":                 (1.05, 0.04, 0.72),
    "Patrick Wisdom":               (0.75, 0.02, 0.65),
    # CWS
    "Luis Robert Jr.":              (0.95, 0.18, 0.82),
    "Andrew Benintendi":            (0.95, 0.06, 0.74),
    "Korey Lee":                    (0.65, 0.04, 0.70),
    "Gavin Sheets":                 (0.80, 0.01, 0.60),
    "Yoan Moncada":                 (0.90, 0.05, 0.70),
    "Andrew Vaughn":                (0.85, 0.02, 0.65),
    "Lenyn Sosa":                   (0.80, 0.06, 0.73),
    "Eloy Jimenez":                 (0.85, 0.02, 0.65),
    "Seby Zavala":                  (0.60, 0.02, 0.65),
    # CIN
    "Elly De La Cruz":              (1.08, 0.38, 0.82),
    "TJ Friedl":                    (1.00, 0.25, 0.86),
    "Jonathan India":               (1.10, 0.08, 0.77),
    "Spencer Steer":                (1.00, 0.08, 0.76),
    "Jake Fraley":                  (0.90, 0.12, 0.80),
    "Christian Encarnacion-Strand": (0.90, 0.02, 0.65),
    "Tyler Stephenson":             (0.80, 0.02, 0.65),
    "Will Benson":                  (0.80, 0.10, 0.78),
    "Stuart Fairchild":             (0.80, 0.10, 0.78),
    # CLE
    "Jose Ramirez":                 (1.20, 0.12, 0.82),
    "Steven Kwan":                  (1.15, 0.18, 0.85),
    "Josh Naylor":                  (1.00, 0.02, 0.65),
    "Bo Naylor":                    (0.80, 0.05, 0.73),
    "Andres Gimenez":               (0.95, 0.10, 0.79),
    "Brayan Rocchio":               (0.90, 0.12, 0.80),
    "Will Brennan":                 (0.85, 0.08, 0.76),
    "Jhonkensy Noel":               (0.80, 0.03, 0.68),
    "Myles Straw":                  (0.90, 0.16, 0.80),
    # COL
    "Ezequiel Tovar":               (0.95, 0.14, 0.80),
    "Brenton Doyle":                (0.90, 0.22, 0.82),
    "Ryan McMahon":                 (0.90, 0.05, 0.72),
    "Kris Bryant":                  (0.90, 0.02, 0.65),
    "Charlie Blackmon":             (0.85, 0.01, 0.60),
    "Elehuris Montero":             (0.80, 0.03, 0.68),
    "Brendan Rodgers":              (0.85, 0.06, 0.74),
    "Elias Diaz":                   (0.70, 0.02, 0.65),
    "Nolan Jones":                  (0.95, 0.10, 0.78),
    # DET
    "Riley Greene":                 (1.00, 0.12, 0.80),
    "Spencer Torkelson":            (0.95, 0.02, 0.65),
    "Javier Baez":                  (0.85, 0.08, 0.75),
    "Akil Baddoo":                  (0.85, 0.14, 0.81),
    "Kerry Carpenter":              (0.85, 0.04, 0.70),
    "Matt Vierling":                (0.90, 0.08, 0.76),
    "Jake Rogers":                  (0.65, 0.02, 0.65),
    "Zach McKinstry":               (0.85, 0.08, 0.76),
    "Andy Ibanez":                  (0.80, 0.04, 0.70),
    # HOU
    "Jose Altuve":                  (1.15, 0.12, 0.80),
    "Alex Bregman":                 (1.10, 0.04, 0.70),
    "Jeremy Pena":                  (1.00, 0.12, 0.80),
    "Yordan Alvarez":               (1.15, 0.02, 0.65),
    "Kyle Tucker":                  (1.10, 0.14, 0.82),
    "Mauricio Dubon":               (0.90, 0.10, 0.78),
    "Yainer Diaz":                  (0.85, 0.02, 0.65),
    "Jon Singleton":                (0.85, 0.01, 0.60),
    "Jose Abreu":                   (0.85, 0.01, 0.60),
    # KC
    "Bobby Witt Jr.":               (1.15, 0.22, 0.95),
    "Salvador Perez":               (0.90, 0.01, 0.60),
    "MJ Melendez":                  (0.90, 0.08, 0.76),
    "Vinnie Pasquantino":           (1.00, 0.01, 0.60),
    "Hunter Renfroe":               (0.85, 0.02, 0.65),
    "Maikel Garcia":                (0.90, 0.16, 0.82),
    "Dairon Blanco":                (0.80, 0.20, 0.84),
    "Freddy Fermin":                (0.70, 0.03, 0.68),
    "Nelson Velazquez":             (0.80, 0.08, 0.75),
    # LAA
    "Mike Trout":                   (1.15, 0.04, 0.73),
    "Zach Neto":                    (0.90, 0.14, 0.81),
    "Taylor Ward":                  (0.90, 0.04, 0.70),
    "Logan O'Hoppe":                (0.80, 0.02, 0.65),
    "Luis Rengifo":                 (0.85, 0.10, 0.78),
    "Mickey Moniak":                (0.80, 0.10, 0.78),
    "Jo Adell":                     (0.85, 0.06, 0.73),
    "Brandon Drury":                (0.80, 0.03, 0.68),
    "Chad Wallach":                 (0.60, 0.01, 0.60),
    # LAD
    "Mookie Betts":                 (1.25, 0.14, 0.84),
    "Shohei Ohtani":                (1.20, 0.14, 0.82),
    "Freddie Freeman":              (1.25, 0.04, 0.70),
    "Will Smith":                   (0.95, 0.02, 0.65),
    "Max Muncy":                    (1.10, 0.03, 0.67),
    "Teoscar Hernandez":            (1.00, 0.10, 0.79),
    "James Outman":                 (0.90, 0.12, 0.80),
    "Tommy Edman":                  (1.05, 0.18, 0.83),
    "Miguel Rojas":                 (0.85, 0.06, 0.74),
    # MIA
    "Bryan De La Cruz":             (0.85, 0.06, 0.74),
    "Jake Burger":                  (0.85, 0.01, 0.60),
    "Nick Gordon":                  (0.85, 0.14, 0.80),
    "Jesus Sanchez":                (0.85, 0.08, 0.75),
    "Nick Fortes":                  (0.65, 0.03, 0.68),
    "Griffin Conine":               (0.80, 0.04, 0.70),
    "Jon Berti":                    (0.85, 0.22, 0.84),
    "Dane Myers":                   (0.80, 0.10, 0.78),
    "Xavier Edwards":               (0.90, 0.16, 0.82),
    # MIL
    "Christian Yelich":             (1.10, 0.10, 0.79),
    "Willy Adames":                 (1.05, 0.10, 0.78),
    "William Contreras":            (0.90, 0.04, 0.70),
    "Joey Wiemer":                  (0.85, 0.12, 0.80),
    "Jackson Chourio":              (0.95, 0.20, 0.83),
    "Brice Turang":                 (0.90, 0.16, 0.82),
    "Rhys Hoskins":                 (1.00, 0.02, 0.65),
    "Sal Frelick":                  (0.90, 0.12, 0.80),
    "Jake Bauers":                  (0.80, 0.04, 0.70),
    # MIN
    "Carlos Correa":                (1.10, 0.04, 0.72),
    "Byron Buxton":                 (1.00, 0.22, 0.85),
    "Ryan Jeffers":                 (0.80, 0.01, 0.60),
    "Max Kepler":                   (0.95, 0.06, 0.74),
    "Royce Lewis":                  (1.00, 0.14, 0.82),
    "Matt Wallner":                 (0.85, 0.06, 0.73),
    "Edouard Julien":               (1.00, 0.10, 0.79),
    "Jose Miranda":                 (0.85, 0.02, 0.65),
    "Kyle Farmer":                  (0.80, 0.03, 0.68),
    # NYM
    "Francisco Lindor":             (1.15, 0.14, 0.82),
    "Pete Alonso":                  (1.05, 0.01, 0.60),
    "Starling Marte":               (1.05, 0.22, 0.84),
    "Brandon Nimmo":                (1.10, 0.06, 0.74),
    "Jeff McNeil":                  (1.05, 0.08, 0.77),
    "Mark Vientos":                 (0.90, 0.04, 0.70),
    "Francisco Alvarez":            (0.85, 0.04, 0.70),
    "Harrison Bader":               (0.90, 0.14, 0.82),
    "Omar Narvaez":                 (0.75, 0.01, 0.60),
    # NYY
    "Aaron Judge":                  (1.30, 0.02, 0.75),
    "Juan Soto":                    (1.30, 0.10, 0.79),
    "Gleyber Torres":               (1.00, 0.06, 0.74),
    "Anthony Volpe":                (1.00, 0.18, 0.83),
    "Jazz Chisholm Jr.":            (1.05, 0.22, 0.84),
    "Austin Wells":                 (0.85, 0.04, 0.70),
    "DJ LeMahieu":                  (0.90, 0.02, 0.65),
    "Giancarlo Stanton":            (0.95, 0.01, 0.60),
    "Alex Verdugo":                 (0.90, 0.08, 0.76),
    # OAK
    "Brent Rooker":                 (0.95, 0.04, 0.70),
    "Tyler Soderstrom":             (0.85, 0.04, 0.70),
    "Lawrence Butler":              (0.85, 0.14, 0.81),
    "Shea Langeliers":              (0.75, 0.03, 0.68),
    "Zack Gelof":                   (0.90, 0.10, 0.79),
    "JJ Bleday":                    (0.85, 0.06, 0.74),
    "Esteury Ruiz":                 (0.90, 0.28, 0.83),
    "Ryan Noda":                    (0.95, 0.06, 0.74),
    "Nick Allen":                   (0.80, 0.10, 0.78),
    # PHI
    "Trea Turner":                  (1.15, 0.19, 0.83),
    "Bryce Harper":                 (1.25, 0.04, 0.72),
    "Kyle Schwarber":               (1.10, 0.02, 0.65),
    "Alec Bohm":                    (1.00, 0.04, 0.70),
    "JT Realmuto":                  (0.90, 0.10, 0.79),
    "Nick Castellanos":             (0.95, 0.04, 0.70),
    "Johan Rojas":                  (0.85, 0.22, 0.85),
    "Bryson Stott":                 (0.95, 0.06, 0.74),
    "Brandon Marsh":                (0.95, 0.08, 0.76),
    # PIT
    "Bryan Reynolds":               (1.05, 0.10, 0.79),
    "Oneil Cruz":                   (1.00, 0.18, 0.83),
    "Andrew McCutchen":             (0.90, 0.06, 0.73),
    "Ji Hwan Bae":                  (0.85, 0.22, 0.84),
    "Connor Joe":                   (0.85, 0.06, 0.74),
    "Henry Davis":                  (0.80, 0.08, 0.76),
    "Liover Peguero":               (0.85, 0.14, 0.81),
    "Jack Suwinski":                (0.85, 0.04, 0.70),
    "Rowdy Tellez":                 (0.85, 0.01, 0.60),
    # SD
    "Fernando Tatis Jr.":           (1.15, 0.20, 0.84),
    "Ha-Seong Kim":                 (1.05, 0.18, 0.83),
    "Jurickson Profar":             (1.05, 0.08, 0.77),
    "Xander Bogaerts":              (1.05, 0.04, 0.70),
    "Jake Cronenworth":             (0.95, 0.06, 0.74),
    "Kyle Higashioka":              (0.70, 0.02, 0.65),
    "Luis Campusano":               (0.75, 0.04, 0.70),
    "Jackson Merrill":              (0.90, 0.12, 0.80),
    "Matthew Batten":               (0.80, 0.10, 0.78),
    # SEA
    "Julio Rodriguez":              (1.05, 0.20, 0.84),
    "Cal Raleigh":                  (0.90, 0.02, 0.65),
    "Ty France":                    (0.95, 0.02, 0.65),
    "Victor Robles":                (0.85, 0.16, 0.82),
    "Josh Rojas":                   (0.90, 0.12, 0.80),
    "Dylan Moore":                  (0.80, 0.14, 0.80),
    "Tom Murphy":                   (0.65, 0.02, 0.65),
    "AJ Pollock":                   (0.80, 0.06, 0.73),
    "Jesse Winker":                 (0.95, 0.04, 0.70),
    # SF
    "Michael Conforto":             (0.95, 0.06, 0.74),
    "Heliot Ramos":                 (0.90, 0.12, 0.80),
    "LaMonte Wade Jr.":             (1.00, 0.06, 0.74),
    "Casey Schmitt":                (0.80, 0.06, 0.74),
    "Wilmer Flores":                (0.85, 0.01, 0.60),
    "Marco Luciano":                (0.85, 0.10, 0.78),
    "Patrick Bailey":               (0.70, 0.03, 0.68),
    "Tyler Fitzgerald":             (0.85, 0.14, 0.82),
    "Jorge Soler":                  (0.95, 0.04, 0.70),
    # STL
    "Paul Goldschmidt":             (1.10, 0.02, 0.67),
    "Nolan Arenado":                (1.05, 0.02, 0.67),
    "Lars Nootbaar":                (1.00, 0.10, 0.79),
    "Masyn Winn":                   (0.95, 0.18, 0.83),
    "Brendan Donovan":              (1.00, 0.06, 0.74),
    "Jordan Walker":                (0.90, 0.10, 0.78),
    "Willson Contreras":            (0.85, 0.04, 0.70),
    "Tommy Edman":                  (1.05, 0.18, 0.83),
    "Dylan Carlson":                (0.85, 0.06, 0.74),
    # TB
    "Randy Arozarena":              (1.00, 0.18, 0.83),
    "Yandy Diaz":                   (1.10, 0.02, 0.65),
    "Jose Caballero":               (0.90, 0.25, 0.85),
    "Isaac Paredes":                (0.95, 0.02, 0.65),
    "Harold Ramirez":               (0.85, 0.04, 0.70),
    "Josh Lowe":                    (0.90, 0.14, 0.81),
    "Taylor Walls":                 (0.80, 0.10, 0.78),
    "Ben Rortvedt":                 (0.65, 0.03, 0.68),
    "Richie Palacios":              (0.85, 0.12, 0.80),
    # TEX
    "Marcus Semien":                (1.10, 0.08, 0.77),
    "Corey Seager":                 (1.15, 0.02, 0.67),
    "Jonah Heim":                   (0.75, 0.02, 0.65),
    "Josh Jung":                    (0.95, 0.04, 0.70),
    "Nathaniel Lowe":               (1.00, 0.02, 0.65),
    "Evan Carter":                  (0.95, 0.14, 0.82),
    "Leody Taveras":                (0.85, 0.16, 0.82),
    "Adolis Garcia":                (0.90, 0.08, 0.76),
    "Travis Jankowski":             (0.80, 0.18, 0.84),
    # TOR
    "Vladimir Guerrero Jr.":        (1.10, 0.02, 0.65),
    "Bo Bichette":                  (1.05, 0.10, 0.79),
    "George Springer":              (1.00, 0.10, 0.79),
    "Daulton Varsho":               (0.95, 0.12, 0.80),
    "Danny Jansen":                 (0.75, 0.02, 0.65),
    "Kevin Kiermaier":              (0.85, 0.12, 0.80),
    "Alejandro Kirk":               (0.85, 0.01, 0.60),
    "Ernie Clement":                (0.80, 0.08, 0.76),
    "Whit Merrifield":              (0.90, 0.10, 0.78),
    # WSH
    "CJ Abrams":                    (1.05, 0.27, 0.79),
    "Joey Meneses":                 (0.90, 0.02, 0.65),
    "Lane Thomas":                  (0.90, 0.14, 0.81),
    "Luis Garcia Jr.":              (0.85, 0.14, 0.81),
    "Michael Chavis":               (0.75, 0.04, 0.70),
    "Alex Call":                    (0.85, 0.12, 0.80),
    "Keibert Ruiz":                 (0.80, 0.02, 0.65),
    "Stone Garrett":                (0.80, 0.06, 0.74),
    "Jacob Young":                  (0.85, 0.22, 0.84),
}

# ─────────────────────────────────────────────────────────────────────────────
# PITCHER_PIF — pitcher influence factor
# LHP base 0.88 (runner sees delivery), RHP base 1.00
# Adjusted for delivery speed and known SB tendencies
# ─────────────────────────────────────────────────────────────────────────────
PITCHER_PIF = {
    # ARI
    "Zac Gallen":           0.98,
    "Merrill Kelly":        1.02,
    "Eduardo Rodriguez":    0.91,
    "Ryne Nelson":          1.02,
    "Brandon Pfaadt":       1.00,
    "Corbin Burnes":        0.96,
    # ATL
    "Spencer Strider":      0.95,
    "Max Fried":            0.90,
    "Charlie Morton":       1.05,
    "Chris Sale":           0.92,
    "Reynaldo Lopez":       1.00,
    "AJ Smith-Shawver":     1.00,
    # BAL
    "Grayson Rodriguez":    1.00,
    "Kyle Bradish":         1.00,
    "Dean Kremer":          1.00,
    "Cole Irvin":           0.93,
    "Trevor Rogers":        0.91,
    "Albert Suarez":        1.02,
    # BOS
    "Brayan Bello":         1.02,
    "Tanner Houck":         1.02,
    "Nick Pivetta":         1.04,
    "Kutter Crawford":      1.00,
    "James Paxton":         0.90,
    # CHC
    "Justin Steele":        0.91,
    "Kyle Hendricks":       1.06,
    "Marcus Stroman":       1.02,
    "Jameson Taillon":      1.00,
    "Jordan Wicks":         0.92,
    "Javier Assad":         1.00,
    # CWS
    "Garrett Crochet":      0.90,
    "Erick Fedde":          1.04,
    "Touki Toussaint":      1.04,
    "Nick Nastrini":        1.00,
    "Davis Martin":         1.00,
    # CIN
    "Hunter Greene":        0.93,
    "Nick Lodolo":          0.89,
    "Graham Ashcraft":      1.02,
    "Andrew Abbott":        0.90,
    "Luke Weaver":          1.00,
    # CLE
    "Shane Bieber":         0.98,
    "Tanner Bibee":         1.00,
    "Logan Allen":          0.91,
    "Ben Lively":           1.02,
    "Gavin Williams":       1.00,
    "Carlos Carrasco":      1.04,
    # COL
    "Kyle Freeland":        0.92,
    "Austin Gomber":        0.93,
    "Cal Quantrill":        1.02,
    "German Marquez":       1.04,
    "Dakota Hudson":        1.04,
    # DET
    "Tarik Skubal":         0.84,
    "Casey Mize":           1.00,
    "Reese Olson":          1.00,
    "Beau Brieske":         1.02,
    "Matt Manning":         1.00,
    # HOU
    "Framber Valdez":       1.04,  # LHP but notorious slow delivery
    "Cristian Javier":      1.00,
    "Hunter Brown":         1.00,
    "Ronel Blanco":         1.00,
    "JP France":            1.02,
    # KC
    "Cole Ragans":          0.90,
    "Brady Singer":         1.00,
    "Seth Lugo":            1.00,
    "Michael Wacha":        1.02,
    "Kris Bubic":           0.91,
    # LAA
    "Patrick Sandoval":     0.90,
    "Tyler Anderson":       0.91,
    "Reid Detmers":         0.90,
    "Jose Soriano":         1.00,
    "Griffin Canning":      1.00,
    # LAD
    "Yoshinobu Yamamoto":   0.92,
    "Tyler Glasnow":        0.98,
    "Clayton Kershaw":      0.89,
    "Bobby Miller":         1.00,
    "Gavin Stone":          1.00,
    # MIA
    "Sandy Alcantara":      1.14,  # RHP, notoriously slow to plate
    "Jesus Luzardo":        0.90,
    "Braxton Garrett":      0.91,
    "Edward Cabrera":       1.02,
    "AJ Puk":               0.90,
    # MIL
    "Freddy Peralta":       0.95,
    "Wade Miley":           0.91,
    "Colin Rea":            1.02,
    "Tobias Myers":         1.00,
    "Aaron Civale":         1.02,
    "DL Hall":              0.90,
    # MIN
    "Pablo Lopez":          0.98,
    "Joe Ryan":             0.96,
    "Bailey Ober":          1.02,
    "Sonny Gray":           0.98,
    "Chris Paddack":        1.00,
    "Louie Varland":        1.00,
    # NYM
    "Justin Verlander":     1.02,
    "Kodai Senga":          0.98,
    "Jose Quintana":        0.90,
    "Sean Manaea":          0.91,
    "David Peterson":       0.90,
    "Adrian Houser":        1.04,
    # NYY
    "Gerrit Cole":          0.94,
    "Carlos Rodon":         0.89,
    "Nestor Cortes":        0.90,
    "Clarke Schmidt":       1.00,
    "Luis Gil":             1.00,
    # OAK
    "JP Sears":             0.90,
    "Mitch Spence":         1.00,
    "Joey Estes":           1.02,
    "Ross Stripling":       1.02,
    "Paul Blackburn":       1.00,
    # PHI
    "Zack Wheeler":         0.94,
    "Aaron Nola":           0.98,
    "Ranger Suarez":        0.91,
    "Cristopher Sanchez":   0.91,
    "Taijuan Walker":       1.02,
    # PIT
    "Mitch Keller":         1.00,
    "Marco Gonzales":       0.91,
    "Johan Oviedo":         1.02,
    "Jared Jones":          1.00,
    "Quinn Priester":       1.00,
    # SD
    "Yu Darvish":           1.10,  # deliberate, lots of SB allowed
    "Joe Musgrove":         0.98,
    "Dylan Cease":          1.00,
    "Michael King":         1.00,
    "Randy Vasquez":        1.00,
    # SEA
    "Logan Gilbert":        0.98,
    "Luis Castillo":        1.08,  # slow windup, high SB% against
    "George Kirby":         0.96,
    "Bryan Woo":            1.00,
    "Emerson Hancock":      1.00,
    # SF
    "Logan Webb":           0.88,  # elite pickoff, quick delivery
    "Blake Snell":          0.92,
    "Jordan Hicks":         1.02,
    "Alex Cobb":            1.04,
    "Kyle Harrison":        0.91,
    "Robbie Ray":           0.90,
    # STL
    "Miles Mikolas":        1.04,
    "Steven Matz":          0.91,
    "Andre Pallante":       1.02,
    "Matthew Liberatore":   0.91,
    "Michael McGreevy":     1.00,
    "Lance Lynn":           1.04,
    # TB
    "Zach Eflin":           1.00,
    "Shane McClanahan":     0.89,
    "Jeffrey Springs":      0.90,
    "Ryan Pepiot":          1.00,
    "Taj Bradley":          1.00,
    # TEX
    "Nathan Eovaldi":       1.00,
    "Andrew Heaney":        0.90,
    "Jon Gray":             1.04,
    "Dane Dunning":         1.02,
    "Kumar Rocker":         1.00,
    # TOR
    "Kevin Gausman":        0.95,
    "Jose Berrios":         1.00,
    "Chris Bassitt":        1.02,
    "Yusei Kikuchi":        0.90,
    "Alek Manoah":          1.00,
    # WSH
    "MacKenzie Gore":       0.90,
    "Patrick Corbin":       1.06,  # LHP but very slow delivery
    "Trevor Williams":      1.04,
    "Jake Irvin":           1.02,
    "DJ Herz":              0.90,
    "Josiah Gray":          1.02,
}

# ─────────────────────────────────────────────────────────────────────────────
# CATCHER_CIF — catcher influence factor
# 1.00 = league avg (2.0s pop time, 28% CS%)
# < 1.00 = elite arm (harder to steal), > 1.00 = weak arm
# ─────────────────────────────────────────────────────────────────────────────
CATCHER_CIF = {
    "Patrick Bailey":       0.78,   # SF — elite, led NL in CS% 2024
    "Jose Trevino":         0.85,   # NYY — quick release
    "Austin Hedges":        0.82,   # journeyman — renowned defensive C
    "Adley Rutschman":      0.88,   # BAL — very good arm
    "Gabriel Moreno":       0.90,   # ARI — excellent
    "Bo Naylor":            0.92,   # CLE
    "Sean Murphy":          0.92,   # ATL
    "Logan O'Hoppe":        0.95,   # LAA
    "Ryan Jeffers":         0.95,   # MIN
    "Jonah Heim":           0.95,   # TEX
    "Jake Rogers":          0.97,   # DET
    "Henry Davis":          0.98,   # PIT
    "JT Realmuto":          0.97,   # PHI
    "Willson Contreras":    0.98,   # STL
    "Kyle Higashioka":      0.93,   # SD — good arm
    "Francisco Alvarez":    1.00,   # NYM
    "Salvador Perez":       1.02,   # KC
    "Yainer Diaz":          1.00,   # HOU
    "William Contreras":    1.02,   # MIL
    "Danny Jansen":         1.02,   # TOR
    "Alejandro Kirk":       1.05,   # TOR
    "Connor Wong":          1.02,   # BOS
    "Luis Campusano":       1.05,   # SD
    "Tyler Stephenson":     1.08,   # CIN
    "Austin Wells":         1.02,   # NYY
    "Cal Raleigh":          1.05,   # SEA
    "Will Smith":           1.08,   # LAD
    "Elias Diaz":           1.05,   # COL
    "Nick Fortes":          1.05,   # MIA
    "Keibert Ruiz":         1.02,   # WSH
    "Shea Langeliers":      1.00,   # OAK
    "Ben Rortvedt":         1.00,   # TB
    "Seby Zavala":          1.00,   # CWS
    "Korey Lee":            1.00,   # CWS
    "Miguel Amaya":         1.02,   # CHC
    "Travis d'Arnaud":      1.00,   # ATL backup
    "Omar Narvaez":         1.12,   # NYM
    "Tom Murphy":           1.00,   # SEA backup
    "Jason Delay":          1.00,   # PIT backup
    "Freddy Fermin":        1.00,   # KC backup
}

# Fallback primary catcher per team ID (used when no lineup posted)
TEAM_CATCHERS = {
    109: "Gabriel Moreno",    # ARI
    144: "Sean Murphy",       # ATL
    110: "Adley Rutschman",   # BAL
    111: "Connor Wong",       # BOS
    112: "Miguel Amaya",      # CHC
    145: "Korey Lee",         # CWS
    113: "Tyler Stephenson",  # CIN
    114: "Bo Naylor",         # CLE
    115: "Elias Diaz",        # COL
    116: "Jake Rogers",       # DET
    117: "Yainer Diaz",       # HOU
    118: "Salvador Perez",    # KC
    108: "Logan O'Hoppe",     # LAA
    119: "Will Smith",        # LAD
    146: "Nick Fortes",       # MIA
    158: "William Contreras", # MIL
    142: "Ryan Jeffers",      # MIN
    121: "Francisco Alvarez", # NYM
    147: "Austin Wells",      # NYY
    133: "Shea Langeliers",   # OAK
    143: "JT Realmuto",       # PHI
    134: "Henry Davis",       # PIT
    135: "Kyle Higashioka",   # SD
    136: "Cal Raleigh",       # SEA
    137: "Patrick Bailey",    # SF
    138: "Willson Contreras", # STL
    139: "Ben Rortvedt",      # TB
    140: "Jonah Heim",        # TEX
    141: "Danny Jansen",      # TOR
    120: "Keibert Ruiz",      # WSH
}

DEFAULT_BATTER = (0.85, 0.05, 0.72)
DEFAULT_PIF    = 1.00
DEFAULT_CIF    = 1.00


# ─────────────────────────────────────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────────────────────────────────────

def calc_psb(batter: str, pitcher: str, catcher: str) -> tuple[float, str]:
    """Return (pSB as 0-1 float, fair American odds string)."""
    pos, par, bsr = BATTER_PROFILES.get(batter, DEFAULT_BATTER)
    pif = PITCHER_PIF.get(pitcher, DEFAULT_PIF)
    cif = CATCHER_CIF.get(catcher, DEFAULT_CIF)
    lam = pos * par * bsr * pif * cif
    p = 1.0 - math.exp(-lam)
    if p <= 0:
        odds = "N/A"
    elif p >= 0.5:
        odds = f"-{round(p / (1 - p) * 100)}"
    else:
        odds = f"+{round((1 - p) / p * 100)}"
    return p, odds


# ─────────────────────────────────────────────────────────────────────────────
# MLB Stats API helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_schedule(date_str: str) -> list[dict]:
    """Return list of game dicts for date_str (YYYY-MM-DD)."""
    mm_dd_yyyy = datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%m/%d/%Y")
    data = _get(f"{MLB}/schedule", {
        "sportId": 1,
        "date": mm_dd_yyyy,
        "hydrate": "probablePitcher,lineups",
        "gameType": "R",
    })
    games = []
    for date_block in data.get("dates", []):
        for g in date_block.get("games", []):
            games.append(g)
    return games


def parse_game_time(game_date: str) -> str:
    """Convert ISO UTC string to 'H:MM AM/PM ET'."""
    try:
        dt = datetime.datetime.fromisoformat(game_date.replace("Z", "+00:00"))
        dt_et = dt.astimezone(ET)
        return dt_et.strftime("%-I:%M %p ET")
    except Exception:
        return "TBD"


def fetch_lineup(game_pk: int) -> tuple[list, list]:
    """Try /game/{gamePk}/lineups; return (away_starters, home_starters).
    Each starter is a dict with 'fullName' and 'primaryPosition'."""
    try:
        data = _get(f"{MLB}/game/{game_pk}/lineups")
        away = data.get("awayStarters", [])
        home = data.get("homeStarters", [])
        if away or home:
            return away, home
    except Exception:
        pass
    return [], []


def fetch_roster_batters(team_id: int) -> list[dict]:
    """Fetch active roster and return non-pitcher position players."""
    try:
        data = _get(f"{MLB}/teams/{team_id}/roster", {"rosterType": "active"})
        players = []
        for p in data.get("roster", []):
            pos = p.get("position", {}).get("abbreviation", "")
            if pos != "P":
                players.append({
                    "fullName": p["person"]["fullName"],
                    "primaryPosition": {"abbreviation": pos},
                })
        return players
    except Exception:
        return []


def find_catcher_in_lineup(lineup: list[dict], team_id: int) -> str:
    """Return catcher name from lineup list, or fall back to TEAM_CATCHERS."""
    for p in lineup:
        if p.get("primaryPosition", {}).get("abbreviation") == "C":
            return p["fullName"]
    return TEAM_CATCHERS.get(team_id, "Unknown Catcher")


def build_game_data(games: list[dict]) -> list[dict]:
    """Enrich raw schedule games with lineups and pSB calculations."""
    results = []
    for g in games:
        gk = g["gamePk"]
        game_date = g.get("gameDate", "")
        time_str = parse_game_time(game_date)

        away_info = g["teams"]["away"]
        home_info = g["teams"]["home"]
        away_team = away_info["team"]["name"]
        home_team = home_info["team"]["name"]
        away_id   = away_info["team"]["id"]
        home_id   = home_info["team"]["id"]

        away_pitcher = (away_info.get("probablePitcher") or {}).get("fullName", "TBD")
        home_pitcher = (home_info.get("probablePitcher") or {}).get("fullName", "TBD")

        # Try lineups from schedule hydrate first, then dedicated endpoint
        sched_lineups = g.get("lineups", {})
        away_starters = sched_lineups.get("awayStarters", [])
        home_starters = sched_lineups.get("homeStarters", [])
        if not away_starters and not home_starters:
            away_starters, home_starters = fetch_lineup(gk)
        lineup_confirmed = bool(away_starters or home_starters)

        if not away_starters:
            away_starters = fetch_roster_batters(away_id)[:9]
        if not home_starters:
            home_starters = fetch_roster_batters(home_id)[:9]

        away_catcher = find_catcher_in_lineup(away_starters, away_id)
        home_catcher = find_catcher_in_lineup(home_starters, home_id)

        # away batters face home pitcher + home catcher
        away_rows = []
        for i, p in enumerate(away_starters, 1):
            name = p["fullName"]
            pos  = p.get("primaryPosition", {}).get("abbreviation", "—")
            psb, odds = calc_psb(name, home_pitcher, home_catcher)
            away_rows.append((i, name, pos, psb, odds))

        # home batters face away pitcher + away catcher
        home_rows = []
        for i, p in enumerate(home_starters, 1):
            name = p["fullName"]
            pos  = p.get("primaryPosition", {}).get("abbreviation", "—")
            psb, odds = calc_psb(name, away_pitcher, away_catcher)
            home_rows.append((i, name, pos, psb, odds))

        results.append({
            "matchup":         f"{away_team} @ {home_team}",
            "time":            time_str,
            "away_team":       away_team,
            "home_team":       home_team,
            "away_pitcher":    away_pitcher,
            "home_pitcher":    home_pitcher,
            "away_catcher":    away_catcher,
            "home_catcher":    home_catcher,
            "away_pif":        PITCHER_PIF.get(away_pitcher, DEFAULT_PIF),
            "home_pif":        PITCHER_PIF.get(home_pitcher, DEFAULT_PIF),
            "away_cif":        CATCHER_CIF.get(away_catcher, DEFAULT_CIF),
            "home_cif":        CATCHER_CIF.get(home_catcher, DEFAULT_CIF),
            "away_rows":       away_rows,
            "home_rows":       home_rows,
            "lineup_confirmed": lineup_confirmed,
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# HTML generation (inline CSS only — Gmail compatible)
# ─────────────────────────────────────────────────────────────────────────────

def psb_bg(p: float) -> str:
    if p >= 0.20:
        return "#c0392b"   # red
    if p >= 0.10:
        return "#e67e22"   # amber
    return "#7f8c8d"       # gray


def odds_color(odds: str) -> str:
    return "#27ae60" if odds.startswith("+") else "#e74c3c"


def batter_table_html(rows: list, title: str, opp_pitcher: str, opp_catcher: str,
                       opp_pif: float, opp_cif: float) -> str:
    S = {
        "wrap": "width:100%;",
        "info": ("padding:6px 10px;background:#eaf0fb;border-radius:4px;"
                 "font-size:11px;color:#555;font-family:Arial,sans-serif;"
                 "margin-bottom:6px;line-height:1.6;"),
        "label": "font-weight:bold;color:#2c3e50;",
        "tbl":   "width:100%;border-collapse:collapse;font-size:12px;font-family:Arial,sans-serif;",
        "th":    ("padding:6px 8px;background:#2c3e50;color:#fff;"
                  "text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.5px;"),
        "th_c":  ("padding:6px 8px;background:#2c3e50;color:#fff;"
                  "text-align:center;font-size:11px;text-transform:uppercase;letter-spacing:.5px;"),
        "td":    "padding:5px 8px;border-bottom:1px solid #ecf0f1;color:#333;",
        "td_c":  "padding:5px 8px;border-bottom:1px solid #ecf0f1;text-align:center;color:#333;",
        "num":   "padding:5px 8px;border-bottom:1px solid #ecf0f1;color:#aaa;width:20px;",
    }
    hand = "LHP" if PITCHER_PIF.get(opp_pitcher, 1.0) < 0.95 and opp_pitcher != "TBD" else "RHP"
    # simple handedness guess from PIF
    pif_val = PITCHER_PIF.get(opp_pitcher, DEFAULT_PIF)
    hand = "LHP" if pif_val <= 0.93 else "RHP"

    info = (
        f'<div style="{S["info"]}">'
        f'<span style="{S["label"]}">vs. P:</span> {opp_pitcher} '
        f'&nbsp;·&nbsp; PIF {pif_val:.2f}'
        f'&nbsp;&nbsp;|&nbsp;&nbsp;'
        f'<span style="{S["label"]}">vs. C:</span> {opp_catcher} '
        f'&nbsp;·&nbsp; CIF {opp_cif:.2f}'
        f'</div>'
    )

    header = (
        f'<tr>'
        f'<th style="{S["th"]}">#</th>'
        f'<th style="{S["th"]}">Batter</th>'
        f'<th style="{S["th_c"]}">Pos</th>'
        f'<th style="{S["th_c"]}">pSB%</th>'
        f'<th style="{S["th_c"]}">Fair odds</th>'
        f'</tr>'
    )

    body_rows = []
    for (num, name, pos, psb, fair_odds) in rows:
        bg = psb_bg(psb)
        oc = odds_color(fair_odds)
        psb_cell = (
            f'<td style="padding:5px 8px;border-bottom:1px solid #ecf0f1;'
            f'text-align:center;background:{bg};color:#fff;font-weight:bold;">'
            f'{psb*100:.1f}%</td>'
        )
        body_rows.append(
            f'<tr>'
            f'<td style="{S["num"]}">{num}</td>'
            f'<td style="{S["td"]}">{name}</td>'
            f'<td style="{S["td_c"]}">{pos}</td>'
            f'{psb_cell}'
            f'<td style="{S["td_c"]};color:{oc};font-weight:bold;">{fair_odds}</td>'
            f'</tr>'
        )

    return (
        f'<div style="{S["wrap"]}">'
        f'<div style="padding:6px 0;font-size:13px;font-weight:bold;color:#2c3e50;'
        f'font-family:Arial,sans-serif;">{title}</div>'
        f'{info}'
        f'<table style="{S["tbl"]}">'
        f'{header}'
        f'{"".join(body_rows)}'
        f'</table>'
        f'</div>'
    )


def build_html_email(games_data: list[dict], date_str: str) -> str:
    today = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    date_display = today.strftime("%A, %B %-d, %Y")
    n = len(games_data)

    sections = []
    for gd in games_data:
        confirmed_note = "" if gd["lineup_confirmed"] else (
            ' <span style="font-size:10px;color:#f39c12;">(projected)</span>'
        )
        heading = (
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td style="padding:14px 20px;background:#16213e;'
            f'border-radius:6px 6px 0 0;">'
            f'<span style="font-size:15px;font-weight:bold;color:#fff;'
            f'font-family:Arial,sans-serif;">'
            f'&#9918; {gd["matchup"]} &mdash; {gd["time"]}{confirmed_note}'
            f'</span></td></tr></table>'
        )

        away_tbl = batter_table_html(
            gd["away_rows"],
            f'{gd["away_team"]} Batters',
            gd["home_pitcher"], gd["home_catcher"],
            gd["home_pif"], gd["home_cif"],
        )
        home_tbl = batter_table_html(
            gd["home_rows"],
            f'{gd["home_team"]} Batters',
            gd["away_pitcher"], gd["away_catcher"],
            gd["away_pif"], gd["away_cif"],
        )

        side_by_side = (
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>'
            f'<td width="50%" valign="top" style="padding:12px 8px 16px 16px;">{away_tbl}</td>'
            f'<td width="50%" valign="top" style="padding:12px 16px 16px 8px;">{home_tbl}</td>'
            f'</tr></table>'
        )

        sections.append(
            f'<div style="background:#fff;border-radius:6px;margin-bottom:20px;'
            f'border:1px solid #dde3ec;overflow:hidden;">'
            f'{heading}{side_by_side}'
            f'</div>'
        )

    legend = (
        '<table cellpadding="0" cellspacing="0" style="margin-bottom:16px;">'
        '<tr>'
        '<td style="padding:4px 10px 4px 0;font-size:11px;font-family:Arial,sans-serif;color:#555;">'
        'pSB colour key:</td>'
        '<td style="padding:3px 8px;background:#c0392b;color:#fff;font-size:11px;'
        'font-family:Arial,sans-serif;border-radius:3px;margin-right:6px;">&#8805;20% Red</td>'
        '<td style="padding:3px 8px;"></td>'
        '<td style="padding:3px 8px;background:#e67e22;color:#fff;font-size:11px;'
        'font-family:Arial,sans-serif;border-radius:3px;">10–19% Amber</td>'
        '<td style="padding:3px 8px;"></td>'
        '<td style="padding:3px 8px;background:#7f8c8d;color:#fff;font-size:11px;'
        'font-family:Arial,sans-serif;border-radius:3px;">&lt;10% Gray</td>'
        '</tr></table>'
    )

    footer = (
        '<table width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td style="padding:16px;text-align:center;font-size:11px;'
        'color:#aaa;font-family:Arial,sans-serif;border-top:1px solid #eee;">'
        'Model estimates only. Not financial advice. Gamble responsibly.'
        '</td></tr></table>'
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;background:#f0f4f8;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0">

<!-- Header -->
<tr><td style="padding-bottom:20px;">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td style="padding:22px 24px;background:#1a1a2e;border-radius:8px;text-align:center;">
<div style="font-size:26px;font-weight:bold;color:#fff;font-family:Arial,sans-serif;">
&#9918; pSB Daily Report
</div>
<div style="font-size:13px;color:#8899bb;margin-top:6px;font-family:Arial,sans-serif;">
{date_display} &nbsp;&middot;&nbsp; {n} game{"s" if n != 1 else ""} today
</div>
</td></tr></table>
</td></tr>

<!-- Legend -->
<tr><td style="padding-bottom:4px;">{legend}</td></tr>

<!-- Game sections -->
<tr><td>{"".join(sections)}</td></tr>

<!-- Footer -->
<tr><td style="background:#fff;border-radius:6px;border:1px solid #dde3ec;">{footer}</td></tr>

</table>
</td></tr></table>
</body>
</html>"""
    return html


# ─────────────────────────────────────────────────────────────────────────────
# Gmail send
# ─────────────────────────────────────────────────────────────────────────────

def send_gmail(html: str, subject: str) -> None:
    addr = os.environ["GMAIL_ADDRESS"]
    pwd  = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = addr
    msg["To"]      = addr
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(addr, pwd)
        server.sendmail(addr, addr, msg.as_string())
    print(f"Email sent to {addr}")


# ─────────────────────────────────────────────────────────────────────────────
# Mock data for --preview when API unreachable
# ─────────────────────────────────────────────────────────────────────────────

MOCK_GAMES_DATA = [
    {
        "matchup": "New York Yankees @ Boston Red Sox",
        "time": "1:35 PM ET",
        "away_team": "New York Yankees",
        "home_team": "Boston Red Sox",
        "away_pitcher": "Gerrit Cole",
        "home_pitcher": "Brayan Bello",
        "away_catcher": "Austin Wells",
        "home_catcher": "Connor Wong",
        "away_pif": PITCHER_PIF.get("Gerrit Cole", 1.0),
        "home_pif": PITCHER_PIF.get("Brayan Bello", 1.0),
        "away_cif": CATCHER_CIF.get("Austin Wells", 1.0),
        "home_cif": CATCHER_CIF.get("Connor Wong", 1.0),
        "lineup_confirmed": True,
        "away_rows": None,   # computed below
        "home_rows": None,
    },
    {
        "matchup": "Cincinnati Reds @ Philadelphia Phillies",
        "time": "6:40 PM ET",
        "away_team": "Cincinnati Reds",
        "home_team": "Philadelphia Phillies",
        "away_pitcher": "Hunter Greene",
        "home_pitcher": "Zack Wheeler",
        "away_catcher": "Tyler Stephenson",
        "home_catcher": "JT Realmuto",
        "away_pif": PITCHER_PIF.get("Hunter Greene", 1.0),
        "home_pif": PITCHER_PIF.get("Zack Wheeler", 1.0),
        "away_cif": CATCHER_CIF.get("Tyler Stephenson", 1.0),
        "home_cif": CATCHER_CIF.get("JT Realmuto", 1.0),
        "lineup_confirmed": False,
        "away_rows": None,
        "home_rows": None,
    },
    {
        "matchup": "Los Angeles Dodgers @ San Francisco Giants",
        "time": "9:45 PM ET",
        "away_team": "Los Angeles Dodgers",
        "home_team": "San Francisco Giants",
        "away_pitcher": "Yoshinobu Yamamoto",
        "home_pitcher": "Logan Webb",
        "away_catcher": "Will Smith",
        "home_catcher": "Patrick Bailey",
        "away_pif": PITCHER_PIF.get("Yoshinobu Yamamoto", 1.0),
        "home_pif": PITCHER_PIF.get("Logan Webb", 1.0),
        "away_cif": CATCHER_CIF.get("Will Smith", 1.0),
        "home_cif": CATCHER_CIF.get("Patrick Bailey", 1.0),
        "lineup_confirmed": True,
        "away_rows": None,
        "home_rows": None,
    },
]

_MOCK_LINEUPS = {
    "New York Yankees": [
        ("Jazz Chisholm Jr.", "LF"), ("Anthony Volpe", "SS"), ("Aaron Judge", "CF"),
        ("Juan Soto", "RF"), ("Gleyber Torres", "2B"), ("Austin Wells", "C"),
        ("DJ LeMahieu", "3B"), ("Giancarlo Stanton", "DH"), ("Alex Verdugo", "1B"),
    ],
    "Boston Red Sox": [
        ("Jarren Duran", "CF"), ("Rafael Devers", "3B"), ("Wilyer Abreu", "RF"),
        ("Masataka Yoshida", "DH"), ("Triston Casas", "1B"), ("Ceddanne Rafaela", "SS"),
        ("Connor Wong", "C"), ("David Hamilton", "2B"), ("Rob Refsnyder", "LF"),
    ],
    "Cincinnati Reds": [
        ("Elly De La Cruz", "SS"), ("TJ Friedl", "CF"), ("Jonathan India", "2B"),
        ("Spencer Steer", "3B"), ("Jake Fraley", "LF"), ("Christian Encarnacion-Strand", "1B"),
        ("Tyler Stephenson", "C"), ("Will Benson", "RF"), ("Stuart Fairchild", "DH"),
    ],
    "Philadelphia Phillies": [
        ("Trea Turner", "SS"), ("Bryce Harper", "1B"), ("Kyle Schwarber", "LF"),
        ("Nick Castellanos", "RF"), ("Alec Bohm", "3B"), ("Brandon Marsh", "CF"),
        ("Bryson Stott", "2B"), ("JT Realmuto", "C"), ("Johan Rojas", "DH"),
    ],
    "Los Angeles Dodgers": [
        ("Mookie Betts", "RF"), ("Shohei Ohtani", "DH"), ("Freddie Freeman", "1B"),
        ("Will Smith", "C"), ("Teoscar Hernandez", "LF"), ("Tommy Edman", "2B"),
        ("Max Muncy", "3B"), ("James Outman", "CF"), ("Miguel Rojas", "SS"),
    ],
    "San Francisco Giants": [
        ("Heliot Ramos", "CF"), ("LaMonte Wade Jr.", "1B"), ("Michael Conforto", "LF"),
        ("Jorge Soler", "DH"), ("Tyler Fitzgerald", "SS"), ("Casey Schmitt", "3B"),
        ("Patrick Bailey", "C"), ("Marco Luciano", "2B"), ("Wilmer Flores", "RF"),
    ],
}


def build_mock_games_data() -> list[dict]:
    result = []
    for gd in MOCK_GAMES_DATA:
        away_lu = _MOCK_LINEUPS[gd["away_team"]]
        home_lu = _MOCK_LINEUPS[gd["home_team"]]
        away_rows = [
            (i+1, name, pos, *calc_psb(name, gd["home_pitcher"], gd["home_catcher"]))
            for i, (name, pos) in enumerate(away_lu)
        ]
        home_rows = [
            (i+1, name, pos, *calc_psb(name, gd["away_pitcher"], gd["away_catcher"]))
            for i, (name, pos) in enumerate(home_lu)
        ]
        result.append({**gd, "away_rows": away_rows, "home_rows": home_rows})
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="pSB Daily Report")
    parser.add_argument("--preview", action="store_true",
                        help="Save HTML to output/preview.html instead of emailing")
    parser.add_argument("--date", default=None,
                        help="Override date (YYYY-MM-DD); defaults to today ET")
    args = parser.parse_args()

    today_et = datetime.datetime.now(ET)
    date_str = args.date or today_et.strftime("%Y-%m-%d")

    print(f"pSB Report — {date_str}")

    # Fetch real data
    games_data = []
    try:
        raw_games = fetch_schedule(date_str)
        if raw_games:
            print(f"Fetched {len(raw_games)} games from MLB API.")
            games_data = build_game_data(raw_games)
        else:
            print("No games found for this date.")
    except Exception as e:
        print(f"API unavailable: {e}")
        if args.preview:
            print("Falling back to mock data for preview.")
            games_data = build_mock_games_data()
        else:
            sys.exit(1)

    if not games_data and args.preview:
        print("No live data; using mock data for preview.")
        games_data = build_mock_games_data()

    html = build_html_email(games_data, date_str)

    # Always save preview HTML
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    preview_path = out_dir / "preview.html"
    preview_path.write_text(html, encoding="utf-8")
    print(f"Preview saved → {preview_path}")

    if args.preview:
        print("Preview mode: skipping email send.")
        return

    n = len(games_data)
    today_display = datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %-d, %Y")
    subject = f"pSB Report — {today_display} · {n} game{'s' if n != 1 else ''} today"
    send_gmail(html, subject)


if __name__ == "__main__":
    main()
