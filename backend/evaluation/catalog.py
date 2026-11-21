"""Fictional vocabulary for the synthetic evaluation dataset.

Every supplier, customer and product below is invented. Items carry two paraphrased search queries that
deliberately avoid the item's own words, so semantic search can be measured separately from keyword search.
"""

SUPPLIERS = [
    "Acme Trading Ltd", "Zenith Logistics Inc", "Omega Printing Co", "Nimbus Cloud Services", "Brightway Supplies",
    "Harbor Point Electronics", "Crescent Office Solutions", "Silverline Consulting", "Northwind Hardware",
    "Evergreen Facilities Ltd", "Pioneer Networks GmbH", "Lotus Stationery House", "Redwood Furniture Co",
    "Atlas Freight Partners", "Meridian Software Corp", "Blue Orchid Catering", "Summit Tools Ltd",
    "Keystone Security Systems", "Riverbend Paper Mills", "Tandem Digital Agency", "Coral Bay Trading",
    "Ironclad Industrial Supply", "Maple Leaf Imports", "Delta Wave Communications", "Sunrise Cleaning Services",
]

CUSTOMERS = [
    "Globex Corporation", "Initech Solutions", "Umbrella Retail Group", "Stark Manufacturing", "Wayne Holdings",
    "Hooli Systems", "Vandelay Industries", "Soylent Foods Ltd", "Wonka Confectionery", "Cyberdyne Labs",
    "Oscorp Pharma", "Gringotts Finance", "Pied Piper Media", "Tyrell Engineering", "Massive Dynamic",
]

# (id, description on the invoice, [two paraphrased queries that share no important words with it])
ITEMS = [
    ("chair", "Ergonomic office chair", ["seating furniture for staff", "chairs for the workplace"]),
    ("laptop", "Laptop computer 15 inch", ["portable notebook PC", "mobile computing device"]),
    ("paper", "A4 copier paper ream", ["printing paper supplies", "photocopy sheets"]),
    ("switch", "Network switch 24-port", ["ethernet networking hardware", "LAN connectivity equipment"]),
    ("license", "Annual software license", ["yearly application subscription", "software usage rights renewal"]),
    ("cleaning", "Cleaning services monthly", ["janitorial work", "office sanitation service"]),
    ("freight", "Freight and delivery charge", ["shipping cost", "transport of goods"]),
    ("toner", "Printer toner cartridge", ["ink supplies for laser printer", "printing consumables"]),
    ("hosting", "Web hosting plan", ["internet server space", "website hosting service"]),
    ("consulting", "Consulting hours", ["professional advisory time", "expert guidance sessions"]),
    ("lamp", "LED desk lamp", ["lighting for workstation", "illumination fixture"]),
    ("camera", "Security camera installation", ["surveillance equipment setup", "CCTV fitting work"]),
]

STREETS = ["12 Market Street", "48 Harbour Road", "7 Station Lane", "301 King Avenue", "5 Mill Court", "90 Park Row"]
