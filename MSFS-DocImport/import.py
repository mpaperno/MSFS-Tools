"""
Utility for importing online MSFS SDK Documentation into data structures.

Currently supports importing Event IDs, Simulation Variables, and Sim. Var. Units
by "scraping" the SDK docs HTML pages (either the current/release or the beta/flighting versions).

Additionally it can import KEY_* macro names and IDs from the MSFS SDK "gauges.h" header.
This is mostly useful for comparison purposes with the published SDK docs. A report can be generated
by using the --ev_report option.

The import destination is an SQLite3 database file. An existing database file is required,
but all tables are created automatically by this script as needed. Any existing data is preserved/updated
unless the --drop option was passed on the command line.

Requires Python 3.8+ with extra modules:  bs4, lxml, requests

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

__version__ = "1.0.1"

from argparse import ArgumentParser
from bs4 import BeautifulSoup as soup, Tag as bs4Tag
import datetime
import lxml
import os
import re
import requests
import sqlite3

DB_FILE = "./MSFS_SDK_Doc_Import.sqlite3"

MSFS_SDKDOCS_URL    = "https://docs.flightsimulator.com/html/Programming_Tools/"
MSFS_SDKDOCS_URL_FL = "https://docs.flightsimulator.com/flighting/html/Programming_Tools/"

MSFS_EVENTS_PATH = "Event_IDs/"
MSFS_EVENTS_INDEX = "Event_IDs.htm"

MSFS_SIMVARS_PATH = "SimVars/"
MSFS_SIMVARS_INDEX = "Simulation_Variables.htm"
MSFS_SIMVARS_UNITS = "Simulation_Variable_Units.htm"

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

DB_TABLE_KEY_EVENTS = """
	BEGIN;
	CREATE TABLE "KeyEvents" (
		"System"	TEXT(50) NOT NULL,
		"Category"	TEXT(50) NOT NULL,
		"Name"	TEXT(50) NOT NULL,
		"Params"	TEXT(300),
		"Description"	TEXT(500),
		"Multiplayer"	TEXT(20),
		"Deprecated"	NUMERIC(1),
		PRIMARY KEY("Name")
	);
	CREATE INDEX "IX_KeyEvents_System" ON "KeyEvents" ("System");
	CREATE INDEX "IX_KeyEvents_Category" ON "KeyEvents" ("Category");
	CREATE INDEX "IX_KeyEvents_Deprecated" ON "KeyEvents" ("Deprecated");
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
		"Settable"	NUMERIC(1),
		"Multiplayer"	TEXT(20),
		"Indexed"	NUMERIC(1),
		"Deprecated"	NUMERIC(1),
		PRIMARY KEY("Name")
	);
	CREATE INDEX "IX_SimVars_System" ON "SimVars" ("System");
	CREATE INDEX "IX_SimVars_Category" ON "SimVars" ("Category");
	CREATE INDEX "IX_SimVars_Settable" ON "SimVars" ("Settable");
	CREATE INDEX "IX_SimVars_Deprecated" ON "SimVars" ("Deprecated");
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
		PRIMARY KEY("KeyName")
	);
	COMMIT;
"""

### Globals

g_dbConn: sqlite3.Connection = None


### Utilities

def getBaseUrl(flighting = False):
	return (MSFS_SDKDOCS_URL_FL if flighting else MSFS_SDKDOCS_URL)

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
	# Remove UTF8 NO-BREAK-SPACE which appears in some texts and blank values.
	if (isinstance(fromElement, bs4Tag)):
		fromElement = fromElement.get_text()
	return re.sub(r'\xC2', '', fromElement).strip()


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

def scrapeSystemEvents(evLink):
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
		catNameHdr = cat.find_previous_sibling(['h3', 'h4'])  # for some reason the heading level isn't always consistent
		catName = catNameHdr.get_text(strip=True) if catNameHdr else ""
		if (not catName):
			print(f"\tWARNING: Table {catIndex} has no apparent category name, using System name instead.")
			catName = sysName
		## EXCEPTION:  Skip "Fuel Selector Codes" table on Aircraft Fuel System Events page (need better way to detect)
		if (catName.endswith("Codes")):
			print(f"\tWARNING: Skipping table '{catName}'.")
			continue
		print(f"Importing '{catName}'...")
		evParams = ""
		evCount = 0
		# check if whole category is deprecated
		catDepr = "deprecated" in catName.lower()
		rows = cat.find_all('tr')
		for row in rows:
			cols = row.find_all('td')
			if (len(cols) < 2):
				continue # skip the TH row
			# In almost all cases there are at least 3 columns with name | params | descript [ | multiplayer ]
			# but at least in one case (Breakers), the first params column has a rowspan and subsequent rows have only 2 columns with name | descript
			colIdxShift = 0 if len(cols) > 2 else -1
			if (colIdxShift > -1):
				evParams = getCleanText(cols[1])
			evDescript = getCleanText(cols[2 + colIdxShift])
			# sometimes the "Multiplayer" column is missing
			evMulti = getCleanText(cols[3 + colIdxShift]) if (len(cols) > 3 + colIdxShift) else ""
			evDepr = catDepr
			if (not evDepr):
				# Determine if event is deprecated, which is most reliably indicated by a red colored background style.
				tdStyle = cols[0].get('style', None)
				evDepr = 1 if tdStyle and 'rgba(255' in tdStyle else 0
			# Each event name table cell may contain multiple names which all share the same params/description.
			for event in cols[0].find_all('code'):
				evName = getCleanText(event)
				g_dbConn.execute(
					"INSERT OR REPLACE INTO KeyEvents (System, Category, Name, Params, Description, Multiplayer, Deprecated) VALUES (?, ?, ?, ?, ?, ?, ?)",
					(sysName, catName, evName, evParams, evDescript, evMulti, evDepr)
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


def scrapeEvents(drop = False, flighting = False):
	createEventsTableIfNeeded(drop)

	baseUrl = (MSFS_SDKDOCS_URL_FL if flighting else MSFS_SDKDOCS_URL) + MSFS_EVENTS_PATH
	print(f"Requesting '{baseUrl + MSFS_EVENTS_INDEX}' ...")
	resp = requests.get(baseUrl + MSFS_EVENTS_INDEX, timeout=60)
	if (not resp.ok):
		print(f"Request Error: {resp.reason}")
		return 1
	bs = soup(resp.text, "lxml")
	evHead = bs.find(name='h2', string="EVENT IDs")
	if (evHead == None):
		print(f"\tWARNING: Could not find 'EVENT IDs' h2 tag.")
		return 1
	evSystemsList = evHead.find_next_sibling('ul').select('li a')  # , limit=1
	print(f"Found {len(evSystemsList)} Systems...\n")
	for evA in evSystemsList:
		evLink = evA.get('href')
		if (evLink):
			scrapeSystemEvents(baseUrl + evLink)

	updateImportMetaData("KeyEvents", baseUrl)
	print("Finished importing Key Events.\n")
	return 0


def importSingleEventSystemPage(pageUrl, drop = False, flighting = False):
		evUrl = getBaseUrl(flighting) + MSFS_EVENTS_PATH + pageUrl + '.htm'
		createEventsTableIfNeeded(drop)
		ret = scrapeSystemEvents(evUrl)
		if (ret == 0):
			updateImportMetaData("KeyEvents", evUrl)
		return ret


### Simulation Variables

def createSimVarsTableIfNeeded(drop = False):
	createTableIfNeeded("SimVars", DB_TABLE_SIM_VARS, drop)

def scrapeSystemSimVars(sysUrl):
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
		rows = cat.find('tbody').find_all('tr')
		for row in rows:
			cols = row.find_all('td')
			if (len(cols) < 4):
				continue  # skip the TH row and some aux tables
			varDescript = getCleanText(cols[1])
			varUnit = getCleanText(cols[2])
			varSettable = 1 if cols[3].find('span', class_='checkmark_circle') != None else 0
			varMulti = getCleanText(cols[4]) if (len(cols) > 4) else ""  # sometimes the "Multiplayer" column is missing, though mostly for deprecated and struct type vars
			varDepr = catDepr
			if (not varDepr):
				# Determine if simvar is deprecated, which is most reliably indicated by a red colored background style.
				tdStyle = cols[0].get('style')
				varDepr = 1 if tdStyle and 'rgba(255' in tdStyle else 0

			# Each event name table cell may contain multiple names which all share the same params/description.
			for simvar in cols[0].find_all('code'):
				varName = getCleanText(simvar)
				# :index indicator may be in the name
				colonIdx = varName.find(':')
				if (colonIdx > -1):
					varName = varName[0:colonIdx]
					varIndexed = 1
				else:
					varIndexed = 0

				g_dbConn.execute(
					"INSERT OR REPLACE INTO SimVars (System, Category, Name, Description, Units, Settable, Multiplayer, Indexed, Deprecated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
					(sysName, catName, varName, varDescript, varUnit, varSettable, varMulti, varIndexed, varDepr)
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


def scrapeSimvars(drop = False, flighting = True):
	createSimVarsTableIfNeeded(drop)

	baseUrl = getBaseUrl(flighting) + MSFS_SIMVARS_PATH
	print(f"Requesting '{baseUrl + MSFS_SIMVARS_INDEX}' ...")
	resp = requests.get(baseUrl + MSFS_SIMVARS_INDEX, timeout=60)
	if (not resp.ok):
		print(f"Request Error: {resp.reason}")
		return 1
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
			scrapeSystemSimVars(baseUrl + svLink)

	updateImportMetaData("SimVars", baseUrl)
	print("Finished importing Simulation Variables.\n")
	return 0

def importSingleSimVarSystemPage(pageUrl, drop = False, flighting = False):
			createSimVarsTableIfNeeded(drop)
			svUrl = getBaseUrl(flighting) + MSFS_SIMVARS_PATH + pageUrl + '.htm'
			ret = scrapeSystemSimVars(svUrl)
			if (ret == 0):
				updateImportMetaData("SimVars", svUrl)
			return ret


### SimVar Units

def scrapeSimvarUnits(drop = False, flighting = False):
	createTableIfNeeded("SimVarUnits", DB_TABLE_SIMVAR_UNITS, drop)

	baseUrl = getBaseUrl(flighting) + MSFS_SIMVARS_PATH + MSFS_SIMVARS_UNITS
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


### Key IDs from gauges.h

def importKeyIDs(sdkPath, drop = False, headerFile = "WASM/include/MSFS/legacy/gauges.h"):
	createTableIfNeeded("KeyEventIDs", FB_TABLE_KEY_EVENT_IDS, drop)

	versionFile = os.path.abspath(os.path.join(sdkPath, 'version.txt'))
	if (not os.path.exists(versionFile)):
		print(f"ERROR: MSFS SDK version.txt file not found at SDK path {sdkPath}.")
		return 1
	with open(versionFile, 'r') as vf:
		sdkVer = vf.read().strip()
	keyDefRx = re.compile(r'#define (\w+)\s+\(KEY_ID_MIN \+ (\d+)\)')
	keyAliasRx = re.compile(r'#define (\w+)\s+(\w+)')
	importCount = 0
	inKeydefs = False
	headerPath = os.path.abspath(os.path.join(sdkPath,  headerFile))
	if (not os.path.exists(headerPath)):
		print(f"ERROR: gauges.h file not found at {headerPath}.")
		return 1
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
			g_dbConn.execute("INSERT OR REPLACE INTO KeyEventIDs (KeyName, KeyID) VALUES (?, ?)", (name, kId))
			importCount += 1

	updateImportMetaData("KeyEventIDs", headerFile + " SDK v" + sdkVer)
	print(f"Finished importing {importCount} Key Event IDs.\n")
	return 0


### Event Matching Report: documented Event IDs vs. KEY_* macros

def eventIdReport():
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

	print("------------------")
	print("Event ID Matching Report")
	print(f"Event IDs imported {evUpd} from {evUrl}")
	print(f"KEY_* macros imported {keysUpd} from {keysUrl}")
	print("------------------")
	sql = """
		SELECT Name, System, Category, Deprecated FROM KeyEvents
		WHERE Name NOT IN (
			SELECT KeyName FROM KeyEventIDs
		)
		ORDER BY Name
	"""
	print("Events which are documented but do not exist in KEY_* macros:\n")
	for row in g_dbConn.execute(sql):
		print(f"{row['Name']:45} {row['System']} - {row['Category']:45}{('[DEPR]' if row['Deprecated'] else '')}")
	print("------------------\n")

	sql = """
		SELECT KeyName, KeyID FROM KeyEventIDs
		WHERE KeyName NOT IN (
			SELECT Name FROM KeyEvents
		)
		ORDER BY KeyName
	"""
	print("Event IDs from KEY_* macros which are not documented:\n")
	for row in g_dbConn.execute(sql):
		print(f"{row['KeyName']:45} {row['KeyID']}")
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
			if (isinstance(val, str)):
				print('"'+val+'"', end='')
			else:
				print(val, end='')
			if (i == colsMaxIdx):
				print('', flush=True)
			else:
				print('\t', end='')
		row = qry.fetchone()
	print('\n')


### Main

def main():
	global g_dbConn

	parser = ArgumentParser(
		add_help=False,
		description="Utility for importing online MSFS SDK Documentation into data structures. Most functions require Internet access to download documentation pages for 'scraping.'"
	)

	dbGrp = parser.add_argument_group(title="Database")
	dbGrp.add_argument("--db", metavar="<file>", default=DB_FILE,
	                   help="SQLite3 database file to import into (default: '%(default)s'). File must exist, table(s) will be created if missing.")
	dbGrp.add_argument("--drop", action='store_true',
	                   help="Delete (drop) existing table(s) (if any) before import. This only drops table(s) of the item type(s) being imported (not necessarily all tables).")

	impGrp = parser.add_argument_group(title="Import")
	impGrp.add_argument("-e", "--events", nargs='*', metavar="<url_path>", action="extend",
	                    help="Import Key Events (enabled by default if no other import or export type is specified). "
											     "The optional <url_path> argument(s) will import events only from given system page(s), specified as the last (file name) "
													 "part of SDK docs URL (excluding the '.htm' suffix, eg: 'Aircraft_Engine_Events').")
	impGrp.add_argument("-v", "--simvars", nargs='*', metavar="<url_path>", action="extend",
	                    help="Import Simulator Variables (enabled by default if no other import or export type is specified). "
											     "The optional <url_path> argument(s) will import variables only from given system page(s), specified as the last one or two parts of SDK docs URL "
	                         "(excluding the '.htm' suffix, eg: 'Aircraft_SimVars/Aircraft_Fuel_Variables' or 'Camera_Variables').")
	impGrp.add_argument("-u", "--units", action='store_true',
	                    help="Import Simulator Variable Units (they are not imported by default).")
	impGrp.add_argument("-k", "--keyids", action='store_true',
	                    help="Import 'KEY_*' macro names and values from gauges.h (they are not imported by default). Requires a valid MSFS SDK path (see below).")
	impGrp.add_argument("--beta", action='store_true',
	                    help=f"Import from 'flighting' (beta/preview) version of online SDK Docs (base URL: {MSFS_SDKDOCS_URL_FL}).")
	impGrp.add_argument("--sdk_path", metavar="<path>", default=os.environ['MSFS_SDK'],
	                    help="MSFS SDK path for importing KEY_* macros with --keyids option. Default: %(default)s")

	expGrp = parser.add_argument_group(title="Export (using these option(s) prevents any default imports from running)")
	expGrp.add_argument("--ev_report", action='store_true', help=f"Run a report comparing documented Event IDs vs. KEY_* macros.")
	expGrp.add_argument("--export", choices=['events','simvars','units','keyids','meta'], action="extend", nargs="+",
	                    help="Exports contents of specified table(s) in tab-delimited text format to stdout (use redirect to capture to file).")

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

	try:
		if (importAll or opts.events is not None):
			if (not opts.events):
				ret += scrapeEvents(drop=opts.drop, flighting=opts.beta)
			else:
				for ev in opts.events:
					ret += importSingleEventSystemPage(ev, opts.drop, opts.beta)


		if (importAll or opts.simvars is not None):
			if (not opts.simvars):
				ret += scrapeSimvars(drop=opts.drop, flighting=opts.beta)
			else:
				for sv in opts.simvars:
					ret += importSingleSimVarSystemPage(sv, opts.drop, opts.beta)

		if (opts.units):
			ret += scrapeSimvarUnits(drop=opts.drop, flighting=opts.beta)

		if (opts.keyids):
			ret += importKeyIDs(opts.sdk_path, drop=opts.drop)

		if (opts.ev_report and ret == 0):
			eventIdReport()

		if (opts.export):
			for table in opts.export:
				if (table == "events"):  exportTable("KeyEvents",   "System, Category, Name")
				if (table == "simvars"): exportTable("SimVars",     "System, Category, Name")
				if (table == "units"):   exportTable("SimVarUnits", "Measure, Name")
				if (table == "keyids"):  exportTable("KeyEventIDs", "KeyName")
				if (table == "meta"):    exportTable("ImportMeta",  "TableName")

	except Exception:
		from traceback import format_exc
		print(format_exc())
		ret += 100

	g_dbConn.close()
	return ret

if __name__ == "__main__":
	exit(main())
