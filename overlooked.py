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
#   prompt:  the category's own lines in RECOGNIZE_PROMPT
# Optional:
#   page:    overrides for the /flip page's fresh_query, fresh_categories and
#            watch; a category without a /flip page ("flip": None) sets all three
#   price:   (min, max) asking price for the hunt and the test's ordinary listings
#   generic: words in this category's model names that don't identify a model
#   stop:    brand words too common to count as the brand on their own
#   brand_keys: replaces the brand words for a model whose brand is an
#            everyday word ("Klein", "Look")
#   model_keys: replaces the model words, e.g. [] when sellers name only the brand
#   reject:  regex on the title for parts and accessories, kept out of the test
#            set and the hunt
#   copied:  a list, or "all" when no model in the category can be "strong"
#   daily:   False keeps the category out of the morning run (still huntable
#            with --category) until its accuracy test has been read
CATEGORIES = {
    "lamps": {
        "source": "Lamps", "flip": "lamps", "noun": "lamps",
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
        "prompt": {
            "clues": '"contragewicht", "opaline glas", "jaren 50", a stamp under the base',
            "parts": 'Loose shades and parts are "unknown".',
            "types": "A different type of lamp (table, floor, wall, pendant) than the "
                     "model is never that model.",
        },
    },
    "chairs": {
        "source": "Chairs", "daily": False, "flip": "chairs", "noun": "chairs and sofas",
        # the /flip chairs categories plus Banken, Banken antiek, Hoekbanken and
        # Antiek stoelen: Togo, DS-600 and Camaleonda are sold as sofas
        "page": {"fresh_categories": {530, 1940, 3194, 1505, 505, 1937, 1938, 1508}},
        "queries": ["vintage fauteuil", "retro fauteuil", "jaren 60 fauteuil",
                    "jaren 70 fauteuil", "vintage loungestoel", "buisframe fauteuil",
                    "chroom fauteuil leer", "vintage bureaustoel", "draaifauteuil",
                    "vintage leren fauteuil", "houten fauteuil vintage", "lage fauteuil",
                    "papierkoord stoel", "webbing stoel", "vintage leren bank",
                    "modulaire bank vintage"],
        "designers": ["charles eames", "ray eames", "eames", "arne jacobsen", "jacobsen",
                      "hans wegner", "wegner", "borge mogensen", "mogensen",
                      "mies van der rohe", "marcel breuer", "breuer", "eero saarinen",
                      "saarinen", "le corbusier", "corbusier", "pierre paulin", "paulin",
                      "martin visser", "michel ducaroy", "ducaroy", "mario bellini",
                      "poul kjaerholm", "kjaerholm", "alvar aalto", "aalto",
                      "geoffrey harcourt", "harcourt", "perriand", "jeanneret"],
        "generic": ["chair", "chairs", "lounge", "soft", "pad", "orange", "chaise",
                    "longue", "dining", "office", "armchair", "les"],
        "copied": ["Herman Miller Eames Lounge Chair 670/671",
                   "Vitra Eames EA 117 / EA 119", "Vitra Eames Soft Pad EA 217 / EA 219",
                   "Fritz Hansen Egg Chair", "Fritz Hansen Swan Chair", "Fritz Hansen PK22",
                   "Carl Hansen CH24 Wishbone", "PP Mobler Papa Bear (PP19)",
                   "Fredericia Spanish Chair", "Knoll Barcelona Chair", "Knoll Wassily",
                   "Knoll Womb Chair", "Cassina LC2", "Cassina LC4 Chaise Longue",
                   "Ligne Roset Togo", "B&B Italia Camaleonda",
                   "Pierre Jeanneret Chandigarh Office Chair"],
        "looks": {
            "Herman Miller Eames Lounge Chair 670/671": "low lounge chair of three curved "
                "plywood shells in dark veneer with black leather cushions, five-star "
                "swivel base, matching ottoman",
            "Vitra Eames EA 117 / EA 119": "office chair: polished aluminium side frames "
                "with a taut fabric or leather sling with horizontal ribs stretched "
                "between them, five-star base",
            "Vitra Eames Soft Pad EA 217 / EA 219": "the same aluminium side frames, with "
                "thick stitched leather pad cushions instead of a sling",
            "Fritz Hansen Egg Chair": "tall upholstered shell shaped like an egg that "
                "wraps around the sitter, on a four-star aluminium swivel foot",
            "Fritz Hansen Swan Chair": "low upholstered shell with curved arms rising "
                "like wings, no straight lines, four-star swivel foot",
            "Fritz Hansen PK22": "low lounge chair: flat brushed steel frame with two "
                "bow-shaped feet, leather or cane seat and back in one piece",
            "Carl Hansen CH24 Wishbone": "wooden dining chair with a Y-shaped back "
                "splat, one steam-bent curved top rail that forms the arms, woven paper "
                "cord seat",
            "Carl Hansen CH25": "low wooden lounge chair with woven paper cord seat and "
                "back, flat wide armrests, open frame",
            "Getama GE290": "low Danish easy chair: open solid wood frame with flat "
                "armrests, loose seat cushion and separate back cushions on a "
                "spring frame",
            "PP Mobler Papa Bear (PP19)": "big upholstered wingback armchair whose wooden "
                "armrests end in carved 'paws' sticking out in front",
            "Fredericia Spanish Chair": "low wide wooden chair with very broad flat "
                "armrests, thick saddle leather seat and back strapped with buckles",
            "Knoll Barcelona Chair": "X-shaped polished flat steel frame, square leather "
                "cushions tufted with buttons in a grid",
            "Knoll Wassily": "chrome tubular steel frame with black leather or canvas "
                "straps as seat, back and armrests",
            "Knoll Womb Chair": "large moulded upholstered shell like a cupped hand, "
                "loose seat and back cushions, thin chrome rod legs",
            "Cassina LC2": "cube armchair: thick leather cushions held in an exposed "
                "chrome tubular frame cage",
            "Cassina LC4 Chaise Longue": "curved chrome cradle resting on a black "
                "H-shaped base, long thin leather or cowhide mat, headroll",
            "Artifort Mushroom F560": "low mushroom-shaped chair in stretch fabric, "
                "rounded seat and flared back in one form, no visible legs",
            "Artifort Ribbon F582": "one continuous ribbon loop of stretch fabric on a "
                "lacquered wooden disc base",
            "Artifort Orange Slice F437": "two curved upholstered shells like orange "
                "slices, seat and back, on a chrome four-leg cross frame",
            "Spectrum SZ01 / SZ02": "1960s Dutch easy chair: bent steel tube frame, "
                "black or chrome, with loose leather or fabric seat and back cushions",
            "Gispen 412": "1930s Dutch tubular steel armchair, chrome or black frame "
                "with continuous curved tube armrests, upholstered seat and back",
            "Ligne Roset Togo": "low frameless seat made only of folded, pleated foam "
                "upholstery like a sleeping bag, no legs",
            "De Sede DS-600": "modular snake sofa of many curved leather segments in a "
                "row, no visible frame",
            "B&B Italia Camaleonda": "low modular sofa blocks with deep square quilting "
                "and metal rings in the seams",
            "Charlotte Perriand Les Arcs Dining Chair": "rustic solid wood dining chair "
                "with a rush or straw seat and plain slatted back",
            "Pierre Jeanneret Chandigarh Office Chair": "teak chair with V-shaped "
                "compass legs, cane seat and curved cane back",
            "Percival Lafer MP-41 Lounge": "low Brazilian lounge chair, bent hardwood "
                "frame with loose leather cushions on a leather sling",
            "Artek Armchair 400 Tank": "wide low armchair whose sides are broad flat "
                "bands of bent birch plywood, upholstered seat",
        },
        "search": {
            "Herman Miller Eames Lounge Chair 670/671": "eames lounge chair",
            "Vitra Eames EA 117 / EA 119": "eames ea 117",
            "Vitra Eames Soft Pad EA 217 / EA 219": "eames soft pad",
            "Carl Hansen CH24 Wishbone": "wishbone chair",
            "Getama GE290": "ge290",
            "PP Mobler Papa Bear (PP19)": "papa bear chair",
            "Fredericia Spanish Chair": "spanish chair mogensen",
            "Artifort Mushroom F560": "artifort mushroom",
            "Artifort Ribbon F582": "artifort ribbon",
            "Artifort Orange Slice F437": "orange slice artifort",
            "Spectrum SZ01 / SZ02": "spectrum sz01",
            "Charlotte Perriand Les Arcs Dining Chair": "perriand les arcs",
            "Pierre Jeanneret Chandigarh Office Chair": "jeanneret chandigarh",
            "Percival Lafer MP-41 Lounge": "percival lafer",
            "Artek Armchair 400 Tank": "artek tank",
        },
        "aliases": {
            "PP Mobler Papa Bear (PP19)": ["pp mobler", "pp mobel"],
            "Herman Miller Eames Lounge Chair 670/671": ["vitra"],
        },
        "reject": r"kussen|hoes|\bcover|bekleding|^poef|^hocker|ottoman$",
        "prompt": {
            "clues": '"leer", "buisframe", "jaren 60", "draaivoet", a label under the seat',
            "parts": 'Loose cushions, covers and footstools on their own are "unknown".',
            "types": "A different type of seat (dining chair, lounge chair, office chair, "
                     "sofa) than the model is never that model.",
        },
    },
    "bikes": {
        "source": "Road Bikes", "daily": False, "flip": "bikes", "noun": "road bikes",
        "queries": ["vintage racefiets", "oude racefiets", "retro racefiets",
                    "stalen racefiets", "klassieke racefiets", "italiaanse racefiets",
                    "racefiets campagnolo", "racefiets shimano 600", "racefiets columbus",
                    "racefiets reynolds 531", "racefiets jaren 70", "racefiets jaren 80",
                    "racefiets opknapper", "racefiets chroom", "koersfiets",
                    "wielrenfiets vintage"],
        "designers": ["ernesto colnago", "ugo de rosa", "giovanni pinarello"],
        "generic": ["super", "steel", "record", "team", "pro", "sport", "amsterdam",
                    "built", "champion", "slx", "aa"],
        "stop": ["rosa", "torino"],
        # "Klein" (small) and "Look" are everyday Dutch and English words
        "brand_keys": {"Klein Quantum": ["klein quantum", "klein bikes"],
                       "Look KG86": ["look kg86", "look kg 86", "look cycle"]},
        "copied": ["Colnago Super / Mexico", "De Rosa Professional SLX",
                   "Pinarello Montello SLX", "Eddy Merckx Corsa Extra",
                   "Tommasini Tecno", "Cinelli Supercorsa", "RIH Sport (Amsterdam built)",
                   "Gazelle Champion Mondial AA", "Koga Miyata FullPro"],
        "looks": {
            "Colnago Master": "steel frame with star-shaped fluted (crimped) tubes, "
                "clover cut-outs in the lugs and fork crown, often bold art-deco paint",
            "Colnago Arabesque": "steel frame with ornate chrome lugs engraved in "
                "arabesque swirls, clover cut-outs",
            "Colnago C40": "carbon tubes joined by carbon lugs, straight-bladed carbon "
                "fork, 1990s",
            "Colnago Super / Mexico": "classic Italian lugged round-tube steel frame, "
                "clover cut-out in the fork crown or bottom bracket",
            "De Rosa Professional SLX": "Italian lugged steel frame, chrome fork crown, "
                "heart emblem on the head tube",
            "Pinarello Montello SLX": "Italian lugged steel frame with a sloping fork "
                "crown, often Del Tongo or team paint",
            "Bianchi Specialissima (steel)": "lugged steel frame in celeste (pale "
                "turquoise) paint with chrome details",
            "Eddy Merckx Corsa Extra": "Belgian lugged steel frame, often in Molteni "
                "orange or 7-Eleven team colours",
            "Eddy Merckx MX Leader": "lugged steel frame whose down tube and chain stays "
                "have spiral ribs inside, oval Columbus MAX tubes",
            "Cinelli Supercorsa": "Italian lugged steel frame with long pointed lugs and "
                "a sloping fork crown, Campagnolo parts",
            "Cinelli Laser": "welded aero frame with smooth sculpted fins where the tubes "
                "meet, no lugs, teardrop tubes",
            "Tommasini Tecno": "Italian lugged steel frame with ornate cut lugs, often "
                "chrome-plated",
            "Gios Torino Super Record": "lugged steel frame in deep royal blue paint, "
                "chrome fork with a coin set in the crown",
            "Raleigh Team Pro 753": "TI-Raleigh team livery: red, yellow and black "
                "bands, slim lugged steel",
            "Gazelle Champion Mondial AA": "Dutch lugged steel frame, often red or "
                "orange with chrome lugs and fork tips",
            "Koga Miyata FullPro": "Japanese-built Koga top road bike: lugged steel "
                "in the 1980s, aluminium later, often Dura-Ace parts",
            "RIH Sport (Amsterdam built)": "Dutch handbuilt lugged steel frame, "
                "hand-painted pin striping and lug lining, often orange or red",
            "Peugeot PX10": "white Reynolds 531 frame with ornate Nervex lugs and "
                "coloured or chequered bands on the tubes, French parts",
            "Look KG86": "early carbon tubes bonded into aluminium lugs, often La Vie "
                "Claire Mondrian-style colour blocks",
            "Klein Quantum": "oversized smooth aluminium tubes, fade or splatter paint, "
                "internal cables",
        },
        "search": {
            "Colnago Super / Mexico": "colnago super",
            "Bianchi Specialissima (steel)": "bianchi specialissima",
            "Gios Torino Super Record": "gios super record",
            "RIH Sport (Amsterdam built)": "rih sport",
            "Gazelle Champion Mondial AA": "gazelle champion mondial",
        },
        "aliases": {"De Rosa Professional SLX": ["derosa"]},
        "reject": r"\bframe|frameset|\bvork\b|\bwiel|velg|zadel|\bstuur|kaders?\b|"
                  r"shirt|trui|\bjersey|\bpet\b|\bcap\b",
        "prompt": {
            "clues": '"campagnolo", "columbus", "531", "jaren 80", a decal on the tubes',
            "parts": 'Loose frames, wheels and parts are "unknown".',
            "types": "A city, touring or mountain bike is never a road bike model.",
        },
    },
    "jackets": {
        "source": "Jackets", "daily": False, "flip": None, "noun": "jackets and coats",
        # No /flip page yet: the plain search and Marktplaats categories live here.
        # Heren- en Damesjassen, leren jassen, motorkleding
        "page": {"fresh_query": "vintage jas",
                 "fresh_categories": {647, 630, 2788, 2784, 689},
                 "watch": ["Schott", "Levis", "Lee", "Carhartt", "Barbour", "Belstaff",
                           "Stone Island", "Moncler", "Burberry"]},
        "queries": ["vintage leren jas", "leren jack vintage", "vintage spijkerjas",
                    "oude spijkerjas", "vintage bomberjack", "vintage parka",
                    "vintage donsjas", "vintage werkjas", "motorjas leer vintage",
                    "vintage trenchcoat", "vintage regenjas", "vintage outdoor jas",
                    "jaren 80 jas", "jaren 90 jas", "tweed jasje", "suede jas vintage"],
        "designers": ["big e", "lvc", "nuptse", "compass badge"],
        "generic": ["leather", "jacket", "vintage", "down", "parka", "type", "icon",
                    "collab", "mountain", "tech", "shearling", "biker", "trench", "tweed",
                    "storm", "rider", "big", "goggle", "iii", "ii", "model"],
        "stop": ["leathers", "leather", "studios", "stone", "island", "north", "face",
                 "real", "company", "canada", "goose"],
        "aliases": {
            "Levi's Type I 506XX": ["levis"], "Levi's Type II 507XX": ["levis"],
            "Levi's Type III 557 / 70505 Big E": ["levis"],
            "C.P. Company Mille Miglia Goggle Jacket": ["cp company"],
            "Arc'teryx Alpha SV": ["arcteryx"],
            "The North Face Steep Tech Apogee": ["north face", "tnf"],
            "The North Face Supreme Collab Mountain / Nuptse": ["north face", "tnf"],
            "The Real McCoy's Type A-2": ["real mccoys", "mccoys"],
        },
        "search": {
            "Schott NYC Perfecto 618 / 613": "schott perfecto",
            "Lewis Leathers Lightning / Cyclone": "lewis leathers",
            "Avirex A-2 / Icon Leather": "avirex",
            "Jeff Hamilton NBA Championship Leather": "jeff hamilton",
            "Rick Owens Stooges Leather": "rick owens stooges",
            "Levi's Type I 506XX": "levis 506xx",
            "Levi's Type II 507XX": "levis 507xx",
            "Levi's Type III 557 / 70505 Big E": "levis big e jacket",
            "Lee 101-J Storm Rider": "lee storm rider",
            "C.P. Company Mille Miglia Goggle Jacket": "cp company goggle",
            "The North Face Supreme Collab Mountain / Nuptse": "supreme north face",
            "The Real McCoy's Type A-2": "real mccoys a-2",
            "Dainese Vintage Race Leather": "dainese leren pak",
            "Helmut Lang Bondage / Astro Biker": "helmut lang jacket",
            "Burberry Vintage Trench": "burberry trenchcoat",
        },
        # Fakes and lookalikes are everywhere, and the value sits in labels a
        # listing photo rarely shows: no jacket is ever a public "strong" find.
        "copied": "all",
        "looks": {
            "Schott NYC Perfecto 618 / 613": "black cowhide biker jacket, diagonal "
                "front zip, belted waist, snap-down lapels, epaulettes with star studs",
            "Lewis Leathers Lightning / Cyclone": "heavy horsehide or steerhide biker "
                "jacket, asymmetric zip, D-shaped pocket, quilted lining",
            "Vanson Model B": "thick competition-weight leather biker, asymmetric zip, "
                "belt, gusseted back",
            "Aero Leather Highwayman": "1930s-style horsehide jacket with half belt, "
                "center zip, slash pockets",
            "Avirex A-2 / Icon Leather": "brown flight jacket in goatskin or horsehide, "
                "knit cuffs and waistband, epaulettes, two flap pockets, snap collar",
            "Jeff Hamilton NBA Championship Leather": "leather jacket covered in "
                "multicolour team logos and embroidered championship patches",
            "Rick Owens Stooges Leather": "thin soft cropped biker jacket, asymmetric "
                "zip, quilted shoulder panels, ribbed sleeve panels",
            "Acne Studios Velocite Shearling": "shearling biker jacket with wide "
                "exposed wool lapels, asymmetric zip, belt",
            "Levi's Type I 506XX": "1930s-50s denim jacket with ONE chest flap pocket, "
                "front pleats and a cinch buckle on the back",
            "Levi's Type II 507XX": "1950s-60s denim jacket with TWO chest flap pockets "
                "and pleats beside the buttons, waistband adjusters",
            "Levi's Type III 557 / 70505 Big E": "denim trucker jacket with pointed "
                "V-seams running down from the two chest pockets, red tab",
            "Lee 101-J Storm Rider": "denim jacket with blanket lining and brown "
                "corduroy collar, one chest pocket",
            "Stone Island Ice Jacket": "colour-changing (heat-sensitive) technical "
                "jacket, detachable compass badge on the left sleeve",
            "Stone Island Tela Stella": "rubberised or coated technical jacket, compass "
                "badge on the left sleeve",
            "C.P. Company Mille Miglia Goggle Jacket": "hood with built-in goggle "
                "lenses, a small lens on the wrist",
            "Arc'teryx Alpha SV": "technical shell jacket, taped seams, helmet hood, "
                "water-tight zips",
            "The North Face Steep Tech Apogee": "1990s ski jacket in bold colour "
                "blocks with padded shoulders and elbows",
            "The North Face Supreme Collab Mountain / Nuptse": "box-quilted puffer or "
                "shell in loud printed patterns",
            "Moncler Grenoble Vintage Down": "glossy nylon quilted down jacket, felt "
                "rooster patch on the sleeve",
            "Canada Goose Expedition Parka": "heavy parka, fur-trimmed hood, round "
                "patch on the upper sleeve, many pockets",
            "Carhartt Detroit Jacket": "short tan or brown duck canvas jacket, "
                "corduroy collar, blanket lining, chest pocket",
            "The Real McCoy's Type A-2": "high-end brown horsehide A-2 flight jacket, "
                "knit cuffs and waistband, epaulettes",
            "Belstaff Trialmaster": "waxed cotton motorcycle jacket, four flap pockets, "
                "belt, corduroy collar",
            "Dainese Vintage Race Leather": "racing leathers with hard knee and "
                "shoulder pads, bold team colours",
            "Chanel Tweed Jacket": "boxy boucle tweed jacket with braided trim on the "
                "edges, gold or jewel buttons, chain in the hem",
            "Helmut Lang Bondage / Astro Biker": "minimal black leather biker with "
                "straps, or padded astro shoulders, late 1990s",
            "Burberry Vintage Trench": "beige gabardine trench coat, double-breasted, "
                "epaulettes, storm flap, belt, check lining",
        },
        "reject": r"patch|knoop|button|\bbadge|\bbroek|\bpet\b|\bcap\b|"
                  r"shirt|trui|sweater|hoodie|jeans",
        "prompt": {
            "clues": '"leer", "paardenleer", "jaren 70", "gevoerd", a label in the collar',
            "parts": 'Loose badges, patches and accessories are "unknown".',
            "types": "A different garment (vest, trousers, shirt) than the model is never "
                     "that model.",
        },
    },
    "bags": {
        "source": "Bags", "daily": False, "flip": None, "noun": "handbags",
        # Tassen dames, Schoudertassen
        "page": {"fresh_query": "vintage tas",
                 "fresh_categories": {626, 1840},
                 "watch": ["Louis Vuitton", "Chanel", "Hermes", "Gucci", "Prada", "Dior",
                           "Fendi", "Delvaux", "Mulberry", "Michael Kors"]},
        "queries": ["vintage handtas", "leren tas vintage", "oude handtas",
                    "vintage schoudertas", "vintage tas leer", "bruine leren tas",
                    "zwarte leren handtas", "tas met slot", "tas met ketting",
                    "gewatteerde tas", "tas bamboe handvat", "vintage reistas",
                    "canvas tas leren hengsels", "kleine handtas vintage", "zadeltas",
                    "vintage clutch"],
        "designers": ["monogram", "damier", "intrecciato", "cannage", "guccissima",
                      "lagerfeld", "ysl"],
        "generic": ["medium", "lock", "top", "handle", "edition", "nylon", "tote", "saint",
                    "louis", "accessoires", "multicolore", "on", "motorcycle", "reissue",
                    "pm", "mm"],
        "stop": ["saint", "laurent", "italia"],
        "aliases": {"Yves Saint Laurent Mombasa": ["ysl", "saint laurent"]},
        "search": {
            "Hermes Birkin 30 / 35": "hermes birkin", "Hermes Kelly 28 / 32": "hermes kelly",
            "Chanel Classic Flap Medium": "chanel classic flap",
            "Chanel 2.55 Reissue": "chanel 2.55", "Chanel Wallet on Chain": "chanel woc",
            "Louis Vuitton Keepall 50 / 55": "louis vuitton keepall",
            "Louis Vuitton Speedy Multicolore (Murakami)": "speedy multicolore",
            "Gucci Bamboo Top Handle": "gucci bamboo",
            "Prada Re-Edition 2005 Nylon": "prada re-edition",
            "Celine Luggage Tote": "celine luggage", "Celine Classic Box": "celine box",
            "Balenciaga City / Motorcycle": "balenciaga city",
            "Goyard Saint Louis PM": "goyard saint louis",
        },
        # Fakes are everywhere and a listing photo can't prove a bag is real:
        # no bag is ever a public "strong" find.
        "copied": "all",
        "looks": {
            "Hermes Birkin 30 / 35": "structured trapezoid bag, two rolled top handles, "
                "flap with a turn-lock strap, padlock and leather key bell",
            "Hermes Kelly 28 / 32": "structured trapezoid bag with ONE top handle, flap "
                "held by two straps and a turn-lock, shoulder strap, key bell",
            "Hermes Constance": "compact flap shoulder bag with a large H-shaped metal "
                "clasp on the flap",
            "Hermes Evelyne": "soft leather shoulder bag with an H punched in holes on "
                "one side, canvas strap",
            "Hermes Picotin Lock": "small bucket bag, two short handles, a strap across "
                "the top with a padlock",
            "Hermes Garden Party": "wide open tote in canvas or leather, leather trim, "
                "single stud closure",
            "Chanel Classic Flap Medium": "diamond-quilted leather flap bag, chain strap "
                "woven with leather, interlocking CC turn-lock",
            "Chanel 2.55 Reissue": "diamond-quilted flap bag with a rectangular turn-lock "
                "and an all-metal chain strap",
            "Chanel Diana Flap": "older, softer quilted flap bag with a chain woven with "
                "leather and a CC turn-lock",
            "Chanel Wallet on Chain": "small quilted wallet-sized flap bag on a chain",
            "Louis Vuitton Speedy 30": "soft barrel-shaped bag, two rolled handles, zip "
                "top, padlock, brown monogram or checker canvas with tan leather trim",
            "Louis Vuitton Keepall 50 / 55": "large soft barrel duffle, two handles, "
                "brown monogram canvas, tan leather trim",
            "Louis Vuitton Neverfull MM": "wide soft open tote, thin straps cinched by "
                "side laces, canvas with tan trim",
            "Louis Vuitton Alma": "dome-shaped structured bag, rounded zip top, two "
                "handles, padlock",
            "Louis Vuitton Pochette Accessoires": "small rectangular zip pouch with a "
                "short thin strap, canvas",
            "Louis Vuitton Speedy Multicolore (Murakami)": "Speedy barrel shape in white "
                "or black canvas with a multicolour pattern",
            "Dior Saddle": "kidney-shaped asymmetric saddle bag with a dangling metal D "
                "charm, short strap",
            "Dior Lady Dior": "structured square bag with rattan-like cannage stitching, "
                "two rounded handles, dangling letter charms",
            "Fendi Baguette": "small rectangular under-arm bag, short strap, big FF "
                "clasp on the flap",
            "Fendi Peekaboo": "structured top-handle bag that opens like a mouth onto "
                "two compartments, turn-locks on the sides",
            "Gucci Jackie": "crescent hobo shoulder bag with a piston clasp",
            "Gucci Bamboo Top Handle": "structured leather bag with a curved bamboo "
                "handle",
            "Prada Re-Edition 2005 Nylon": "small nylon shoulder bag with a detachable "
                "mini pouch, triangle plaque",
            "Bottega Veneta Jodie": "soft woven-leather hobo with a knot at the handle "
                "base",
            "Bottega Veneta Cassette": "padded woven-leather rectangular crossbody",
            "Celine Luggage Tote": "tote that looks like a face: front zip pocket as a "
                "mouth, wing-like sides",
            "Celine Classic Box": "structured rectangular flap bag with a metal clasp",
            "Balenciaga City / Motorcycle": "soft distressed leather bag, tassel zip "
                "pulls, studs and buckles",
            "Loewe Puzzle": "geometric patchwork of leather panels, folds flat",
            "Goyard Saint Louis PM": "open tote in chevron dotted canvas, thin handles",
            "Delvaux Brillant": "structured trapezoid bag with a large D-shaped metal "
                "buckle clasp",
            "Yves Saint Laurent Mombasa": "hobo bag with a curved horn handle",
            "Chloe Paddington": "soft satchel with a huge padlock hanging on the front",
        },
        "reject": r"stofzak|dustbag|portemonnee|\bwallet$|\briem|strap\b|hengsel|"
                  r"charm|sleutelhanger|doos\b|\bbox$|\bbon\b|organizer|insert",
        "prompt": {
            "clues": '"echt leer", "gewatteerd", "slotje", "jaren 90", a stamp inside',
            "parts": 'Loose straps, dust bags, boxes and charms are "unknown".',
            "types": "A different type of bag (backpack, wallet, tote, clutch) than the "
                     "model is never that model.",
        },
    },
    "boats": {
        "source": "Boats", "daily": False, "flip": None, "noun": "boats",
        # Kajuitzeilboten, Open zeilboten, Sloepen, Speedboten, Motorboten,
        # Consoleboten, Roeiboten
        "page": {"fresh_query": "boot", "fresh_categories": {985, 990, 1407, 994, 989,
                                                             1408, 1264},
                 "watch": ["Van de Stadt", "Waarschip", "Valk", "Sloep", "Bayliner",
                           "Quicksilver", "Marieholm", "Kaag"]},
        "price": (500, 20000),
        "queries": ["zeilboot", "kajuitzeilboot", "open zeilboot", "klassieke zeilboot",
                    "polyester zeilboot", "houten zeilboot", "zeilboot met buitenboordmotor",
                    "kielboot", "sloep", "polyester sloep", "motorboot", "houten motorboot",
                    "mahonie boot", "kajuitboot", "toerboot", "consoleboot"],
        "designers": ["van de stadt", "uffa fox", "tord sundén", "sunden",
                      "rod johnstone", "olle enderlein", "enderlein", "pelle petterson"],
        "generic": ["touring", "family", "explorer", "mahogany", "motorboat", "sport",
                    "international", "if"],
        "stop": ["boats", "nordic", "cornish", "crabbers", "boston"],
        "brand_keys": {"J/Boats J/22": ["j 22", "j22"], "J/Boats J/24": ["j 24", "j24"],
                       "Cornish Crabbers Shrimper 19": ["shrimper", "cornish crabbers"]},
        # model numbers sellers don't write: any boat of the brand counts
        "model_keys": {"Interboat 19 / 6.5": [], "Boston Whaler 13 Sport / Montauk 17": [],
                       "Coronet 24 Family / Explorer": [],
                       "Marieholm International Folkboat (IF)": [],
                       "Albin Albin 25": ["albin25", "25"]},
        "copied": ["Antaris Fifty5", "Interboat 19 / 6.5", "Makma Caribbean 21",
                   "Oud Huijzer 575 / 616", "Maxima 630", "Maril 6Nine",
                   "Marieholm International Folkboat (IF)", "Nordic Folkboat Folkboat",
                   "Boston Whaler 13 Sport / Montauk 17",
                   "Pettersson Mahogany Motorboat", "J/Boats J/22", "J/Boats J/24"],
        "looks": {
            "Antaris Fifty5": "compact modern polyester sloep around 5.5 m, wide open "
                "cockpit, curved bench seating, steering console",
            "Interboat 19 / 6.5": "classic-lined polyester sloep 6 to 6.5 m, teak "
                "gunwale and floor, small steering console",
            "Makma Caribbean 21": "polyester sloep about 6.4 m, high freeboard, lots of "
                "cushions",
            "Oud Huijzer 575 / 616": "polyester sloep with a traditional curved sheer "
                "and wooden trim",
            "Maxima 630": "modern polyester sloep 6.3 m, high bow, wide U-shaped seating",
            "Maril 6Nine": "modern 6.9 m tender with a straight high bow and very clean "
                "flat lines",
            "Randmeer Randmeer Touring": "Dutch open keel sailing boat about 6 m, long "
                "open cockpit, no cabin",
            "Regenboog Regenboog": "long narrow 7.6 m Dutch racing keelboat, tall rig, "
                "open cockpit, no cabin, often varnished wood",
            "Pampus Pampus": "slim 7.6 m Dutch open keelboat with long overhangs at bow "
                "and stern, no cabin",
            "Polyvalk Polyvalk": "6.5 m open polyester sailing boat, round bilge, "
                "centreboard, falcon emblem on the sail",
            "Marieholm International Folkboat (IF)": "7.9 m Scandinavian keelboat, long "
                "overhangs, small low cabin, outboard well",
            "Nordic Folkboat Folkboat": "7.6 m keelboat with overlapping clinker planks, "
                "small cabin, rudder hung on the transom",
            "Albin Vega 27": "8.2 m cabin sailboat, rounded coachroof with small "
                "windows, masthead rig",
            "Contessa Contessa 26": "7.9 m cabin sailboat with long overhangs, narrow "
                "beam and a pronounced sheer",
            "Victoire Victoire 26": "Dutch 7.9 m cabin sailboat, sturdy, with a low "
                "coachroof",
            "Hallberg-Rassy Monsun 31": "9.4 m blue-water cruiser, white hull with a "
                "blue stripe, teak deck, fixed windscreen",
            "Drascombe Lugger": "5.7 m open boat pointed at both ends, tan sails, small "
                "mizzen at the stern",
            "Cornish Crabbers Shrimper 19": "small gaff-rigged boat with a little cabin, "
                "tan sails, bowsprit",
            "J/Boats J/22": "6.7 m sport keelboat, small cabin, tall fractional rig",
            "J/Boats J/24": "7.3 m sport keelboat, low cabin, big open cockpit",
            "Boston Whaler 13 Sport / Montauk 17": "small white open motorboat with a "
                "three-hull 'cathedral' bow, wooden console and seat",
            "Pettersson Mahogany Motorboat": "classic varnished mahogany motorboat, long "
                "foredeck, windscreen, inboard engine",
            "Coronet 24 Family / Explorer": "Danish motor cruiser with a raked "
                "windscreen and small cabin, blue or white hull",
            "Albin Albin 25": "Swedish small motor cruiser, high wheelhouse, sturdy "
                "rounded hull, diesel",
            "Saga Saga 27": "Norwegian motor cruiser with a sturdy wheelhouse and deep "
                "V hull",
            "Doerak 780 / 850": "Dutch cabin sloep-cruiser with a fixed or folding "
                "cabin and displacement hull",
        },
        "search": {"Nordic Folkboat Folkboat": "folkboat",
                   "Randmeer Randmeer Touring": "randmeer",
                   "Regenboog Regenboog": "regenboog zeilboot",
                   "Pampus Pampus": "pampus zeilboot",
                   "Polyvalk Polyvalk": "polyvalk",
                   "Pettersson Mahogany Motorboat": "pettersson",
                   "Marieholm International Folkboat (IF)": "marieholm"},
        "reject": r"\bzeil\b|zeilen\b|dekkleed|huik|\bkap\b|trailer|\bmast\b|"
                  r"model|onderdel|inkoop|opkoper|gezocht|ligplaats|stalling|registratie",
        "prompt": {
            "clues": '"polyester", "kajuit", "kiel", "bouwjaar 1975", a builder\'s plate',
            "parts": 'Sails, covers, trailers and loose engines are "unknown".',
            "types": "A motorboat is never a sailing model and a sailing boat is never a "
                     "motorboat model; a boat clearly much larger or smaller than the "
                     "model's length is never that model.",
        },
    },
}

HUNT_PRICE_MAX = 250    # asking price cap, the same as the rest of /flip
HUNT_PRICE_MIN = 10     # €1 "n.o.t.k." placeholders aren't real prices
NEG_PRICE = (20, 250)   # asking price range of the test's ordinary listings
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
                         r"kopie|copy|onderdel|kap\b|shade\b|gezocht|gevraagd|fitting|"
                         r"\bvoor\b|boek|book|poster", re.I)


def _norm(text):
    """Lowercase, accents stripped, only letters and digits: 'Jieldé' -> 'jielde'."""
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", " ", text.decode().lower()).strip()


def _page(key):
    """The /flip page settings a category searches with, plus its overrides."""
    cat = CATEGORIES[key]
    page = dict(FLIP_PAGES.get(cat.get("flip")) or {})
    page.update(cat.get("page", {}))
    return page


def _price(key, default):
    """A category's (min, max) asking price, or the default."""
    return CATEGORIES[key].get("price", default)


def _is_copied(key, name):
    copied = CATEGORIES[key].get("copied", [])
    return copied == "all" or name in copied


def _rejected(key, title):
    """True for titles that aren't the item itself: copies, parts, wanted ads."""
    t = _norm(title)
    extra = CATEGORIES[key].get("reject")
    return bool(_REPLICA_RE.search(t) or (extra and re.search(extra, t)))


def load_models(key):
    """The valuable models for one category, each with a display name, the words
    that would mean the seller already knows what it is, and prices."""
    with open(MODELS_FILE, encoding="utf-8") as f:
        items = json.load(f)["items"]
    cat = CATEGORIES[key]
    generic = _GENERIC | set(cat.get("generic", []))
    stop = _BRAND_STOP | set(cat.get("stop", []))
    models = []
    for it in items:
        if it.get("category") != cat["source"]:
            continue
        brand, model = it["brand"], it["model"]
        words = [w for w in _norm(model).split() if w not in generic]
        # "PH 3/2" -> "ph32", matched with spaces squashed out ("PH 3 2", "PH3/2")
        # ("AJ" is too short to squash, so it only counts as a whole word)
        squashed = "".join(words)
        keys = [w for w in words if len(w) >= 3] + ([squashed] if squashed else [])
        keys = cat.get("model_keys", {}).get(f"{brand} {model}", keys)
        brand_words = [w for w in _norm(brand).split()
                       if len(w) >= 4 and w not in stop]
        name = f"{brand} {model}"
        aliases = [_norm(a) for a in cat.get("aliases", {}).get(name, [])]
        brand_keys = {_norm(brand), *brand_words, *aliases}
        if name in cat.get("brand_keys", {}):
            brand_keys = {_norm(b) for b in cat["brand_keys"][name]}
        # plain words a seller would type: no "Table", "Floor (10A, UF4)"
        query = " ".join([brand] + [w for w in re.sub(r"\(.*?\)", "", model).split()
                                    if _norm(w) not in generic])
        models.append({
            "name": name,
            "query": cat.get("search", {}).get(name, query),
            "brand_keys": sorted(brand_keys),
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
photograph stamps, so a missing stamp alone is no reason to doubt. %(parts)s When the item
looks like none of the models, answer "unknown". %(types)s
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
             "content": RECOGNIZE_PROMPT % {**CATEGORIES[key]["prompt"],
                                            "noun": CATEGORIES[key]["noun"],
                                            "catalog": catalog}},
            {"role": "user", "content": content},
        ],
        max_tokens=400,
        # the free fallback can't be trusted with photos; a failed call is skipped
        models=MODELS[:1],
    )
    names = {m["name"] for m in models}
    match = str(result.get("match") or "").strip()
    raw = "strong" if result.get("confidence") == "strong" else "possible"
    copied = _is_copied(key, match)
    confidence = "possible" if copied else raw
    why = str(result.get("why") or "").replace("\u2014", ",").replace("\u2013", "-")
    return {"match": match if match in names else None,   # check it in code
            "confidence": confidence,
            "copied_strong": copied and raw == "strong",
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
    page = _page(key)
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
        # the title isn't stored; printed so the labels can be checked by hand
        print(f"    + {l['url']}  {l['title'][:70]}")
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
            # in the category's own Marktplaats categories: a Chanel bag is
            # never the Chanel jacket
            if (names_model(l["title"], m) and not _rejected(key, l["title"])
                    and l.get("category_id") in page["fresh_categories"]):
                kept += add(l, m["name"])
        note = "" if kept >= 3 else "  <- too few, check by hand"
        print(f"  {m['name']}: {kept}{note}")
        time.sleep(SEARCH_PAUSE_S)

    negatives = have["none"]
    found = []
    if negatives < EVAL_NEGATIVES:
        try:
            lo, hi = _price(key, NEG_PRICE)
            found, _total = search_marktplaats(page["fresh_query"], price_min_euro=lo,
                                               price_max_euro=hi, limit=60)
        except Exception as e:
            print(f"  ! negatives search failed: {e}", file=sys.stderr)
    for l in found:
        if negatives >= EVAL_NEGATIVES:
            break
        text = f"{l['title']} {l['description']}"
        if (l.get("category_id") in page["fresh_categories"]
                and not _rejected(key, l["title"])
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
    page = _page(key)
    lo, hi = _price(key, NEG_PRICE)
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
                    {"price_min_euro": lo, "price_max_euro": hi, "limit": 60}))
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
    # copied models are always "possible"; this is how often the model itself
    # said strong for one, right and wrong
    copied_ok = sum(1 for c, r in pos if r.get("copied_strong") and r["match"] == c["truth"])
    copied_bad = sum(1 for c, r in pos if r.get("copied_strong") and r["match"] != c["truth"])
    copied_neg = sum(1 for _c, r in neg if r.get("copied_strong"))

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
    if copied_ok + copied_bad + copied_neg:
        print(f"Said strong for a copied model (shown as possible): "
              f"{copied_ok} right, {copied_bad} wrong, {copied_neg} on ordinary listings")
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
    page = _page(key)
    designers = cat.get("designers", [])
    lo, hi = _price(key, (HUNT_PRICE_MIN, HUNT_PRICE_MAX))
    listings, seen = [], set()
    for q in cat["queries"]:
        try:
            found, _total = search_marktplaats(q, price_max_euro=hi,
                                               limit=60, exclude_bids=True)
        except Exception as e:
            print(f"  ! search '{q}' failed: {e}", file=sys.stderr)
            found = []
        for l in found:
            text = f"{l['title']} {l['description']}"
            ask = l.get("asking_euro")
            if (l["id"] in seen or not ask or not lo <= ask <= hi
                    or not l.get("images") or is_auction_lot(l)
                    or _NEW_RE.search(_norm(l["title"]))
                    or (cat.get("reject") and re.search(cat["reject"], _norm(l["title"])))
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
    """Hunt every category (or the given keys) and store the record in Redis."""
    if not OPENROUTER_API_KEY:
        sys.exit("OPENROUTER_API_KEY is not set: recognition needs the LLM.")
    keys = [k for k in CATEGORIES if k in categories] if categories else \
        [k for k in CATEGORIES if CATEGORIES[k].get("daily", True)]
    record = {"date": time.strftime("%Y-%m-%d", time.gmtime()), "ts": time.time(),
              "scanned": 0, "categories": []}
    for key in keys:
        print(f"{key}...")
        finds, scanned = hunt(key)
        record["scanned"] += scanned
        # /flip shows a category under its page key; one without a page is
        # stored under its own key until it gets one
        record["categories"].append({"key": CATEGORIES[key]["flip"] or key,
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
                    help="daily hunt: only this category (repeatable)")
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
