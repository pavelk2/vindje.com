#!/usr/bin/env python3
"""
Overlooked finds for vindje.com (issue #50, pilot: lamps): second-hand items
whose listing doesn't name the brand, but whose photos look like a valuable
model. Sellers who don't know what they have tend to ask the least.

The valuable models, with typical resale and buy prices, come from
data/vintage_resale_icons.json. A category here only says which part of that
file to use and how to search for it, so adding one is data, not code.

Daily hunt: search Marktplaats in a seller's plain words ("lamp contragewicht"),
drop listings that already name a brand or designer, show the model up to 3
large photos plus the listing text with every name cut out, and keep the
listings it recognizes at or under the model's buy price. The record goes to
Redis as overlooked:latest, and /flip shows the strong matches under
"Overlooked" (?possible=1 also shows possible ones, for testing). In
production a step in .github/workflows/daily-deals.yml runs it every morning.

  python3 overlooked.py --dry-run         # hunt and print, save nothing
  python3 overlooked.py                   # hunt and save to Redis
  python3 overlooked.py --dry-run --category bags   # a category not in DAILY

Only the DAILY categories run by default. The others (bikes, chairs, jackets,
bags, boats) have test sets and run on request until their numbers hold up.

Accuracy test: the same recognition on listings whose title names the model,
so the answer is known but hidden. Listings that name the brand tend to be
written in a more expert style even with the names cut out, so --no-text
gives the cautious, photos-only number.

  python3 overlooked.py --collect lamps   # build data/overlooked_eval_lamps.json
  python3 overlooked.py --refresh lamps   # update photos and text of saved cases
  python3 overlooked.py --eval lamps      # ask the model, print the score
  python3 overlooked.py --eval lamps --no-text    # photos only
  python3 overlooked.py --eval lamps --limit 24   # cheap first look

Searches run one at a time with a pause in between. --eval only calls the LLM.
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from app import (FLIP_PAGES, MODELS, OPENROUTER_API_KEY, OVERLOOKED_KEY, llm_json,
                 search_marktplaats, upstash_command)
from deals import dedupe_relistings, is_auction_lot

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_FILE = os.path.join(HERE, "data", "vintage_resale_icons.json")

# ---------------------------------------------------------------- categories

# key -> which items in MODELS_FILE ("source") and which /flip page it feeds.
# The flip page supplies the plain Dutch search and Marktplaats category ids.
#   search:  what sellers type when a model's own name finds nothing
#   aliases: names sellers use instead of the brand ("Kaiser Idell", not
#            "Fritz Hansen"); they count as naming the brand
#   looks:   what each model looks like in a photo. The data file's
#            descriptions are about value, and the model needs shapes.
#   copied:  models so widely copied that a photo can't tell an original from
#            a copy; they're never a "strong" match, so never public
#   designers: names that also give the model away; cut from the listing text
#            the model sees, and a listing that names one is skipped
#   queries: the daily hunt's searches, in the words of a seller who doesn't
#            know the brand: by type, by era, and by what the item looks like
CATEGORIES = {
    "lamps": {
        "source": "Lamps", "flip": "lamps", "noun": "lamps",
        "clues": '"contragewicht", "opaline glas", "jaren 50", a stamp under the base',
        "parts": 'Loose shades and parts are "unknown".',
        "rule": "A different type of lamp (table, floor, wall, pendant) than the model is "
                "never that model.",
        "queries": ["vintage bureaulamp", "vintage vloerlamp", "vintage hanglamp",
                    "vintage wandlamp", "oude lamp", "retro lamp", "jaren 60 lamp",
                    "jaren 70 lamp", "lamp contragewicht", "glazen blokken lamp",
                    "opaline lamp", "industriele lamp scharnier", "lamp marmeren voet",
                    "paddenstoel lamp", "papieren lamp", "schalenlamp"],
        "designers": ["poul henningsen", "henningsen", "arne jacobsen", "jacobsen",
                      "verner panton", "panton", "verpan", "achille castiglioni",
                      "pier giacomo", "castiglioni", "vico magistretti", "magistretti",
                      "gae aulenti", "aulenti", "hoogervorst", "willem van oyen",
                      "van oyen", "christian dell", "isamu noguchi", "noguchi",
                      "mouille", "vitra"],
        "copied": ["Louis Poulsen PH5", "Flos Arco", "Louis Poulsen Panthella Floor",
                   "Noguchi Akari Floor (10A, UF4)", "Ingo Maurer Uchiwa",
                   "Serge Mouille Three-Arm Floor Lamp"],
        "looks": {
            "Louis Poulsen PH5": "pendant of three separate stacked curved shades with "
                "small inner reflectors, bulb hidden, flat and wide. Many Danish shell "
                "lamps and cheap copies look alike",
            "Louis Poulsen PH Artichoke": "pendant of many leaf-shaped metal blades in "
                "staggered rows, like an artichoke or pine cone",
            "Louis Poulsen PH 3/2 Table": "table lamp with three stacked opal or frosted "
                "glass shades on a curved stem and round base",
            "Louis Poulsen PH Snowball": "white ball-shaped pendant of eight stacked "
                "metal shades with open gaps between them",
            "Louis Poulsen AJ Floor": "slim floor lamp, tilted asymmetric cone shade on "
                "a thin straight stem, round base with a circular cut-out",
            "Louis Poulsen Panthella Floor": "mushroom floor lamp: wide dome shade on a "
                "trumpet-shaped stem that flares out to the floor",
            "Flos Arco": "huge steel arc reaching far out, dome reflector at the end, "
                "rectangular white marble block as the base",
            "Flos Taccia": "wide glass bowl resting on top of a ribbed cylindrical "
                "aluminium base, light shines up into the bowl",
            "Flos Snoopy": "table lamp: tilted enamel helmet-shaped shade on a round "
                "marble base, small glass disc on top, like a beagle's head",
            "Oluce Atollo 233": "table lamp of pure shapes: cylinder base, cone neck, "
                "half-sphere dome balanced on top",
            "Martinelli Luce Pipistrello": "table lamp with one white shade whose edge "
                "has four or five scalloped lobes like bat wings, on a telescopic "
                "stem and flared base",
            "Verner Panton VP Globe": "clear acrylic sphere pendant with coloured or "
                "metal reflector discs visible inside the clear ball",
            "Ingo Maurer Uchiwa": "rice paper stretched over radiating bamboo ribs, "
                "shaped like Japanese hand fans, often several together",
            "Raak Amsterdam Chartres": "ceiling or wall lamp built from thick chunky "
                "clear glass blocks set in a metal frame",
            "Anvia Counterbalance Lamp": "1950s Dutch wall, floor or ceiling lamp with "
                "a thin black or brass arm and a visible round counterweight at the "
                "other end of the arm; small cone shade",
            "Gispen Giso": "1930s lamp with a white opaline glass globe or shade on "
                "chrome or black tubular metal fittings",
            "Jielde Standard Floor Lamp": "French workshop lamp: thick enamelled metal "
                "tubes joined by round knuckle joints, conical metal shade, no "
                "counterweight and no visible wires, heavy round base",
            "Fritz Hansen Kaiser Idell 6631 Luxus": "Bauhaus desk lamp: conical "
                "metal shade on a short arm with a ball joint, round stepped base; "
                "no counterweight",
            "Noguchi Akari Floor (10A, UF4)": "white washi paper over thin bamboo or "
                "wire ribs, lantern or column shape, on thin metal legs",
            "Serge Mouille Three-Arm Floor Lamp": "black floor lamp with three long thin "
                "curved arms, each ending in a pointed, breast-shaped shade",
        },
        "search": {
            "Louis Poulsen PH 3/2 Table": "poulsen ph 3/2",
            "Louis Poulsen PH Snowball": "poulsen snowball",
            "Oluce Atollo 233": "atollo lamp",
            "Fritz Hansen Kaiser Idell 6631 Luxus": "kaiser idell",
            "Noguchi Akari Floor (10A, UF4)": "noguchi akari",
        },
        "aliases": {
            "Fritz Hansen Kaiser Idell 6631 Luxus": ["kaiser idell"],
            "Oluce Atollo 233": ["atollo"],
        },
    },
    "bikes": {
        "source": "Road Bikes", "flip": "bikes", "noun": "racing bikes",
        "clues": '"columbus", "reynolds 531", "campagnolo", "jaren 80", a sticker on '
                 'the frame',
        "parts": 'A bare frame still counts; loose forks, wheels and parts are "unknown".',
        "rule": "A modern, city, touring or mountain bike is never one of these models.",
        # "record" is Campagnolo's groupset, on every good bike: not Gios's name
        "generic": ["super", "sport", "team", "pro", "amsterdam", "built", "steel",
                    "record"],
        # Dutch "klein" is small, "look" is in "retro look"
        "brand_stop": ["klein", "look", "torino"],
        "aliases": {"Klein Quantum": ["klein quantum", "gary klein"],
                    "Look KG86": ["look kg86", "look kg 86"]},
        "designers": ["ernesto colnago", "ugo de rosa", "pinarello", "cino cinelli",
                      "eddy merckx", "merckx"],
        "copied": [],
        "queries": ["oude racefiets", "vintage racefiets", "retro racefiets",
                    "stalen racefiets", "racefiets jaren 80", "racefiets jaren 70",
                    "racefiets campagnolo", "racefiets columbus", "racefiets reynolds",
                    "koersfiets", "oude koersfiets", "italiaanse racefiets"],
        "looks": {
            "Colnago Master": "steel road frame with crimped, star-shaped tubes that show "
                "ridges along their length, clover cut-outs in the lugs, often loud "
                "Art Decor paint",
            "Colnago Arabesque": "lugged steel frame with very ornate engraved lugs in "
                "swirling patterns, often chrome plated",
            "Colnago C40": "1990s frame of black round carbon tubes joined by lugs, "
                "straight carbon fork, often Mapei multicolour cubes",
            "Colnago Super / Mexico": "1970s-80s lugged steel frame with thin round tubes, "
                "clover cut-outs in the lugs and a chromed clover fork crown",
            "De Rosa Professional SLX": "1980s lugged steel frame with small heart-shaped "
                "cut-outs in the lugs or fork crown, heart logo",
            "Pinarello Montello SLX": "1980s lugged steel frame, often chrome with "
                "'Spumoni' multicolour fade paint",
            "Bianchi Specialissima (steel)": "lugged steel race frame in celeste, the pale "
                "turquoise Bianchi green, eagle head badge",
            "Eddy Merckx Corsa Extra": "late 1980s lugged steel frame, often in team paint: "
                "7-Eleven red, white and green, Motorola, Telekom magenta",
            "Eddy Merckx MX Leader": "1990s oversized steel frame with fluted, ribbed tubes, "
                "often Motorola red, white and blue",
            "Cinelli Supercorsa": "classic lugged steel frame, sloping fork crown, seat stays "
                "joined flat behind the seat tube, winged C badge",
            "Cinelli Laser": "1980s welded steel aero frame, smooth joints with small fins "
                "where the tubes meet, no lugs",
            "Tommasini Tecno": "lugged steel frame with chromed lugs and detailed "
                "multicolour Italian paint",
            "Gios Torino Super Record": "lugged steel frame in bright royal blue, chromed "
                "fork, coins set into the fork crown",
            "Raleigh Team Pro 753": "lugged steel frame in TI-Raleigh team colours: red with "
                "yellow and black bands",
            "Gazelle Champion Mondial AA": "Dutch lugged steel racer, often red or blue, "
                "chromed fork ends and lugs, Gazelle head badge",
            "Koga Miyata FullPro": "1980s Japanese lugged steel frame, often pearl white or "
                "grey, Shimano Dura-Ace parts",
            "RIH Sport (Amsterdam built)": "Dutch lugged steel frame, often orange-red or "
                "blue, plain RIH lettering",
            "Peugeot PX10": "white French racer with a chequered black band and coloured "
                "stripes on the seat tube, ornate cut lugs",
            "Look KG86": "1986 frame of black carbon tubes in aluminium lugs, often in "
                "Mondrian blocks of red, yellow and blue",
            "Klein Quantum": "fat oversized aluminium tubes with smooth welds, bright fade "
                "paint, cables run inside the frame",
        },
        "search": {"RIH Sport (Amsterdam built)": "rih racefiets",
                   "Raleigh Team Pro 753": "raleigh 753",
                   "Bianchi Specialissima (steel)": "bianchi specialissima",
                   "Colnago Super / Mexico": "colnago super"},
    },
    "chairs": {
        "source": "Chairs", "flip": "chairs", "noun": "chairs",
        "clues": '"teak", "skai", "buisframe", "jaren 60", a label under the seat',
        "parts": 'Loose cushions, bare frames without a seat and parts are "unknown".',
        "rule": "A different kind of seat (dining chair, lounge chair, office chair, "
                "sofa) than the model is never that model.",
        "generic": ["chair", "lounge", "armchair", "dining", "office", "soft", "pad",
                    "chaise", "longue"],
        "brand_stop": ["italia", "charlotte", "pierre", "herman", "carl", "fritz"],
        "designers": ["eames", "arne jacobsen", "jacobsen", "wegner", "kjaerholm",
                      "mogensen", "mies van der rohe", "breuer", "saarinen",
                      "le corbusier", "corbusier", "perriand", "paulin", "martin visser",
                      "ducaroy", "bellini", "jeanneret", "lafer", "aalto"],
        "copied": ["Herman Miller Eames Lounge Chair 670/671", "Vitra Eames EA 117 / EA 119",
                   "Fritz Hansen Egg Chair", "Fritz Hansen Swan Chair",
                   "Carl Hansen CH24 Wishbone", "Knoll Barcelona Chair", "Knoll Wassily",
                   "Cassina LC2", "Cassina LC4 Chaise Longue",
                   "Pierre Jeanneret Chandigarh Office Chair"],
        "queries": ["vintage fauteuil", "retro fauteuil", "design stoel", "vintage stoel",
                    "jaren 60 fauteuil", "jaren 70 fauteuil", "leren fauteuil vintage",
                    "buisframe stoel", "rotan fauteuil", "teak fauteuil", "deense fauteuil",
                    "lounge stoel", "bureaustoel aluminium", "stoelen set vintage"],
        "looks": {
            "Herman Miller Eames Lounge Chair 670/671": "low lounge chair of three curved "
                "plywood shells (seat, back, headrest) with black leather cushions, "
                "five-star swivel base, matching ottoman",
            "Vitra Eames EA 117 / EA 119": "office chair with fabric or leather stretched "
                "tight between two polished cast aluminium side ribs, five-star base",
            "Vitra Eames Soft Pad EA 217 / EA 219": "the aluminium office chair with thick "
                "stitched leather pads in horizontal sections on seat and back",
            "Fritz Hansen Egg Chair": "large upholstered shell curving up into a high back "
                "with wing-like sides that wrap the sitter, four-star swivel base",
            "Fritz Hansen Swan Chair": "lower upholstered shell with no straight lines, back "
                "curving out into wing-shaped arms, four-star swivel base",
            "Fritz Hansen PK22": "low lounge chair: leather or cane seat on a flat brushed "
                "steel frame with two curved steel runners at the sides",
            "Carl Hansen CH24 Wishbone": "wooden dining chair with a bent half-round top "
                "rail that is also the armrest, Y-shaped back splat, woven paper cord seat",
            "Carl Hansen CH25": "low wooden lounge chair with seat and back both woven of "
                "paper cord, straight armrests",
            "Getama GE290": "solid oak or teak armchair: flat plank armrests, back of wood "
                "slats, loose cushions",
            "PP Mobler Papa Bear (PP19)": "big upholstered wing chair with exposed wooden "
                "arm ends shaped like a bear's paws",
            "Fredericia Spanish Chair": "low oak frame with very wide flat armrests, seat "
                "and back of thick saddle leather on straps",
            "Knoll Barcelona Chair": "low square chair on an X-shaped flat chromed steel "
                "frame, tufted leather cushions in square panels",
            "Knoll Wassily": "bent chromed steel tube frame with strips of leather or canvas "
                "as seat, back and armrests, no cushions",
            "Knoll Womb Chair": "fabric-covered fibreglass shell wide enough to curl up in, "
                "thin chrome rod legs, loose cushions",
            "Cassina LC2": "cube armchair: square cushions held inside an exposed chromed "
                "tubular steel cage",
            "Cassina LC4 Chaise Longue": "long curved chromed tube cradle with a hide or "
                "leather pad, on a black H-shaped base",
            "Artifort Mushroom F560": "low round mushroom-shaped chair, one stretch-fabric "
                "body with a hollow seat, no legs visible",
            "Artifort Ribbon F582": "one fabric-covered ribbon looping into seat and back, "
                "on a flat lacquered disc base",
            "Artifort Orange Slice F437": "two identical curved shells like orange segments, "
                "on a slim chrome four-leg frame",
            "Spectrum SZ01 / SZ02": "low easy chair on a simple tubular steel frame with a "
                "wide wicker or saddle leather seat",
            "Gispen 412": "1930s lounge chair with a bent chromed tube cantilever frame and "
                "upholstered seat and back",
            "Ligne Roset Togo": "low legless all-foam seat with heavy pleated fabric, like a "
                "bent tube, no frame visible",
            "De Sede DS-600": "long snake of upholstered leather wedge elements linked "
                "together, curving freely",
            "B&B Italia Camaleonda": "modular sofa of deep square padded elements with "
                "button-tufted channels held by rings and ropes",
            "Charlotte Perriand Les Arcs Dining Chair": "dining chair with a chromed tube "
                "frame and saddle leather seat and back panels",
            "Pierre Jeanneret Chandigarh Office Chair": "teak chair with V-shaped legs at "
                "the sides, cane woven seat and back",
            "Percival Lafer MP-41 Lounge": "low 1970s Brazilian lounge chair on a solid wood "
                "base, two leather cushions held by straps",
            "Artek Armchair 400 Tank": "low armchair with wide flat birch plywood bands as "
                "arms that curve down into the legs, upholstered cushion",
        },
        "search": {"Herman Miller Eames Lounge Chair 670/671": "eames lounge chair",
                   "Vitra Eames EA 117 / EA 119": "vitra ea 117",
                   "Vitra Eames Soft Pad EA 217 / EA 219": "vitra soft pad",
                   "Charlotte Perriand Les Arcs Dining Chair": "perriand les arcs",
                   "Pierre Jeanneret Chandigarh Office Chair": "jeanneret chandigarh",
                   "Spectrum SZ01 / SZ02": "spectrum martin visser"},
        # "Eames" alone names three of these: the numbers tell them apart
        "keys": {"Vitra Eames EA 117 / EA 119": ["ea 117", "ea 119", "ea117", "ea119",
                                                 "aluminium group", "aluminum group"],
                 "Vitra Eames Soft Pad EA 217 / EA 219": ["soft pad", "softpad", "ea 217",
                                                          "ea 219", "ea217", "ea219"]},
        "aliases": {"Herman Miller Eames Lounge Chair 670/671": ["eames lounge"],
                    "Pierre Jeanneret Chandigarh Office Chair": ["jeanneret"],
                    "Charlotte Perriand Les Arcs Dining Chair": ["perriand"]},
    },
    "jackets": {
        "source": "Jackets", "flip": None, "noun": "and archive jackets",
        "clues": '"paardenleer", "made in usa", "made in england", "jaren 80", a label '
                 'inside the collar',
        "parts": 'Loose linings, patches and parts are "unknown".',
        "rule": "A different kind of jacket (leather biker, denim, down, shell, coat) "
                "than the model is never that model.",
        "market": {"fresh_query": "vintage jas",
                   # Heren- en damesjassen, leren jassen, motorkleding
                   "fresh_categories": {630, 647, 648, 689, 2784, 2788},
                   "watch": ["Wrangler", "Barbour", "Diesel", "Hugo Boss", "Zara"],
                   "price_max": 150},
        "generic": ["jacket", "leather", "vintage", "down", "parka", "type", "model",
                    "shearling", "tech", "mountain", "collab", "trench", "tweed", "biker",
                    "race"],
        # Dutch "lang" is long; "stone washed", "made in canada", "real leather"
        "brand_stop": ["north", "face", "real", "company", "studios", "stone", "island",
                       "canada", "leathers", "leather", "lang", "jeff"],
        "aliases": {"The North Face Steep Tech Apogee": ["north face"],
                    "The North Face Supreme Collab Mountain / Nuptse": ["north face"],
                    "C.P. Company Mille Miglia Goggle Jacket": ["cp company"],
                    "Arc'teryx Alpha SV": ["arcteryx"],
                    "The Real McCoy's Type A-2": ["real mccoys", "mccoys"]},
        "designers": ["massimo osti", "osti", "scot schmidt", "lagerfeld", "supreme"],
        "copied": ["Schott NYC Perfecto 618 / 613", "Levi's Type III 557 / 70505 Big E",
                   "Burberry Vintage Trench", "Chanel Tweed Jacket",
                   "Moncler Grenoble Vintage Down", "Canada Goose Expedition Parka",
                   "The North Face Supreme Collab Mountain / Nuptse",
                   "Jeff Hamilton NBA Championship Leather", "Carhartt Detroit Jacket",
                   "Avirex A-2 / Icon Leather", "Lee 101-J Storm Rider"],
        "queries": ["vintage leren jas", "leren motorjas", "vintage spijkerjas",
                    "spijkerjack vintage", "oude leren jas", "vliegeniersjas",
                    "bomberjack leer", "vintage donsjas", "trenchcoat",
                    "waxjas", "vintage ski jas", "werkjas canvas"],
        "looks": {
            "Schott NYC Perfecto 618 / 613": "black heavy leather motorcycle jacket, "
                "diagonal front zip, wide snap-down lapels, belt at the waist, epaulettes "
                "(small stars on them on the 613)",
            "Lewis Leathers Lightning / Cyclone": "British leather motorcycle jacket, "
                "diagonal zip, quilted lining, zipped cuffs, belt and epaulettes",
            "Vanson Model B": "very thick stiff leather biker jacket, diagonal zip, often "
                "contrasting colour panels or stripes",
            "Aero Leather Highwayman": "horsehide motorcycle jacket with a straight centre "
                "zip, zipped chest pockets, short cut, half belt at the back",
            "Avirex A-2 / Icon Leather": "leather flight or varsity jacket covered in large "
                "embroidered patches, badges and lettering",
            "Jeff Hamilton NBA Championship Leather": "leather jacket fully covered in NBA "
                "team logos, colour panels and embroidered trophies",
            "Rick Owens Stooges Leather": "slim black lamb leather biker, short body, "
                "diagonal zip, no lapel snaps, long narrow sleeves",
            "Acne Studios Velocite Shearling": "oversized shearling aviator jacket, leather "
                "outside, thick fleece collar and lining, belted",
            "Levi's Type I 506XX": "pre-1953 denim jacket with one flap chest pocket, pleats "
                "down the front, a cinch buckle at the back waist",
            "Levi's Type II 507XX": "denim jacket with two flap chest pockets, front pleats, "
                "no cinch, buttoned adjusters at the sides of the waistband",
            "Levi's Type III 557 / 70505 Big E": "1960s denim trucker with two pointed chest "
                "pocket flaps and V-shaped seams running down from them",
            "Lee 101-J Storm Rider": "denim jacket with a corduroy collar and a striped "
                "blanket lining",
            "Stone Island Ice Jacket": "technical jacket in fabric that changes colour with "
                "temperature, compass badge on the left sleeve",
            "Stone Island Tela Stella": "1980s jacket in stiff waxed military tarp canvas, "
                "compass badge on the sleeve",
            "C.P. Company Mille Miglia Goggle Jacket": "jacket whose zipped hood has two "
                "goggle lenses built in over the eyes, small lens on the wrist",
            "Arc'teryx Alpha SV": "technical hard shell rain jacket, large helmet hood, taped "
                "seams, bird skeleton logo on the chest",
            "The North Face Steep Tech Apogee": "1990s ski jacket in bold colour blocks, "
                "padded shoulders and elbows, many zips",
            "The North Face Supreme Collab Mountain / Nuptse": "Nuptse puffer or Mountain "
                "shell in a loud all-over print with Supreme lettering",
            "Moncler Grenoble Vintage Down": "shiny nylon down puffer with horizontal "
                "quilting, felt rooster badge on the sleeve",
            "Canada Goose Expedition Parka": "long heavy down parka, fur trimmed hood, many "
                "large pockets, round Arctic map badge on the sleeve",
            "Carhartt Detroit Jacket": "short boxy duck canvas jacket with a corduroy collar "
                "and striped blanket lining, often brown",
            "The Real McCoy's Type A-2": "brown horsehide WWII flight jacket, knit cuffs and "
                "waistband, snap-down collar, two flap pockets",
            "Belstaff Trialmaster": "waxed cotton motorcycle jacket with four flap pockets, "
                "belt, cord collar and buckled throat strap",
            "Dainese Vintage Race Leather": "1980s-90s motorcycle racing leather jacket in "
                "bold colour blocks, padded shoulders and elbows",
            "Chanel Tweed Jacket": "short boxy boucle tweed jacket with contrast braid trim, "
                "patch pockets, CC buttons",
            "Helmut Lang Bondage / Astro Biker": "slim minimal leather or denim jacket with "
                "straps inside or across the back",
            "Burberry Vintage Trench": "beige gabardine trench coat with epaulettes, storm "
                "flap, belt with D-rings, nova check lining",
        },
        "search": {"Levi's Type I 506XX": "levis 506xx", "Levi's Type II 507XX": "levis 507xx",
                   "Levi's Type III 557 / 70505 Big E": "levis big e jacket",
                   "Avirex A-2 / Icon Leather": "avirex leren jas",
                   "The North Face Supreme Collab Mountain / Nuptse": "supreme north face",
                   "Burberry Vintage Trench": "burberry trenchcoat",
                   "Moncler Grenoble Vintage Down": "moncler grenoble",
                   "Jeff Hamilton NBA Championship Leather": "jeff hamilton jas",
                   "Vanson Model B": "vanson leren jas"},
        "keys": {"Avirex A-2 / Icon Leather": [], "Burberry Vintage Trench": [],
                 "Vanson Model B": [],
                 "Dainese Vintage Race Leather": [],
                 "Levi's Type III 557 / 70505 Big E": ["big e", "557", "70505", "type 3",
                                                       "type iii"]},
    },
    "bags": {
        "source": "Bags", "flip": None, "noun": "and luxury bags",
        "clues": '"echt leer", "met stofzak", "slot en sleutel", "jaren 90", a stamp '
                 'inside',
        "parts": 'Loose straps, dust bags, boxes and wallets on their own are "unknown".',
        "rule": "No item is copied more than these bags: a logo pattern, quilting or a "
                "famous shape alone is only \"possible\"; \"strong\" needs signs of "
                "quality you can see (even stitching, solid hardware, a clean stamp).",
        "market": {"fresh_query": "vintage handtas",
                   # Tassen: handtassen, schoudertassen, overige
                   "fresh_categories": {626, 1764, 1838, 1840},
                   "watch": ["Michael Kors", "Guess", "Bulaggi", "Liu Jo", "Coach",
                             "Furla", "Mulberry", "Longchamp"],
                   "price_max": 500},
        "generic": ["bag", "classic", "medium", "top", "handle", "tote", "mm", "pm",
                    "mini", "on", "nylon", "re", "party", "accessoires", "lock"],
        "brand_stop": ["yves", "saint", "laurent", "bottega"],
        "aliases": {"Yves Saint Laurent Mombasa": ["ysl", "saint laurent"]},
        "designers": ["galliano", "lagerfeld", "phoebe philo", "ghesquiere", "tom ford",
                      "murakami"],
        "copied": ["Hermes Birkin 30 / 35", "Hermes Kelly 28 / 32", "Chanel Classic Flap Medium",
                   "Louis Vuitton Speedy 30", "Louis Vuitton Neverfull MM"],
        "queries": ["vintage tas leer", "leren handtas", "vintage handtas", "designer tas",
                    "leren schoudertas vintage", "tas met slot", "oude handtas",
                    "vintage clutch", "tas bamboe handvat", "gevlochten leren tas",
                    "monogram tas"],
        "looks": {
            "Hermes Birkin 30 / 35": "structured trapezoid leather handbag, two rolled top "
                "handles, flap closed by a strap over a turn-lock, padlock and key bell",
            "Hermes Kelly 28 / 32": "trapezoid leather handbag with one top handle, flap with "
                "a strap and turn-lock, padlock, often a shoulder strap",
            "Hermes Constance": "flap shoulder bag with a large metal H clasp on the front",
            "Hermes Evelyne": "flat soft leather crossbody with a perforated H pattern on the "
                "front, canvas strap",
            "Hermes Picotin Lock": "small leather bucket bag with two handles, a tab with a "
                "padlock across the top",
            "Hermes Garden Party": "open tote in canvas or leather with leather trim, one "
                "strap with a snap closing the top",
            "Chanel Classic Flap Medium": "diamond-quilted leather flap bag with an "
                "interlocking CC turn-lock, chain strap woven with leather",
            "Chanel 2.55 Reissue": "quilted flap bag with a rectangular turn-lock and an "
                "all-metal chain strap",
            "Chanel Diana Flap": "soft slouchy quilted flap bag with a CC turn-lock and chain "
                "strap",
            "Chanel Wallet on Chain": "small flat quilted wallet with CC turn-lock on a long "
                "chain strap",
            "Louis Vuitton Speedy 30": "soft barrel bag in brown LV monogram canvas, natural "
                "leather handles, zip top, padlock",
            "Louis Vuitton Keepall 50 / 55": "large soft barrel duffle in monogram canvas "
                "with leather handles",
            "Louis Vuitton Neverfull MM": "wide open tote in monogram or checked canvas, thin "
                "leather straps laced through the sides",
            "Louis Vuitton Alma": "structured dome-shaped bag with two rounded handles and a "
                "zip around the top",
            "Louis Vuitton Pochette Accessoires": "small flat zip pouch in monogram canvas "
                "with a short thin strap",
            "Louis Vuitton Speedy Multicolore (Murakami)": "barrel bag with the LV monogram "
                "printed in 33 bright colours on white or black",
            "Dior Saddle": "kidney-shaped saddle bag with a curved flap and a hanging D "
                "charm, often in monogram canvas",
            "Dior Lady Dior": "boxy top handle bag with diamond cannage stitching, hanging "
                "D-I-O-R letter charms",
            "Fendi Baguette": "small long shoulder bag with a short strap and an FF clasp on "
                "the flap",
            "Fendi Peekaboo": "structured top handle bag that opens at both sides with twist "
                "locks, the inside showing like a mouth",
            "Gucci Jackie": "crescent hobo bag with a piston push-lock on the side",
            "Gucci Bamboo Top Handle": "structured leather bag with a curved horseshoe handle "
                "of glossy bent bamboo",
            "Prada Re-Edition 2005 Nylon": "small black nylon shoulder bag with a triangle "
                "logo plate and a little zip pouch hanging on it",
            "Bottega Veneta Jodie": "small woven leather hobo with a knotted short handle",
            "Bottega Veneta Cassette": "rectangular crossbody in a wide weave of thick leather "
                "strips",
            "Celine Luggage Tote": "trapezoid tote with wings sticking out at the sides and a "
                "front zip pocket that looks like a smiling face",
            "Celine Classic Box": "rigid box flap bag with a metal tab clasp and a long strap",
            "Balenciaga City / Motorcycle": "slouchy distressed leather bag with studs, "
                "buckles, long leather tassels on the zips",
            "Loewe Puzzle": "geometric bag made of many leather panels like a puzzle, folds "
                "flat",
            "Goyard Saint Louis PM": "flat tote in coated canvas with a painted chevron "
                "pattern of small Y shapes, thin straps",
            "Delvaux Brillant": "structured trapezoid handbag with a large D-shaped buckle on "
                "the front",
            "Yves Saint Laurent Mombasa": "soft hobo bag with a curved horn handle",
            "Chloe Paddington": "soft bag with a heavy oversized padlock hanging on the front",
        },
        "search": {"Chanel Classic Flap Medium": "chanel classic flap",
                   "Chanel Wallet on Chain": "chanel wallet on chain",
                   "Louis Vuitton Speedy Multicolore (Murakami)": "speedy multicolore",
                   "Prada Re-Edition 2005 Nylon": "prada re edition"},
        # "Dior", "chain" and "Louis" alone would name the wrong model
        "keys": {"Dior Lady Dior": ["lady"], "Chanel Wallet on Chain": ["wallet on chain",
                                                                         "woc"],
                 "Goyard Saint Louis PM": ["saint louis"]},
    },
    "boats": {
        "source": "Boats", "flip": None, "noun": "and classic boats",
        "clues": '"polyester", "inboard diesel", "trailer", "lengte", "bouwjaar"',
        "parts": 'Engines, sails, trailers and dinghies on their own are "unknown".',
        "rule": "A boat of a clearly different length or kind (sloep, open sailboat, "
                "sailing yacht, motor cruiser) than the model is never that model.",
        "market": {"fresh_query": "boot",
                   # Sloepen, kajuitzeiljachten, open zeilboten, motorboten, overige
                   "fresh_categories": {1407, 985, 989, 990, 998},
                   "watch": ["Bayliner", "Jeanneau", "Beneteau", "Bénéteau", "Linssen",
                             "Quicksilver", "Sea Ray"],
                   "price_min": 1000, "price_max": 20000},
        "generic": ["boat", "motorboat", "mahogany", "family", "explorer", "touring",
                    "sport", "international"],
        "brand_stop": ["boats", "cornish", "nordic"],
        "aliases": {"J/Boats J/22": ["j22", "j 22"], "J/Boats J/24": ["j24", "j 24"],
                    "Nordic Folkboat Folkboat": ["folkboot", "nordic folkboot"]},
        # one model per brand on the list: the brand alone names it
        "keys": {"Interboat 19 / 6.5": [], "Makma Caribbean 21": [],
                 "Oud Huijzer 575 / 616": [], "Maxima 630": [], "Maril 6Nine": [],
                 "Randmeer Randmeer Touring": [], "Regenboog Regenboog": [],
                 "Pampus Pampus": [], "Polyvalk Polyvalk": [],
                 "Marieholm International Folkboat (IF)": ["if", "folkboat", "folkboot"],
                 "Nordic Folkboat Folkboat": [], "Albin Vega 27": ["vega"],
                 "Albin Albin 25": ["25"], "Contessa Contessa 26": [],
                 "Victoire Victoire 26": [], "Hallberg-Rassy Monsun 31": ["monsun"],
                 "Drascombe Lugger": [], "Cornish Crabbers Shrimper 19": [],
                 "J/Boats J/22": ["j22", "j 22"], "J/Boats J/24": ["j24", "j 24"],
                 "Boston Whaler 13 Sport / Montauk 17": [],
                 "Pettersson Mahogany Motorboat": [], "Coronet 24 Family / Explorer": [],
                 "Saga Saga 27": [], "Doerak 780 / 850": [], "Antaris Fifty5": []},
        "designers": ["van de stadt", "tord sunden", "sunden", "pettersson"],
        "copied": [],
        "queries": ["sloep", "sloep met trailer", "tender sloep", "zeilboot", "open zeilboot",
                    "kielboot", "kajuitzeiljacht", "klassiek zeiljacht", "houten boot",
                    "motorkruiser", "toerboot", "klassieke motorboot"],
        "looks": {
            "Antaris Fifty5": "5.5 m open polyester sloep, wide beam, wood trim on the "
                "gunwale, cushioned benches around an open cockpit, small console",
            "Interboat 19 / 6.5": "6 m modern polyester sloep, upright bow, wide teak "
                "gunwale, U-shaped bench and table, console with windscreen",
            "Makma Caribbean 21": "classic-looking polyester sloep with varnished teak "
                "gunwale and details, open cockpit, steering console",
            "Oud Huijzer 575 / 616": "compact tender sloep with a round bow and a thick "
                "fender all around, open cockpit",
            "Maxima 630": "6.3 m tender sloep with a thick fender all around, outboard or "
                "inboard, open cockpit",
            "Maril 6Nine": "upmarket 6.9 m sloep, straight bow, teak deck, sharp modern lines",
            "Randmeer Randmeer Touring": "6.5 m open keelboat, white polyester hull, small "
                "cuddy at the front, tiller, sloop rig",
            "Regenboog Regenboog": "9 m long narrow open wooden keelboat, varnished, big "
                "sloop rig, low freeboard",
            "Pampus Pampus": "8.5 m wooden one-design keelboat, long narrow low hull, small "
                "open cockpit",
            "Polyvalk Polyvalk": "6 m open sailing boat with white polyester hull, big open "
                "cockpit, centreboard, small foredeck",
            "Marieholm International Folkboat (IF)": "7.9 m polyester sloop with a long "
                "keel, low cabin with small windows, rudder hung on the transom",
            "Nordic Folkboat Folkboat": "7.6 m clinker hull of overlapping planks, long keel, "
                "small cabin, rudder hung on the transom",
            "Albin Vega 27": "27 ft polyester sailing yacht with high sides, small cabin "
                "windows, fin keel",
            "Contessa Contessa 26": "26 ft long-keel sailing yacht, low sheer, small cabin, "
                "rudder hung on the transom",
            "Victoire Victoire 26": "Dutch 26 ft polyester sailing yacht, compact cabin, "
                "sturdy build",
            "Hallberg-Rassy Monsun 31": "31 ft sailing yacht with a fixed windscreen over "
                "the cockpit, blue stripe on a white hull, teak deck",
            "Drascombe Lugger": "open boat with tan sails on two masts, pointed at both ends, "
                "outboard in a well",
            "Cornish Crabbers Shrimper 19": "small gaff-rigged sailboat with tan sails, "
                "bowsprit and a small cabin, traditional look",
            "J/Boats J/22": "22 ft white sports keelboat, low cabin with slit windows, open "
                "cockpit",
            "J/Boats J/24": "24 ft white sports keelboat, flat low cabin top, long open "
                "cockpit",
            "Boston Whaler 13 Sport / Montauk 17": "flat wide motorboat hull with a "
                "three-ridged front, white, wooden console and seats on classics",
            "Pettersson Mahogany Motorboat": "Swedish varnished mahogany motorboat with a "
                "wooden cabin and round portholes, 1910-1950",
            "Coronet 24 Family / Explorer": "1960s-70s Danish sport cruiser, deep V hull, "
                "windscreen, small cabin, wood trim",
            "Albin Albin 25": "25 ft white motor cruiser with a wheelhouse, aft cabin, slow "
                "displacement hull",
            "Saga Saga 27": "27 ft Norwegian motor cruiser pointed at both bow and stern, "
                "wheelhouse",
            "Doerak 780 / 850": "1970s Dutch steel motor cruiser, round bilge, wheelhouse, "
                "rear deck",
        },
        "search": {"Interboat 19 / 6.5": "interboat", "Oud Huijzer 575 / 616": "oud huijzer",
                   "Maxima 630": "maxima sloep", "Randmeer Randmeer Touring": "randmeer",
                   "Regenboog Regenboog": "regenboog boot", "Pampus Pampus": "pampus",
                   "Polyvalk Polyvalk": "polyvalk",
                   "Marieholm International Folkboat (IF)": "marieholm",
                   "Nordic Folkboat Folkboat": "folkboot",
                   "Contessa Contessa 26": "contessa 26",
                   "Victoire Victoire 26": "victoire 26", "Saga Saga 27": "saga 27", "Albin Albin 25": "albin 25",
                   "J/Boats J/22": "j22", "J/Boats J/24": "j24",
                   "Boston Whaler 13 Sport / Montauk 17": "boston whaler",
                   "Pettersson Mahogany Motorboat": "pettersson",
                   "Coronet 24 Family / Explorer": "coronet", "Doerak 780 / 850": "doerak"},
    },
}

HUNT_PRICE_MAX = 250    # asking price cap, the same as the rest of /flip
HUNT_PRICE_MIN = 10     # €1 "n.o.t.k." placeholders aren't real prices
# Categories the daily run hunts (and /flip shows) when none are named. A
# category joins once its --eval numbers hold up; the rest run on request.
DAILY = ["lamps"]
HUNT_MAX = 100          # photos sent to the model per category per day: the cost cap
EVAL_PER_MODEL = 5      # positives kept per model
EVAL_NEGATIVES = 30     # ordinary listings that name no listed brand
SEARCH_PAUSE_S = 2      # between Marktplaats searches: be gentle

# Words in a model name that say nothing about which model it is.
_GENERIC = {"lamp", "lamps", "floor", "table", "pendant", "desk", "wall", "light",
            "standard", "series", "the", "and", "with", "three", "arm"}
# "Nieuw" in a title means new retail stock, never a vintage find; "zo goed als
# nieuw" is only the condition of an old one.
_NEW_RE = re.compile(r"(?<!als )\bnieuwe?\b|\bnew\b")
# Brand words too common to mean the brand on their own ("Raak" alone does).
_BRAND_STOP = {"louis", "luce", "amsterdam"}
# Titles that aren't the lamp itself: copies, parts, wanted ads, books.
_REPLICA_RE = re.compile(r"replica|stijl|style|look ?a ?like|geinspireerd|inspired|"
                         r"kopie|copy|onderdel|kap\b|shade\b|gezocht|fitting|"
                         r"\bvoor\b|boek|book|poster", re.I)


def market(key):
    """Where a category's listings live on Marktplaats: plain search, category
    ids, brands that mean the seller knows. From its /flip page, or its own
    "market" entry when it has none. Plus the asking price bounds."""
    cat = CATEGORIES[key]
    page = dict(FLIP_PAGES[cat["flip"]]) if cat.get("flip") else dict(cat["market"])
    page.setdefault("price_min", HUNT_PRICE_MIN)
    page.setdefault("price_max", HUNT_PRICE_MAX)
    return page


def _norm(text):
    """Lowercase, accents stripped, only letters and digits: 'Jieldé' -> 'jielde'."""
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", " ", text.decode().lower()).strip()


def load_models(key):
    """The valuable models for one category, each with a display name, the words
    that would mean the seller already knows what it is, and prices."""
    with open(MODELS_FILE, encoding="utf-8") as f:
        items = json.load(f)["items"]
    cat = CATEGORIES[key]
    models = []
    for it in items:
        if it.get("category") != cat["source"]:
            continue
        brand, model = it["brand"], it["model"]
        name = f"{brand} {model}"
        generic = _GENERIC | set(cat.get("generic", ()))
        stop = _BRAND_STOP | set(cat.get("brand_stop", ()))
        words = [w for w in _norm(model).split() if w not in generic]
        # "PH 3/2" -> "ph32", matched with spaces squashed out ("PH 3 2", "PH3/2")
        # ("AJ" is too short to squash, so it only counts as a whole word)
        squashed = "".join(words)
        keys = [w for w in words if len(w) >= 3] + ([squashed] if squashed else [])
        # "keys" overrides: [] means the brand alone names the model (one model
        # per brand, and sellers write "Interboat 19" or "Interboat 6.5")
        keys = [_norm(k) for k in cat.get("keys", {}).get(name, keys)]
        brand_words = [w for w in _norm(brand).split() if len(w) >= 4]
        aliases = [_norm(a) for a in cat.get("aliases", {}).get(name, [])]
        # brand words that are also ordinary words ("klein", "lang", "stone")
        brands = {_norm(brand), *brand_words, *aliases} - stop
        # plain words a seller would type: no "Table", "Floor (10A, UF4)"
        query = " ".join([brand] + [w for w in re.sub(r"\(.*?\)", "", model).split()
                                    if _norm(w) not in generic])
        models.append({
            "name": name,
            "query": cat.get("search", {}).get(name, query),
            "brand_keys": sorted(brands),
            "model_keys": sorted(set(keys)),
            "model_words": sorted(set(words + ([squashed] if squashed else []))),
            "look": cat.get("looks", {}).get(name, ""),
            "hint": it.get("description", ""),
            "resell_eur": it["resell_eur"],
            "buy_eur": it["buy_eur"],
        })
    return models


def _has(text, phrase):
    """Whole-word match of a normalized phrase in normalized text."""
    return bool(phrase) and f" {phrase} " in f" {text} "


def _has_key(text, key):
    """A model key in normalized text: as a whole word, or for keys of 3+
    characters also with the spaces squashed out ("ph 5" matches "ph5")."""
    if _has(text, key):
        return True
    return len(key) >= 3 and key in text.replace(" ", "")


def names_model(text, m):
    """True when the text names this model: its brand and its model name."""
    t = _norm(text)
    return (any(_has(t, b) for b in m["brand_keys"])
            and (not m["model_keys"] or any(_has_key(t, k) for k in m["model_keys"])))


def names_any_brand(text, models, designers=()):
    """True when the text names any listed brand, model or designer, i.e. the
    seller already knows what they have."""
    t = _norm(text)
    return (any(_has(t, _norm(d)) for d in designers)
            or any(any(_has(t, b) for b in m["brand_keys"])
                   or any(_has_key(t, k) for k in m["model_keys"] if len(k) >= 4)
                   for m in models))


_MODEL_NUMBER_RE = re.compile(r"\b(?!19\d\d\b|20\d\d\b)[a-z]?\d{3,4}\b")


def masked_text(listing, key, models, limit=400):
    """The listing's title and description with every brand, model, designer
    and model number cut out: what a seller who doesn't know the brand might
    write ("oude wandlamp met contragewicht, jaren 50")."""
    words = set(_norm(d) for d in CATEGORIES[key].get("designers", []))
    for m in models:
        words.update(m["brand_keys"])
        words.update(w for w in m["model_words"] if not (w.isdigit() and len(w) < 3))
    t = _norm(f"{listing.get('title', '')}. {listing.get('description', '')}")
    # "ph5" also cuts "ph 5": an optional space where letters meet digits
    names = "|".join(re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ?", w)
                     for w in sorted(words, key=len, reverse=True) if w)
    t = re.sub(rf"\b(?:{names})\b", " ", t)
    t = _MODEL_NUMBER_RE.sub(" ", t)
    return " ".join(t.split())[:limit]


# ---------------------------------------------------------------- recognition

RECOGNIZE_PROMPT = """You are an expert in vintage design %(noun)s. You see up to 3 photos of one
second-hand listing, plus the seller's Dutch text with all brand, model and designer names
cut out. The text can help (%(clues)s), but the seller may be wrong, and the photos decide.

Valuable models to look for (name: what it looks like. Notes on value and originality):
%(catalog)s

Decide which ONE model on the list the item in the photos is, or "unknown". Judge only what
you see: shape, proportions, materials, construction, stamps and labels. Sellers rarely
photograph stamps, so a missing stamp alone is no reason to doubt. %(parts)s
When the item looks like none of the models, answer "unknown". %(rule)s
- "strong": the overall shape and its distinctive details clearly match the description,
  and nothing visible (cheap materials, wrong proportions, modern fittings) argues
  against it.
- "possible": it resembles the model, but the photo is unclear or it could be a copy or
  a similar design by another maker.

Reply with ONLY JSON:
{"match": "<exact name from the list, or unknown>", "confidence": "strong" or "possible",
 "why": "<max 15 words, English, no em dashes: what in the photos shows it>"}"""


def recognize(key, models, images, text=""):
    """Ask the model which listed model these photos (and the brand-free
    listing text) show. Returns
    {"match": name or None, "confidence": "strong"|"possible", "why": str}."""
    catalog = "\n".join(f"- {m['name']}: {m['look']}. {m['hint']}".replace(": . ", ": ")
                        for m in models)
    content = [{"type": "text",
                "text": f"Seller's text, names removed: {text or '(none)'}\nPhotos:"}]
    content += [{"type": "image_url", "image_url": {"url": u}} for u in images[:3]]
    result = llm_json(
        [
            {"role": "system",
             "content": RECOGNIZE_PROMPT % dict(CATEGORIES[key], catalog=catalog)},
            {"role": "user", "content": content},
        ],
        max_tokens=400,
        # the free fallback can't be trusted with photos; a failed call is skipped
        models=MODELS[:1],
    )
    names = {m["name"] for m in models}
    match = str(result.get("match") or "").strip()
    confidence = "strong" if result.get("confidence") == "strong" else "possible"
    if match in CATEGORIES[key].get("copied", []):
        confidence = "possible"
    why = str(result.get("why") or "").replace("\u2014", ",").replace("\u2013", "-")
    return {"match": match if match in names else None,   # check it in code
            "confidence": confidence,
            "why": why[:200]}


# ---------------------------------------------------------------- eval: collect

def _eval_path(key):
    return os.path.join(HERE, "data", f"overlooked_eval_{key}.json")


def collect(key):
    """Build the test set: listings whose title names a listed model (the answer
    is known) plus ordinary ones that name none. Only the brand-free text is
    stored, so names can't leak into the test. Re-running tops up an existing
    set: only models with fewer than 3 cases are searched again."""
    models = load_models(key)
    page = market(key)
    designers = CATEGORIES[key].get("designers", [])
    cases = []
    if os.path.exists(_eval_path(key)):
        with open(_eval_path(key), encoding="utf-8") as f:
            cases = json.load(f)["cases"]
    have = Counter(c["truth"] for c in cases)
    seen = {c["id"] for c in cases}

    def add(l, truth):
        if l["id"] in seen or not l.get("images"):
            return False
        seen.add(l["id"])
        cases.append({"id": l["id"], "url": l["url"], "images": l["images"],
                      "text": masked_text(l, key, models), "truth": truth})
        return True

    for m in models:
        kept = have[m["name"]]
        if kept >= 3:
            print(f"  {m['name']}: {kept} (already collected)")
            continue
        try:
            found, _total = search_marktplaats(m["query"], limit=30)
        except Exception as e:
            print(f"  ! search '{m['query']}' failed: {e}", file=sys.stderr)
            found = []
        for l in found:
            if kept >= EVAL_PER_MODEL:
                break
            if names_model(l["title"], m) and not _REPLICA_RE.search(_norm(l["title"])):
                kept += add(l, m["name"])
        note = "" if kept >= 3 else "  <- too few, check by hand"
        print(f"  {m['name']}: {kept}{note}")
        time.sleep(SEARCH_PAUSE_S)

    negatives = have["none"]
    found = []
    if negatives < EVAL_NEGATIVES:
        try:
            found, _total = search_marktplaats(
                page["fresh_query"], price_min_euro=max(20, page["price_min"]),
                price_max_euro=page["price_max"], limit=60)
        except Exception as e:
            print(f"  ! negatives search failed: {e}", file=sys.stderr)
    for l in found:
        if negatives >= EVAL_NEGATIVES:
            break
        text = f"{l['title']} {l['description']}"
        if (l.get("category_id") in page["fresh_categories"]
                and not names_any_brand(text, models, designers)
                and not any(_has(_norm(text), _norm(w)) for w in page["watch"])):
            negatives += add(l, "none")
    print(f"  ordinary listings (negatives): {negatives}")
    _save_eval(key, cases)


def _save_eval(key, cases):
    """Write the cases back, keeping other top-level fields such as "note"."""
    data = {}
    if os.path.exists(_eval_path(key)):
        with open(_eval_path(key), encoding="utf-8") as f:
            data = json.load(f)
    data.update(category=key, collected=time.strftime("%Y-%m-%d"), cases=cases)
    with open(_eval_path(key), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    print(f"Saved {len(cases)} cases to {os.path.relpath(_eval_path(key), HERE)}")


def refresh(key):
    """Re-fetch the saved cases with the same searches and update their photos
    and brand-free text in place. Adds nothing, so hand-checked labels stay;
    cases whose listing is gone are dropped."""
    models = load_models(key)
    page = market(key)
    with open(_eval_path(key), encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    by_id = {c["id"]: c for c in cases}
    fresh = {}
    queries = []
    for m in models:
        # the first collection searched by full name, top-ups by m["query"]
        for q in dict.fromkeys([m["name"], m["query"]]):
            if any(c["truth"] == m["name"] for c in cases):
                queries.append((q, {}))
    queries.append((page["fresh_query"],
                    {"price_min_euro": max(20, page["price_min"]),
                     "price_max_euro": page["price_max"], "limit": 60}))
    for q, kw in queries:
        try:
            found, _total = search_marktplaats(q, **{"limit": 30, **kw})
        except Exception as e:
            print(f"  ! search '{q}' failed: {e}", file=sys.stderr)
            found = []
        for l in found:
            if l["id"] in by_id and l.get("images"):
                fresh[l["id"]] = l
        time.sleep(SEARCH_PAUSE_S)
    kept = []
    for c in cases:
        l = fresh.get(c["id"])
        if l:
            c.update(images=l["images"], text=masked_text(l, key, models))
            kept.append(c)
    print(f"  {len(kept)} of {len(cases)} cases refreshed, {len(cases) - len(kept)} gone")
    _save_eval(key, kept)


# ---------------------------------------------------------------- eval: score

def _spread(cases, limit):
    """Up to `limit` cases: a quarter ordinary listings, the rest taken
    round-robin across models so a small run still covers every model."""
    negatives = [c for c in cases if c["truth"] == "none"]
    picked = negatives[:limit // 4]
    by_truth = {}
    for c in cases:
        if c["truth"] != "none":
            by_truth.setdefault(c["truth"], []).append(c)
    while len(picked) < limit and any(by_truth.values()):
        for group in by_truth.values():
            if group and len(picked) < limit:
                picked.append(group.pop(0))
    return picked


def evaluate(key, limit=None, use_text=True):
    """Run recognition on the test cases and print how often it was right."""
    if not OPENROUTER_API_KEY:
        sys.exit("OPENROUTER_API_KEY is not set: the test needs the LLM.")
    models = load_models(key)
    with open(_eval_path(key), encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    if limit:
        cases = _spread(cases, limit)
    print(f"Testing {len(cases)} listings...")

    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(recognize, key, models, c["images"],
                             c.get("text", "") if use_text else ""): c
                   for c in cases}
        for fut in as_completed(futures):
            c = futures[fut]
            try:
                results.append((c, fut.result()))
            except Exception as e:
                print(f"  ! {c['id']}: recognition failed: {e}", file=sys.stderr)

    pos = [(c, r) for c, r in results if c["truth"] != "none"]
    neg = [(c, r) for c, r in results if c["truth"] == "none"]
    score = Counter()
    confused = Counter()
    for c, r in pos:
        if r["match"] is None:
            score["unknown"] += 1
            continue
        ok = r["match"] == c["truth"]
        score[(r["confidence"], ok)] += 1
        if not ok:
            confused[(c["truth"], r["match"])] += 1
    false_hits = Counter(r["confidence"] for _c, r in neg if r["match"])

    def pct(a, b):
        return f"{a}/{b} ({100 * a / b:.0f}%)" if b else f"{a}/0"

    s_ok, s_bad = score[("strong", True)], score[("strong", False)]
    p_ok, p_bad = score[("possible", True)], score[("possible", False)]
    print(f"\nKnown models, title hidden: {len(pos)} listings")
    print(f"  strong match right:   {pct(s_ok, s_ok + s_bad)}")
    print(f"  possible match right: {pct(p_ok, p_ok + p_bad)}")
    print(f"  said unknown:         {pct(score['unknown'], len(pos))}")
    print(f"Ordinary listings: {len(neg)}")
    print(f"  wrongly strong:       {pct(false_hits['strong'], len(neg))}")
    print(f"  wrongly possible:     {pct(false_hits['possible'], len(neg))}")
    if confused:
        print("Confusions (truth -> answer):")
        for (truth, got), n in confused.most_common():
            print(f"  {truth} -> {got}: {n}")
    misses = [(c, r) for c, r in results
              if r["match"] and r["match"] != c["truth"]]
    if misses:
        print("Wrong answers, to look at by hand:")
        for c, r in misses:
            print(f"  {c['url']}  truth={c['truth']}  got={r['match']} "
                  f"({r['confidence']}): {r['why']}")


# ---------------------------------------------------------------- daily hunt

def hunt(key):
    """Search in plain words, keep listings that name no brand, recognize their
    photos, and return the finds: a listed model at or under its buy price.
    Strong matches first, then by margin. Also returns how many were checked."""
    models = load_models(key)
    by_name = {m["name"]: m for m in models}
    cat = CATEGORIES[key]
    page = market(key)
    designers = cat.get("designers", [])
    listings, seen = [], set()
    for q in cat["queries"]:
        try:
            found, _total = search_marktplaats(q, price_max_euro=page["price_max"],
                                               limit=60, exclude_bids=True)
        except Exception as e:
            print(f"  ! search '{q}' failed: {e}", file=sys.stderr)
            found = []
        for l in found:
            text = f"{l['title']} {l['description']}"
            ask = l.get("asking_euro")
            if (l["id"] in seen or not ask
                    or not page["price_min"] <= ask <= page["price_max"]
                    or not l.get("images") or is_auction_lot(l)
                    or _NEW_RE.search(_norm(l["title"]))
                    or l.get("category_id") not in page["fresh_categories"]
                    # the seller already knows what it is: not overlooked
                    or names_any_brand(text, models, designers)
                    or any(_has(_norm(text), _norm(w)) for w in page["watch"])):
                continue
            seen.add(l["id"])
            listings.append(l)
        time.sleep(SEARCH_PAUSE_S)
    listings = dedupe_relistings(listings)[:HUNT_MAX]
    print(f"  {len(listings)} unbranded listings from {len(cat['queries'])} searches")

    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(recognize, key, models, l["images"],
                             masked_text(l, key, models)): l for l in listings}
        for fut in as_completed(futures):
            try:
                results.append((futures[fut], fut.result()))
            except Exception as e:
                print(f"  ! {futures[fut]['id']}: recognition failed: {e}",
                      file=sys.stderr)

    finds = []
    for l, r in results:
        m = by_name.get(r["match"])
        # re-check the price in code: at or under what the model is worth buying at
        if not m or l["asking_euro"] > m["buy_eur"][1]:
            continue
        finds.append({
            "id": l["id"], "title": l["title"], "url": l["url"], "image": l["image"],
            "city": l["city"], "asking_euro": l["asking_euro"],
            "match": m["name"], "confidence": r["confidence"], "why": r["why"],
            "resale_low": m["resell_eur"][0], "resale_high": m["resell_eur"][1],
        })
    finds.sort(key=lambda f: (f["confidence"] != "strong",
                              f["asking_euro"] - f["resale_low"]))
    strong = sum(f["confidence"] == "strong" for f in finds)
    print(f"  {len(finds)} find(s): {strong} strong, {len(finds) - strong} possible")
    return finds, len(listings)


def run(categories=None, save=True):
    """Hunt the DAILY categories (or the given keys) and store the record in Redis."""
    if not OPENROUTER_API_KEY:
        sys.exit("OPENROUTER_API_KEY is not set: recognition needs the LLM.")
    keys = [k for k in CATEGORIES if k in (categories or DAILY)]
    record = {"date": time.strftime("%Y-%m-%d", time.gmtime()), "ts": time.time(),
              "scanned": 0, "categories": []}
    for key in keys:
        print(f"{key}...")
        finds, scanned = hunt(key)
        record["scanned"] += scanned
        # /flip reads its own page key; categories without a page are stored
        # under their own key and shown nowhere yet
        record["categories"].append({"key": CATEGORIES[key].get("flip") or key,
                                     "finds": finds})
    if save:
        payload = json.dumps(record)
        try:
            upstash_command("SET", OVERLOOKED_KEY, payload)
            upstash_command("SET", f"overlooked:{record['date']}", payload)
            print(f"Saved to Redis as {OVERLOOKED_KEY} and overlooked:{record['date']}")
        except Exception as e:
            print(f"  ! not saved to Redis: {e}", file=sys.stderr)
    return record


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Overlooked finds: unbranded items "
                                             "recognized from their photos.")
    ap.add_argument("--collect", metavar="CATEGORY", choices=sorted(CATEGORIES),
                    help="build the test set for a category (searches Marktplaats)")
    ap.add_argument("--eval", metavar="CATEGORY", choices=sorted(CATEGORIES),
                    help="score photo recognition on the saved test set")
    ap.add_argument("--refresh", metavar="CATEGORY", choices=sorted(CATEGORIES),
                    help="update the saved test set's photos and text (searches "
                         "Marktplaats, adds no new cases)")
    ap.add_argument("--no-text", action="store_true",
                    help="with --eval: photos only, to see what the text adds")
    ap.add_argument("--limit", type=int,
                    help="with --eval: test only this many listings, spread over models")
    ap.add_argument("--dry-run", action="store_true",
                    help="daily hunt: print the finds as JSON, don't write to Redis")
    ap.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                    help="daily hunt: only this category (repeatable); default: "
                         + ", ".join(DAILY))
    args = ap.parse_args()
    if args.collect:
        collect(args.collect)
    elif args.refresh:
        refresh(args.refresh)
    elif args.eval:
        evaluate(args.eval, limit=args.limit, use_text=not args.no_text)
    else:
        rec = run(categories=args.category, save=not args.dry_run)
        if args.dry_run:
            print(json.dumps(rec, indent=2, ensure_ascii=False))
