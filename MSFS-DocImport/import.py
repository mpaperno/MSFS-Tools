"""
Utility for importing online MSFS SDK Documentation into data structures.

Currently supports importing Event IDs, Simulation Variables, and Sim. Var. Units
by "scraping" the HTML pages of MSFS 2020 or 2024 SDK docs.

Both versions of the documentation can be imported to form a combined database.
The Key Events and Sim Vars tables have individual columns for the two sim versions to
indicate where it is supported and/or deprecated.

Additionally it can import KEY_* macro names and IDs from the MSFS SDK "gauges.h/EventsEnum.h" header.
This is mostly useful for comparison purposes with the published SDK docs. A report can be generated
by using the --ev_report option.

The import destination is an SQLite3 database file. An existing database file is required,
but all tables are created automatically by this script as needed. Any existing data is preserved/updated
unless the --drop option was passed on the command line.

Requires Python 3.12+ with extra modules:  bs4, lxml, requests

Run with -h to see all options with descriptions.
"""

__copyright__ = """
Copyright Maxim Paperno; all rights reserved.

This file may be used under the terms of the GNU
General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

A copy of the GNU General Public License is available at <http://www.gnu.org/licenses/>.
"""

__version__ = "1.1.0"

from argparse import ArgumentParser
from bs4 import BeautifulSoup as soup, Tag as bs4Tag, XMLParsedAsHTMLWarning
import datetime
import lxml
import os
import re
import requests
import sqlite3

# bs4 emits warnings about the HTML pages starting with an xml tag
import warnings
warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)

# require Py 3.12+
import sys
if (sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 12)):
    raise Exception("Requires Python 3.12+")


### Constants

DB_FILE = "./MSFS_SDK_Doc_Import.sqlite3"

MSFS_SDKDOCS_URL    = "https://docs.flightsimulator.com/html/Programming_Tools/"
MSFS_SDKDOCS_URL_24 = "https://docs.flightsimulator.com/msfs2024/html/6_Programming_APIs/"
# This URL seems dead
# MSFS_SDKDOCS_URL_FL = "https://docs.flightsimulator.com/flighting/html/Programming_Tools/"
# Don't know if there are/will be separate 2024 flighting version

MSFS_EVENTS_PATH = "Event_IDs/"
MSFS_EVENTS_INDEX = "Event_IDs.htm"

MSFS_EVENTS_PATH_24 = "Key_Events/"
MSFS_EVENTS_INDEX_24 = "Key_Events.htm"

MSFS_SIMVARS_PATH = "SimVars/"
MSFS_SIMVARS_INDEX = "Simulation_Variables.htm"
MSFS_SIMVARS_UNITS = "Simulation_Variable_Units.htm"

### SQL Table Definitions

DB_TABLE_IMPORT_META = """
	BEGIN;
	CREATE TABLE "ImportMeta" (
		"TableName"	TEXT(20) NOT NULL UNIQUE,
		"LastUpdate"	DATE,
		"FromURL"	TEXT(50),
		PRIMARY KEY("TableName")
	);
	INSERT INTO ImportMeta (TableName) VALUES ('KeyEvents'), ('SimVars'), ('SimVarUnits'), ('KeyEventIDs');
	COMMIT;
"""

# The KeyEvents and SimVars tables have columns "MSFS_10", "MSFS_11" and "MSFS_12" whose values
# are enums indicating support in that version of the sim (2020 and 2024, respectively):
#   0 = not supported
#   1 = supported
#   2 = deprecated
#
# The "Deprecated" column is deprecated since it depends on import order.

DB_TABLE_KEY_EVENTS = """
	BEGIN;
	CREATE TABLE "KeyEvents" (
		"System"	TEXT(50) NOT NULL,
		"Category"	TEXT(50) NOT NULL,
		"Name"	TEXT(50) NOT NULL,
		"Params"	TEXT(300),
		"Description"	TEXT(500),
		"Multiplayer"	TEXT(20),
		"MSFS_10"	NUMERIC(1) DEFAULT 0,
		"MSFS_11"	NUMERIC(1) DEFAULT 0,
		"MSFS_12"	NUMERIC(1) DEFAULT 0,
		"Deprecated"	NUMERIC(1) DEFAULT 0,
		PRIMARY KEY("Name")
	);
	CREATE INDEX "IX_KeyEvents_System" ON "KeyEvents" ("System");
	CREATE INDEX "IX_KeyEvents_Category" ON "KeyEvents" ("Category");
	CREATE INDEX "IX_KeyEvents_MSFS_10" ON "KeyEvents" ("MSFS_10");
	CREATE INDEX "IX_KeyEvents_MSFS_11" ON "KeyEvents" ("MSFS_11");
	CREATE INDEX "IX_KeyEvents_MSFS_12" ON "KeyEvents" ("MSFS_12");
	COMMIT;
"""

DB_TABLE_SIM_VARS = """
	BEGIN;
	CREATE TABLE "SimVars" (
		"System"	TEXT(50) NOT NULL,
		"Category"	TEXT(50) NOT NULL,
		"Name"	TEXT(75) NOT NULL UNIQUE,
		"Description"	TEXT(500),
		"Units"	TEXT(500),
		"Settable"	NUMERIC(1) DEFAULT 0,
		"Multiplayer"	TEXT(20),
		"Indexed"	NUMERIC(1) DEFAULT 0,
		"Component"	NUMERIC(1) DEFAULT 0,
		"MSFS_10"	NUMERIC(1) DEFAULT 0,
		"MSFS_11"	NUMERIC(1) DEFAULT 0,
		"MSFS_12"	NUMERIC(1) DEFAULT 0,
		"Deprecated"	NUMERIC(1) DEFAULT 0,
		PRIMARY KEY("Name")
	);
	CREATE INDEX "IX_SimVars_System" ON "SimVars" ("System");
	CREATE INDEX "IX_SimVars_Category" ON "SimVars" ("Category");
	CREATE INDEX "IX_SimVars_Settable" ON "SimVars" ("Settable");
	CREATE INDEX "IX_SimVars_MSFS_10" ON "SimVars" ("MSFS_10");
	CREATE INDEX "IX_SimVars_MSFS_11" ON "SimVars" ("MSFS_11");
	CREATE INDEX "IX_SimVars_MSFS_12" ON "SimVars" ("MSFS_12");
	COMMIT;
"""

DB_TABLE_SIMVAR_UNITS = """
	BEGIN;
	CREATE TABLE "SimVarUnits" (
		"Measure"	TEXT(20) NOT NULL,
		"Name"	TEXT(50) NOT NULL UNIQUE,
		"ShortName"	TEXT(50) NOT NULL UNIQUE,
		"Aliases"	TEXT(150) NOT NULL,
		"Description"	TEXT(500),
		PRIMARY KEY("Name")
	);
	CREATE INDEX "IX_SimVarUnits_Measure" ON "SimVarUnits" ("Measure");
	CREATE INDEX "IX_SimVarUnits_ShortName" ON "SimVarUnits" ("ShortName");
	COMMIT;
"""

FB_TABLE_KEY_EVENT_IDS = """
	BEGIN;
	CREATE TABLE "KeyEventIDs" (
		"KeyName"	TEXT,
		"KeyID"	INTEGER,
		"SDK_VERSION"	TEXT(15),
		PRIMARY KEY("KeyName")
	);
	COMMIT;
"""

### Globals

g_dbConn: sqlite3.Connection = None
g_baseUrl = MSFS_SDKDOCS_URL

### Utilities

def createTableIfNeeded(tableName, tableDef, drop = False):
	exists = g_dbConn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (tableName,)).fetchone() != None
	if (exists and not drop):
		return
	if (drop and exists):
		print(f"Dropping table {tableName}...")
	g_dbConn.executescript(f"BEGIN; DROP TABLE IF EXISTS {tableName}; COMMIT;")
	print(f"Creating table {tableName}...")
	g_dbConn.executescript(tableDef)
	print("Table created.\n")

def getCleanText(fromElement):
	# Clean any non-printable characters which seem to pepper the online docs.
	if (isinstance(fromElement, bs4Tag)):
		fromElement = fromElement.get_text()
	# brute-force, just strip anything non-ascii
	return re.sub(r'[^\x09\x0A\x0D\x20-\x7E]+', ' ', fromElement).strip()


# sqlite3 v3.12 deprecated built-in date converters
def adapt_datetime_iso(val):
    return val.isoformat(' ')
def convert_datetime(val):
	return datetime.datetime.fromisoformat(val.decode())

sqlite3.register_adapter(datetime.datetime, adapt_datetime_iso)
sqlite3.register_converter("datetime", convert_datetime)

### Meta Data

def updateImportMetaData(table, url):
	createTableIfNeeded("ImportMeta", DB_TABLE_IMPORT_META, False)
	dt = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
	g_dbConn.execute("UPDATE ImportMeta SET LastUpdate = ?, FromURL = ? WHERE TableName = ?", (dt, url, table))
	g_dbConn.commit()
	print(f"Updated import meta data for table '{table}' at {dt} with URL '{url}'")


### Key Events

def createEventsTableIfNeeded(drop = False):
	createTableIfNeeded("KeyEvents", DB_TABLE_KEY_EVENTS, drop)

def scrapeSystemEvents(evLink, fs24):
	print(f"Requesting '{evLink}'  ...")
	resp = requests.get(evLink, timeout=60)
	if (not resp.ok):
		print(f"Error getting {evLink}: {resp.reason}")
		return 1
	bsSystem = soup(resp.text, "lxml")
	sysNameHdr = bsSystem.find('h2')
	if (not sysNameHdr):
		print("\tWARNING: Could not find a System name in H2 tag!")
		return 1
	sysName = sysNameHdr.text.replace(" EVENTS", "").title()
	## EXCEPTION:  Wrong title on Aircraft Fuel System Events page
	if (sysName.lower() == "event ids"):
		sysName = "Aircraft Fuel System"
	cats = sysNameHdr.find_next_siblings('table')
	print(f"Found {len(cats)} Categories in '{sysName} Events'")
	importCount = 0
	catIndex = 0  # just for error reporting
	for cat in cats:
		catIndex += 1
		rows = cat.find_all('tr')
		colsCount = len(rows[0].find_all('th')) if rows else 0
		catNameHdr = cat.find_previous_sibling(['h3', 'h4'])  # for some reason the heading level isn't always consistent
		catName = catNameHdr.get_text(strip=True) if catNameHdr else ""
		if (not catName):
			print(f"\tWARNING: Table {catIndex} has no apparent category name, using System name instead.")
			catName = sysName
		# Expected column layout: name | params | description [ | multiplayer ]
		# special case for "Concorde" events with only 2 columns (tho they're deprecated anyway)
		if (colsCount < 3 and not "Concorde" in catName):
			print(f"\tWARNING: Skipping table {catIndex}, not enough columns.")
			continue
		print(f"Importing '{catName}'...")
		evParams = ""
		evCount = 0
		# check if whole category is deprecated
		catDepr = "deprecated" in catName.lower()
		for row in rows[1::]:
			cols = row.find_all('td')
			rowColsLen = len(cols)
			if (rowColsLen < 2):
				continue
			# In almost all cases there are at least 3 columns, but at least in one case (Breakers),
			# the first params column has a rowspan and subsequent rows have only 2 columns with name | descript
			colIdxShift = -1 if rowColsLen < colsCount or colsCount == 2 else 0
			# if the params column is missing then we reuse the previous params which is scoped outside the loop
			if (colIdxShift > -1):
				evParams = getCleanText(cols[1])
			evDescript = getCleanText(cols[2 + colIdxShift])
			# sometimes the "Multiplayer" column is missing
			evMulti = getCleanText(cols[3 + colIdxShift]) if (rowColsLen > 3 + colIdxShift) else ""
			evDepr = catDepr
			if (not evDepr):
				# Determine if event is deprecated, which is most reliably indicated by a red colored background style.
				tdStyle = cols[0].get('style', None)
				evDepr = 1 if tdStyle and 'rgba(255' in tdStyle else 0

			simVerCol = "MSFS_12" if fs24 else "MSFS_11"
			simStat = 2 if evDepr else 1
			# Each event name table cell may contain multiple names which all share the same params/description.
			for event in cols[0].find_all('code'):
				evName = re.sub(r'\W', '', getCleanText(event))
				g_dbConn.execute(
					f"""
						INSERT INTO KeyEvents
							(System, Category, Name, Params, Description, Multiplayer, Deprecated, {simVerCol})
						VALUES (?, ?, ?, ?, ?, ?, ?, ?)
						ON CONFLICT(Name) DO UPDATE SET {simVerCol} = excluded.{simVerCol}
					""",
					(sysName, catName, evName, evParams, evDescript, evMulti, evDepr, simStat)
				)
				evCount += 1
				# Check the link ID  (optional); The <a> tag is usually before the <code> tag with event name, but sometimes it is inside the code tag.
				evA = event.find_previous_siblings('a')
				evId = evA[0].get('id') if evA else event.find('a').get('id') if event.find('a') else "NO LINK"
				if (evName != evId):
					print(f"\tWARNING: Event Name and link ID do not match for name: '{evName}'; id: '{evId}').")
		print(f"Imported {evCount} Key Events from '{catName}'.")
		importCount += evCount
	g_dbConn.commit()
	print(f"Finished importing {importCount} events from '{sysName} Events'.\n")
	return 0


def getEventBaseUrl(fs24):
	return g_baseUrl + (MSFS_EVENTS_PATH_24 if fs24 else MSFS_EVENTS_PATH)


def scrapeEvents(drop, fs24):
	createEventsTableIfNeeded(drop)

	baseUrl = getEventBaseUrl(fs24)
	eventsIndex = baseUrl + (MSFS_EVENTS_INDEX_24 if fs24 else MSFS_EVENTS_INDEX)

	print(f"Requesting '{eventsIndex}' ...")
	resp = requests.get(eventsIndex, timeout=60)
	if (not resp.ok):
		print(f"Request Error: {resp.reason}")
		return 1
	bs = soup(resp.text, "lxml")
	evHeadTitle = "KEY EVENTS" if fs24 else "EVENT IDs"
	evHead = bs.find(name='h2', string=evHeadTitle)
	if (evHead == None):
		print(f"\tWARNING: Could not find '{evHeadTitle}' h2 tag.")
		return 1
	evSystemsList = evHead.find_next_sibling('ul').select('li a')  # , limit=1
	print(f"Found {len(evSystemsList)} Systems...\n")
	for evA in evSystemsList:
		evLink = evA.get('href')
		if (evLink):
			scrapeSystemEvents(baseUrl + evLink, fs24)

	updateImportMetaData("KeyEvents", baseUrl)
	print("Finished importing Key Events.\n")
	return 0


def importSingleEventSystemPage(pageUrl, drop, fs24):
		evUrl = getEventBaseUrl(fs24) + pageUrl + '.htm'
		createEventsTableIfNeeded(drop)
		ret = scrapeSystemEvents(evUrl, fs24)
		if (ret == 0):
			updateImportMetaData("KeyEvents", evUrl)
		return ret


### Simulation Variables

def createSimVarsTableIfNeeded(drop = False):
	createTableIfNeeded("SimVars", DB_TABLE_SIM_VARS, drop)

def scrapeSystemSimVars(sysUrl, fs24):
	print(f"Requesting '{sysUrl}'  ...")
	resp = requests.get(sysUrl, timeout=60)
	if (not resp.ok):
		print(f"Error getting {sysUrl}: {resp.reason}")
		return 1
	bsSystem = soup(resp.text, "lxml")
	sysNameHdr = bsSystem.find('h2')
	if (not sysNameHdr):
		print("\tWARNING: Could not find a System name in H2 tag!")
		return 1
	sysName = sysNameHdr.text.replace(" VARIABLES", "").title()
	cats = sysNameHdr.find_next_siblings('table')
	print(f"Found {len(cats)} Categories in '{sysName} Variables'")
	importCount = 0
	catIndex = 0  # just for error reporting
	for cat in cats:
		catIndex += 1
		rows = cat.find('tbody').find_all('tr')
		colsCount = len(rows[0].find_all('th')) if rows else 0
		# SU10 docs have 4 columns, SU11 docs add Multiplayer column (in most cases, but not all)
		# name | description | units | settable [ | multiplayer ]
		if (colsCount < 4):
			print(f"\tWARNING: Skipping table {catIndex}, not enough columns.")
			continue
		catNameHdr = cat.find_previous_sibling(['h3', 'h4'])
		catName = ""
		if (catNameHdr):
			catName = catNameHdr.get_text(strip=True)
		else:
			# sometimes the first h3/h4 tag is missing, use the main system name instead
			print(f"\tWARNING: Table {catIndex} has no apparent category name, using System name instead.")
			catName = sysName
		print(f"Importing '{catName}'...")
		catImportCount = 0
		# check if whole category is deprecated
		catDepr = "deprecated" in catName.lower()
		varDescript = ""
		for row in rows[1::]:
			cols = row.find_all('td')
			rowColsLen = len(cols)
			if (rowColsLen < 3):
				continue
			# In almost all cases there are at least 4 columns, but at least in one case (Breakers),
			# the description column has a rowspan and subsequent rows have only 3-4 columns: name | units | settable [ | multiplayer ]
			colIdxShift = 0
			if rowColsLen < colsCount:
				colIdxShift -= 1
			# ... oh and in the SU10 docs they cram the Multiplayer info into the description cell on 17 SimVars... though this is fixed in SU11 version.
			elif rowColsLen > colsCount:
				colIdxShift += 1
			# if the description column is missing then we reuse the previous description which is scoped outside the loop
			if (colIdxShift > -1):
				varDescript = getCleanText(cols[1])
			varUnit = getCleanText(cols[2 + colIdxShift])
			varSettable = 1 if cols[3 + colIdxShift].find('span', class_='checkmark_circle') != None else 0
			# sometimes the "Multiplayer" column is missing in SU11 docs also
			varMulti = getCleanText(cols[4 + colIdxShift]) if (rowColsLen > 4 + colIdxShift) else ""
			varDepr = catDepr
			if (not varDepr):
				# Determine if simvar is deprecated, which is most reliably indicated by a red colored background style.
				tdStyle = cols[0].get('style')
				varDepr = 1 if tdStyle and 'rgba(255' in tdStyle else 0

			simVerCol = "MSFS_12" if fs24 else "MSFS_11"
			simStat = 2 if varDepr else 1

			# Each event name table cell may contain multiple names which all share the same params/description.
			for simvar in cols[0].find_all('code'):
				varName = getCleanText(simvar)
				# :name indicator for sub-component (new in fs24);
				varComponent = 1 if re.search(r':name', varName) != None else 0
				# :index indicator may be in the name; if it has a component name then assume it also can take an index (unclear if this is true in all cases)
				varIndexed = 1 if varComponent or re.search(r':(i|I|N)', varName) != None else 0
				# clean the name
				varName = re.sub(r':.+', '', varName)  # index/name separator and anything after it
				varName = re.sub(r'_', ' ', varName)   # at least one sim var is listed incorrectly with underscores
				varName = re.sub(r'[^A-Z\d\s]', '', varName).strip()  # any other junk, and trim

				g_dbConn.execute(
					f"""
						INSERT OR REPLACE INTO SimVars
							(System, Category, Name, Description, Units, Settable, Multiplayer, Indexed, Component, Deprecated, {simVerCol})
						VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
						ON CONFLICT(Name) DO UPDATE SET {simVerCol} = excluded.{simVerCol}
					""",
					(sysName, catName, varName, varDescript, varUnit, varSettable, varMulti, varIndexed, varComponent, varDepr, simStat)
				)
				catImportCount += 1
				# Check the link ID  (optional); The <a> tag is usually before the <code> tag with event name, but sometimes it is inside the code tag.
				varNameLink = simvar.find_previous_siblings('a')
				varId = (varNameLink[0].get('id') if varNameLink else simvar.find('a').get('id') if simvar.find('a') else "NO LINK").replace('_', ' ')
				if (varId != varName):
					print(f"\tWARNING: Sim Var Name and link ID do not match for name: '{varName}'; id: '{varId}').")

		print(f"Imported {catImportCount} Simulator Variables from '{catName}'.")
		importCount += catImportCount
	g_dbConn.commit()
	print(f"Finished importing {importCount} Variables from '{sysName} Variables'.\n")
	return 0


def scrapeSimvars(drop, fs24):
	createSimVarsTableIfNeeded(drop)

	baseUrl = g_baseUrl + MSFS_SIMVARS_PATH
	print(f"Requesting '{baseUrl + MSFS_SIMVARS_INDEX}' ...")
	resp = requests.get(baseUrl + MSFS_SIMVARS_INDEX, timeout=60)
	if (not resp.ok):
		print(f"Request Error: {resp.reason}")
		return 1
	# print(getCleanText(resp.text))
	bs = soup(resp.text, "lxml")
	svHead = bs.find(name='h2', string="SIMULATION VARIABLES")
	if (svHead == None):
		print(f"\tWARNING: Could not find 'SIMULATION VARIABLES' h2 tag.")
		return 1
	svSystemsList = svHead.find_next_sibling('ul').select('li a')[1::]  # skip the first link which should be the Units listing
	print(f"Found {len(svSystemsList)} Systems...\n")
	for svA in svSystemsList:
		svLink = svA.get('href')
		if (svLink):
			scrapeSystemSimVars(baseUrl + svLink, fs24)

	# the "ADF ACTIVE FREQUENCY" SimVar lists a unit type of "Frequency ADF BCD32" which is not a thing. It's been like that for years.
	g_dbConn.execute("UPDATE SimVars SET Units = ? WHERE Name = ?", ("Frequency BCD32", "ADF ACTIVE FREQUENCY"))
	# fix spelling on "Reciprical (Piston) Engine"
	g_dbConn.execute("UPDATE SimVars SET Category = 'Reciprocal (Piston) Engine' WHERE Category = 'Reciprical (Piston) Engine Vars'")
	g_dbConn.commit()

	updateImportMetaData("SimVars", baseUrl)
	print("Finished importing Simulation Variables.\n")
	return 0

def importSingleSimVarSystemPage(pageUrl, drop, fs24):
			createSimVarsTableIfNeeded(drop)
			svUrl = g_baseUrl + MSFS_SIMVARS_PATH + pageUrl + '.htm'
			ret = scrapeSystemSimVars(svUrl, fs24)
			if (ret == 0):
				updateImportMetaData("SimVars", svUrl)
			return ret


### SimVar Units

def scrapeSimvarUnits(drop, baseUrl):
	createTableIfNeeded("SimVarUnits", DB_TABLE_SIMVAR_UNITS, drop)

	baseUrl += MSFS_SIMVARS_PATH + MSFS_SIMVARS_UNITS
	print(f"Requesting '{baseUrl}' ...")
	resp = requests.get(baseUrl, timeout=60)
	if (not resp.ok):
		print(f"Request Error: {resp.reason}")
		return 1
	bs = soup(resp.text, "lxml")
	svHead = bs.find(name='h2', string="SIMULATION VARIABLE UNITS")
	if (svHead == None):
		print(f"\tWARNING: Could not find 'SIMULATION VARIABLE UNITS' h2 tag.")
		return 1

	cats = svHead.find_next_siblings('table')
	print(f"Found {len(cats)} Unit Categories")
	importCount = 0
	catIndex = 0  # just for error reporting
	for cat in cats:
		catIndex += 1
		catNameHdr = cat.find_previous_sibling(['h3', 'h4'])
		catName = catNameHdr.get_text(strip=True) if catNameHdr else ""
		if (not catName):
			print(f"\tWARNING: Skipping table {catIndex} with no apparent category name.")
			continue
		## EXCEPTION: skip "Structs And Other Complex Units"
		if (catName.startswith("Structs")):
			continue
		print(f"Importing '{catName}'...")
		catCount = 0
		rows = cat.find_all('tr')
		for row in rows:
			cols = row.find_all('td')
			if (len(cols) < 2):
				continue  # skip the TH row
			allNames = getCleanText(cols[0])
			descript = getCleanText(cols[1])
			names = list(map(getCleanText, allNames.split(',')))
			# The name listed second is usually "best" for primary name, except in some cases where there
			# is only one full name and an abbreviation, in which case we want to keep the first, longer, name.
			unitName = names[0] if len(names) < 2 or len(names[1]) < len(names[0]) else names[1]
			shortName = min(names, key=len)
			aliases = ','.join(names) + ','  # append a comma at end for simpler lookups
			g_dbConn.execute(
				"INSERT OR REPLACE INTO SimVarUnits (Measure, Name, ShortName, Aliases, Description) VALUES (?, ?, ?, ?, ?)",
				(catName, unitName, shortName, aliases, descript)
			)
			catCount += 1
		print(f"Imported {catCount} Units from '{catName}'.")
		importCount += catCount

	updateImportMetaData("SimVarUnits", baseUrl)
	print(f"Finished importing {importCount} SimVar Units.\n")
	return 0


### Key IDs from gauges.h or MSFS_EventsEnum.h

def importKeyIDs(sdkPath, drop = False, fs24 = False):
	createTableIfNeeded("KeyEventIDs", FB_TABLE_KEY_EVENT_IDS, drop)

	headerFile = "WASM/include/MSFS/" + ("Types/MSFS_EventsEnum.h" if fs24 else "legacy/gauges.h")

	versionFile = os.path.abspath(os.path.join(sdkPath, 'version.txt'))
	if (not os.path.exists(versionFile)):
		print(f"ERROR: MSFS SDK version.txt file not found at SDK path {sdkPath}.")
		return 1

	headerPath = os.path.abspath(os.path.join(sdkPath,  headerFile))
	if (not os.path.exists(headerPath)):
		print(f"ERROR: event definitions file not found at {headerPath}.")
		return 1

	with open(versionFile, 'r') as vf:
		sdkVer = vf.read().strip()
	keyDefRx = re.compile(r'#define (\w+)\s+\(KEY_ID_MIN \+ (\d+)\)')
	keyAliasRx = re.compile(r'#define (\w+)\s+(\w+)')
	importCount = 0
	inKeydefs = False

	print(f"Importing KEY_* macros from MSFS SDK v{sdkVer} file {headerPath}...")
	with open(headerPath, 'r') as hf:
		for line in hf:
			match = re.search(keyDefRx, line)
			kId = 0
			if (match):
				kId = int(match.group(2)) + 0x10000
			elif (inKeydefs):
				match = re.search(keyAliasRx, line)
				if (match):
					kId = g_dbConn.execute("SELECT KeyID FROM KeyEventIDs WHERE KeyName = ?", (match.group(2).replace("KEY_", ""),)).fetchone()
					kId = kId[0] if kId else 0
				else:
					break
			else:
				continue
			inKeydefs = True
			if ((name := match.group(1).replace("KEY_", "")) == "NULL"):
				continue
			g_dbConn.execute(
				"INSERT OR IGNORE INTO KeyEventIDs (KeyName, KeyID, SDK_VERSION) VALUES (?, ?, ?)",
				(name, kId, sdkVer)
			)
			importCount += 1

	updateImportMetaData("KeyEventIDs", headerFile + " SDK v" + sdkVer)
	print(f"Finished importing {importCount} Key Event IDs.\n")
	return 0


### Event Matching Report: documented Event IDs vs. KEY_* macros

def eventIdReport(fs24):
	sql = """
		SELECT LastUpdate, FromURL FROM ImportMeta
		WHERE TableName = 'KeyEvents' AND LastUpdate IS NOT NULL
	"""
	qry = g_dbConn.execute(sql).fetchone()
	if (not qry):
		print("ERROR: Could not get import data for KeyEvents table.")
		return 1
	evUpd = qry['LastUpdate']
	evUrl = qry['FromURL']

	sql = """
		SELECT LastUpdate, FromURL FROM ImportMeta
		WHERE TableName = 'KeyEventIDs' AND LastUpdate IS NOT NULL
	"""
	qry = g_dbConn.execute(sql).fetchone()
	if (not qry):
		print("ERROR: Could not get import data for KeyEventIDs table.")
		return 1
	keysUpd = qry['LastUpdate']
	keysUrl = qry['FromURL']

	simVerCol = "MSFS_12" if fs24 else "MSFS_11"

	print("------------------")
	print("Event ID Matching Report")
	print(f"Simulator Version: {simVerCol}")
	print(f"Event IDs imported {evUpd} from {evUrl}")
	print(f"KEY_* macros imported {keysUpd} from {keysUrl}")
	print("------------------")
	sql = f"""
		SELECT Name, System, Category, {simVerCol}
		FROM KeyEvents
		WHERE Name NOT LIKE 'DEBUG%'
			AND {simVerCol} > 0
			AND Name NOT IN (
				SELECT KeyName FROM KeyEventIDs
			)
			AND (
				NOT (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'PubKeyEventNameToKeyID')
				OR Name NOT IN (
					SELECT PublishedName FROM PubKeyEventNameToKeyID
				)
			)
		ORDER BY Name
	"""
	print("Events which are documented but do not exist in KEY_* macros:\n")
	for row in g_dbConn.execute(sql):
		print(f"{row['Name']:45} {row['System']} - {row['Category']:45}{('[DEPR]' if row[simVerCol] == 2 else '')}")
	print("------------------\n")

	sql = f"""
		SELECT *
		FROM KeyEventIDs
		WHERE KeyName NOT LIKE 'DEBUG%'
			AND SDK_VERSION LIKE '{"%" if fs24 else "0.%"}'
			AND KeyName NOT IN (
				SELECT Name FROM KeyEvents WHERE Category not like 'Undocumented%'
			)
			AND (
				NOT (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'PubKeyEventNameToKeyID')
				OR KeyName NOT IN (
					SELECT KeyName FROM PubKeyEventNameToKeyID
				)
			)
		ORDER BY KeyName
	"""
	print("Event IDs from KEY_* macros which are not documented:\n")
	print(f"{'Macro_Name,':50} KeyID,   SDK_VERSION")
	for row in g_dbConn.execute(sql):
		print(f"{'\"KEY_'+row['KeyName']+'\",':50} {row['KeyID']},   \"{re.sub(r'(\d+\.\d+\.\d+)\.0$', r'\1', row['SDK_VERSION'])}\"")
		# print(f"{row['KeyName']:50} {row['KeyID']}   {row['SDK_VERSION']}")
	print("------------------\n")


### Data Export

def exportTable(tableName, order):
	sql = f"""
		SELECT * FROM {tableName}
		ORDER BY {order}
	"""
	qry = g_dbConn.execute(sql)
	row = qry.fetchone()
	if (not row):
		return
	keys = row.keys()
	for col in keys:
		print(col, end='')
		if (col == keys[-1]):
			print('', flush=True)
		else:
			print('\t', end='')
	colsMaxIdx = len(keys) - 1
	while row:
		for i in range(0, colsMaxIdx+1):
			val = row[i]
			try:
				if (isinstance(val, str)):
					print('"'+val+'"', end='')
				else:
					print(val, end='')
			except Exception:
				print(f"can't export value!", end='')
			if (i == colsMaxIdx):
				print('', flush=True)
			else:
				print('\t', end='')
		row = qry.fetchone()
	print('\n')


### Main

def main():
	global g_dbConn, g_baseUrl

	parser = ArgumentParser(
		add_help=False,
		description="Utility for importing online MSFS SDK Documentation into data structures. Most functions require Internet access to download documentation pages for 'scraping.'"
	)

	dbGrp = parser.add_argument_group(title="Database")
	dbGrp.add_argument(
		"--db", metavar="<file>", default=DB_FILE,
		help="SQLite3 database file to import into (default: '%(default)s'). File must exist, table(s) will be created if missing."
	)
	dbGrp.add_argument(
		"--drop", action='store_true',
		help="Delete (drop) existing table(s) (if any) before import. This only drops table(s) of the item type(s) being imported (not necessarily all tables)."
	)

	impGrp = parser.add_argument_group(title="Import")
	impGrp.add_argument(
		"-e", "--events", nargs='*', metavar="<url_path>", action="extend",
		help="Import Key Events (enabled by default if no other import or export type is specified). "
			"The optional <url_path> argument(s) will import events only from given system page(s), specified as the last (file name) "
			"part of SDK docs URL (excluding the '.htm' suffix, eg: 'Aircraft_Engine_Events')."
	)
	impGrp.add_argument(
		"-v", "--simvars", nargs='*', metavar="<url_path>", action="extend",
		help="Import Simulator Variables (enabled by default if no other import or export type is specified). "
			"The optional <url_path> argument(s) will import variables only from given system page(s), specified as the last one or two parts of SDK docs URL "
			"(excluding the '.htm' suffix, eg: 'Aircraft_SimVars/Aircraft_Fuel_Variables' or 'Camera_Variables')."
	)
	impGrp.add_argument(
		"-u", "--units", action='store_true',
		help="Import Simulator Variable Units (they are not imported by default)."
	)
	impGrp.add_argument(
		"-k", "--keyids", action='store_true',
		help="Import 'KEY_*' macro names and values from gauges.h (they are not imported by default). Requires a valid MSFS SDK path (see below)."
	)
	# impGrp.add_argument("--beta", action='store_true',
	#                     help=f"Import from 'flighting' (beta/preview) version of online SDK Docs (base URL: {MSFS_SDKDOCS_URL_FL}).")
	impGrp.add_argument(
		"--fs24", action='store_true',
		help=f"Import from 'msfs2024' version of online SDK Docs (base URL: {MSFS_SDKDOCS_URL_24})."
	)
	impGrp.add_argument(
		"--sdk_path", metavar="<path>",
		help="MSFS SDK path for importing KEY_* macros with --keyids option. Default: The value of 'MSFS_SDK' or 'MSFS2024_SDK' environment variable."
	)

	expGrp = parser.add_argument_group(title="Export (using these option(s) prevents any default imports from running)")
	expGrp.add_argument(
		"--ev_report", action='store_true',
		help="Run a report comparing documented Event IDs vs. KEY_* macros."
	)
	expGrp.add_argument(
		"--export", choices=['events','simvars','units','keyids','meta'], action="extend", nargs="+",
		help="Exports contents of specified table(s) in tab-delimited text format to stdout (use redirect to capture to file)."
	)

	metaGrp = parser.add_argument_group(title="Meta")
	metaGrp.add_argument("-h", "--help", action="help", help="show this help message and exit")
	metaGrp.add_argument("-V", "--version", action="version", version=f"{__version__}")

	opts = parser.parse_args()
	del parser

	g_dbConn = sqlite3.connect(opts.db)
	if (g_dbConn is None):
		print(f"Could not open database {opts.db}!")
		return 1
	g_dbConn.row_factory = sqlite3.Row

	ret = 0
	importAll = True
	for (k, v) in vars(opts).items():
		if ((v or isinstance(v, list)) and k not in ['db', 'drop', 'beta', 'sdk_path']):
			importAll = False
			break

	if (opts.fs24):
		g_baseUrl = MSFS_SDKDOCS_URL_24
	# elif (opts.beta):
	# 	g_baseUrl = MSFS_SDKDOCS_URL_FL

	try:
		if (importAll or opts.events is not None):
			if (not opts.events):
				ret += scrapeEvents(opts.drop, opts.fs24)
			else:
				for ev in opts.events:
					ret += importSingleEventSystemPage(ev, opts.drop, opts.fs24)


		if (importAll or opts.simvars is not None):
			if (not opts.simvars):
				ret += scrapeSimvars(opts.drop, opts.fs24)
			else:
				for sv in opts.simvars:
					ret += importSingleSimVarSystemPage(sv, opts.drop, opts.fs24)

		if (opts.units):
			ret += scrapeSimvarUnits(opts.drop, g_baseUrl)

		if (opts.keyids):
			if (opts.sdk_path is None):
				opts.sdk_path = os.environ['MSFS2024_SDK'] if opts.fs24 else os.environ['MSFS_SDK']
			ret += importKeyIDs(opts.sdk_path, opts.drop, opts.fs24)

		if (opts.ev_report and ret == 0):
			eventIdReport(opts.fs24)

		if (opts.export):
			for table in opts.export:
				if (table == "events"):  exportTable("KeyEvents",   "System, Category, Name")
				if (table == "simvars"): exportTable("SimVars",     "System, Category, Name")
				if (table == "units"):   exportTable("SimVarUnits", "Measure, Name")
				if (table == "keyids"):  exportTable("KeyEventIDs", "KeyName")
				if (table == "meta"):    exportTable("ImportMeta",  "TableName")
				if (table == "keymap"):  exportTable("PubKeyEventNameToKeyID", "PublishedName")

	except Exception:
		from traceback import format_exc
		print(format_exc())
		ret += 100

	g_dbConn.close()
	return ret

if __name__ == "__main__":
	exit(main())
