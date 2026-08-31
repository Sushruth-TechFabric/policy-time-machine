"""Synthetic value pools.

Nothing here is drawn from a real person, address book or vehicle registry. The
name pool is invented, birth *year* is the only demographic precision carried
(spec 01 section 3), and `vin` is deliberately absent from the vehicle table so
nobody has to wonder whether the data is real.
"""

from __future__ import annotations

FIRST_NAMES = (
    "Adele", "Bram", "Caris", "Dorian", "Elowen", "Ferris", "Greer", "Halden",
    "Ilona", "Jarek", "Kesler", "Linnea", "Marlow", "Nessa", "Orrin", "Perrin",
    "Quilla", "Rowan", "Saskia", "Tarek", "Ursa", "Verity", "Wendell", "Xanthe",
    "Yarrow", "Zephyr", "Alric", "Brynn", "Calla", "Devan", "Emrys", "Fenna",
    "Gideon", "Hollis", "Iris", "Joss", "Kiera", "Lucan", "Merrit", "Nolan",
    "Oona", "Piers", "Reeve", "Sable", "Tamsin", "Ulric", "Vesper", "Willa",
    "Ysolde", "Zeva", "Ansel", "Brisa", "Cormac", "Delia", "Evrard", "Fable",
    "Garnet", "Hesper", "Ivo", "Juno",
)

LAST_NAMES = (
    "Ashcroft", "Brambleton", "Carrowmore", "Dunleavy", "Ellsworth", "Fairholm",
    "Glenmoor", "Havelock", "Inverness", "Jessamine", "Kilbride", "Langmere",
    "Marchetti", "Northwood", "Oakhaven", "Pembridge", "Quarrington", "Redmayne",
    "Stonebrook", "Thornbury", "Underhill", "Vandermere", "Westerlund", "Yarborough",
    "Zaltana", "Ainsworth", "Blackwood", "Colvin", "Draycott", "Everly",
    "Fenwick", "Grimsby", "Holloway", "Ironside", "Jourdain", "Kestrel",
    "Lindqvist", "Merriweather", "Norrington", "Ostrander", "Pallister", "Quimby",
    "Rutherglen", "Sandoval", "Tremaine", "Ulverston", "Vasquez", "Whitlock",
    "Yeardley", "Ziegler",
)

# (city, state, postal base) - invented placements, five-digit postal codes.
LOCATIONS = (
    ("Ashford Bend", "OH", 44100), ("Bellhaven", "OH", 44300),
    ("Cedar Grange", "MI", 48100), ("Dunmore Park", "MI", 48400),
    ("Eastvale", "IN", 46200), ("Fallbrook Heights", "IN", 46500),
    ("Glenhurst", "IL", 60400), ("Harlowe", "IL", 60700),
    ("Ivyfield", "WI", 53100), ("Junction Mills", "WI", 53500),
    ("Kettering Row", "PA", 15200), ("Larchmont Hollow", "PA", 17100),
    ("Marbury", "NY", 12200), ("Northgate Springs", "NY", 14600),
    ("Orchard Falls", "NJ", 7300), ("Pinewick", "NJ", 8500),
    ("Quarry Ridge", "MD", 21200), ("Rosemont Landing", "MD", 21700),
    ("Saltmarsh", "VA", 23200), ("Thistledown", "VA", 24000),
    ("Umberfield", "NC", 27400), ("Vinehill", "NC", 28200),
    ("Wrenford", "GA", 30300), ("Yarrowdale", "GA", 31400),
    ("Zephyr Point", "FL", 32600), ("Alderbrook", "FL", 33700),
    ("Braddock Fields", "TN", 37200), ("Copperton", "TN", 38100),
    ("Dellwood Cross", "TX", 75200), ("Emberly", "TX", 77300),
    ("Fairmont Reach", "CO", 80200), ("Grantsville Park", "CO", 80900),
    ("Highmoor", "AZ", 85200), ("Ironwood Flats", "AZ", 85700),
    ("Juniper Landing", "WA", 98100), ("Kelso Heights", "WA", 98500),
    ("Lakemont", "OR", 97200), ("Millbrae Cross", "OR", 97400),
    ("Newbury Point", "CA", 92600), ("Overton Sands", "CA", 95800),
)

# make -> models. Invented marques; no real manufacturer is named.
VEHICLES = {
    "Arlo": ("Tessera", "Kite", "Meridian"),
    "Boreal": ("Crest", "Tundra", "Vantage"),
    "Cascadia": ("Ridge", "Loop", "Harbor"),
    "Delmar": ("Sable", "Cadence", "Prospect"),
    "Everline": ("Nimbus", "Halo", "Trace"),
    "Fenwood": ("Trail", "Quarry", "Beacon"),
    "Grantwell": ("Summit", "Verge", "Lantern"),
    "Halcyon": ("Drift", "Aster", "Compass"),
    "Ivorine": ("Solace", "Pique", "Reach"),
    "Juniper": ("Fern", "Willow", "Basin"),
    "Kestrel": ("Talon", "Glide", "Perch"),
    "Lumen": ("Arc", "Ember", "Quartz"),
}

BODY_STYLES = ("sedan", "hatchback", "coupe", "suv", "crossover", "pickup", "minivan", "wagon")

AGENT_REGIONS = ("Great Lakes", "Northeast", "Mid-Atlantic", "Southeast", "South Central", "Mountain", "Pacific")
