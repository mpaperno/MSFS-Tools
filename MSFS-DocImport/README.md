# MSFS-DocImport
## Utility tool for "scraping" MSFS SDK Documentation Event IDs and Simulator Variables from HTML pages into a structured database format.

### Features:
* Imports all Event ID and Simulator Variable definitions, indexed by base "system" (reference page) and by category/component.
  * Creates separate fields indicating if an item is deprecated, is indexed and/or settable (for SimVars), or participates in Multiplayer environment.
* Imports all SimVar Unit types, indexed by type of measure (length/angle/etc), with "primary" name, abbreviation (short name), and all
  aliases broken out into individual columns.
* Imports the `KEY_*` macro names from MSFS SDK `gauges.h` header file along with the corresponding IDs.
  * Optionally generates a comparison report of KEY_ macros vs. SDK Docs (which events names are in documentation vs. in the macros).
* Imported data is stored in a SQLite3 database, with tables automatically created at runtime if needed.
* Can dump/export all data to tab-delimited text files.
* Written in Python for simple modification/customization. Can also be used as a module providing importable functions.

The folder includes imported data ready for download, both the current release version and next beta/preview "flighting" version
(if different from current release).

#### NOTE

The SDK documentation HTML is parsed on a "best effort" basis, taking into account several inconsistencies in the formatting of
the various reference pages which were discovered in the process of writing this script. However I **cannot guarantee that every
one of the thousands of events and sim vars. are properly captured.**  Furthermore, the parsing effectiveness is subject to changes
in the documentation formatting.

**Please let me know if you find any inconsistencies!**

This utility has prompted the following relevant discussion on MSFS Dev forum:<br/>
https://devsupport.flightsimulator.com/questions/11870/errata-between-sdk-documentation-event-ids-vs-key.html

### Requirements
* Python 3.8+ with extra modules:  `bs4` (Beautiful Soup HTML lexer), `lxml` (for parsing HTML), `requests` (for network downloads).
  All can be installed at once with the provided requirements.txt file, eg:

    pip3 install -r requirements.txt

* Internet connection for downloading the SDK Documentation Web pages.
* Optional: MSFS SDK installation for parsing KEY_* macros in gauges.h.


### Usage
```
import.py [--db <file>] [--drop]
          [-e  [url_path ...] | --events [url_path ...]] [-v  [url_path ...] | --simvars  [url_path ...]]
          [-u | --units] [-k | --keyids]
          [--beta] [--ev_report] [--sdk_path <path>]
          [--export {events,simvars,units,keyids,meta} [...]]
          [-h | --help] [-V | --version]

Database:
  --db <file>           SQLite3 database file to import into (default: './MSFS_SDK_Doc_Import.sqlite3').
                        File must exist, table(s) will be created if missing.
  --drop                Delete (drop) existing table(s) (if any) before import.
                        This only drops table(s) of the item type(s) being imported (not necessarily all tables).

Import:
  -e [<url_path> ...], --events [<url_path> ...]
                        Import Key Events (enabled by default if no other import or export type is specified).
                        The optional <url_path> argument(s) will import events only from given system page(s),
                        specified as the last (file name) part of SDK docs URL (excluding the '.htm' suffix,
                        eg: 'Aircraft_Engine_Events').
  -v [<url_path> ...], --simvars [<url_path> ...]
                        Import Simulator Variables (enabled by default if no other import or export type is specified).
                        The optional <url_path> argument(s) will import variables only from given system page(s),
                        specified as the last one or two parts of SDK docs URL (excluding the '.htm' suffix, eg:
                        'Aircraft_SimVars/Aircraft_Fuel_Variables' or 'Camera_Variables').
  -u, --units           Import Simulator Variable Units (they are not imported by default).
  -k, --keyids          Import 'KEY_*' macro names and values from gauages.h (they are not imported by default).
                        Requires a valid MSFS SDK path (see below).
  --beta                Import from 'flighting' (beta/preview) version of online SDK Docs.
  --sdk_path <path>     MSFS SDK path for importing KEY_* macros with --keyids option. Default: %MSFS_SDK% (env. variable)

Export (using these option(s) prevents any default imports from running):

  --ev_report           Run a report comparing documented Event IDs vs. KEY_* macros.
  --export {events,simvars,units,keyids,meta} [ ...]
                        Exports contents of specified table(s) in tab-delimited text format to stdout
                        (use redirect to capture to file).

Meta:
  -h, --help            show this help message and exit
  -V, --version         show program's version number and exit
```


### Example Data

#### Event IDs

| System | Category | Name | Params | Description | Multiplayer | Deprecated |
| :---   | :---     | :--- | :---   | :---        | :--         | :---:      |
| Aircraft Autopilot/Flight Assistance | Flight Assistance    | HEADING_BUG_SELECT | | Selects the heading bug for use with +/- | | 0 |
| Aircraft Autopilot/Flight Assistance | Flight Assistance     | HEADING_BUG_SET	   | [0]: Value in degrees<br/>[1]: Index | Set the heading hold reference bug in degrees. The event takes integer values only, from 0º to 360º. | | 0 |
| Aircraft Flight Control | Ailerons | AILERONS_RIGHT | | Increments ailerons right | Shared Cockpit (Pilot only).| 0 |
| Aircraft Instrumentation | Aircraft Instruments | GYRO_DRIFT_SET_EX1 | | | | 0 |
| Aircraft Instrumentation | Aircraft Instruments | HEADING_GYRO_SET | | Sets heading indicator to 0 drift error. | | 0 |
| Aircraft Miscellaneous | Helicopter Specific Systems | HELI_BEEP_DECREASE | | | | 1 |


#### Simulator Variables

| System | Category | Name | Description | Units  | Settable  | Multiplayer | Indexed | Deprecated |
| :---   | :---     | :--- | :---        | :---   | :---:     | :--         | :---:   | :---:      |
| Aircraft Control | Elevator | ELEVATOR DEFLECTION | Angle deflection. | Radians | 0 | | 0 | 0 |
| Aircraft Electrics | Batteries | ELECTRICAL MASTER BATTERY | The battery switch position, true if the switch is ON. Use a battery index when referencing. | Bool | 1 | | 0 | 0 |
| Aircraft Electrics | General / Buses | ELECTRICAL OLD CHARGING AMPS | Deprecated, do not use! Use ELECTRICAL BATTERY LOAD. | Amps | 0 | | 0 | 1 |
| Aircraft Electrics | General / Buses | ELECTRICAL TOTAL LOAD AMPS | Total load amps | Amperes | 1 | | 0 | 0 |
| Aircraft Engine | Aircraft Engine | ENG ANTI ICE | Anti-ice switch for the indexed engine (see note), true if enabled false otherwise. | Bool | 0 | | 1 | 0 |
| Aircraft Engine | Aircraft Engine | ENG COMBUSTION | True if the indexed engine (see note) is running, false otherwise. | Bool | 0 | | 1 | 0 |

#### Units

| Measure | Name | ShortName | Aliases | Description |
| :---   | :--- | :---        | :---   | :---        |
| Area | square meters | m2 | square meter,square meters,sq m,m2, | A square meter is an SI unit of area, equal to the area of a square with sides of one meter. It is equal to 10.7639ft². |
| Area | square kilometers | km2 | square kilometer,square kilometers,sq km,km2, | A square kilometer is an SI unit of area, equal to the area of a square with sides of one kilometer. It is equal to 0.386102 mi². |
| Volume | cubic inches | in3 | cubic inch,cubic inches,cu in,in3, | A cubic inch is an imperial unit of area, equal to the area of a cube with sides of one inch. It is equal to 16.3871cm³. |
| Volume | cubic feet | ft3 | cubic foot,cubic feet,cu ft,ft3, | A cubic foot is an imperial unit of area, equal to the area of a cube with sides of one foot. It is equal to 28316.917cm³ or 1728.01in³. |
| Volume | cubic yards | yd3 | cubic yard,cubic yards,cu yd,yd3, | A cubic yard is an imperial unit of area, equal to the area of a cube with sides of one yard. It is equal to 0.764555m³ or 27ft³. |


### Copyright and Disclaimer

MSFS-DocImport Project<br/>
Code and documentation: Copyright Maxim Paperno, all rights reserved.

This program and associated files may be used under the terms of the GNU
General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

A copy of the GNU General Public License is included in this repository
and is also available at <http://www.gnu.org/licenses/>.

**NOTE**: For all data published here which was originally
obtained by downloading publicly-available MSFS SDK Documentation pages,
all rights, copyrights, trademarks, and errata remain solely with the original
publisher (Microsoft).
