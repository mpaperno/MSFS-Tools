# Max Paperno's MSFS Tools

## A collection of utilities, code, and examples for Microsoft Flight Simulator.

### MSFS-DocImport
Utility tool for "scraping" MSFS SDK Documentation Event IDs and Simulator Variables from HTML pages into a structured database.

* Imports all event and sim var. defintions, sorted by base "system" (reference page) and sub-sorted by category/component.
* Imports all SimVar Unit types, sorted by type of meausre (length/angle/etc) and grouped name aliases.
* Imports the `KEY_*` macro names from MSFS SDK `gauges.h` header file along with the corresponding IDs.
  This is mostly useful for comparing to the documented events list.
* Written in Python for simple modification/customization. Can also be used as a module (from other code) providing importable functions.

The folder includes imported data ready for download, both the current release version and next beta/preview "flighting" version 
(if different from current release).

### SimConnect-Request-Tracker
C++ utility class for tracking `SimConnect` function invocations (requests) in order to provide stateful references in case of
`SIMCONNECT_RECV_ID_EXCEPTION` messages.

`SimConnectRequestTracker` provides methods for recording and retrieving data associated with SimConnect function calls.
When SimConnect sends an exception message (`SIMCONNECT_RECV_ID_EXCEPTION`), it only provides a "send ID" with
which to identify what caused the exception in the first place. Since requests are asynchronous, there needs to
be some way to record what the original function call was in order to find out what the exception is referring to.
This class provides methods to achieve this, as well as a few general utility functions for exception message handling
(such as returning the exception enum name as a string).
