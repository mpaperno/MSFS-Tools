# Max Paperno's MSFS Tools

## A collection of utilities/code/examples for Microsoft Flight Simulator.


### Index

* [MSFS-DocImport](MSFS-DocImport/) -
  Utility tool for "scraping" MSFS SDK Documentation Event IDs, Simulator Variables,
  and Units from HTML pages into a structured database. Multiple import, export, and reporting options.
  * This folder also includes imported data ready for download, both the current release version and next beta/preview
    "flighting" version (if different from current release).

* [SimConnect-Request-Tracker](SimConnect-Request-Tracker/) -
  C++ utility class for tracking and reporting `SimConnect` function invocations (requests) in order to provide stateful
  references in case of `SIMCONNECT_RECV_ID_EXCEPTION` messages (that is, being able to see the actual function call and
  parameters which caused the exception).
  * C# version to be released, but a working example implementation is available.


### Other Projects

* [WASimCommander](https://github.com/mpaperno/WASimCommander) -
  MSFS2020 WASM Module, Client, and developer API for remote access to the Microsoft Flight Simulator 2020 "Gauge API" functions.
* [MSFS Touch Portal Plugin](https://github.com/mpaperno/MSFSTouchPortalPlugin) -
  A plugin which provides a two-way interface between Touch Portal (macro launcher) clients and Flight Simulators which use SimConnect,
  such as MSFS 2020 and FS-X.


### Copyright and Disclaimer
Contents Copyright Maxim Paperno, all rights reserved.

Components within this project are distributed under terms of their own licenses,
as found in their respective folders/code. Primarily the GNU GPL v3 (or later) is employed.

This project is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

This project may also use 3rd-party Open Source software under the terms
of their respective licenses, and/or distribute publicly-available data originating
from other sources. The copyright notice above does not apply to any 3rd-party
components or data.
